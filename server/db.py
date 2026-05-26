"""
db.py — Capa de persistencia con SQLite (aiosqlite para async).

Decisiones de diseño:
- SQLite es suficiente para esta herramienta (no es multi-usuario concurrente)
- El resultado OSINT completo se guarda como JSON en una columna TEXT
  → No normalizamos cada fuente en tablas separadas — demasiado acoplamiento
  → Si el esquema de un módulo cambia, solo cambia el JSON, no la DB
- Migraciones: CREATE TABLE IF NOT EXISTS — no necesitamos Alembic aún
- risk_score calculado al guardar para poder ordenar sin deserializar JSON

Esquema:
  searches(id, nombre, rut, fecha, resultado, risk_score, risk_level,
           hallazgos, fuentes)
"""
from __future__ import annotations

import json
import logging
import os
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional

import aiosqlite

from models.schemas import OSINTResponse

logger = logging.getLogger(__name__)

# DB_PATH can be overridden by the launcher (standalone app stores DB in ~/.emailanalyzer/)
_db_path_env = os.environ.get("DB_PATH", "")
DB_PATH = Path(_db_path_env) if _db_path_env else Path(__file__).parent / "osint_chile.db"


# ── Inicialización ────────────────────────────────────────────────────────────

async def init_db() -> None:
    """Crea las tablas si no existen. Llamar en el startup de FastAPI."""
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute("""
            CREATE TABLE IF NOT EXISTS searches (
                id          TEXT PRIMARY KEY,
                nombre      TEXT NOT NULL,
                rut         TEXT,
                fecha       TEXT NOT NULL,
                resultado   TEXT NOT NULL,
                risk_score  REAL NOT NULL DEFAULT 0.0,
                risk_level  TEXT NOT NULL DEFAULT 'Sin datos',
                hallazgos   INTEGER NOT NULL DEFAULT 0,
                fuentes     INTEGER NOT NULL DEFAULT 0
            )
        """)
        await db.execute("CREATE INDEX IF NOT EXISTS idx_nombre ON searches(nombre)")
        await db.execute("CREATE INDEX IF NOT EXISTS idx_fecha  ON searches(fecha DESC)")
        await _init_baja_tables(db)
        await db.commit()
    logger.info(f"DB inicializada: {DB_PATH}")


async def _init_baja_tables(db: aiosqlite.Connection) -> None:
    """Crea tablas de solicitudes de baja y violaciones post-baja."""
    await db.execute("""
        CREATE TABLE IF NOT EXISTS baja_requests (
            id                TEXT PRIMARY KEY,
            dominio           TEXT NOT NULL,
            empresa           TEXT NOT NULL,
            estado            TEXT NOT NULL DEFAULT 'SOLICITADA',
            numero_solicitud  INTEGER NOT NULL DEFAULT 1,
            fecha_solicitud   TEXT NOT NULL,
            fecha_limite      TEXT NOT NULL,
            fecha_acuse       TEXT,
            destinatario      TEXT NOT NULL,
            holder_email      TEXT NOT NULL,
            evidencia_json    TEXT NOT NULL,
            baja_anterior_id  TEXT
        )
    """)
    await db.execute("CREATE INDEX IF NOT EXISTS idx_baja_dominio ON baja_requests(dominio)")
    await db.execute("CREATE INDEX IF NOT EXISTS idx_baja_estado  ON baja_requests(estado)")
    await db.execute("""
        CREATE TABLE IF NOT EXISTS baja_violations (
            id           TEXT PRIMARY KEY,
            baja_id      TEXT NOT NULL REFERENCES baja_requests(id),
            message_id   TEXT NOT NULL UNIQUE,
            received_at  TEXT NOT NULL,
            subject      TEXT,
            from_address TEXT,
            snippet      TEXT
        )
    """)
    await db.execute(
        "CREATE INDEX IF NOT EXISTS idx_violation_baja ON baja_violations(baja_id)"
    )


# ── Guardar búsqueda ─────────────────────────────────────────────────────────

async def save_search(response: OSINTResponse) -> str:
    """Persiste una búsqueda OSINT completa. Devuelve el ID generado."""
    search_id      = str(uuid.uuid4())
    fecha          = datetime.now(timezone.utc).isoformat()
    risk_score, risk_level = _calcular_riesgo(response)
    hallazgos      = response.resumen.total_hallazgos
    fuentes        = len(response.resumen.fuentes_con_datos)
    resultado_json = response.model_dump_json()

    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute(
            """INSERT INTO searches
               (id, nombre, rut, fecha, resultado, risk_score, risk_level, hallazgos, fuentes)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)""",
            (search_id, response.query, response.rut, fecha,
             resultado_json, risk_score, risk_level, hallazgos, fuentes),
        )
        await db.commit()

    logger.info(f"Búsqueda guardada: id={search_id} nombre='{response.query}'")
    return search_id


