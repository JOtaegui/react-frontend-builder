from __future__ import annotations

import asyncio
import base64
import logging
import smtplib
import ssl
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText

import httpx

from config import SMTP_FROM, SMTP_HOST, SMTP_PASSWORD, SMTP_PORT, SMTP_USE_SSL, SMTP_USER
from models.schemas import IdentifiedSender

logger = logging.getLogger(__name__)

PERSONAL_DATA_LABELS: dict[str, str] = {
    "nombre": "Nombre",
    "direccion": "Dirección",
    "patente": "Patente",
    "rut": "RUT",
    "telefono": "Teléfono",
    "pedido": "Pedidos/Compras",
    "pago": "Pagos/Facturación",
    "cuenta": "Cuenta/Sesión",
}


GMAIL_SEND_URL = "https://gmail.googleapis.com/gmail/v1/users/me/messages/send"


def is_smtp_configured() -> bool:
    return bool(SMTP_HOST and SMTP_USER and SMTP_PASSWORD)


async def send_correo_via_gmail_api(
    *,
    access_token: str,
    from_address: str,
    destination: str,
    subject: str,
    html_body: str,
    text_body: str,
) -> None:
    """Envía un correo arbitrario via Gmail API con contenido preformateado."""
    msg = MIMEMultipart("alternative")
    msg["Subject"] = subject
    msg["From"] = from_address
    msg["To"] = destination
    msg.attach(MIMEText(text_body, "plain", "utf-8"))
    msg.attach(MIMEText(html_body, "html", "utf-8"))

    raw = base64.urlsafe_b64encode(msg.as_bytes()).decode("utf-8")

    async with httpx.AsyncClient(timeout=30.0) as client:
        response = await client.post(
            GMAIL_SEND_URL,
            json={"raw": raw},
            headers={"Authorization": "Bearer " + access_token},
        )
        response.raise_for_status()

    logger.info("Correo enviado via Gmail API a %s | asunto: %s", destination, subject)


async def send_baja_report_via_gmail_api(
    *,
    access_token: str,
    from_address: str,
    destination: str,
    sender: IdentifiedSender,
    holder_email: str,
) -> None:
    subject = "Informe de datos personales - " + sender.company_name
    html_body = _build_html_report(sender, holder_email)
    text_body = _build_text_report(sender, holder_email)

    msg = MIMEMultipart("alternative")
    msg["Subject"] = subject
    msg["From"] = from_address
    msg["To"] = destination
    msg.attach(MIMEText(text_body, "plain", "utf-8"))
    msg.attach(MIMEText(html_body, "html", "utf-8"))

    raw = base64.urlsafe_b64encode(msg.as_bytes()).decode("utf-8")

    async with httpx.AsyncClient(timeout=30.0) as client:
        response = await client.post(
            GMAIL_SEND_URL,
            json={"raw": raw},
            headers={"Authorization": "Bearer " + access_token},
        )
        response.raise_for_status()

    logger.info("Informe de baja enviado via Gmail API a %s para empresa %s", destination, sender.company_name)


async def send_baja_report(
    *,
    destination: str,
    sender: IdentifiedSender,
    holder_email: str,
) -> None:
    subject = "[Prueba] Informe de datos personales - " + sender.company_name
    html_body = _build_html_report(sender, holder_email)
    text_body = _build_text_report(sender, holder_email)

    loop = asyncio.get_event_loop()
    await loop.run_in_executor(None, _send_smtp, destination, subject, html_body, text_body)
    logger.info("Informe de baja enviado a %s para empresa %s", destination, sender.company_name)


def _send_smtp(destination: str, subject: str, html_body: str, text_body: str) -> None:
    msg = MIMEMultipart("alternative")
    msg["Subject"] = subject
    msg["From"] = SMTP_FROM or SMTP_USER
    msg["To"] = destination

    msg.attach(MIMEText(text_body, "plain", "utf-8"))
    msg.attach(MIMEText(html_body, "html", "utf-8"))

    if SMTP_USE_SSL:
        ctx = ssl.create_default_context()
        with smtplib.SMTP_SSL(SMTP_HOST, SMTP_PORT, context=ctx) as server:
            server.login(SMTP_USER, SMTP_PASSWORD)
            server.sendmail(msg["From"], destination, msg.as_string())
    else:
        with smtplib.SMTP(SMTP_HOST, SMTP_PORT) as server:
            server.ehlo()
            server.starttls()
            server.login(SMTP_USER, SMTP_PASSWORD)
            server.sendmail(msg["From"], destination, msg.as_string())


