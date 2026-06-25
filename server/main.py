"""
main.py — FastAPI application entry point.

Endpoints:
  GET  /__health              → health check (frontend lo llama cada 10s)
  GET  /api/osint             → búsqueda principal (guarda en SQLite)
  GET  /api/searches          → listado de búsquedas recientes (reemplaza mockData)
  GET  /api/searches/{id}     → detalle de una búsqueda guardada
  DELETE /api/searches/{id}   → eliminar búsqueda
  GET  /api/modules           → estado de módulos
"""
from __future__ import annotations

import asyncio
import logging
import os
import sys
import time
from contextlib import asynccontextmanager
from pathlib import Path as FilePath
from typing import Optional

import uvicorn
import httpx
from fastapi import FastAPI, Query, HTTPException, Path
from pydantic import BaseModel
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, HTMLResponse, RedirectResponse
from fastapi.staticfiles import StaticFiles

from config import APP_NAME, APP_VERSION, BAJA_REPORT_DESTINATION, DEBUG, CORS_ORIGINS
from core.email_identification import identify_email_footprint
from core.browser_history import analyze_browser_history_async, REGISTRY as BROWSER_REGISTRY
from core.breach_crossref import run_breach_crossref, check_domains_hibp
from core.breach_scraper import run_scraper as run_breach_scraper, scraper_stats, load_incidents
from core.email_sender import (
    is_smtp_configured, send_baja_report, send_baja_report_via_gmail_api,
    send_correo_via_gmail_api, _send_smtp, build_baja_con_evidencia_html,
    send_simple_email,
)
from core.gmail_oauth import (
    build_gmail_oauth_url,
    build_gmail_popup_error_html,
    build_gmail_popup_response_html,
    exchange_gmail_code,
    gmail_oauth_is_configured,
)
from core.orchestrator import run_search
from core.baja_monitor import (
    scan_all_active_bajas,
    build_baja_subject,
    build_baja_texto,
    compute_fecha_limite,
    add_business_days,
)
from models.schemas import (
    BajaReportRequest,
    BajaViolationFound,
    BajaRecord,
    EmailIdentificationRequest,
    EmailIdentificationResponse,
    MarcarCumplidaRequest,
    OSINTResponse,
    ReescalarRequest,
    SolicitarBajaRequest,
)
from db import (
    init_db, save_search, list_searches, get_search, delete_search,
    save_baja_request, list_baja_requests, get_baja_request,
    update_baja_estado, get_baja_history,
    save_baja_violation, list_all_bajas_with_violations,
    delete_demo_bajas,
)
from datetime import datetime, timezone

# ── Logging ──────────────────────────────────────────────────────────────────
logging.basicConfig(
    level=logging.DEBUG if DEBUG else logging.INFO,
    format="%(asctime)s | %(levelname)-8s | %(name)s | %(message)s",
    stream=sys.stdout,
)
logger = logging.getLogger(__name__)


# ── Lifespan (startup / shutdown) ────────────────────────────────────────────
@asynccontextmanager
async def lifespan(app: FastAPI):
    """Inicializa la DB al arrancar el servidor."""
    await init_db()
    logger.info(f"{APP_NAME} v{APP_VERSION} listo")
    yield
    # shutdown hooks aquí si los necesitamos


# ── App ───────────────────────────────────────────────────────────────────────
app = FastAPI(
    title=APP_NAME,
    version=APP_VERSION,
    docs_url="/docs",
    redoc_url="/redoc",
    lifespan=lifespan,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=CORS_ORIGINS,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


# ── Health ────────────────────────────────────────────────────────────────────
@app.get("/__health")
async def health():
    return {"status": "ok", "version": APP_VERSION}


# ── Búsqueda principal ────────────────────────────────────────────────────────
@app.get("/api/osint", response_model=OSINTResponse)
async def osint_search(
    nombre: str       = Query(..., min_length=2, description="Nombre completo"),
    rut:    Optional[str] = Query(default=None,  description="RUT (opcional)"),
    email:  Optional[str] = Query(default=None,  description="Email semilla (opcional)"),
):
    """
    Búsqueda OSINT principal.
    - Corre todos los módulos en paralelo
    - Guarda el resultado en SQLite automáticamente
    - Devuelve OSINTResponse con id de búsqueda incluido
    """
    t0 = time.time()
    logger.info(f"Búsqueda | nombre='{nombre}' rut={rut}")

    try:
        resultado = await run_search(nombre=nombre, rut=rut, email=email)
    except Exception as exc:
        logger.error(f"Error en búsqueda: {exc}", exc_info=True)
        raise HTTPException(status_code=500, detail=str(exc))

    # Guardar en SQLite (no bloqueante — si falla no rompe la respuesta)
    try:
        search_id = await save_search(resultado)
        logger.info(
            f"OK | id={search_id} | {resultado.resumen.total_hallazgos} hallazgos "
            f"| {int((time.time()-t0)*1000)}ms"
        )
    except Exception as exc:
        logger.error(f"Error guardando en DB: {exc}", exc_info=True)
        search_id = None

    # Inyectar el ID en la respuesta para que el frontend pueda navegar al detalle
    response_dict = resultado.model_dump()
    response_dict["search_id"] = search_id
    return OSINTResponse(**response_dict)


async def _perform_email_identification(
    request: EmailIdentificationRequest,
    progress_cb=None,
) -> EmailIdentificationResponse:
    """Ejecuta el análisis de correo y, si hay token, el monitor de bajas.
    Compartido por el endpoint síncrono y por el trabajo en segundo plano."""
    result = await identify_email_footprint(request, progress_cb=progress_cb)

    # ── Monitor automático de bajas ───────────────────────────────────────────
    # Corre solo cuando hay token de Gmail. Si falla, no rompe el análisis.
    token = request.gmail_access_token
    if token:
        try:
            violations = await scan_all_active_bajas(token)
            if violations:
                logger.info("[baja-monitor] %d violación(es) detectada(s) durante el sync", len(violations))
                violation_models = [BajaViolationFound(**v) for v in violations]
                result = result.model_copy(update={"baja_violations": violation_models})
        except Exception as exc:
            logger.warning("[baja-monitor] Error en monitor automático: %s", exc)

    return result


@app.post("/api/identification/email-footprint", response_model=EmailIdentificationResponse)
async def email_identification(request: EmailIdentificationRequest):
    """
    Fase 1: identificación por correo autorizado (síncrono).
    Se mantiene para mensajes manuales y análisis pequeños. Para buzones grandes
    usa el flujo por trabajo en segundo plano (/start + /status), que no expira.
    """
    try:
        return await _perform_email_identification(request)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc))
    except httpx.HTTPStatusError as exc:
        detail = exc.response.text[:500] if exc.response is not None else str(exc)
        raise HTTPException(status_code=502, detail=f"Proveedor de correo rechazó la solicitud: {detail}")
    except Exception as exc:
        logger.error(f"Error en identificación de email: {exc}", exc_info=True)
        raise HTTPException(status_code=500, detail="No se pudo completar la identificación por correo")


# ── Análisis de correo en segundo plano (no expira; con progreso) ─────────────
# Registro en memoria de trabajos. Es una app local de un solo usuario, así que
# un dict en memoria es suficiente; se podan los terminados más antiguos.
_EMAIL_JOBS: dict[str, dict] = {}
_EMAIL_JOBS_MAX = 12


def _prune_email_jobs() -> None:
    if len(_EMAIL_JOBS) <= _EMAIL_JOBS_MAX:
        return
    finished = [j for j, s in _EMAIL_JOBS.items() if s.get("status") in ("done", "error")]
    for job_id in finished[: max(0, len(_EMAIL_JOBS) - _EMAIL_JOBS_MAX)]:
        _EMAIL_JOBS.pop(job_id, None)


async def _run_email_job(job_id: str, request: EmailIdentificationRequest) -> None:
    state = _EMAIL_JOBS[job_id]

    def cb(done: int, total: int, stage: str = "") -> None:
        state["processed"] = done
        state["total"] = total
        if stage:
            state["stage"] = stage

    try:
        result = await _perform_email_identification(request, progress_cb=cb)
        state["result"] = result.model_dump()
        state["status"] = "done"
    except ValueError as exc:
        state["status"], state["error"] = "error", str(exc)
    except httpx.HTTPStatusError as exc:
        detail = exc.response.text[:300] if exc.response is not None else str(exc)
        state["status"], state["error"] = "error", f"Proveedor de correo rechazó la solicitud: {detail}"
    except Exception as exc:
        logger.error(f"[email-job {job_id}] {exc}", exc_info=True)
        state["status"], state["error"] = "error", "No se pudo completar la identificación por correo"


