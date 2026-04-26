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
        await db.commit()
    logger.info(f"DB inicializada: {DB_PATH}")


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