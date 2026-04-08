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
import sys
import time
from contextlib import asynccontextmanager
from typing import Optional

import uvicorn
import httpx
from fastapi import FastAPI, Query, HTTPException, Path
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import HTMLResponse, RedirectResponse

from config import APP_NAME, APP_VERSION, DEBUG, CORS_ORIGINS
from core.email_identification import identify_email_footprint
from core.gmail_oauth import (
    build_gmail_oauth_url,
    build_gmail_popup_error_html,
    build_gmail_popup_response_html,
    exchange_gmail_code,
    gmail_oauth_is_configured,
)
from core.orchestrator import run_search
from models.schemas import EmailIdentificationRequest, EmailIdentificationResponse, OSINTResponse
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


# ── Dev runner ────────────────────────────────────────────────────────────────
if __name__ == "__main__":
    uvicorn.run(
        "main:app",
        host="0.0.0.0",
        port=8000,
        reload=DEBUG,
        log_level="debug" if DEBUG else "info",
    )