@app.post("/api/identification/email-footprint/start")
async def email_identification_start(request: EmailIdentificationRequest):
    """Inicia el análisis en segundo plano y devuelve un job_id para sondear."""
    import uuid as _uuid
    job_id = _uuid.uuid4().hex
    _EMAIL_JOBS[job_id] = {"status": "running", "processed": 0, "total": 0, "stage": "Iniciando…", "result": None, "error": None}
    _prune_email_jobs()
    asyncio.create_task(_run_email_job(job_id, request))
    return {"job_id": job_id}


@app.get("/api/identification/email-footprint/status")
async def email_identification_status(job_id: str):
    """Estado del análisis: running (con processed/total), done (con result) o error."""
    state = _EMAIL_JOBS.get(job_id)
    if state is None:
        raise HTTPException(status_code=404, detail="Trabajo no encontrado o ya expirado.")
    return {
        "status":    state["status"],
        "processed": state["processed"],
        "total":     state["total"],
        "stage":     state.get("stage", ""),
        "error":     state["error"],
        "result":    state["result"] if state["status"] == "done" else None,
    }


@app.get("/api/identification/baja-status")
async def baja_status():
    """Estado del servicio de envío de informes de baja."""
    return {
        "smtp_configured": is_smtp_configured(),
        "gmail_api_available": True,   # siempre disponible si el usuario tiene Gmail conectado
        "destination": BAJA_REPORT_DESTINATION,
    }


@app.post("/api/identification/send-baja-report")
async def send_baja_report_endpoint(request: BajaReportRequest):
    """
    Envía a holder_email el mismo correo que se mandaría a la empresa
    (texto legal de baja N°1) más la evidencia completa (datos personales,
    cantidad de correos, IPs chilenas, etc.).

    Intenta Gmail API primero; si falla o no hay token, usa SMTP.
    Siempre entrega a holder_email.
    """
    destination = request.holder_email or BAJA_REPORT_DESTINATION

    # Construir texto legal de baja N°1
    subject = build_baja_subject(1, request.sender.company_name)
    legal_text, legal_html = build_baja_texto(
        numero=1,
        empresa=request.sender.company_name,
        holder_email=request.holder_email,
        historial_fechas=[],
        violations=[],
    )

    # Combinar texto legal + evidencia en un solo email
    html_body, text_body = build_baja_con_evidencia_html(
        sender=request.sender,
        holder_email=request.holder_email,
        numero=1,
        baja_legal_html=legal_html,
        baja_legal_text=legal_text,
    )

    # ── 1) Intentar Gmail API ──────────────────────────────────────────────
    if request.access_token:
        try:
            from_addr = request.sender_email or request.holder_email
            await send_correo_via_gmail_api(
                access_token=request.access_token,
                from_address=from_addr,
                destination=destination,
                subject=subject,
                html_body=html_body,
                text_body=text_body,
            )
            return {"sent": True, "destination": destination, "method": "gmail"}
        except Exception as exc:
            logger.warning("[baja-report] Gmail API falló (%s), usando SMTP", exc)

    # ── 2) Fallback SMTP ──────────────────────────────────────────────────
    if is_smtp_configured():
        import asyncio as _asyncio
        loop = _asyncio.get_event_loop()
        try:
            await loop.run_in_executor(None, _send_smtp, destination, subject, html_body, text_body)
            return {"sent": True, "destination": destination, "method": "smtp"}
        except Exception as exc:
            logger.error("[baja-report] Error SMTP: %s", exc, exc_info=True)
            raise HTTPException(status_code=500, detail=f"No se pudo enviar el correo: {exc}")

    raise HTTPException(
        status_code=503,
        detail="Conecta tu Gmail o configura SMTP para poder enviar el informe.",
    )


@app.get("/api/auth/gmail/status")
async def gmail_auth_status():
    from config import GOOGLE_OAUTH_REDIRECT_URI
    from urllib.parse import urlparse

    parsed = urlparse(GOOGLE_OAUTH_REDIRECT_URI)
    callback_origin = f"{parsed.scheme}://{parsed.netloc}" if parsed.scheme and parsed.netloc else None
    return {"configured": gmail_oauth_is_configured(), "callback_origin": callback_origin}


@app.get("/api/auth/gmail/start")
async def gmail_auth_start():
    try:
        return RedirectResponse(url=build_gmail_oauth_url(), status_code=302)
    except ValueError as exc:
        raise HTTPException(status_code=503, detail=str(exc))


@app.get("/api/auth/gmail/callback", response_class=HTMLResponse)
async def gmail_auth_callback(
    code: Optional[str] = Query(default=None),
    state: Optional[str] = Query(default=None),
    error: Optional[str] = Query(default=None),
):
    if error:
        return HTMLResponse(build_gmail_popup_error_html(f"Google devolvio un error: {error}"), status_code=400)
    if not code or not state:
        return HTMLResponse(build_gmail_popup_error_html("Faltan parametros de OAuth en el callback."), status_code=400)

    try:
        payload = await exchange_gmail_code(code=code, state=state)
        return HTMLResponse(build_gmail_popup_response_html(payload))
    except ValueError as exc:
        return HTMLResponse(build_gmail_popup_error_html(str(exc)), status_code=400)
    except httpx.HTTPStatusError as exc:
        detail = exc.response.text[:500] if exc.response is not None else str(exc)
        return HTMLResponse(build_gmail_popup_error_html(f"Google rechazo el intercambio del token: {detail}"), status_code=502)
    except Exception as exc:
        logger.error(f"Error en callback Gmail OAuth: {exc}", exc_info=True)
        return HTMLResponse(build_gmail_popup_error_html("No se pudo completar la conexión con Gmail."), status_code=500)


# ── Bajas automáticas ────────────────────────────────────────────────────────

@app.get("/api/baja/historial")
async def baja_historial():
    """
    Devuelve todas las solicitudes de baja agrupadas por empresa/dominio,
    con el flujo completo de escalación y las violaciones detectadas.
    Usado por la vista de Historial de Bajas del frontend.
    """
    groups = await list_all_bajas_with_violations()
    return {"groups": groups, "total": len(groups)}