def _label(values: list[str], fallback: str = "No detectado", limit: int = 8) -> str:
    cleaned = [v.strip() for v in values if v and v.strip()]
    if not cleaned:
        return fallback
    return ", ".join(cleaned[:limit])


def _build_text_report(sender: IdentifiedSender, holder_email: str) -> str:
    ev = sender.evidence
    data_labels = [PERSONAL_DATA_LABELS.get(t, t) for t in (sender.personal_data_types or [])]
    ips = ev.header_ips or []
    chile_ips = ev.header_ip_chile_matches or []

    lines = [
        "INFORME DE DATOS PERSONALES DETECTADOS — " + sender.company_name,
        "=" * 60,
        "",
        "Este informe es una PRUEBA generada por la herramienta de análisis de privacidad.",
        "Titular analizado : " + holder_email,
        "Empresa analizada : " + sender.company_name + " (" + sender.primary_domain + ")",
        "País              : " + sender.country,
        "Tipo de empresa   : " + sender.sender_type,
        "",
        "─" * 60,
        "1) DATOS PERSONALES DETECTADOS EN SUS CORREOS",
        "─" * 60,
        "  Tipos de datos : " + _label(data_labels),
        "  Nombre(s)      : " + _label(sender.personal_names or []),
        "  Dirección(es)  : " + _label(sender.personal_addresses or []),
        "  RUT(s)         : " + _label(sender.personal_ruts or []),
        "  Teléfono(s)    : " + _label(sender.personal_phones or []),
        "  Patente(s)     : " + _label(sender.personal_plates or []),
        "",
        "─" * 60,
        "2) EVIDENCIA DEL TRATAMIENTO DE CORREOS",
        "─" * 60,
        "  Correos detectados de esta empresa : " + str(ev.message_count),
        "  Clasificados como spam             : " + str(ev.spam_count),
        "  Clasificados como papelera         : " + str(ev.trash_count),
        "  Primer correo detectado            : " + (ev.first_seen or "Desconocido"),
        "  Último correo detectado            : " + (ev.last_seen or "Desconocido"),
        "",
        "  Remitentes (From)     : " + _label(ev.from_addresses or []),
        "  Reply-To              : " + _label(ev.reply_to_addresses or []),
        "  Return-Path           : " + _label(ev.return_path_addresses or []),
        "",
        "  IPs en cabeceras (" + str(len(ips)) + ") : " + _label(ips, "No detectadas", 12),
        "  IPs asociadas a Chile (" + str(len(chile_ips)) + ") : " + _label(chile_ips, "Ninguna", 12),
        "",
        "  Asuntos de muestra : " + _label(ev.sample_subjects or [], "Sin muestra", 6),
        "  Adjuntos vistos    : " + _label(ev.attachment_filenames or [], "Ninguno", 6),
        "",
        "─" * 60,
        "3) RIESGO DETECTADO",
        "─" * 60,
        "  Nivel : " + sender.risk.level.upper(),
    ]

    if sender.risk.reasons:
        lines.append("  Razones:")
        for reason in sender.risk.reasons:
            lines.append("    · " + reason)

    lines += [
        "",
        "─" * 60,
        "4) SOLICITUD DE DERECHOS (BORRADOR)",
        "─" * 60,
        "",
        "Estimado equipo de privacidad,",
        "",
        "Solicito el ejercicio de mis derechos sobre datos personales:",
        "· Acceso, oposición y supresión/eliminación.",
        "· Confirmar si mantienen mis datos y detallar su origen, finalidad y base legal.",
        "· Eliminar mis datos de sus sistemas y detener futuros envíos.",
        "· Entregar evidencia de cumplimiento.",
        "",
        "Saludos,",
        holder_email,
        "",
        "─" * 60,
        "NOTA: Este es un informe de prueba generado automáticamente.",
        "No ha sido enviado a la empresa. Revise y envíe manualmente si lo considera pertinente.",
    ]

    return "\n".join(lines)


