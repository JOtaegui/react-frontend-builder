"""
core/browser_history — Package de análisis de historial de navegación.

API pública:
  analyze_browser_history_async(browser, limit) → dict con companies + autofill_summary
  get_reader(browser)                            → BaseHistoryReader
  REGISTRY                                       → dict de lectores disponibles

Los consumidores (main.py, tests) solo importan desde aquí.

Módulos internos:
  _data.py      → KNOWN_COMPANIES, IGNORE_DOMAINS   (solo datos)
  _patterns.py  → patrones de actividad compilados  (solo regexes)
  _readers.py   → BaseHistoryReader + implementaciones por navegador
  _autofill.py  → lector de Chrome Web Data (autofill + perfiles de dirección)
  _pipeline.py  → orquestador de las 5 etapas de análisis
"""
from __future__ import annotations

import asyncio
import logging

from ._autofill import AutofillSnapshot, read_chrome_autofill
from ._login_data import LoginDataSnapshot, read_chrome_login_data
from ._readers import REGISTRY, BaseHistoryReader, get_reader
from ._pipeline import run_pipeline

logger = logging.getLogger(__name__)

__all__ = [
    "analyze_browser_history_async",
    "get_reader",
    "REGISTRY",
    "BaseHistoryReader",
]


def _run_full_analysis(reader: BaseHistoryReader, limit: int) -> dict:
    """
    Sincrónico — se ejecuta en thread pool.
    Lee historial + Login Data + autofill y devuelve resultado completo.
    """
    # Web Data y Login Data viven en la carpeta de perfil del navegador Chromium
    # seleccionado (None para Firefox/Safari → autofill/login no aplican).
    profile_dir = reader.chromium_profile_dir()

    try:
        autofill = read_chrome_autofill(profile_dir)
    except Exception as exc:
        logger.warning("[autofill] No se pudo leer Web Data: %s", exc)
        autofill = AutofillSnapshot(disponible=False)

    try:
        login_data = read_chrome_login_data(profile_dir)
    except Exception as exc:
        logger.warning("[login-data] No se pudo leer Login Data: %s", exc)
        login_data = LoginDataSnapshot(disponible=False)

    companies = run_pipeline(reader, limit, autofill, login_data)

    autofill_summary = {
        "disponible":        autofill.disponible,
        "emails":            autofill.emails,
        "nombres":           autofill.nombres,
        "telefonos":         autofill.telefonos,
        "direcciones":       autofill.direcciones,
        "ruts":              autofill.ruts,
        "patentes":          autofill.patentes,
        "usernames":         autofill.usernames,
        "login_data_domains": list(login_data.by_domain.keys()) if login_data.disponible else [],
    }

    return {"companies": companies, "autofill_summary": autofill_summary}


async def analyze_browser_history_async(
    browser: str = "chrome",
    limit: int = 5000,
) -> dict:
    """
    Punto de entrada async para el endpoint FastAPI.

    Returns:
        {
          companies:       lista de empresas clasificadas con confirmed_data,
          autofill_summary: resumen de datos personales en Chrome autofill
        }
    """
    reader = get_reader(browser)
    loop = asyncio.get_event_loop()
    return await loop.run_in_executor(None, _run_full_analysis, reader, limit)
