"""
baja_monitor.py — Monitor automático de solicitudes de baja.

Diseño:
- NO usa polling ni timers. Se ejecuta como efecto del sync de Gmail.
- Cuando el usuario sincroniza su bandeja, este módulo corre en paralelo
  y detecta si llegaron correos de dominios con baja activa.
- Si detecta un correo nuevo (posterior a la solicitud, no visto antes),
  lo registra como violación y actualiza el estado a REINCIDENTE.
- El texto de cada solicitud escala de tono según el número de intento.
"""
from __future__ import annotations

import asyncio
import logging
from datetime import datetime, timedelta, timezone
from typing import Optional

import httpx

logger = logging.getLogger(__name__)

GMAIL_API_BASE = "https://gmail.googleapis.com/gmail/v1/users/me"


# ── Utilidades de fechas ───────────────────────────────────────────────────────

def add_business_days(start: datetime, days: int) -> datetime:
    """Suma N días hábiles (lunes a viernes) a una fecha."""
    current = start
    added = 0
    while added < days:
        current += timedelta(days=1)
        if current.weekday() < 5:
            added += 1
    return current


def compute_fecha_limite(fecha_solicitud: datetime, numero_solicitud: int) -> str:
    """15 días hábiles para la primera solicitud, 5 para las siguientes."""
    dias = 15 if numero_solicitud == 1 else 5
    limite = add_business_days(fecha_solicitud, dias)
    return limite.isoformat()


# ── Monitor principal ──────────────────────────────────────────────────────────

async def scan_all_active_bajas(access_token: str) -> list[dict]:
    """
    Punto de entrada del monitor. Carga todas las bajas activas desde la DB
    y verifica si llegaron correos nuevos de esos dominios.

    Retorna lista de dicts BajaViolationFound para mostrar en la UI.
    """
    # Import aquí para evitar circular imports al inicio del módulo
    from db import get_active_bajas_for_monitor

    active_bajas = await get_active_bajas_for_monitor()
    if not active_bajas:
        return []

    logger.info("[baja-monitor] Verificando %d baja(s) activa(s)", len(active_bajas))

    timeout = httpx.Timeout(20.0, connect=8.0)
    async with httpx.AsyncClient(timeout=timeout) as client:
        tasks = [_check_baja(client, access_token, baja) for baja in active_bajas]
        results = await asyncio.gather(*tasks, return_exceptions=True)

    found: list[dict] = []
    for i, result in enumerate(results):
        if isinstance(result, Exception):
            logger.warning(
                "[baja-monitor] Error verificando baja %s: %s",
                active_bajas[i].get("id"), result,
            )
        elif isinstance(result, list):
            found.extend(result)

    if found:
        logger.info("[baja-monitor] %d violación(es) detectada(s)", len(found))

    return found


async def _check_baja(
    client: httpx.AsyncClient,
    access_token: str,
    baja: dict,
) -> list[dict]:
    """Verifica un dominio específico en busca de correos post-baja."""
    from db import get_violation_message_ids, save_baja_violation, update_baja_estado

    baja_id = baja["id"]
    dominio = baja["dominio"]
    empresa = baja["empresa"]
    numero = baja["numero_solicitud"]
    fecha_solicitud = baja["fecha_solicitud"]

    # Convertir fecha al formato que acepta Gmail en el parámetro q=
    try:
        dt = datetime.fromisoformat(fecha_solicitud.replace("Z", "+00:00"))
        after_str = dt.strftime("%Y/%m/%d")
    except Exception as exc:
        logger.warning("[baja-monitor] Fecha inválida en baja %s: %s", baja_id, exc)
        return []

    known_ids = await get_violation_message_ids(baja_id)

    try:
        messages = await _fetch_domain_messages(
            client, access_token, dominio, after_str, known_ids
        )
    except Exception as exc:
        logger.warning("[baja-monitor] Error Gmail para dominio %s: %s", dominio, exc)
        return []

    if not messages:
        return []

    violations: list[dict] = []

    for msg in messages:
        message_id = msg.get("id", "")
        if not message_id or message_id in known_ids:
            continue

        # Extraer metadatos del mensaje
        payload = msg.get("payload") or {}
        headers_raw = payload.get("headers") or []
        hmap = {
            h["name"].lower(): h["value"]
            for h in headers_raw
            if isinstance(h, dict) and "name" in h and "value" in h
        }

        subject = hmap.get("subject") or msg.get("snippet", "")[:80] or "(sin asunto)"
        from_address = hmap.get("from", "")
        snippet = (msg.get("snippet") or "")[:200]

        # Convertir internalDate (ms epoch) a ISO
        internal_date_ms = msg.get("internalDate")
        try:
            received_at = datetime.fromtimestamp(
                int(internal_date_ms) / 1000, tz=timezone.utc
            ).isoformat()
        except Exception:
            received_at = datetime.now(timezone.utc).isoformat()

        # Persistir violación
        saved = await save_baja_violation(
            baja_id=baja_id,
            message_id=message_id,
            received_at=received_at,
            subject=subject,
            from_address=from_address,
            snippet=snippet,
        )
        if not saved:
            continue  # ya existía (UNIQUE constraint)

        violations.append({
            "baja_id": baja_id,
            "dominio": dominio,
            "empresa": empresa,
            "numero_solicitud": numero,
            "message_id": message_id,
            "received_at": received_at,
            "subject": subject,
            "from_address": from_address,
            "snippet": snippet,
        })

    if violations:
        await update_baja_estado(baja_id, "REINCIDENTE")
        logger.info(
            "[baja-monitor] REINCIDENCIA | empresa=%s | dominio=%s | correos_nuevos=%d",
            empresa, dominio, len(violations),
        )

    return violations