@app.post("/api/baja/solicitar")
async def solicitar_baja(request: SolicitarBajaRequest):
    """
    Crea una nueva solicitud de baja:
    1. Calcula la fecha límite legal (15 días hábiles).
    2. Genera el texto de la solicitud según el número de intento.
    3. Envía el correo a la empresa (si hay OAuth activo) y SIEMPRE envía
       una copia al titular (holder_email) con la evidencia completa via SMTP.
    4. Persiste el registro en SQLite.
    """
    sender = request.sender
    numero = 1
    baja_anterior_id = None

    # Verificar si ya existe una solicitud previa para este dominio
    todas = await list_baja_requests()
    previas = [
        b for b in todas
        if b["dominio"] == sender.primary_domain
        and b["estado"] not in ("DENUNCIADA",)
    ]
    if previas:
        ultima = previas[0]  # ya ordenadas DESC
        numero = ultima["numero_solicitud"] + 1
        baja_anterior_id = ultima["id"]

    # Recuperar historial de fechas para el texto
    historial_fechas: list[str] = []
    if baja_anterior_id:
        history = await get_baja_history(baja_anterior_id)
        historial_fechas = [
            h["fecha_solicitud"][:10] for h in history if h.get("fecha_solicitud")
        ]

    # Violaciones de la solicitud previa (para incluir en el texto escalado)
    violations_for_text: list[dict] = []
    if baja_anterior_id:
        baja_prev = await get_baja_request(baja_anterior_id)
        if baja_prev:
            violations_for_text = baja_prev.get("violations", [])

    # Construir texto legal de la baja
    subject = build_baja_subject(numero, sender.company_name)
    legal_text, legal_html = build_baja_texto(
        numero=numero,
        empresa=sender.company_name,
        holder_email=request.holder_email,
        historial_fechas=historial_fechas,
        violations=violations_for_text,
    )

    # Construir email enriquecido con evidencia para el titular
    evidence_html, evidence_text = build_baja_con_evidencia_html(
        sender=sender,
        holder_email=request.holder_email,
        numero=numero,
        baja_legal_html=legal_html,
        baja_legal_text=legal_text,
    )

    import asyncio as _asyncio
    loop = _asyncio.get_event_loop()
    sent_to_company = False
    sent_to_holder = False

    # ── 1) Intentar envío a la empresa via Gmail API ────────────────────────
    if request.access_token:
        try:
            from_addr = request.sender_email or request.holder_email
            await send_correo_via_gmail_api(
                access_token=request.access_token,
                from_address=from_addr,
                destination=request.destinatario,
                subject=subject,
                html_body=legal_html,
                text_body=legal_text,
            )
            sent_to_company = True
            logger.info("[baja] Enviado a empresa %s via Gmail API", request.destinatario)
        except httpx.HTTPStatusError as exc:
            detail = exc.response.text[:300] if exc.response is not None else str(exc)
            logger.warning("[baja] Gmail API falló (%s), usando SMTP como fallback", detail)
        except Exception as exc:
            logger.warning("[baja] Gmail API error: %s, usando SMTP", exc)

    # ── 2) Enviar copia al titular via SMTP (siempre, independiente del OAuth) ──
    if is_smtp_configured():
        copy_subject = f"[Copia] {subject}"
        try:
            await loop.run_in_executor(
                None, _send_smtp, request.holder_email, copy_subject, evidence_html, evidence_text
            )
            sent_to_holder = True
            logger.info("[baja] Copia con evidencia enviada a titular %s via SMTP", request.holder_email)
        except Exception as exc:
            logger.error("[baja] Error enviando copia SMTP al titular: %s", exc, exc_info=True)

    if not sent_to_company and not sent_to_holder:
        raise HTTPException(
            status_code=503,
            detail=(
                "No se pudo enviar la solicitud: OAuth no disponible y SMTP no configurado. "
                "Configura SMTP_USER y SMTP_PASSWORD en .env o conecta tu Gmail."
            ),
        )

    # ── 3) Calcular fecha límite y persistir ────────────────────────────────
    now_dt = datetime.now(timezone.utc)
    fecha_limite = compute_fecha_limite(now_dt, numero)

    import json as _json
    baja_id = await save_baja_request(
        dominio=sender.primary_domain,
        empresa=sender.company_name,
        numero_solicitud=numero,
        fecha_limite=fecha_limite,
        destinatario=request.destinatario,
        holder_email=request.holder_email,
        evidencia_json=_json.dumps(sender.evidence.model_dump()),
        baja_anterior_id=baja_anterior_id,
    )

    baja = await get_baja_request(baja_id)
    return {
        "ok": True,
        "baja_id": baja_id,
        "numero_solicitud": numero,
        "sent_to_company": sent_to_company,
        "sent_to_holder": sent_to_holder,
        "baja": baja,
    }


@app.get("/api/baja")
async def listar_bajas():
    """Lista todas las solicitudes de baja con estado calculado."""
    return await list_baja_requests()


@app.get("/api/baja/{baja_id}")
async def obtener_baja(baja_id: str = Path(..., description="ID de la solicitud de baja")):
    """Detalle completo de una baja con correos de reincidencia adjuntos."""
    baja = await get_baja_request(baja_id)
    if not baja:
        raise HTTPException(status_code=404, detail="Solicitud de baja no encontrada")
    return baja


@app.post("/api/baja/{baja_id}/cumplida")
async def marcar_cumplida(
    baja_id: str = Path(...),
    request: MarcarCumplidaRequest = MarcarCumplidaRequest(),
):
    """El usuario confirma que recibió evidencia de que la empresa eliminó sus datos."""
    baja = await get_baja_request(baja_id)
    if not baja:
        raise HTTPException(status_code=404, detail="Solicitud de baja no encontrada")
    fecha_acuse = datetime.now(timezone.utc).isoformat()
    await update_baja_estado(baja_id, "CUMPLIDA", fecha_acuse=fecha_acuse)
    return {"ok": True, "estado": "CUMPLIDA", "fecha_acuse": fecha_acuse}


@app.post("/api/baja/{baja_id}/reescalar")
async def reescalar_baja(
    baja_id: str = Path(...),
    request: ReescalarRequest = ReescalarRequest(),
):
    """
    Genera y envía una nueva solicitud escalada para un dominio reincidente.
    Crea un nuevo registro encadenado al anterior y eleva el tono del correo.
    """
    baja = await get_baja_request(baja_id)
    if not baja:
        raise HTTPException(status_code=404, detail="Solicitud de baja no encontrada")

    if baja["estado"] not in ("REINCIDENTE", "VENCIDA"):
        raise HTTPException(
            status_code=400,
            detail="Solo se puede reescalar una baja en estado REINCIDENTE o VENCIDA.",
        )

    if not request.access_token:
        raise HTTPException(status_code=503, detail="Token de Gmail requerido para reescalar.")

    # Reconstruir contexto de la solicitud escalada
    numero = baja["numero_solicitud"] + 1
    history = await get_baja_history(baja_id)
    historial_fechas = [h["fecha_solicitud"][:10] for h in history if h.get("fecha_solicitud")]
    violations = baja.get("violations", [])
    destinatario = request.destinatario or baja["destinatario"]
    holder_email = baja["holder_email"]
    empresa = baja["empresa"]

    subject = build_baja_subject(numero, empresa)
    text_body, html_body = build_baja_texto(
        numero=numero,
        empresa=empresa,
        holder_email=holder_email,
        historial_fechas=historial_fechas,
        violations=violations,
    )

    try:
        from_addr = request.sender_email or holder_email
        await send_correo_via_gmail_api(
            access_token=request.access_token,
            from_address=from_addr,
            destination=destinatario,
            subject=subject,
            html_body=html_body,
            text_body=text_body,
        )
    except Exception as exc:
        logger.error("Error reescalando baja: %s", exc, exc_info=True)
        raise HTTPException(status_code=500, detail=f"No se pudo enviar: {exc}")

    # Marcar la baja anterior como DENUNCIADA (superada por la nueva)
    await update_baja_estado(baja_id, "DENUNCIADA")

    # Crear nuevo registro encadenado
    import json as _json
    now_dt = datetime.now(timezone.utc)
    fecha_limite = compute_fecha_limite(now_dt, numero)
    nuevo_id = await save_baja_request(
        dominio=baja["dominio"],
        empresa=empresa,
        numero_solicitud=numero,
        fecha_limite=fecha_limite,
        destinatario=destinatario,
        holder_email=holder_email,
        evidencia_json=_json.dumps(baja.get("evidencia_json", "{}")),
        baja_anterior_id=baja_id,
    )

    nueva_baja = await get_baja_request(nuevo_id)
    return {
        "ok": True,
        "nuevo_baja_id": nuevo_id,
        "numero_solicitud": numero,
        "baja": nueva_baja,
    }


@app.post("/api/baja/{baja_id}/sincronizar")
async def sincronizar_baja(
    baja_id: str = Path(...),
    access_token: str = "",
):
    """
    Fuerza una verificación inmediata de un dominio específico sin esperar
    al próximo sync completo de la bandeja.
    """
    if not access_token:
        raise HTTPException(status_code=400, detail="access_token requerido en query param")
    baja = await get_baja_request(baja_id)
    if not baja:
        raise HTTPException(status_code=404, detail="Solicitud de baja no encontrada")

    from core.baja_monitor import _check_baja
    import httpx as _httpx
    timeout = _httpx.Timeout(20.0, connect=8.0)
    async with _httpx.AsyncClient(timeout=timeout) as client:
        violations = await _check_baja(client, access_token, baja)

    return {
        "violations_found": len(violations),
        "violations": violations,
        "baja": await get_baja_request(baja_id),
    }


# ── POC de baja ───────────────────────────────────────────────────────────────

_POC_EMPRESA  = "Empresa POC S.A. (Prueba de Concepto)"
_POC_DOMINIO  = "empresa-poc-test.cl"
_POC_CONTACTO = "privacidad@empresa-poc-test.cl"  # ficticio, solo se muestra en el asunto