def _badge(text: str, color: str = "#10b981") -> str:
    bg = color + "22"
    border = color + "44"
    return (
        '<span style="display:inline-block;background:' + bg + ';color:' + color + ';'
        'border:1px solid ' + border + ';border-radius:6px;padding:2px 8px;'
        'font-size:12px;margin:2px;">' + text + '</span>'
    )


def _row(label: str, value: str) -> str:
    return (
        '<tr>'
        '<td style="padding:6px 12px 6px 0;color:#6b7280;font-size:13px;white-space:nowrap;vertical-align:top;">'
        + label +
        '</td>'
        '<td style="padding:6px 0;font-size:13px;color:#111827;">'
        + value +
        '</td></tr>'
    )


def _section(title: str, content: str) -> str:
    return (
        '<div style="margin-bottom:24px;">'
        '<div style="font-size:11px;font-weight:600;letter-spacing:0.1em;'
        'text-transform:uppercase;color:#10b981;margin-bottom:10px;">' + title + '</div>'
        + content +
        '</div>'
    )


def build_baja_con_evidencia_html(
    sender: IdentifiedSender,
    holder_email: str,
    numero: int,
    baja_legal_html: str,
    baja_legal_text: str,
) -> tuple[str, str]:
    """
    Construye un email combinado para el titular (no para la empresa):
    - Encabezado de "copia para ti"
    - Informe de evidencia completa (datos personales, IPs, correos)
    - Texto legal de la solicitud que se enviaría a la empresa

    Retorna (html, text_plano).
    """
    ev = sender.evidence
    data_labels = [PERSONAL_DATA_LABELS.get(t, t) for t in (sender.personal_data_types or [])]
    ips = ev.header_ips or []
    chile_ips = ev.header_ip_chile_matches or []

    risk_colors = {"low": "#10b981", "medium": "#f59e0b", "high": "#ef4444"}
    risk_names  = {"low": "Bajo", "medium": "Medio", "high": "Alto"}
    risk_color = risk_colors.get(sender.risk.level, "#6b7280")
    risk_name  = risk_names.get(sender.risk.level, sender.risk.level.upper())

    tone_colors = {1: "#10b981", 2: "#f59e0b"}
    tone_labels = {
        1: "Solicitud N°1 — Formal",
        2: "Solicitud N°2 — Advertencia de denuncia",
    }
    tone_color = tone_colors.get(min(numero, 2), "#ef4444")
    tone_label = tone_labels.get(min(numero, 2), f"Solicitud N°{numero} — Denuncia inminente")

    no_val = "<em style='color:#9ca3af'>No detectado</em>"

    def badges(values: list[str], color: str = "#10b981", limit: int = 8) -> str:
        cleaned = [v.strip() for v in values if v and v.strip()][:limit]
        if not cleaned:
            return no_val
        return " ".join(_badge(v, color) for v in cleaned)

    names_html   = badges(sender.personal_names or [])
    addrs_html   = badges(sender.personal_addresses or [], "#6366f1")
    ruts_html    = badges(sender.personal_ruts or [], "#f59e0b")
    phones_html  = badges(sender.personal_phones or [], "#0ea5e9")
    plates_html  = badges(sender.personal_plates or [], "#8b5cf6")
    types_html   = badges(data_labels) or "<em style='color:#9ca3af'>Sin tipificar</em>"
    ips_html     = badges(ips, "#6b7280", 12) if ips else "<em style='color:#9ca3af'>No detectadas</em>"
    cl_ips_html  = badges(chile_ips, "#10b981") if chile_ips else "<em style='color:#9ca3af'>Ninguna</em>"

    subjects_html = "".join(
        '<div style="background:#f9fafb;border:1px solid #e5e7eb;border-radius:6px;'
        'padding:6px 10px;font-size:12px;color:#374151;margin-bottom:4px;">' + s + '</div>'
        for s in (ev.sample_subjects or [])[:5]
    ) or "<em style='color:#9ca3af;font-size:12px;'>Sin muestra</em>"

    from_addrs_html = badges(ev.from_addresses or [], "#374151")
    rt_addrs_html   = badges(ev.reply_to_addresses or [], "#374151")
    rp_addrs_html   = badges(ev.return_path_addresses or [], "#374151")

    risk_reasons_html = "".join(
        '<li style="font-size:12px;color:#374151;margin-bottom:4px;">' + r + '</li>'
        for r in (sender.risk.reasons or [])
    )
    risk_ul = (
        '<ul style="margin:6px 0 0 0;padding-left:20px;">' + risk_reasons_html + '</ul>'
        if risk_reasons_html else ""
    )

    # ── Legal text section (styled) ──────────────────────────────────────────
    # Strip outer HTML from baja_legal_html to embed as a section
    import re as _re
    body_match = _re.search(r'<body[^>]*>(.*?)</body>', baja_legal_html, _re.DOTALL | _re.IGNORECASE)
    legal_inner = body_match.group(1).strip() if body_match else (
        '<pre style="font-family:inherit;font-size:13px;white-space:pre-wrap;">'
        + baja_legal_text + '</pre>'
    )

    html = f"""<!DOCTYPE html>
<html lang="es">
<head><meta charset="UTF-8"><meta name="viewport" content="width=device-width,initial-scale=1.0">
<title>Copia solicitud de baja — {sender.company_name}</title></head>
<body style="margin:0;padding:0;background:#f3f4f6;font-family:-apple-system,BlinkMacSystemFont,'Segoe UI',sans-serif;">
<div style="max-width:700px;margin:28px auto;background:#fff;border-radius:14px;overflow:hidden;box-shadow:0 4px 24px rgba(0,0,0,0.08);">

  <!-- header -->
  <div style="background:linear-gradient(135deg,#1e3a5f,#2563eb);padding:28px 36px;">
    <div style="font-size:11px;letter-spacing:.15em;text-transform:uppercase;color:#93c5fd;margin-bottom:6px;">
      Copia para ti · {tone_label}
    </div>
    <div style="font-size:22px;font-weight:700;color:#fff;margin-bottom:4px;">{sender.company_name}</div>
    <div style="font-size:13px;color:#bfdbfe;">{sender.primary_domain} · {sender.country}</div>
  </div>

  <div style="padding:28px 36px;">

    <!-- aviso -->
    <div style="background:#eff6ff;border:1px solid #bfdbfe;border-radius:10px;padding:14px 18px;margin-bottom:24px;">
      <div style="font-size:12px;color:#1e40af;font-weight:600;text-transform:uppercase;letter-spacing:.08em;margin-bottom:4px;">
        Esta es tu copia
      </div>
      <div style="font-size:13px;color:#1e3a8a;">
        La solicitud fue enviada a <strong>{sender.primary_domain}</strong>.
        Este correo resume la evidencia que respalda tu pedido.
      </div>
    </div>

    <!-- SECCIÓN 1: datos personales -->
    <div style="margin-bottom:22px;">
      <div style="font-size:11px;font-weight:600;letter-spacing:.1em;text-transform:uppercase;color:#2563eb;margin-bottom:10px;">
        1 — Datos personales que esta empresa tiene de ti
      </div>
      <table style="border-collapse:collapse;width:100%;">
        {_row("Tipos de datos", types_html)}
        {_row("Nombre(s)", names_html)}
        {_row("Dirección(es)", addrs_html)}
        {_row("RUT(s)", ruts_html)}
        {_row("Teléfono(s)", phones_html)}
        {_row("Patente(s)", plates_html)}
      </table>
    </div>

    <!-- SECCIÓN 2: actividad -->
    <div style="margin-bottom:22px;">
      <div style="font-size:11px;font-weight:600;letter-spacing:.1em;text-transform:uppercase;color:#2563eb;margin-bottom:10px;">
        2 — Actividad detectada en tu bandeja
      </div>
      <table style="border-collapse:collapse;width:100%;">
        {_row("Correos enviados", f'<strong style="font-size:16px;">{ev.message_count}</strong>')}
        {_row("En spam", str(ev.spam_count))}
        {_row("En papelera", str(ev.trash_count))}
        {_row("Primer correo", ev.first_seen or "Desconocido")}
        {_row("Último correo", ev.last_seen or "Desconocido")}
        {_row("From", from_addrs_html)}
        {_row("Reply-To", rt_addrs_html)}
        {_row("Return-Path", rp_addrs_html)}
      </table>
      <div style="margin-top:12px;">
        <div style="font-size:11px;color:#6b7280;text-transform:uppercase;letter-spacing:.08em;margin-bottom:6px;">Asuntos detectados</div>
        {subjects_html}
      </div>
    </div>

    <!-- SECCIÓN 3: IPs -->
    <div style="margin-bottom:22px;">
      <div style="font-size:11px;font-weight:600;letter-spacing:.1em;text-transform:uppercase;color:#2563eb;margin-bottom:10px;">
        3 — IPs en cabeceras de correo
      </div>
      <table style="border-collapse:collapse;width:100%;">
        {_row(f"Todas las IPs ({len(ips)})", ips_html)}
        {_row(f"IPs chilenas ({len(chile_ips)})", cl_ips_html)}
      </table>
      {"<div style='font-size:12px;color:#065f46;background:#f0fdf4;border:1px solid #bbf7d0;border-radius:6px;padding:8px 12px;margin-top:8px;'>✅ Se detectaron IPs asociadas a Chile — posible tratamiento de datos dentro del país.</div>" if chile_ips else ""}
    </div>

    <!-- SECCIÓN 4: riesgo -->
    <div style="margin-bottom:22px;">
      <div style="font-size:11px;font-weight:600;letter-spacing:.1em;text-transform:uppercase;color:#2563eb;margin-bottom:10px;">
        4 — Nivel de riesgo
      </div>
      <div style="display:inline-block;background:{risk_color}22;color:{risk_color};border:1px solid {risk_color}55;
        border-radius:8px;padding:4px 16px;font-weight:600;font-size:14px;margin-bottom:8px;">{risk_name.upper()}</div>
      {risk_ul}
    </div>

    <!-- SECCIÓN 5: texto legal enviado -->
    <div style="margin-bottom:8px;">
      <div style="font-size:11px;font-weight:600;letter-spacing:.1em;text-transform:uppercase;color:{tone_color};margin-bottom:12px;">
        5 — Texto legal enviado a la empresa
      </div>
      {legal_inner}
    </div>

  </div>
</div>
</body></html>"""

    # ── Plain text version ────────────────────────────────────────────────────
    def lbl(vals: list[str], fallback: str = "No detectado") -> str:
        cleaned = [v.strip() for v in vals if v and v.strip()]
        return ", ".join(cleaned[:8]) if cleaned else fallback

    text = "\n".join([
        f"=== COPIA SOLICITUD DE BAJA N°{numero} — {sender.company_name} ===",
        f"Empresa: {sender.company_name} ({sender.primary_domain})",
        f"País: {sender.country}",
        "",
        "--- DATOS PERSONALES DETECTADOS ---",
        f"Tipos      : {lbl(data_labels)}",
        f"Nombre(s)  : {lbl(sender.personal_names or [])}",
        f"Dirección  : {lbl(sender.personal_addresses or [])}",
        f"RUT(s)     : {lbl(sender.personal_ruts or [])}",
        f"Teléfono(s): {lbl(sender.personal_phones or [])}",
        f"Patente(s) : {lbl(sender.personal_plates or [])}",
        "",
        "--- ACTIVIDAD ---",
        f"Correos enviados : {ev.message_count}",
        f"Spam             : {ev.spam_count}",
        f"Papelera         : {ev.trash_count}",
        f"Primer correo    : {ev.first_seen or 'Desconocido'}",
        f"Último correo    : {ev.last_seen or 'Desconocido'}",
        f"From             : {lbl(ev.from_addresses or [])}",
        f"Asuntos          : {lbl(ev.sample_subjects or [], 'Sin muestra')}",
        "",
        "--- IPs EN CABECERAS ---",
        f"Total IPs   : {len(ips)} — {lbl(ips, 'No detectadas')}",
        f"IPs chilenas: {len(chile_ips)} — {lbl(chile_ips, 'Ninguna')}",
        "",
        "--- RIESGO ---",
        f"Nivel: {risk_name.upper()}",
        *(["Razones: " + r for r in (sender.risk.reasons or [])]),
        "",
        "--- TEXTO LEGAL ENVIADO A LA EMPRESA ---",
        baja_legal_text,
    ])

    return html, text


