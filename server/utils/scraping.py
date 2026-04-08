"""
utils/scraping.py — Utilidades compartidas para todos los módulos.

Centralizar aquí:
- Normalización de RUT chileno
- Extracción de emails con regex
- Parser de tablas HTML genérico
- Retry con backoff exponencial
- Detección de CAPTCHAs / bloqueos
"""
from __future__ import annotations

import asyncio
import logging
import re
import unicodedata
from typing import Any, List, Optional, Union

import httpx
from bs4 import BeautifulSoup, Tag

logger = logging.getLogger(__name__)

# ── RUT ───────────────────────────────────────────────────────────────────────

RUT_REGEX = re.compile(r"\b(\d{1,2}\.?\d{3}\.?\d{3}[-–][\dkK])\b")


def limpiar_rut(rut: str) -> str:
    """12.345.678-9 → 12345678-9"""
    rut = rut.strip().replace(".", "").replace(" ", "")
    if "-" not in rut and len(rut) > 1:
        rut = rut[:-1] + "-" + rut[-1]
    return rut.upper()


def formatear_rut(rut: str) -> str:
    """12345678-9 → 12.345.678-9"""
    rut = limpiar_rut(rut)
    if "-" in rut:
        cuerpo, dv = rut.split("-", 1)
        cuerpo_fmt = f"{int(cuerpo):,}".replace(",", ".")
        return f"{cuerpo_fmt}-{dv}"
    return rut


def separar_rut(rut: str) -> tuple[str, str]:
    """Devuelve (cuerpo_sin_puntos, dv)."""
    rut = limpiar_rut(rut)
    if "-" in rut:
        cuerpo, dv = rut.split("-", 1)
        return cuerpo, dv
    return rut[:-1], rut[-1]


def extraer_ruts(texto: str) -> list[str]:
    """Extrae todos los RUTs válidos de un texto."""
    return RUT_REGEX.findall(texto)


# ── Emails ────────────────────────────────────────────────────────────────────

EMAIL_REGEX = re.compile(
    r"\b[a-zA-Z0-9._%+\-]+@[a-zA-Z0-9.\-]+\.[a-zA-Z]{2,}\b"
)

# Dominios que no son emails personales reales (filtrar ruido)
DOMINIOS_FALSOS = {"example.com", "test.com", "correo.com", "email.com", "mail.com"}


def extraer_emails(texto: str) -> list[str]:
    """Extrae emails válidos de un texto, filtrando dominios falsos."""
    encontrados = EMAIL_REGEX.findall(texto)
    return [
        e.lower() for e in encontrados
        if e.split("@")[-1].lower() not in DOMINIOS_FALSOS
    ]


# ── Normalización de texto ────────────────────────────────────────────────────

def normalizar(texto: str) -> str:
    """Lowercase, sin tildes, sin dobles espacios."""
    nfkd = unicodedata.normalize("NFKD", texto)
    sin_tildes = "".join(c for c in nfkd if not unicodedata.combining(c))
    return re.sub(r"\s+", " ", sin_tildes.lower().strip())


def nombre_en_texto(nombre: str, texto: str, umbral: float = 0.5) -> bool:
    """
    Verifica si un nombre aparece en un texto.
    umbral: fracción mínima de palabras del nombre que deben aparecer.
    """
    palabras = normalizar(nombre).split()
    texto_norm = normalizar(texto)
    matches = sum(1 for p in palabras if p in texto_norm)
    return matches >= max(1, len(palabras) * umbral)


# ── Parser de tablas HTML ─────────────────────────────────────────────────────

def parsear_tabla(
    soup: Union[BeautifulSoup, Tag],
    columnas: Optional[List[str]] = None,
) -> List[dict[str, str]]:
    """
    Parsea la primera tabla encontrada en un elemento BeautifulSoup.

    Si `columnas` es None, usa los headers de la tabla como claves.
    Si `columnas` es una lista, mapea por posición (útil cuando no hay <th>).

    Devuelve lista de dicts.
    """
    tabla = soup.find("table") if not isinstance(soup, Tag) or soup.name != "table" else soup
    if not tabla:
        return []

    filas = tabla.find_all("tr")
    if not filas:
        return []

    # Detectar headers
    headers: List[str] = []
    primera_fila = filas[0]
    ths = primera_fila.find_all("th")

    if ths:
        headers = [th.get_text(strip=True).lower() for th in ths]
        filas = filas[1:]  # skip header row
    elif columnas:
        headers = columnas
    else:
        # Sin headers: usar col_0, col_1, ...
        n_cols = max(len(f.find_all("td")) for f in filas if f.find("td"))
        headers = [f"col_{i}" for i in range(n_cols)]

    resultados = []
    for fila in filas:
        celdas = [td.get_text(strip=True) for td in fila.find_all("td")]
        if not any(celdas):
            continue
        entry = {}
        for i, header in enumerate(headers):
            entry[header] = celdas[i] if i < len(celdas) else ""
        resultados.append(entry)

    return resultados


# ── Detección de bloqueos ─────────────────────────────────────────────────────

BLOQUEO_KEYWORDS = [
    "captcha", "robot", "access denied", "403 forbidden",
    "too many requests", "rate limit", "cloudflare",
    "acceso denegado", "no autorizado",
]


def detectar_bloqueo(html: str) -> bool:
    """Devuelve True si la respuesta parece un CAPTCHA o bloqueo."""
    texto = html.lower()[:2000]  # solo revisar el inicio
    return any(kw in texto for kw in BLOQUEO_KEYWORDS)


# ── Retry con backoff ─────────────────────────────────────────────────────────

async def get_with_retry(
    client: httpx.AsyncClient,
    url: str,
    max_retries: int = 2,
    backoff: float = 2.0,
    **kwargs: Any,
) -> Optional[httpx.Response]:
    """
    GET con reintentos automáticos para errores transitorios (5xx, timeouts).
    No reintenta en 4xx (errores del cliente).
    """
    for attempt in range(max_retries + 1):
        try:
            resp = await client.get(url, **kwargs)
            if resp.status_code < 400:
                return resp
            if resp.status_code == 429:
                wait = backoff * (2 ** attempt)
                logger.warning(f"Rate limit en {url} — esperando {wait}s")
                await asyncio.sleep(wait)
                continue
            if resp.status_code >= 500:
                if attempt < max_retries:
                    await asyncio.sleep(backoff)
                    continue
            return resp
        except (httpx.TimeoutException, httpx.ConnectError) as e:
            if attempt < max_retries:
                logger.debug(f"Reintento {attempt+1} para {url}: {e}")
                await asyncio.sleep(backoff)
            else:
                logger.warning(f"Agotados reintentos para {url}: {e}")
                return None
    return None