@app.post("/api/baja/poc/seed-demo")
async def poc_seed_demo():
    """
    Siembra la DB con 12 escenarios que cubren todos los casos del flujo de baja.

     1 Ripley    — N°1 → empresa respondió → cumplió (caso ideal)
     2 Falabella — N°1 → 2 correos post-baja → N°2 en espera
     3 Paris     — N°1 → plazo vencido sin respuesta
     4 BCI       — N°1 → en espera (solicitud reciente)
     5 Entel     — N°1 → cierre por inactividad (sin acuse formal)
     6 Santander — N°1 → respondió → 3 correos → N°2 en espera
     7 Walmart   — N°1 → correo → N°2 → 2 correos → N°3 en espera
     8 Líder     — N°1 → 3 correos → N°2 → empresa finalmente cumple
     9 Tricot    — N°1 → respuesta ambigua (acuse sin confirmar) → en espera
    10 Corona    — N°1 → correo → N°2 también vencida (ninguna atendida)
    11 Hites     — N°1 → respondió → silencio 2 meses → reaparece → N°2
    12 Jumbo     — N°1 → 5 correos distintos → N°2 en espera
    """
    import json as _json, uuid as _uuid
    from datetime import timedelta

    now = datetime.now(timezone.utc)

    # Limpiar datos demo anteriores para evitar duplicados al re-seedear
    await delete_demo_bajas()

    def iso(dt: datetime) -> str:
        return dt.isoformat()

    async def mk_baja(
        dominio: str, empresa: str, contacto: str,
        numero: int, fecha_sol: datetime, dias_limite: int,
        holder: str = "juanotaegui61@gmail.com",
        anterior_id: str | None = None,
        send_email: bool = True,
        prev_fechas: list[str] | None = None,
        prev_violations: list[dict] | None = None,
    ) -> str:
        fl = add_business_days(fecha_sol, dias_limite)
        subject = build_baja_subject(numero, empresa)
        text_body, html_body = build_baja_texto(
            numero, empresa, holder,
            prev_fechas or [],
            prev_violations or [],
        )
        body_preview = text_body[:400].strip()

        baja_id = await save_baja_request(
            dominio=dominio, empresa=empresa, numero_solicitud=numero,
            fecha_solicitud=iso(fecha_sol),
            fecha_limite=iso(fl), destinatario=contacto,
            holder_email=holder,
            evidencia_json=_json.dumps({
                "demo": True,
                "subject": subject,
                "to": contacto,
                "body_preview": body_preview,
            }),
            baja_anterior_id=anterior_id,
        )

        if send_email:
            await send_simple_email(
                to=holder,
                subject=f"[DEMO enviado a {contacto}] {subject}",
                html=html_body,
                text=text_body,
            )

        return baja_id

    async def send_respuesta_empresa(empresa: str, dominio: str, holder: str, fecha: str) -> None:
        subject = f"[DEMO respuesta de {dominio}] RE: Solicitud de supresión — {empresa}"
        text = f"""Estimado/a titular,

Hemos recibido y procesado su solicitud de supresión de datos personales con fecha {fecha[:10]}.

Confirmamos que:
1. Sus datos personales han sido eliminados de nuestros sistemas.
2. Ha sido dado de baja de todas nuestras listas de comunicación.
3. No recibirá más comunicaciones comerciales de nuestra parte.

Atentamente,
Equipo de Privacidad — {empresa}
"""
        html = f"""<!DOCTYPE html><html><body style="font-family:sans-serif;max-width:600px;margin:32px auto;">
<div style="background:#f0fdf4;border:1px solid #bbf7d0;border-radius:12px;padding:24px 32px;">
<p style="font-size:11px;color:#065f46;text-transform:uppercase;letter-spacing:.1em;margin:0 0 12px 0;">
  DEMO — Respuesta simulada de {empresa}</p>
<h2 style="color:#064e3b;margin:0 0 16px 0;">Confirmación de baja de datos</h2>
<p>Estimado/a titular,</p>
<p>Hemos recibido y procesado su solicitud de supresión de datos personales.</p>
<ul>
  <li>Sus datos personales han sido <strong>eliminados de nuestros sistemas</strong>.</li>
  <li>Ha sido dado de baja de todas nuestras <strong>listas de comunicación</strong>.</li>
  <li>No recibirá más comunicaciones comerciales de nuestra parte.</li>
</ul>
<p style="color:#6b7280;font-size:12px;">Atentamente,<br><strong>Equipo de Privacidad — {empresa}</strong></p>
</div></body></html>"""
        await send_simple_email(to=holder, subject=subject, html=html, text=text)

    async def send_reincidencia_email(
        empresa: str, dominio: str, holder: str,
        subj: str, from_addr: str, snippet: str,
    ) -> None:
        subject = f"[DEMO reincidencia de {dominio}] {subj}"
        html = f"""<!DOCTYPE html><html><body style="font-family:sans-serif;max-width:600px;margin:32px auto;">
<div style="background:#fef2f2;border:1px solid #fecaca;border-radius:12px;padding:24px 32px;">
<p style="font-size:11px;color:#991b1b;text-transform:uppercase;letter-spacing:.1em;margin:0 0 12px 0;">
  DEMO — Correo post-baja de {empresa}</p>
<p style="font-size:11px;color:#6b7280;">De: {from_addr}</p>
<h3 style="color:#111827;margin:0 0 16px 0;">{subj}</h3>
<p style="color:#374151;">{snippet}</p>
<p style="font-size:11px;color:#9ca3af;margin-top:24px;">
  Este correo fue enviado a pesar de tu solicitud de baja. Ha sido registrado como reincidencia.</p>
</div></body></html>"""
        text = f"DEMO reincidencia de {empresa}\nDe: {from_addr}\nAsunto: {subj}\n\n{snippet}"
        await send_simple_email(to=holder, subject=subject, html=html, text=text)

    holder = "juanotaegui61@gmail.com"

    # ── Escenario 1: CUMPLIDA ─────────────────────────────────────────────────
    dom1 = "ripley.cl-demo"
    t1 = now - timedelta(days=25)
    id1 = await mk_baja(dom1, "Ripley (Demo)", f"privacidad@{dom1}", 1, t1, 15)
    await update_baja_estado(id1, "CUMPLIDA", fecha_acuse=iso(t1 + timedelta(days=10)))
    await send_respuesta_empresa("Ripley (Demo)", dom1, holder, iso(t1 + timedelta(days=10)))

    # ── Escenario 2: REINCIDENTE + N°2 enviada ────────────────────────────────
    dom2 = "falabella.cl-demo"
    t2 = now - timedelta(days=30)
    id2 = await mk_baja(dom2, "Falabella (Demo)", f"privacidad@{dom2}", 1, t2, 15)
    # Dos violaciones post-baja
    v2_list = [
        ("¡Cyberday exclusivo para ti!", timedelta(days=18)),
        ("Tu oferta de crédito disponible", timedelta(days=22)),
    ]
    for subj, delta in v2_list:
        await save_baja_violation(
            baja_id=id2,
            message_id=f"demo-violation-{_uuid.uuid4()}",
            received_at=iso(t2 + delta),
            subject=subj,
            from_address=f"marketing@{dom2}",
            snippet="Aprovecha esta oferta exclusiva solo para clientes seleccionados. Válida hasta agotar stock.",
        )
        await send_reincidencia_email(
            "Falabella (Demo)", dom2, holder, subj, f"marketing@{dom2}",
            "Aprovecha esta oferta exclusiva solo para clientes seleccionados. Válida hasta agotar stock.",
        )
    await update_baja_estado(id2, "REINCIDENTE")
    # N°2 enviada
    t2b = now - timedelta(days=7)
    id2b = await mk_baja(dom2, "Falabella (Demo)", f"privacidad@{dom2}", 2, t2b, 5, anterior_id=id2)

    # ── Escenario 3: VENCIDA (sin respuesta) ──────────────────────────────────
    # Caso 4 del flujo: nunca responde y dejó de enviar — plazo expirado
    dom3 = "paris.cl-demo"
    t3 = now - timedelta(days=22)
    id3 = await mk_baja(dom3, "Paris (Demo)", f"privacidad@{dom3}", 1, t3, 15)
    # Estado VENCIDA se calcula dinámicamente (fecha_limite < now)

    # ── Escenario 4: SOLICITADA (en espera reciente) ──────────────────────────
    # Caso 1 en progreso: solicitud reciente, aguardando respuesta
    dom4 = "bci.cl-demo"
    t4 = now - timedelta(days=3)
    id4 = await mk_baja(dom4, "BCI (Demo)", f"privacidad@{dom4}", 1, t4, 15)

    # ── Escenario 5: CUMPLIDA por inactividad (sin acuse formal) ─────────────
    # Caso 3 del flujo: empresa nunca respondió pero dejó de enviar → cierre
    dom5 = "entel.cl-demo"
    t5 = now - timedelta(days=50)
    id5 = await mk_baja(dom5, "Entel (Demo)", f"privacidad@{dom5}", 1, t5, 15)
    await update_baja_estado(id5, "CUMPLIDA")  # sin fecha_acuse = cierre por inactividad

    # ── Escenario 6: Empresa respondió pero reincidió → N°2 ──────────────────
    # Caso 5 del flujo: confirmó baja formalmente, pero siguieron llegando correos
    dom6 = "santander.cl-demo"
    t6 = now - timedelta(days=45)
    id6 = await mk_baja(dom6, "Santander (Demo)", f"privacidad@{dom6}", 1, t6, 15)
    # Empresa acusó recibo formal a los 8 días
    await update_baja_estado(id6, "REINCIDENTE", fecha_acuse=iso(t6 + timedelta(days=8)))
    await send_respuesta_empresa("Santander (Demo)", dom6, holder, iso(t6 + timedelta(days=8)))
    # Pero luego igual llegaron campañas
    v6_list = [
        ("Tu resumen de cuenta — julio", timedelta(days=20)),
        ("Ofertas exclusivas Santander Select", timedelta(days=28)),
        ("Cuotas sin interés este fin de semana", timedelta(days=35)),
    ]
    for subj, delta in v6_list:
        await save_baja_violation(
            baja_id=id6,
            message_id=f"demo-santander-{_uuid.uuid4()}",
            received_at=iso(t6 + delta),
            subject=subj,
            from_address=f"noreply@{dom6}",
            snippet="Esta comunicación fue enviada porque tienes una cuenta activa con Santander.",
        )
        await send_reincidencia_email(
            "Santander (Demo)", dom6, holder, subj, f"noreply@{dom6}",
            "Esta comunicación fue enviada porque tienes una cuenta activa con Santander.",
        )
    # N°2 automática enviada
    t6b = now - timedelta(days=8)
    id6b = await mk_baja(dom6, "Santander (Demo)", f"privacidad@{dom6}", 2, t6b, 5, anterior_id=id6)

    # ── Escenario 7: Nunca responde, sigue enviando → N°1, N°2, N°3 ──────────
    # Caso 4: reincidencia persistente sin respuesta, 3 solicitudes automáticas
    # Flujo: [N°1] → [correo] → [N°2] → [correo×2] → [N°3] → [en espera]
    dom7 = "walmart.cl-demo"
    t7 = now - timedelta(days=70)
    id7 = await mk_baja(dom7, "Walmart (Demo)", f"privacidad@{dom7}", 1, t7, 15)
    await save_baja_violation(
        baja_id=id7,
        message_id=f"demo-walmart-{_uuid.uuid4()}",
        received_at=iso(t7 + timedelta(days=20)),
        subject="¡Ofertas de la semana en Walmart!",
        from_address=f"ofertas@{dom7}",
        snippet="No te pierdas estas ofertas exclusivas preparadas especialmente para ti.",
    )
    await send_reincidencia_email(
        "Walmart (Demo)", dom7, holder,
        "¡Ofertas de la semana en Walmart!", f"ofertas@{dom7}",
        "No te pierdas estas ofertas exclusivas preparadas especialmente para ti.",
    )
    await update_baja_estado(id7, "REINCIDENTE")
    t7b = t7 + timedelta(days=22)
    id7b = await mk_baja(dom7, "Walmart (Demo)", f"privacidad@{dom7}", 2, t7b, 5, anterior_id=id7)
    v7b_list = [
        ("Cyber lunes — descuentos hasta 50%", timedelta(days=8)),
        ("Tu carrito te espera", timedelta(days=14)),
    ]
    for subj, delta in v7b_list:
        await save_baja_violation(
            baja_id=id7b,
            message_id=f"demo-walmart-{_uuid.uuid4()}",
            received_at=iso(t7b + delta),
            subject=subj,
            from_address=f"ofertas@{dom7}",
            snippet="Aprovecha estas ofertas por tiempo limitado. Precios válidos hasta agotar stock.",
        )
        await send_reincidencia_email(
            "Walmart (Demo)", dom7, holder, subj, f"ofertas@{dom7}",
            "Aprovecha estas ofertas por tiempo limitado. Precios válidos hasta agotar stock.",
        )
    await update_baja_estado(id7b, "REINCIDENTE")
    t7c = now - timedelta(days=10)
    id7c = await mk_baja(dom7, "Walmart (Demo)", f"privacidad@{dom7}", 3, t7c, 5, anterior_id=id7b)

    # ── Escenario 8: Ciclo completo exitoso tras escalación ───────────────────
    # N°1 → 3 reincidencias → N°2 → empresa finalmente cumple con acuse formal
    # Flujo: [N°1] → [correo×3] → [N°2] → [Empresa respondió] → [Empresa cumplió]
    dom8 = "lider.cl-demo"
    t8 = now - timedelta(days=55)
    id8 = await mk_baja(dom8, "Líder (Demo)", f"privacidad@{dom8}", 1, t8, 15)
    v8_list = [
        ("Ofertas frescas de la semana", timedelta(days=18)),
        ("¡Tu descuento de cumpleaños!", timedelta(days=23)),
        ("Novedades en electro Líder", timedelta(days=27)),
    ]
    for subj, delta in v8_list:
        await save_baja_violation(
            baja_id=id8,
            message_id=f"demo-lider-{_uuid.uuid4()}",
            received_at=iso(t8 + delta),
            subject=subj,
            from_address=f"newsletter@{dom8}",
            snippet="Descubre las mejores ofertas seleccionadas para ti esta semana en Lider.cl.",
        )
        await send_reincidencia_email(
            "Líder (Demo)", dom8, holder, subj, f"newsletter@{dom8}",
            "Descubre las mejores ofertas seleccionadas para ti esta semana en Lider.cl.",
        )
    await update_baja_estado(id8, "REINCIDENTE")
    t8b = t8 + timedelta(days=30)
    id8b = await mk_baja(dom8, "Líder (Demo)", f"privacidad@{dom8}", 2, t8b, 5, anterior_id=id8)
    await update_baja_estado(id8b, "CUMPLIDA", fecha_acuse=iso(t8b + timedelta(days=3)))
    await send_respuesta_empresa("Líder (Demo)", dom8, holder, iso(t8b + timedelta(days=3)))

    # ── Escenario 9: Respuesta ambigua → seguimos monitoreando ───────────────
    # Empresa respondió (acuse) pero NO confirmó eliminación → estado sigue abierto
    # Flujo: [N°1] → [Empresa respondió] → [En espera]
    dom9 = "tricot.cl-demo"
    t9 = now - timedelta(days=10)
    id9 = await mk_baja(dom9, "Tricot (Demo)", f"privacidad@{dom9}", 1, t9, 15)
    # Acuse recibido (respondió) pero sin confirmar eliminación → SOLICITADA aún
    await update_baja_estado(id9, "SOLICITADA", fecha_acuse=iso(t9 + timedelta(days=2)))
    await send_respuesta_empresa("Tricot (Demo)", dom9, holder, iso(t9 + timedelta(days=2)))

    # ── Escenario 10: N°2 también vencida (empresa jamás responde) ────────────
    # Ninguna solicitud fue atendida, ambos plazos expirados
    # Flujo: [N°1] → [correo] → [N°2 vencida]
    dom10 = "corona.cl-demo"
    t10 = now - timedelta(days=50)
    id10 = await mk_baja(dom10, "Corona (Demo)", f"privacidad@{dom10}", 1, t10, 15)
    await save_baja_violation(
        baja_id=id10,
        message_id=f"demo-corona-{_uuid.uuid4()}",
        received_at=iso(t10 + timedelta(days=20)),
        subject="Nuevas colecciones otoño-invierno",
        from_address=f"marketing@{dom10}",
        snippet="Descubre nuestra nueva colección. Envío gratis sobre $30.000.",
    )
    await send_reincidencia_email(
        "Corona (Demo)", dom10, holder,
        "Nuevas colecciones otoño-invierno", f"marketing@{dom10}",
        "Descubre nuestra nueva colección. Envío gratis sobre $30.000.",
    )
    await update_baja_estado(id10, "REINCIDENTE")
    t10b = t10 + timedelta(days=22)
    id10b = await mk_baja(dom10, "Corona (Demo)", f"privacidad@{dom10}", 2, t10b, 5, anterior_id=id10)
    # N°2 con plazo vencido hace +20 días (calculado dinámicamente)

    # ── Escenario 11: Reapertura — cumplió y luego volvió a reicidir ──────────
    # Empresa respondió formalmente, largo silencio, luego meses después reincide
    # Flujo: [N°1] → [Empresa respondió] → [correo post-baja] → [N°2] → [en espera]
    dom11 = "hites.cl-demo"
    t11 = now - timedelta(days=120)
    id11 = await mk_baja(dom11, "Hites (Demo)", f"privacidad@{dom11}", 1, t11, 15)
    await update_baja_estado(id11, "REINCIDENTE", fecha_acuse=iso(t11 + timedelta(days=10)))
    await send_respuesta_empresa("Hites (Demo)", dom11, holder, iso(t11 + timedelta(days=10)))
    # Largo silencio de ~2 meses, luego reaparece
    await save_baja_violation(
        baja_id=id11,
        message_id=f"demo-hites-{_uuid.uuid4()}",
        received_at=iso(t11 + timedelta(days=90)),
        subject="¡Vuelven los precios bajos de siempre!",
        from_address=f"promo@{dom11}",
        snippet="Han pasado meses desde tu última visita. Te esperamos con precios especiales.",
    )
    await send_reincidencia_email(
        "Hites (Demo)", dom11, holder,
        "¡Vuelven los precios bajos de siempre!", f"promo@{dom11}",
        "Han pasado meses desde tu última visita. Te esperamos con precios especiales.",
    )
    t11b = now - timedelta(days=28)
    id11b = await mk_baja(dom11, "Hites (Demo)", f"privacidad@{dom11}", 2, t11b, 5, anterior_id=id11)

    # ── Escenario 12: Acumulación intensa de reincidencias → N°2 ─────────────
    # Empresa ignora y sigue enviando muchos correos → flujo con 5 violations visibles
    # Flujo: [N°1] → [correo×5] → [N°2] → [en espera]
    dom12 = "jumbo.cl-demo"
    t12 = now - timedelta(days=40)
    id12 = await mk_baja(dom12, "Jumbo (Demo)", f"privacidad@{dom12}", 1, t12, 15)
    v12_list = [
        ("Club Jumbo — beneficios de esta semana", f"club@{dom12}",
         "Como socio Club Jumbo tienes beneficios exclusivos esperándote.", timedelta(days=17)),
        ("Recarga tu Tarjeta Jumbo y gana puntos", f"tarjeta@{dom12}",
         "Recarga ahora y duplica tus puntos en todas tus compras.", timedelta(days=19)),
        ("Cyber especial — 40% en electro", f"cyber@{dom12}",
         "Solo por hoy: descuentos de hasta 40% en línea blanca y electrónica.", timedelta(days=22)),
        ("Tu resumen de puntos del mes", f"club@{dom12}",
         "Tienes 1.240 puntos acumulados. ¡Canjéalos antes de que venzan!", timedelta(days=25)),
        ("Ofertas frescas: verduras y frutas de temporada", f"frescos@{dom12}",
         "Frutas y verduras seleccionadas directo del campo a tu mesa.", timedelta(days=28)),
    ]
    for subj, from_addr, snippet_txt, delta in v12_list:
        await save_baja_violation(
            baja_id=id12,
            message_id=f"demo-jumbo-{_uuid.uuid4()}",
            received_at=iso(t12 + delta),
            subject=subj,
            from_address=from_addr,
            snippet=snippet_txt,
        )
        await send_reincidencia_email(
            "Jumbo (Demo)", dom12, holder, subj, from_addr, snippet_txt,
        )
    await update_baja_estado(id12, "REINCIDENTE")
    t12b = now - timedelta(days=10)
    id12b = await mk_baja(dom12, "Jumbo (Demo)", f"privacidad@{dom12}", 2, t12b, 5, anterior_id=id12)

    return {
        "ok": True,
        "escenarios": [
            {"empresa": "Ripley",    "flujo": "N°1 → empresa respondió → cumplió",                      "id": id1},
            {"empresa": "Falabella", "flujo": "N°1 → correo×2 → N°2 en espera",                         "ids": [id2, id2b]},
            {"empresa": "Paris",     "flujo": "N°1 → plazo vencido sin respuesta",                       "id": id3},
            {"empresa": "BCI",       "flujo": "N°1 → en espera (reciente)",                              "id": id4},
            {"empresa": "Entel",     "flujo": "N°1 → cierre por inactividad (sin acuse)",                "id": id5},
            {"empresa": "Santander", "flujo": "N°1 → respondió → correo×3 → N°2 en espera",             "ids": [id6, id6b]},
            {"empresa": "Walmart",   "flujo": "N°1 → correo → N°2 → correo×2 → N°3 en espera",          "ids": [id7, id7b, id7c]},
            {"empresa": "Lider",     "flujo": "N°1 → correo×3 → N°2 → respondió → cumplió",             "ids": [id8, id8b]},
            {"empresa": "Tricot",    "flujo": "N°1 → respondió (ambiguo) → en espera",                  "id": id9},
            {"empresa": "Corona",    "flujo": "N°1 → correo → N°2 vencida (ninguna atendida)",          "ids": [id10, id10b]},
            {"empresa": "Hites",     "flujo": "N°1 → respondió → silencio → reapertura → N°2",          "ids": [id11, id11b]},
            {"empresa": "Jumbo",     "flujo": "N°1 → correo×5 → N°2 en espera",                        "ids": [id12, id12b]},
        ],
    }