async def _fetch_domain_messages(
    client: httpx.AsyncClient,
    access_token: str,
    domain: str,
    after_date: str,
    known_ids: set[str],
) -> list[dict]:
    """
    Busca en Gmail correos de un dominio específico después de una fecha.
    Usa el parámetro q= de la Gmail API para acotar la búsqueda.
    Solo descarga metadatos (no el cuerpo completo) para ser eficiente.
    """
    headers = {"Authorization": f"Bearer {access_token}"}
    query = f"from:@{domain} after:{after_date}"

    # Paso 1: obtener lista de IDs
    resp = await client.get(
        f"{GMAIL_API_BASE}/messages",
        params={"q": query, "maxResults": 50, "includeSpamTrash": "true"},
        headers=headers,
    )
    resp.raise_for_status()
    refs = resp.json().get("messages") or []

    # Filtrar los que ya conocemos
    new_refs = [r for r in refs if r.get("id") and r["id"] not in known_ids]
    if not new_refs:
        return []

    # Paso 2: descargar solo metadatos de los mensajes nuevos
    semaphore = asyncio.Semaphore(6)

    async def fetch_one(ref: dict) -> dict | None:
        async with semaphore:
            r = await client.get(
                f"{GMAIL_API_BASE}/messages/{ref['id']}",
                params={
                    "format": "metadata",
                    "metadataHeaders": ["From", "Subject", "Date"],
                },
                headers=headers,
            )
            r.raise_for_status()
            return r.json()

    results = await asyncio.gather(
        *[fetch_one(ref) for ref in new_refs],
        return_exceptions=True,
    )
    return [r for r in results if isinstance(r, dict)]


# ── Constructor de texto de solicitud ─────────────────────────────────────────

def build_baja_subject(numero: int, empresa: str) -> str:
    if numero == 1:
        return f"Solicitud de supresión de datos personales — {empresa}"
    if numero == 2:
        return f"Segunda solicitud de supresión de datos — {empresa} — Incumplimiento previo"
    return f"Notificación previa a denuncia — {empresa} — Reincidencia en tratamiento no autorizado"


def build_baja_texto(
    numero: int,
    empresa: str,
    holder_email: str,
    historial_fechas: list[str],
    violations: list[dict],
) -> tuple[str, str]:
    """
    Construye el texto plano y HTML de la solicitud según el número de intento.
    Retorna (texto_plano, texto_html).
    """
    text = _build_text(numero, empresa, holder_email, historial_fechas, violations)
    html = _build_html(numero, empresa, holder_email, historial_fechas, violations)
    return text, html


# ── Texto plano por tono ───────────────────────────────────────────────────────

def _build_text(
    numero: int,
    empresa: str,
    holder_email: str,
    historial_fechas: list[str],
    violations: list[dict],
) -> str:
    if numero == 1:
        return _text_n1(empresa, holder_email)
    if numero == 2:
        return _text_n2(empresa, holder_email, historial_fechas, violations)
    return _text_n3plus(numero, empresa, holder_email, historial_fechas, violations)


