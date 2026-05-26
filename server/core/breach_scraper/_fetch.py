"""
_fetch.py — Descarga y limpia el texto de artículos de noticias.

Convierte HTML a texto plano legible, eliminando nav, footer, scripts, etc.
Retorna los primeros ~3000 caracteres (suficiente para que Gemini extraiga
los hechos relevantes sin exceder el contexto innecesariamente).
"""
from __future__ import annotations

import logging
import re
from typing import Optional

import httpx

logger = logging.getLogger(__name__)

_MAX_CHARS = 4000   # máximo de texto a pasar a Gemini por artículo
_TIMEOUT   = 12.0


async def fetch_article_text(client: httpx.AsyncClient, url: str) -> Optional[str]:
    """
    Descarga una URL y retorna el texto limpio del artículo.
    Retorna None si falla o si el contenido no es HTML.
    """
    try:
        resp = await client.get(
            url,
            headers={
                "User-Agent": (
                    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
                    "AppleWebKit/537.36 (KHTML, like Gecko) "
                    "Chrome/123.0.0.0 Safari/537.36"
                ),
                "Accept-Language": "es,en;q=0.9",
            },
            timeout=_TIMEOUT,
            follow_redirects=True,
        )
        if resp.status_code != 200:
            return None

        content_type = resp.headers.get("content-type", "")
        if "html" not in content_type and "text" not in content_type:
            return None

        return _clean_html(resp.text)

    except Exception as exc:
        logger.debug("[breach-scraper] fetch error %s: %s", url, exc)
        return None


def _clean_html(html: str) -> str:
    """
    Convierte HTML a texto plano simple.
    No usamos BeautifulSoup para evitar dependencia extra — regex básico
    es suficiente para extraer el texto del body.
    """
    # Eliminar scripts, styles, nav, footer, header
    html = re.sub(r"<(script|style|nav|footer|header|aside)[^>]*>.*?</\1>",
                  " ", html, flags=re.DOTALL | re.IGNORECASE)

    # Convertir <br>, <p>, <li>, <div> en saltos de línea
    html = re.sub(r"<(br|p|li|div|tr|h[1-6])[^>]*>", "\n", html, flags=re.IGNORECASE)

    # Eliminar todas las etiquetas restantes
    html = re.sub(r"<[^>]+>", " ", html)

    # Decodificar entidades HTML comunes
    html = (html
            .replace("&amp;",  "&")
            .replace("&lt;",   "<")
            .replace("&gt;",   ">")
            .replace("&quot;", '"')
            .replace("&#39;",  "'")
            .replace("&nbsp;", " ")
            .replace("&aacute;", "á").replace("&eacute;", "é")
            .replace("&iacute;", "í").replace("&oacute;", "ó")
            .replace("&uacute;", "ú").replace("&ntilde;",  "ñ"))

    # Colapsar espacios y líneas en blanco
    html = re.sub(r"[ \t]+",  " ",  html)
    html = re.sub(r"\n{3,}",  "\n\n", html)

    text = html.strip()
    return text[:_MAX_CHARS]