@app.post("/api/baja/poc/iniciar")
async def poc_iniciar_baja(payload: dict):
    """
    POC paso 1: genera y envía por SMTP la solicitud de baja N°1 a tu propio
    correo (para que veas exactamente cómo llega), y la guarda en la DB.

    Body JSON: { "holder_email": "tu@email.com" }
    """
    holder_email: str = (payload.get("holder_email") or "").strip()
    if not holder_email:
        raise HTTPException(status_code=400, detail="holder_email requerido")
    if not is_smtp_configured():
        raise HTTPException(status_code=503, detail="SMTP no configurado en .env")

    # Verificar si ya existe una baja previa de POC no finalizada
    todas = await list_baja_requests()
    previas = [b for b in todas if b["dominio"] == _POC_DOMINIO and b["estado"] not in ("DENUNCIADA",)]
    numero = (previas[0]["numero_solicitud"] + 1) if previas else 1
    baja_anterior_id = previas[0]["id"] if previas else None

    historial_fechas: list[str] = []
    violations_for_text: list[dict] = []
    if baja_anterior_id:
        history = await get_baja_history(baja_anterior_id)
        historial_fechas = [h["fecha_solicitud"][:10] for h in history if h.get("fecha_solicitud")]
        prev = await get_baja_request(baja_anterior_id)
        if prev:
            violations_for_text = prev.get("violations", [])

    subject = build_baja_subject(numero, _POC_EMPRESA)
    text_body, html_body = build_baja_texto(
        numero=numero,
        empresa=_POC_EMPRESA,
        holder_email=holder_email,
        historial_fechas=historial_fechas,
        violations=violations_for_text,
    )

    # Enviar a la dirección del propio usuario para que vea el correo real
    import asyncio as _asyncio
    loop = _asyncio.get_event_loop()
    try:
        await loop.run_in_executor(None, _send_smtp, holder_email, subject, html_body, text_body)
    except Exception as exc:
        logger.error("[POC] Error SMTP: %s", exc, exc_info=True)
        raise HTTPException(status_code=502, detail=f"Error enviando por SMTP: {exc}")

    now_dt = datetime.now(timezone.utc)
    fecha_limite = compute_fecha_limite(now_dt, numero)

    import json as _json
    baja_id = await save_baja_request(
        dominio=_POC_DOMINIO,
        empresa=_POC_EMPRESA,
        numero_solicitud=numero,
        fecha_limite=fecha_limite,
        destinatario=_POC_CONTACTO,
        holder_email=holder_email,
        evidencia_json=_json.dumps({"poc": True}),
        baja_anterior_id=baja_anterior_id,
    )

    baja = await get_baja_request(baja_id)
    return {
        "ok": True,
        "baja_id": baja_id,
        "numero_solicitud": numero,
        "email_enviado_a": holder_email,
        "asunto": subject,
        "mensaje": (
            f"✅ Solicitud de baja N°{numero} enviada a {holder_email}. "
            "Revisa tu bandeja de entrada para ver el correo real. "
            "Luego llama a /api/baja/poc/simular-reincidencia para simular que la empresa reincidió."
        ),
        "baja": baja,
    }