# ── Listar búsquedas ─────────────────────────────────────────────────────────

async def list_searches(limit: int = 50) -> list[dict]:
    """
    Historial de búsquedas — solo metadatos (sin el JSON completo).
    Formato compatible con mockSearches del frontend.
    """
    async with aiosqlite.connect(DB_PATH) as db:
        db.row_factory = aiosqlite.Row
        cursor = await db.execute(
            """SELECT id, nombre, rut, fecha, risk_level, hallazgos, fuentes
               FROM searches ORDER BY fecha DESC LIMIT ?""",
            (limit,),
        )
        rows = await cursor.fetchall()

    return [
        {
            "id":        row["id"],
            "nombre":    row["nombre"],
            "rut":       row["rut"],
            "fecha":     _format_fecha(row["fecha"]),
            "riesgo":    row["risk_level"],
            "hallazgos": row["hallazgos"],
            "fuentes":   row["fuentes"],
        }
        for row in rows
    ]


# ── Obtener por ID ────────────────────────────────────────────────────────────

async def get_search(search_id: str) -> Optional[dict]:
    """Devuelve resultado completo de una búsqueda."""
    async with aiosqlite.connect(DB_PATH) as db:
        db.row_factory = aiosqlite.Row
        cursor = await db.execute(
            "SELECT * FROM searches WHERE id = ?", (search_id,)
        )
        row = await cursor.fetchone()

    if not row:
        return None

    return {
        "id":         row["id"],
        "nombre":     row["nombre"],
        "rut":        row["rut"],
        "fecha":      _format_fecha(row["fecha"]),
        "riesgo":     row["risk_level"],
        "risk_score": row["risk_score"],
        "hallazgos":  row["hallazgos"],
        "fuentes":    row["fuentes"],
        "resultado":  json.loads(row["resultado"]),
    }


async def delete_search(search_id: str) -> bool:
    """Elimina una búsqueda. Devuelve True si existía."""
    async with aiosqlite.connect(DB_PATH) as db:
        cursor = await db.execute(
            "DELETE FROM searches WHERE id = ?", (search_id,)
        )
        await db.commit()
        return cursor.rowcount > 0


# ── Risk scoring ─────────────────────────────────────────────────────────────

def _calcular_riesgo(response: OSINTResponse) -> tuple[float, str]:
    """
    Score 0.0–1.0.

    Pesos:
      Antecedentes judiciales (PJUD) → 0.35
      Leaks (HIBP)                   → 0.30
      Actividad empresarial          → 0.15
      Nº fuentes con datos           → 0.10
      Nº hallazgos totales           → 0.10
    """
    r = response.resumen
    f = response.fuentes
    score = 0.0

    if r.tiene_antecedentes_judiciales:
        score += 0.35 * min(1.0, len(f.pjud) / 3)

    if r.total_leaks > 0:
        score += 0.30 * min(1.0, r.total_leaks / 5)

    if r.tiene_actividad_empresarial:
        n = len(f.empresas) + (1 if f.sii else 0)
        score += 0.15 * min(1.0, n / 5)

    if r.fuentes_con_datos:
        score += 0.10 * min(1.0, len(r.fuentes_con_datos) / 6)

    if r.total_hallazgos > 0:
        score += 0.10 * min(1.0, r.total_hallazgos / 20)

    score = round(min(1.0, score), 3)

    if   score >= 0.70: level = "Alto"
    elif score >= 0.40: level = "Medio"
    elif score  > 0.0:  level = "Bajo"
    else:               level = "Sin datos"

    return score, level


def _format_fecha(iso: str) -> str:
    try:
        dt = datetime.fromisoformat(iso.replace("Z", "+00:00"))
        return dt.strftime("%d/%m/%Y")
    except Exception:
        return iso[:10]


# ── Baja requests CRUD ────────────────────────────────────────────────────────

async def delete_demo_bajas() -> None:
    """Elimina todos los registros de baja marcados como demo (evidencia_json con demo:true)."""
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute(
            "DELETE FROM baja_violations WHERE baja_id IN "
            "(SELECT id FROM baja_requests WHERE evidencia_json LIKE '%\"demo\": true%')"
        )
        await db.execute(
            "DELETE FROM baja_requests WHERE evidencia_json LIKE '%\"demo\": true%'"
        )
        await db.commit()


