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
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, HTMLResponse, RedirectResponse
from fastapi.staticfiles import StaticFiles

from config import APP_NAME, APP_VERSION, BAJA_REPORT_DESTINATION, DEBUG, CORS_ORIGINS
from core.email_identification import identify_email_footprint
from core.email_sender import is_smtp_configured, send_baja_report, send_baja_report_via_gmail_api
from core.gmail_oauth import (
    build_gmail_oauth_url,
    build_gmail_popup_error_html,
    build_gmail_popup_response_html,
    exchange_gmail_code,
    gmail_oauth_is_configured,
)
from core.orchestrator import run_search
from models.schemas import BajaReportRequest, EmailIdentificationRequest, EmailIdentificationResponse, OSINTResponse
from db import init_db, save_search, list_searches, get_search, delete_search

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


@app.post("/api/identification/email-footprint", response_model=EmailIdentificationResponse)
async def email_identification(request: EmailIdentificationRequest):
    """
    Fase 1: identificación por correo autorizado.
    Acepta mensajes manuales para pruebas y Gmail API con bearer token temporal.
    """
    try:
        return await identify_email_footprint(request)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc))
    except httpx.HTTPStatusError as exc:
        detail = exc.response.text[:500] if exc.response is not None else str(exc)
        raise HTTPException(status_code=502, detail=f"Proveedor de correo rechazó la solicitud: {detail}")
    except Exception as exc:
        logger.error(f"Error en identificación de email: {exc}", exc_info=True)
        raise HTTPException(status_code=500, detail="No se pudo completar la identificación por correo")


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
    Envía el informe de baja usando Gmail API (si el usuario tiene token)
    o SMTP como fallback. La prioridad es siempre Gmail API.
    """
    try:
        if request.access_token:
            from_addr = request.sender_email or request.holder_email
            destination = request.sender_email or BAJA_REPORT_DESTINATION or request.holder_email
            await send_baja_report_via_gmail_api(
                access_token=request.access_token,
                from_address=from_addr,
                destination=destination,
                sender=request.sender,
                holder_email=request.holder_email,
            )
            return {"sent": True, "destination": destination}

        if is_smtp_configured():
            await send_baja_report(
                destination=BAJA_REPORT_DESTINATION,
                sender=request.sender,
                holder_email=request.holder_email,
            )
            return {"sent": True, "destination": BAJA_REPORT_DESTINATION}

        raise HTTPException(
            status_code=503,
            detail="Conecta tu Gmail primero para poder enviar el informe.",
        )
    except HTTPException:
        raise
    except Exception as exc:
        logger.error("Error enviando informe de baja: %s", exc, exc_info=True)
        raise HTTPException(status_code=500, detail=f"No se pudo enviar el correo: {exc}")


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