@app.post("/api/baja/poc/simular-reincidencia")
async def poc_simular_reincidencia(payload: dict):
    """
    POC paso 2: simula que la empresa ignoró la baja y volvió a enviar un
    correo de marketing.  Inserta la violación en la DB, actualiza el estado a
    REINCIDENTE y envía la solicitud escalada N°2 con la evidencia adjunta.

    Body JSON: { "baja_id": "uuid-de-la-baja-anterior" }
    """
    baja_id: str = (payload.get("baja_id") or "").strip()
    if not baja_id:
        raise HTTPException(status_code=400, detail="baja_id requerido")
    if not is_smtp_configured():
        raise HTTPException(status_code=503, detail="SMTP no configurado en .env")

    baja = await get_baja_request(baja_id)
    if not baja:
        raise HTTPException(status_code=404, detail="Solicitud de baja no encontrada")
    if baja["dominio"] != _POC_DOMINIO:
        raise HTTPException(status_code=400, detail="Este endpoint solo funciona para bajas POC")

    # Insertar violación simulada
    import uuid as _uuid
    fake_message_id = f"poc-violation-{_uuid.uuid4()}"
    received_at = datetime.now(timezone.utc).isoformat()

    await save_baja_violation(
        baja_id=baja_id,
        message_id=fake_message_id,
        received_at=received_at,
        subject="🎉 ¡Oferta exclusiva de Empresa POC! ¡No te la pierdas!",
        from_address=f"marketing@{_POC_DOMINIO}",
        snippet=(
            "Hola, tenemos una oferta increíble para ti. "
            "Solo por hoy: 50% de descuento en todos nuestros productos. "
            "No te quedes sin tu cupón exclusivo."
        ),
    )
    await update_baja_estado(baja_id, "REINCIDENTE")

    # Cargar baja actualizada con la violación
    baja_actualizada = await get_baja_request(baja_id)
    violations = baja_actualizada.get("violations", [])

    # Construir baja N°2
    numero = baja["numero_solicitud"] + 1
    history = await get_baja_history(baja_id)
    historial_fechas = [h["fecha_solicitud"][:10] for h in history if h.get("fecha_solicitud")]
    holder_email = baja["holder_email"]

    subject_n2 = build_baja_subject(numero, _POC_EMPRESA)
    text_n2, html_n2 = build_baja_texto(
        numero=numero,
        empresa=_POC_EMPRESA,
        holder_email=holder_email,
        historial_fechas=historial_fechas,
        violations=violations,
    )

    import asyncio as _asyncio
    loop = _asyncio.get_event_loop()
    try:
        await loop.run_in_executor(None, _send_smtp, holder_email, subject_n2, html_n2, text_n2)
    except Exception as exc:
        logger.error("[POC] Error SMTP N°2: %s", exc, exc_info=True)
        raise HTTPException(status_code=502, detail=f"Error enviando por SMTP: {exc}")

    return {
        "ok": True,
        "mensaje": (
            f"✅ Violación simulada insertada. Baja N°{numero} enviada a {holder_email}. "
            "Revisa tu correo para ver el email escalado con la evidencia de reincidencia."
        ),
        "violacion_simulada": {
            "message_id": fake_message_id,
            "subject": "🎉 ¡Oferta exclusiva de Empresa POC! ¡No te la pierdas!",
            "from_address": f"marketing@{_POC_DOMINIO}",
            "received_at": received_at,
        },
        "baja_anterior": baja_actualizada,
        "baja_n2_asunto": subject_n2,
    }