def _text_n1(empresa: str, holder_email: str) -> str:
    return f"""Estimado(a) Equipo de Protección de Datos de {empresa},

Por medio del presente correo, y al amparo de lo dispuesto en el artículo 14 de la Ley N° 21.719 sobre Protección de Datos Personales, solicito formalmente:

1. La supresión definitiva de todos mis datos personales que obren en sus sistemas o bases de datos, incluyendo nombre, correo electrónico, dirección postal y cualquier otro dato que hayan recopilado sobre mi persona.

2. El cese inmediato de toda comunicación comercial, de marketing o publicitaria dirigida a mi correo electrónico.

3. Confirmación escrita del cumplimiento de esta solicitud, indicando:
   - Fecha efectiva de eliminación de mis datos.
   - Sistemas o bases de datos impactados.
   - Terceros a quienes hayan cedido mis datos y que deban ser notificados.

El plazo legal para atender esta solicitud es de 15 días hábiles contados desde la recepción del presente correo, conforme al artículo 14 de la Ley N° 21.719.

Atentamente,
{holder_email}

---
Base legal: Ley N° 21.719 sobre Protección de Datos Personales, Art. 14 (Derecho de supresión).
"""


def _text_n2(
    empresa: str,
    holder_email: str,
    historial_fechas: list[str],
    violations: list[dict],
) -> str:
    fecha_anterior = historial_fechas[0] if historial_fechas else "[fecha de solicitud anterior]"
    evidencia_ref = ""
    if violations:
        v = violations[0]
        fecha_v = (v.get("received_at") or "")[:10]
        asunto_v = v.get("subject") or "(sin asunto)"
        evidencia_ref = (
            f'\n\nEvidencia de incumplimiento: con fecha {fecha_v} recibí un correo de '
            f'su parte con asunto "{asunto_v}", lo que demuestra que mis datos continúan '
            f'siendo utilizados en contra de mi voluntad expresada.'
        )

    return f"""Estimado(a) Equipo de Protección de Datos de {empresa},

Con fecha {fecha_anterior} remití a su empresa una solicitud formal de supresión de datos personales al amparo del artículo 14 de la Ley N° 21.719, la cual no fue debidamente atendida.{evidencia_ref}

Esta conducta constituye una infracción a los artículos 13 y 14 de la Ley N° 21.719, pues evidencia que mis datos personales continúan siendo tratados sin mi consentimiento y en contravención directa a lo solicitado.

En consecuencia, le notifico que:

1. Reitero formalmente mi solicitud de supresión inmediata e íntegra de todos mis datos personales en sus sistemas.

2. En caso de no obtener respuesta fundada dentro de los próximos 5 días hábiles, procederé a interponer un reclamo formal ante la autoridad competente, invocando el artículo 39 de la Ley N° 21.719, que contempla sanciones de hasta 5.000 UTM para infracciones graves.

Esta comunicación queda registrada como segunda notificación formal y formará parte del historial de incumplimiento que se adjuntará a la eventual denuncia.

Atentamente,
{holder_email}

---
Base legal: Ley N° 21.719, Art. 13 (Derecho de oposición), Art. 14 (Derecho de supresión), Art. 39 (Infracciones y sanciones).
"""