async def send_simple_email(
    *,
    to: str,
    subject: str,
    html: str,
    text: str,
) -> None:
    """Envía un correo simple via SMTP. Silencia errores para no romper el seed."""
    if not is_smtp_configured():
        logger.info("[demo-email] SMTP no configurado, skip: %s → %s", subject, to)
        return
    try:
        loop = asyncio.get_event_loop()
        await loop.run_in_executor(None, _send_smtp, to, subject, html, text)
        logger.info("[demo-email] Enviado: %s → %s", subject, to)
    except Exception as exc:
        logger.warning("[demo-email] Error enviando: %s", exc)


def _build_html_report(sender: IdentifiedSender, holder_email: str) -> str:
    ev = sender.evidence
    data_labels = [PERSONAL_DATA_LABELS.get(t, t) for t in (sender.personal_data_types or [])]
    ips = ev.header_ips or []
    chile_ips = ev.header_ip_chile_matches or []

    risk_colors = {"low": "#10b981", "medium": "#f59e0b", "high": "#ef4444"}
    risk_color = risk_colors.get(sender.risk.level, "#6b7280")

    no_name = "<em style='color:#9ca3af'>No detectado</em>"
    no_addr = "<em style='color:#9ca3af'>No detectada</em>"
    no_ip = "<em style='color:#9ca3af'>No detectadas</em>"

    names_html = " ".join(_badge(n) for n in (sender.personal_names or [])[:8]) or no_name
    addresses_html = " ".join(_badge(a, "#6366f1") for a in (sender.personal_addresses or [])[:5]) or no_addr
    ruts_html = " ".join(_badge(r, "#f59e0b") for r in (sender.personal_ruts or [])[:5]) or no_name
    phones_html = " ".join(_badge(p, "#0ea5e9") for p in (sender.personal_phones or [])[:5]) or no_name
    plates_html = " ".join(_badge(pl, "#8b5cf6") for pl in (sender.personal_plates or [])[:5]) or no_addr
    data_types_html = " ".join(_badge(dl) for dl in data_labels) or "<em style='color:#9ca3af'>Sin tipificar</em>"
    ips_html = " ".join(_badge(ip, "#6b7280") for ip in ips[:12]) or no_ip
    chile_ips_html = " ".join(_badge(ip, "#10b981") for ip in chile_ips[:8]) or "<em style='color:#9ca3af'>Ninguna</em>"

    subjects_html_parts = [
        '<div style="background:#f9fafb;border:1px solid #e5e7eb;border-radius:6px;'
        'padding:6px 10px;font-size:12px;color:#374151;margin-bottom:4px;">' + s + '</div>'
        for s in (ev.sample_subjects or [])[:5]
    ]
    subjects_html = "".join(subjects_html_parts) or "<em style='color:#9ca3af;font-size:12px;'>Sin muestra</em>"

    reasons_html = "".join(
        '<li style="font-size:12px;color:#374151;margin-bottom:4px;">' + r + '</li>'
        for r in (sender.risk.reasons or [])
    )
    risk_ul = '<ul style="margin:8px 0 0 0;padding-left:20px;">' + reasons_html + '</ul>' if reasons_html else ""

    # ── Section 1: personal data ──────────────────────────────────────────────
    section1_table = (
        '<table style="border-collapse:collapse;width:100%;">'
        + _row("Tipos de datos", data_types_html)
        + _row("Nombre(s)", names_html)
        + _row("Dirección(es)", addresses_html)
        + _row("RUT(s)", ruts_html)
        + _row("Teléfono(s)", phones_html)
        + _row("Patente(s)", plates_html)
        + '</table>'
    )
    section1 = _section("1 — Datos personales detectados", section1_table)

    # ── Section 2: evidence ───────────────────────────────────────────────────
    section2_table = (
        '<table style="border-collapse:collapse;width:100%;">'
        + _row("Correos detectados", '<strong>' + str(ev.message_count) + '</strong>')
        + _row("Spam", str(ev.spam_count))
        + _row("Papelera", str(ev.trash_count))
        + _row("Primer correo", ev.first_seen or "Desconocido")
        + _row("Último correo", ev.last_seen or "Desconocido")
        + _row("From", _label(ev.from_addresses or []))
        + _row("Reply-To", _label(ev.reply_to_addresses or []))
        + _row("Return-Path", _label(ev.return_path_addresses or []))
        + _row("IPs en cabeceras (" + str(len(ips)) + ")", ips_html)
        + _row("IPs asociadas a Chile (" + str(len(chile_ips)) + ")", chile_ips_html)
        + '</table>'
        + '<div style="margin-top:12px;">'
        + '<div style="font-size:11px;color:#6b7280;text-transform:uppercase;letter-spacing:0.08em;margin-bottom:6px;">Asuntos de muestra</div>'
        + subjects_html
        + '</div>'
    )
    section2 = _section("2 — Evidencia de tratamiento de correos", section2_table)

    # ── Section 3: risk ───────────────────────────────────────────────────────
    risk_badge = (
        '<div style="display:inline-block;background:' + risk_color + '22;color:' + risk_color + ';'
        'border:1px solid ' + risk_color + '55;border-radius:8px;padding:4px 14px;'
        'font-weight:600;font-size:14px;margin-bottom:12px;">'
        + sender.risk.level.upper() + '</div>'
    )
    section3 = _section("3 — Nivel de riesgo detectado", risk_badge + risk_ul)

    # ── Section 4: rights draft ───────────────────────────────────────────────
    draft_content = (
        '<div style="background:#f9fafb;border:1px solid #e5e7eb;border-radius:8px;'
        'padding:16px 20px;font-size:13px;color:#374151;line-height:1.6;">'
        '<p style="margin:0 0 10px 0;">Estimado equipo de privacidad de <strong>'
        + sender.company_name + '</strong>,</p>'
        '<p style="margin:0 0 10px 0;">Solicito el ejercicio de mis derechos sobre datos personales '
        '(acceso, oposición y supresión/eliminación).</p>'
        '<ul style="margin:0 0 10px 0;padding-left:20px;">'
        '<li>Confirmar si mantienen mis datos y detallar origen, finalidad, base legal y destinatarios.</li>'
        '<li>Eliminar mis datos de sus sistemas y detener futuros envíos.</li>'
        '<li>Entregar evidencia de cumplimiento (fecha, sistemas impactados y terceros notificados).</li>'
        '</ul>'
        '<p style="margin:0;">Saludos,<br><strong>' + holder_email + '</strong></p>'
        '</div>'
    )
    section4 = _section("4 — Borrador de solicitud de derechos", draft_content)

    # ── Assemble full HTML ────────────────────────────────────────────────────
    html = (
        '<!DOCTYPE html>'
        '<html lang="es">'
        '<head><meta charset="UTF-8"><meta name="viewport" content="width=device-width,initial-scale=1.0">'
        '<title>Informe de datos personales - ' + sender.company_name + '</title></head>'
        '<body style="margin:0;padding:0;background:#f3f4f6;'
        "font-family:-apple-system,BlinkMacSystemFont,'Segoe UI',sans-serif;\">"
        '<div style="max-width:680px;margin:32px auto;background:#ffffff;border-radius:16px;'
        'overflow:hidden;box-shadow:0 4px 24px rgba(0,0,0,0.08);">'

        '<div style="background:linear-gradient(135deg,#065f46,#10b981);padding:32px 40px;">'
        '<div style="font-size:11px;letter-spacing:0.15em;text-transform:uppercase;'
        'color:#6ee7b7;margin-bottom:8px;">Informe de Privacidad — Prueba</div>'
        '<div style="font-size:24px;font-weight:700;color:#ffffff;margin-bottom:4px;">'
        + sender.company_name + '</div>'
        '<div style="font-size:14px;color:#a7f3d0;">' + sender.primary_domain + ' · ' + sender.country + '</div>'
        '</div>'

        '<div style="padding:32px 40px;">'

        '<div style="background:#f0fdf4;border:1px solid #bbf7d0;border-radius:10px;'
        'padding:16px 20px;margin-bottom:28px;">'
        '<div style="font-size:11px;color:#065f46;font-weight:600;text-transform:uppercase;'
        'letter-spacing:0.1em;margin-bottom:6px;">Titular analizado</div>'
        '<div style="font-size:15px;color:#064e3b;font-weight:500;">' + holder_email + '</div>'
        '<div style="font-size:12px;color:#6b7280;margin-top:4px;">'
        'Este informe es una PRUEBA y no ha sido enviado a la empresa.</div>'
        '</div>'

        + section1
        + section2
        + section3
        + section4

        + '<div style="margin-top:28px;padding-top:20px;border-top:1px solid #e5e7eb;'
        'font-size:11px;color:#9ca3af;text-align:center;line-height:1.5;">'
        'Generado por la herramienta de análisis de privacidad · Solo para uso de prueba<br>'
        'Este informe no ha sido enviado a la empresa mencionada.'
        '</div>'

        '</div>'
        '</div>'
        '</body></html>'
    )

    return html