# ── Historial de navegación (Chrome local) ───────────────────────────────────
@app.get("/api/local/system-info")
async def system_info():
    """Reporta el sistema operativo detectado y qué navegadores están realmente
    disponibles en este equipo (cuyo archivo de historial existe). Permite que la
    interfaz se adapte al SO y ofrezca solo los navegadores instalados."""
    from core.browser_history._readers import OS_NAME, get_reader, REGISTRY as _REG
    os_label = {"Darwin": "macOS", "Windows": "Windows", "Linux": "Linux"}.get(OS_NAME, OS_NAME)
    available = []
    for slug in _REG:
        # Safari en macOS siempre está instalado, pero su historial puede estar
        # protegido por TCC y .exists() devolver False sin Acceso completo al
        # disco. Se ofrece igual; si falta el permiso, el análisis lo indicará.
        if slug == "safari":
            if OS_NAME == "Darwin":
                available.append(slug)
            continue
        try:
            if get_reader(slug).history_db_path.exists():
                available.append(slug)
        except Exception:
            pass
    return {"os": OS_NAME, "os_label": os_label, "available_browsers": available}


@app.get("/api/system-info/debug")
async def system_info_debug():
    """Diagnóstico de detección de navegadores: muestra la ruta que revisa cada
    uno y si existe. Abrir http://localhost:8787/api/system-info/debug en el
    navegador y compartir el JSON. Si devuelve 404, el servidor corre código
    viejo (hay que reiniciar start.bat)."""
    import os as _os
    from pathlib import Path as _Path
    from core.browser_history._readers import OS_NAME, get_reader, REGISTRY as _REG

    browsers: dict[str, dict] = {}
    for slug in _REG:
        try:
            reader = get_reader(slug)
            path = reader.history_db_path
            browsers[slug] = {"path": str(path), "exists": path.exists()}
        except Exception as exc:
            browsers[slug] = {"path": f"error: {exc}", "exists": False}

    # Detalle de Opera GX: candidatos probados + carpetas reales bajo "Opera Software"
    opera: dict = {}
    try:
        from core.browser_history._readers import OperaGXHistoryReader
        og = OperaGXHistoryReader()
        opera["candidates"] = [{"path": str(p), "exists": p.exists()} for p in og._candidates()]
    except Exception as exc:
        opera["candidates_error"] = str(exc)

    opera_dirs: list[str] = []
    if OS_NAME == "Windows":
        for env in ("APPDATA", "LOCALAPPDATA"):
            root = _os.environ.get(env)
            if not root:
                continue
            od = _Path(root) / "Opera Software"
            if od.is_dir():
                try:
                    opera_dirs += [str(s) for s in od.iterdir() if s.is_dir()]
                except OSError:
                    pass
    opera["opera_software_dirs"] = opera_dirs

    return {"os": OS_NAME, "browsers": browsers, "opera_gx": opera}


@app.get("/api/local/browser-history")
async def browser_history_analysis(
    browser: str = Query(default="chrome", description=f"Navegador a analizar. Opciones: {', '.join(['chrome', 'brave', 'edge', 'firefox', 'chrome-canary'])}"),
    limit:   int  = Query(default=5000, le=20000, description="Máximo de URLs a leer del historial"),
):
    """
    Lee el historial del navegador local y clasifica los dominios por empresa,
    actividad detectada (login, compra, perfil) y riesgo de retención de datos.

    El historial nunca sale del equipo — el análisis es 100% local.
    El SQLite del navegador se copia a /tmp antes de leerlo para evitar bloqueos.
    """
    if browser not in BROWSER_REGISTRY:
        valid = ", ".join(BROWSER_REGISTRY.keys())
        raise HTTPException(status_code=400, detail=f"Navegador '{browser}' no soportado. Opciones: {valid}")
    try:
        result = await analyze_browser_history_async(browser=browser, limit=limit)
    except FileNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc))
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc))
    except Exception as exc:
        logger.error(f"Error analizando historial de {browser}: {exc}", exc_info=True)
        raise HTTPException(status_code=500, detail=f"No se pudo leer el historial: {exc}")

    companies = result["companies"]
    return {
        "total_companies":   len(companies),
        "login_count":       sum(1 for c in companies if c["login_detected"]),
        "chilean_count":     sum(1 for c in companies if c["is_chilean"]),
        "high_risk_count":   sum(1 for c in companies if c["risk_level"] == "high"),
        "data_broker_count": sum(1 for c in companies if c["sender_type"] == "data_broker"),
        "confirmed_count":   sum(1 for c in companies if c.get("confirmed_data")),
        "companies":         companies,
        "autofill_summary":  result["autofill_summary"],
    }


# ── Cruce de filtraciones ─────────────────────────────────────────────────────

class BreachCrossrefRequest(BaseModel):
    browser:      str       = "chrome"
    limit:        int       = 5000
    email_domains: list[str] = []   # dominios del análisis de correo (opcional)
    max_hibp_domains: int   = 9999  # consultar todos los dominios en HIBP
    # Perfiles enriquecidos del análisis de email:
    # [{primary_domain, personal_data_types, sender_type, sample_subjects}]
    email_senders: list[dict] = []


