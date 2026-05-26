"""
core/breach_scraper — Scraper automatizado de incidentes de breach chilenos.

API pública:
  run_scraper(max_articles)  → dict con stats del scrape
  load_incidents()           → list[dict] de incidentes verificados
  get_incidents_by_domain(d) → list[dict] para un dominio específico
  scraper_stats()            → dict con totales y última ejecución

Flujo:
  1. Brave Search → URLs de artículos sobre breaches en Chile
  2. Fetch del texto de cada artículo
  3. Gemini extrae datos estructurados (empresa, fecha, datos, confianza)
  4. Filtra: solo is_chile_related=True y confidence != "low"
  5. Upsert en server/data/cl_incidents.json (deduplicado por domain+fecha)

Requisitos:
  - GEMINI_API_KEY en .env para la extracción con Gemini
  - DuckDuckGo para búsqueda: sin API key, completamente gratis

Si GEMINI_API_KEY falta, la extracción se omite sin fallar.
"""
from __future__ import annotations

import asyncio
import logging

import httpx

from ._search import search_breach_urls
from ._fetch  import fetch_article_text
from ._extract import extract_incident
from ._store  import load_incidents, get_by_domain, upsert_incident, stats

logger = logging.getLogger(__name__)

__all__ = [
    "run_scraper",
    "load_incidents",
    "get_incidents_by_domain",
    "scraper_stats",
]


def get_incidents_by_domain(domain: str) -> list[dict]:
    return get_by_domain(domain)


def scraper_stats() -> dict:
    return stats()


async def run_scraper(max_articles: int = 30) -> dict:
    """
    Ejecuta el pipeline completo de scraping.

    Args:
        max_articles: máximo de artículos a procesar (limita tiempo de ejecución)

    Returns:
        {
          urls_found:    int,
          articles_processed: int,
          incidents_found:    int,
          incidents_new:      int,
          errors:             int,
        }
    """
    result = {
        "urls_found":          0,
        "articles_processed":  0,
        "incidents_found":     0,
        "incidents_new":       0,
        "errors":              0,
    }

    async with httpx.AsyncClient() as client:

        # ── Etapa 1: Búsqueda (DuckDuckGo — sin API key) ─────────────────────
        urls = await search_breach_urls()
        result["urls_found"] = len(urls)

        if not urls:
            logger.warning("[breach-scraper] No se encontraron URLs — DuckDuckGo no retornó resultados")
            return result

        # Tomar los más relevantes (high confidence primero, ya vienen ordenados)
        urls_to_process = urls[:max_articles]

        # ── Etapas 2+3: Fetch + Extract (con semáforos para no saturar) ─────
        # fetch_sem: hasta 5 fetches paralelos (I/O bound, sin problema)
        # gemini_sem: UNA sola llamada a Gemini a la vez para respetar los 10 RPM
        fetch_sem  = asyncio.Semaphore(5)
        gemini_sem = asyncio.Semaphore(1)  # creado aquí = dentro del event loop activo

        async def _process(url_info: dict) -> None:
            async with fetch_sem:
                url        = url_info["url"]
                confidence = url_info["source_confidence"]

                # Fetch
                text = await fetch_article_text(client, url)
                if not text:
                    result["errors"] += 1
                    return

                result["articles_processed"] += 1

                # Extract (pasa el semáforo de Gemini para serializar las llamadas)
                incident = await extract_incident(client, text, url, confidence, gemini_sem)
                if not incident:
                    return

                result["incidents_found"] += 1

                # Store
                was_new = upsert_incident(incident)
                if was_new:
                    result["incidents_new"] += 1
                    logger.info(
                        "[breach-scraper] Nuevo incidente: %s (%s) confianza=%s",
                        incident.get("company_name"),
                        incident.get("domain"),
                        incident.get("confidence"),
                    )

        await asyncio.gather(*[_process(u) for u in urls_to_process])

    logger.info(
        "[breach-scraper] Completado: %d URLs → %d artículos → %d incidentes (%d nuevos)",
        result["urls_found"], result["articles_processed"],
        result["incidents_found"], result["incidents_new"],
    )
    return result