def _text_n3plus(
    numero: int,
    empresa: str,
    holder_email: str,
    historial_fechas: list[str],
    violations: list[dict],
) -> str:
    now = datetime.now(timezone.utc)
    fecha_denuncia = add_business_days(now, 2).strftime("%d/%m/%Y")
    n_anteriores = numero - 1
    fechas_str = (
        ", ".join(historial_fechas)
        if historial_fechas
        else "[ver historial de solicitudes adjunto]"
    )
    evidencia_str = ""
    if violations:
        lineas = [
            f'  - {(v.get("received_at") or "")[:10]}: "{v.get("subject") or "(sin asunto)"}"'
            for v in violations[:5]
        ]
        evidencia_str = "\nCorreos recibidos en contravención a mis solicitudes:\n" + "\n".join(lineas) + "\n"

    return f"""Estimado(a) Equipo de Protección de Datos de {empresa},

En {n_anteriores} oportunidad(es) anteriores he ejercido formalmente mis derechos de supresión y oposición conforme a la Ley N° 21.719, enviando solicitudes con fecha(s): {fechas_str}.

En todas esas oportunidades, su empresa ignoró mis requerimientos legítimos y continuó enviando comunicaciones comerciales no autorizadas.
{evidencia_str}
Le notifico formalmente que el día {fecha_denuncia} presentaré un reclamo ante el Consejo para la Transparencia — autoridad de control transitoria conforme al artículo 40 de la Ley N° 21.719 —, adjuntando el historial completo de solicitudes ignoradas y los correos recibidos con posterioridad a cada una de ellas.

Dicho reclamo invocará los artículos 13, 14 y 39 de la Ley N° 21.719, que contempla sanciones de hasta 5.000 UTM por infracciones graves, y solicitará la apertura de un procedimiento sancionatorio en contra de su empresa.

Esta comunicación constituye notificación previa formal antes de la interposición de la denuncia y formará parte íntegra del expediente presentado ante la autoridad.

{holder_email}

---
Base legal: Ley N° 21.719, Art. 13, Art. 14, Art. 39 (hasta 5.000 UTM), Art. 40 (autoridad de control).
"""


# ── HTML por tono ──────────────────────────────────────────────────────────────

_TONE_COLORS = {1: "#10b981", 2: "#f59e0b", 3: "#ef4444"}
_TONE_LABELS = {
    1: "Solicitud N°1 — Formal",
    2: "Solicitud N°2 — Advertencia de denuncia",
    3: "Solicitud N°3+ — Denuncia inminente",
}


def _build_html(
    numero: int,
    empresa: str,
    holder_email: str,
    historial_fechas: list[str],
    violations: list[dict],
) -> str:
    text = _build_text(numero, empresa, holder_email, historial_fechas, violations)
    color = _TONE_COLORS.get(min(numero, 3), "#ef4444")
    label = _TONE_LABELS.get(min(numero, 3), f"Solicitud N°{numero}")

    escaped = text.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")
    paragraphs = escaped.split("\n\n")
    body_html = "".join(
        f'<p style="margin:0 0 14px 0;line-height:1.6;">{p.replace(chr(10), "<br>")}</p>'
        for p in paragraphs
        if p.strip()
    )

    violations_html = ""
    if violations and numero >= 2:
        rows = "".join(
            f'<tr>'
            f'<td style="padding:6px 12px 6px 0;color:#6b7280;font-size:12px;">{(v.get("received_at") or "")[:10]}</td>'
            f'<td style="padding:6px 0;font-size:12px;color:#111827;">{v.get("subject") or "(sin asunto)"}</td>'
            f'</tr>'
            for v in violations[:5]
        )
        violations_html = f"""
        <div style="margin-bottom:20px;background:#fef2f2;border:1px solid #fecaca;border-radius:8px;padding:14px 18px;">
          <div style="font-size:11px;font-weight:600;text-transform:uppercase;letter-spacing:.08em;color:#dc2626;margin-bottom:8px;">
            Correos recibidos tras la solicitud de baja (evidencia de reincidencia)
          </div>
          <table style="border-collapse:collapse;width:100%;">{rows}</table>
        </div>"""

    return f"""<!DOCTYPE html>
<html lang="es">
<head><meta charset="UTF-8">
<title>Solicitud de baja — {empresa}</title></head>
<body style="margin:0;padding:0;background:#f3f4f6;font-family:-apple-system,BlinkMacSystemFont,'Segoe UI',sans-serif;">
<div style="max-width:640px;margin:32px auto;background:#fff;border-radius:12px;overflow:hidden;box-shadow:0 4px 20px rgba(0,0,0,.08);">
  <div style="background:{color};padding:24px 32px;">
    <div style="font-size:11px;color:rgba(255,255,255,.8);letter-spacing:.1em;text-transform:uppercase;margin-bottom:6px;">{label}</div>
    <div style="font-size:20px;font-weight:700;color:#fff;">Solicitud de supresión de datos personales</div>
    <div style="font-size:13px;color:rgba(255,255,255,.85);margin-top:4px;">{empresa}</div>
  </div>
  <div style="padding:32px;font-size:14px;color:#374151;">
    {violations_html}
    {body_html}
  </div>
</div>
</body></html>"""