@app.post("/api/local/breach-crossref")
async def breach_crossref_endpoint(req: BreachCrossrefRequest):
    """
    Cruza las empresas del historial del navegador con:
      1. Filtraciones HIBP por dominio (endpoint público, sin API key)
      2. Dominios del análisis de correo (si el frontend los envía)

    El historial nunca sale del equipo. Solo los nombres de dominio
    se envían a HIBP para verificar si ese dominio tuvo una filtración.

    Composite risk:
      critical = breach + (in_email | browser_risk=high)
      high     = breach | (in_email + browser_risk=high)
      medium   = in_email | browser_risk=high
      low      = resto
    """
    if req.browser not in BROWSER_REGISTRY:
        valid = ", ".join(BROWSER_REGISTRY.keys())
        raise HTTPException(status_code=400, detail=f"Navegador '{req.browser}' no soportado. Opciones: {valid}")

    # 1. Correr análisis de historial
    try:
        history_result = await analyze_browser_history_async(browser=req.browser, limit=req.limit)
    except FileNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc))
    except Exception as exc:
        logger.error(f"[breach-crossref] Error analizando historial: {exc}", exc_info=True)
        raise HTTPException(status_code=500, detail=f"No se pudo leer el historial: {exc}")

    companies = history_result["companies"]

    # 2. Cruzar con HIBP y dominios de correo
    try:
        enriched = await run_breach_crossref(
            browser_companies=companies,
            email_domains=req.email_domains or None,
            email_senders=req.email_senders or None,
            max_domains=req.max_hibp_domains,
        )
    except Exception as exc:
        logger.error(f"[breach-crossref] Error en cruce HIBP: {exc}", exc_info=True)
        raise HTTPException(status_code=500, detail=f"Error consultando filtraciones: {exc}")

    # 3. Estadísticas de resumen
    critical_count = sum(1 for c in enriched if c["composite_risk"] == "critical")
    breach_count   = sum(1 for c in enriched if c["has_breach"])
    in_email_count = sum(1 for c in enriched if c["also_in_email"])
    hibp_checked   = sum(1 for c in enriched if c["hibp_checked"])

    return {
        "total_companies":  len(enriched),
        "critical_count":   critical_count,
        "breach_count":     breach_count,
        "in_email_count":   in_email_count,
        "hibp_checked":     hibp_checked,
        "email_domains_received": len(req.email_domains),
        "companies":        enriched,
        "autofill_summary": history_result["autofill_summary"],
    }


# ── Scraper de incidentes chilenos ────────────────────────────────────────────

@app.post("/api/local/breach-scraper/run")
async def breach_scraper_run(max_articles: int = Query(default=30, le=60)):
    """
    Lanza el scraper automatizado de incidentes chilenos.
    Usa Brave Search para encontrar noticias + Gemini para extraer datos.
    Persiste en server/data/cl_incidents.json.

    Requiere BRAVE_SEARCH_API_KEY y GEMINI_API_KEY en .env.
    Si alguna falta, esa etapa se omite sin fallar.
    Tiempo estimado: 30-90 segundos según artículos encontrados.
    """
    try:
        result = await run_breach_scraper(max_articles=max_articles)
        return {"ok": True, **result, "stats": scraper_stats()}
    except Exception as exc:
        logger.error("[breach-scraper] Error en run: %s", exc, exc_info=True)
        raise HTTPException(status_code=500, detail=str(exc))


@app.get("/api/local/breach-scraper/incidents")
async def breach_scraper_incidents(confidence: str = Query(default="medium")):
    """Lista todos los incidentes scrapeados con confianza >= {confidence}."""
    return {
        "incidents": load_incidents(min_confidence=confidence),
        "stats":     scraper_stats(),
    }


@app.get("/api/local/breach-scraper/stats")
async def breach_scraper_stats_endpoint():
    """Estadísticas del store de incidentes."""
    return scraper_stats()


class HibpCheckRequest(BaseModel):
    domains: list[str] = []


@app.post("/api/local/hibp-check")
async def hibp_check_endpoint(req: HibpCheckRequest):
    """Consulta HIBP por una lista de dominios (solo por dominio, sin datos del
    usuario). Permite que la vista consolidada muestre el estado de filtración
    sin pasar por el cruce completo."""
    results = await check_domains_hibp(req.domains[:150])
    return {"results": results}


# ── Historial ─────────────────────────────────────────────────────────────────
@app.get("/api/searches")
async def get_searches(limit: int = Query(default=50, le=200)):
    """
    Lista el historial de búsquedas (metadatos, sin el JSON completo).
    Reemplaza mockSearches del frontend.
    """
    return await list_searches(limit=limit)


@app.get("/api/searches/{search_id}")
async def get_search_detail(
    search_id: str = Path(..., description="UUID de la búsqueda"),
):
    """Detalle completo de una búsqueda guardada."""
    data = await get_search(search_id)
    if not data:
        raise HTTPException(status_code=404, detail="Búsqueda no encontrada")
    return data


@app.delete("/api/searches/{search_id}")
async def remove_search(
    search_id: str = Path(..., description="UUID de la búsqueda"),
):
    """Elimina una búsqueda del historial."""
    deleted = await delete_search(search_id)
    if not deleted:
        raise HTTPException(status_code=404, detail="Búsqueda no encontrada")
    return {"deleted": search_id}


# ── Estado de módulos ─────────────────────────────────────────────────────────
@app.get("/api/modules")
async def list_modules():
    from config import HIBP_API_KEY, BRAVE_SEARCH_API_KEY
    return {
        "modules": [
            {"name": "nryf",           "description": "NombreRutYFirma.com",    "requires": [],             "status": "active"},
            {"name": "servel",         "description": "Padrón Electoral",        "requires": ["rut_mejora"], "status": "active"},
            {"name": "sii",            "description": "Estado Tributario SII",   "requires": ["rut"],        "status": "active"},
            {"name": "empresas",       "description": "Registro de Empresas",    "requires": [],             "status": "active"},
            {"name": "pjud",           "description": "Poder Judicial",          "requires": [],             "status": "active"},
            {"name": "diario_oficial", "description": "Diario Oficial de Chile", "requires": [],             "status": "active"},
            {
                "name": "emails_publicos",
                "description": "Busqueda de emails publicos",
                "requires": ["BRAVE_SEARCH_API_KEY"],
                "status": "active" if BRAVE_SEARCH_API_KEY else "needs_config",
            },
            {
                "name": "instituciones_publicas",
                "description": "Instituciones asociadas via LinkedIn y web",
                "requires": ["BRAVE_SEARCH_API_KEY"],
                "status": "active" if BRAVE_SEARCH_API_KEY else "needs_config",
            },
            {
                "name":        "hibp",
                "description": "HaveIBeenPwned — Filtraciones",
                "requires":    ["HIBP_API_KEY"],
                "status":      "active" if HIBP_API_KEY else "needs_config",
            },
        ]
    }


# ── Static frontend (production / standalone build) ──────────────────────────
# When STATIC_DIST_PATH is set (by the launcher), FastAPI serves the React app.
# In development this block is skipped — Vite's dev server handles the frontend.
_dist_path_str = os.environ.get("STATIC_DIST_PATH", "")
if not _dist_path_str:
    # Fallback: check for a dist/ folder next to this file (manual build)
    _candidate = FilePath(__file__).parent.parent / "dist"
    if _candidate.is_dir():
        _dist_path_str = str(_candidate)

if _dist_path_str:
    _dist = FilePath(_dist_path_str)
    _assets = _dist / "assets"
    if _assets.is_dir():
        app.mount("/assets", StaticFiles(directory=str(_assets)), name="assets")

    @app.get("/{full_path:path}", include_in_schema=False)
    async def _serve_spa(full_path: str) -> FileResponse:
        # Let actual API and health routes through (they're registered earlier)
        target = _dist / full_path
        if target.is_file():
            return FileResponse(str(target))
        return FileResponse(str(_dist / "index.html"))


# ── Dev runner ────────────────────────────────────────────────────────────────
if __name__ == "__main__":
    uvicorn.run(
        "main:app",
        host="0.0.0.0",
        port=8000,
        reload=DEBUG,
        log_level="debug" if DEBUG else "info",
    )
