"""
_search.py — Búsqueda de noticias de breaches chilenos via DuckDuckGo.

Sin API key. Sin cuenta. Sin tarjeta de crédito.

Problemas conocidos con DDG scraping:
  - Bloquea con 403 si se hacen muchas queries seguidas (rate limit agresivo)
  - El modo news() es más sensible que text()
  - La opción timelimit="y" no es válida para news() — solo "d","w","m"

Estrategia anti-bloqueo:
  - Máximo 6 queries por ejecución (las más amplias y útiles)
  - Delay de 3s entre queries
  - Retry con backoff exponencial en 403
  - Mezcla text() + news() para reducir la detección de patrones
"""
from __future__ import annotations

import asyncio
import logging
import time

logger = logging.getLogger(__name__)

HIGH_CONFIDENCE_DOMAINS = {
    "bleepingcomputer.com",
    "securityaffairs.com",
    "csirt.gob.cl",
    "welivesecurity.com",
    "therecord.media",
    "darkreading.com",
    "krebsonsecurity.com",
    "helpnetsecurity.com",
}

MEDIUM_CONFIDENCE_DOMAINS = {
    "latercera.com",
    "df.cl",
    "emol.com",
    "biobiochile.cl",
    "cnnchile.com",
    "trendtic.cl",
    "muycomputerpro.com",
    "cybernews.com",
    "techcrunch.com",
    "wired.com",
}

# Queries específicas que generan resultados de fuentes de calidad.
# Estrategia: mezclar queries en inglés (más resultados en BleepingComputer/SecurityAffairs)
# con queries en español (más resultados en prensa chilena).
# Pocas queries (6) con delay entre ellas para evitar el 403.
_QUERIES = [
    # Inglés — apunta a BleepingComputer / SecurityAffairs / TheRecord
    # Nota: DDG no soporta bien 'site:A OR site:B', se usa sin site: operator
    ("text", "Chile data breach ransomware bleepingcomputer securityaffairs therecord"),
    ("text", "Chilean company data breach leaked customers 2024 2025 cybernews"),
    # Empresas chilenas específicas con términos de breach explícitos
    ("text", "Cencosud data breach leaked OR BancoEstado ransomware OR Falabella hack"),
    # Español — prensa chilena y regional
    ("news", "empresa chilena hackeo filtración datos clientes 2024 2025"),
    ("text", "Chile ciberataque datos filtrados empresa clientes RUT correos"),
    # CSIRT Chile — fuente oficial, máxima confianza
    ("text", "incidente ciberseguridad Chile CSIRT alerta empresa datos"),
]

_DELAY_BETWEEN_QUERIES = 3.0   # segundos — conservador para no ser bloqueado
_MAX_RETRIES           = 2
_RETRY_DELAY           = 8.0   # esperar 8s antes de reintentar tras 403

# Dominios a descartar: portales corporativos, wikis, redes sociales, etc.
_SKIP_DOMAINS = {
    "wikipedia.org", "en.m.wikipedia.org",
    "facebook.com", "twitter.com", "x.com", "instagram.com",
    "linkedin.com", "youtube.com", "reddit.com",
    "vk.com", "avito.ru",
    "amazon.com", "apple.com", "microsoft.com",
    # Sitios corporativos propios de empresas (sin noticias de breach)
    "cencosud.com", "tarjetacencosud.cl", "puntoscencosud.cl", "puntoscencosud.co",
    "falabella.com", "bancoestado.cl", "entel.cl",
}


def _is_skippable(url: str) -> bool:
    url_lower = url.lower()
    for skip in _SKIP_DOMAINS:
        if skip in url_lower:
            return True
    return False


def _source_confidence(url: str) -> str:
    url_lower = url.lower()
    for domain in HIGH_CONFIDENCE_DOMAINS:
        if domain in url_lower:
            return "high"
    for domain in MEDIUM_CONFIDENCE_DOMAINS:
        if domain in url_lower:
            return "medium"
    return "low"


def _run_query(ddgs, mode: str, query: str, max_results: int) -> list[dict]:
    """
    Ejecuta una sola query (text o news) con retry en 403.
    """
    for attempt in range(_MAX_RETRIES + 1):
        try:
            if mode == "news":
                items = ddgs.news(query, max_results=max_results, timelimit="m") or []
            else:
                items = ddgs.text(query, max_results=max_results, timelimit="y") or []
            return items
        except Exception as exc:
            msg = str(exc)
            if "403" in msg or "Ratelimit" in msg:
                if attempt < _MAX_RETRIES:
                    logger.warning(
                        "[breach-scraper] DDG rate limit en '%s' — esperando %.0fs (intento %d/%d)",
                        query[:50], _RETRY_DELAY, attempt + 1, _MAX_RETRIES,
                    )
                    time.sleep(_RETRY_DELAY)
                else:
                    logger.warning("[breach-scraper] DDG bloqueó '%s' tras %d intentos — saltando", query[:50], _MAX_RETRIES + 1)
                    return []
            else:
                logger.warning("[breach-scraper] DDG error en '%s': %s", query[:50], exc)
                return []
    return []


def _search_sync(max_per_query: int) -> list[dict]:
    """Sincrónico — se ejecuta en thread pool."""
    try:
        from ddgs import DDGS
    except ImportError:
        try:
            from duckduckgo_search import DDGS  # fallback versión antigua
        except ImportError:
            logger.error("[breach-scraper] Instala: pip install ddgs")
            return []

    seen_urls: set[str] = set()
    results:   list[dict] = []

    with DDGS() as ddgs:
        for i, (mode, query) in enumerate(_QUERIES):
            if i > 0:
                time.sleep(_DELAY_BETWEEN_QUERIES)

            items = _run_query(ddgs, mode, query, max_per_query)

            for item in items:
                url = item.get("url") or item.get("href", "")
                if not url or url in seen_urls:
                    continue
                if _is_skippable(url):
                    continue
                seen_urls.add(url)
                results.append({
                    "url":               url,
                    "title":             item.get("title", ""),
                    "description":       item.get("body") or item.get("snippet", ""),
                    "source_confidence": _source_confidence(url),
                    "query":             query,
                    "date":              item.get("date", ""),
                })

    # Ordenar: high → medium → low
    _order = {"high": 0, "medium": 1, "low": 2}
    results.sort(key=lambda r: _order.get(r["source_confidence"], 3))

    logger.info("[breach-scraper] DDG: %d URLs encontradas", len(results))
    return results


async def search_breach_urls(max_results_per_query: int = 6) -> list[dict]:
    """
    Busca noticias de breaches chilenos via DuckDuckGo.
    Sin API key requerida.
    """
    loop = asyncio.get_event_loop()
    return await loop.run_in_executor(None, _search_sync, max_results_per_query)