async def save_baja_request(
    *,
    dominio: str,
    empresa: str,
    numero_solicitud: int,
    fecha_limite: str,
    destinatario: str,
    holder_email: str,
    evidencia_json: str,
    baja_anterior_id: Optional[str] = None,
    fecha_solicitud: Optional[str] = None,
) -> str:
    """Crea una nueva solicitud de baja. Devuelve el ID generado."""
    baja_id = str(uuid.uuid4())
    fecha_solicitud = fecha_solicitud or datetime.now(timezone.utc).isoformat()
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute(
            """INSERT INTO baja_requests
               (id, dominio, empresa, estado, numero_solicitud, fecha_solicitud,
                fecha_limite, destinatario, holder_email, evidencia_json, baja_anterior_id)
               VALUES (?, ?, ?, 'SOLICITADA', ?, ?, ?, ?, ?, ?, ?)""",
            (
                baja_id, dominio, empresa, numero_solicitud,
                fecha_solicitud, fecha_limite, destinatario,
                holder_email, evidencia_json, baja_anterior_id,
            ),
        )
        await db.commit()
    logger.info(f"Baja guardada: id={baja_id} dominio='{dominio}' intento={numero_solicitud}")
    return baja_id


async def list_baja_requests() -> list[dict]:
    """Lista todas las solicitudes de baja con estado calculado dinámicamente."""
    now = datetime.now(timezone.utc).isoformat()
    async with aiosqlite.connect(DB_PATH) as db:
        db.row_factory = aiosqlite.Row
        cursor = await db.execute(
            "SELECT * FROM baja_requests ORDER BY fecha_solicitud DESC"
        )
        rows = await cursor.fetchall()
    return [_baja_row_to_dict(dict(row), now) for row in rows]


async def list_all_bajas_with_violations() -> list[dict]:
    """
    Devuelve todas las bajas con sus violaciones embebidas, en 2 queries.
    Agrupa por dominio para armar el historial de escalación por empresa.
    """
    now = datetime.now(timezone.utc).isoformat()
    async with aiosqlite.connect(DB_PATH) as db:
        db.row_factory = aiosqlite.Row

        cursor = await db.execute(
            "SELECT * FROM baja_requests ORDER BY dominio ASC, numero_solicitud ASC"
        )
        baja_rows = await cursor.fetchall()

        cursor2 = await db.execute(
            "SELECT * FROM baja_violations ORDER BY received_at ASC"
        )
        violation_rows = await cursor2.fetchall()

    # Indexar violaciones por baja_id
    violations_by_baja: dict[str, list[dict]] = {}
    for vrow in violation_rows:
        v = dict(vrow)
        violations_by_baja.setdefault(v["baja_id"], []).append(v)

    # Construir bajas con violaciones embebidas
    bajas_by_domain: dict[str, list[dict]] = {}
    for brow in baja_rows:
        b = _baja_row_to_dict(dict(brow), now)
        b["violations"] = violations_by_baja.get(b["id"], [])
        bajas_by_domain.setdefault(b["dominio"], []).append(b)

    # Convertir a lista de grupos ordenados por fecha de última actividad desc
    groups = []
    for dominio, solicitudes in bajas_by_domain.items():
        last = solicitudes[-1]
        groups.append({
            "dominio": dominio,
            "empresa": last["empresa"],
            "estado_actual": last["estado"],
            "numero_actual": last["numero_solicitud"],
            "ultima_solicitud": last["fecha_solicitud"],
            "solicitudes": solicitudes,
            "total_violations": sum(len(s["violations"]) for s in solicitudes),
        })

    groups.sort(key=lambda g: g["ultima_solicitud"], reverse=True)
    return groups


async def get_baja_request(baja_id: str) -> Optional[dict]:
    """Devuelve una solicitud de baja con sus violaciones adjuntas."""
    now = datetime.now(timezone.utc).isoformat()
    async with aiosqlite.connect(DB_PATH) as db:
        db.row_factory = aiosqlite.Row
        cursor = await db.execute(
            "SELECT * FROM baja_requests WHERE id = ?", (baja_id,)
        )
        row = await cursor.fetchone()
        if not row:
            return None
        baja = _baja_row_to_dict(dict(row), now)
        cursor2 = await db.execute(
            "SELECT * FROM baja_violations WHERE baja_id = ? ORDER BY received_at DESC",
            (baja_id,),
        )
        violations = await cursor2.fetchall()
    baja["violations"] = [dict(v) for v in violations]
    return baja


async def update_baja_estado(
    baja_id: str,
    estado: str,
    fecha_acuse: Optional[str] = None,
) -> None:
    async with aiosqlite.connect(DB_PATH) as db:
        if fecha_acuse:
            await db.execute(
                "UPDATE baja_requests SET estado = ?, fecha_acuse = ? WHERE id = ?",
                (estado, fecha_acuse, baja_id),
            )
        else:
            await db.execute(
                "UPDATE baja_requests SET estado = ? WHERE id = ?",
                (estado, baja_id),
            )
        await db.commit()


async def get_active_bajas_for_monitor() -> list[dict]:
    """Retorna bajas en estado SOLICITADA o CUMPLIDA para que el monitor las verifique."""
    now = datetime.now(timezone.utc).isoformat()
    async with aiosqlite.connect(DB_PATH) as db:
        db.row_factory = aiosqlite.Row
        cursor = await db.execute(
            "SELECT * FROM baja_requests WHERE estado IN ('SOLICITADA', 'CUMPLIDA', 'REINCIDENTE')"
        )
        rows = await cursor.fetchall()
    return [_baja_row_to_dict(dict(row), now) for row in rows]


async def get_baja_history(baja_id: str) -> list[dict]:
    """Recorre la cadena de solicitudes previas siguiendo baja_anterior_id."""
    history: list[dict] = []
    current_id: Optional[str] = baja_id
    visited: set[str] = set()
    now = datetime.now(timezone.utc).isoformat()

    async with aiosqlite.connect(DB_PATH) as db:
        db.row_factory = aiosqlite.Row
        while current_id and current_id not in visited:
            visited.add(current_id)
            cursor = await db.execute(
                "SELECT * FROM baja_requests WHERE id = ?", (current_id,)
            )
            row = await cursor.fetchone()
            if not row:
                break
            d = _baja_row_to_dict(dict(row), now)
            history.append(d)
            current_id = d.get("baja_anterior_id")

    return history


# ── Baja violations CRUD ──────────────────────────────────────────────────────

async def save_baja_violation(
    *,
    baja_id: str,
    message_id: str,
    received_at: str,
    subject: Optional[str],
    from_address: Optional[str],
    snippet: Optional[str],
) -> str:
    """
    Registra un correo recibido post-baja. Retorna el ID creado o vacío si ya existía
    (UNIQUE constraint en message_id evita duplicados entre sincronizaciones).
    """
    violation_id = str(uuid.uuid4())
    async with aiosqlite.connect(DB_PATH) as db:
        try:
            await db.execute(
                """INSERT INTO baja_violations
                   (id, baja_id, message_id, received_at, subject, from_address, snippet)
                   VALUES (?, ?, ?, ?, ?, ?, ?)""",
                (violation_id, baja_id, message_id, received_at, subject, from_address, snippet),
            )
            await db.commit()
        except Exception:
            return ""  # ya existía
    return violation_id


async def get_violation_message_ids(baja_id: str) -> set[str]:
    """Retorna los message_id ya registrados para una baja (evita re-procesar)."""
    async with aiosqlite.connect(DB_PATH) as db:
        cursor = await db.execute(
            "SELECT message_id FROM baja_violations WHERE baja_id = ?", (baja_id,)
        )
        rows = await cursor.fetchall()
    return {row[0] for row in rows}


# ── Helpers internos ──────────────────────────────────────────────────────────

def _baja_row_to_dict(row: dict, now: str) -> dict:
    """
    Convierte una fila de baja_requests a dict.
    Calcula VENCIDA dinámicamente (no se escribe en DB) y días restantes/mora.
    """
    d = dict(row)
    # VENCIDA es un estado calculado: si venció el plazo y nadie marcó cumplida
    if d.get("estado") == "SOLICITADA" and d.get("fecha_limite", "") < now:
        d["estado"] = "VENCIDA"

    # Días restantes o en mora
    try:
        limite = datetime.fromisoformat(d["fecha_limite"].replace("Z", "+00:00"))
        now_dt = datetime.fromisoformat(now.replace("Z", "+00:00"))
        delta = (limite - now_dt).days
        if delta >= 0:
            d["dias_restantes"] = delta
            d["dias_en_mora"] = None
        else:
            d["dias_restantes"] = None
            d["dias_en_mora"] = abs(delta)
    except Exception:
        d["dias_restantes"] = None
        d["dias_en_mora"] = None

    d.setdefault("violations", [])
    return d