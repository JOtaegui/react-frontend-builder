"""
_extract.py — Extrae datos estructurados de un artículo usando Gemini.

Dado el texto de un artículo de noticias, Gemini devuelve un JSON con:
  - company_name     : nombre de la empresa afectada
  - domain           : dominio web (ej: "falabella.com")
  - country          : "Chile" si es chilena, si no el país
  - incident_date    : "YYYY-MM" (mes y año del incidente)
  - data_types       : lista de tipos de datos expuestos CONFIRMADOS
  - confirmed_facts  : resumen en 1-2 oraciones de qué está confirmado
  - unconfirmed      : qué no está confirmado (estimaciones, rumores)
  - pwn_count        : número de registros si fue publicado oficialmente (null si no)
  - confidence       : "high" | "medium" | "low"
  - is_chile_related : true si afecta a empresa o clientes chilenos

Si el artículo no describe un breach concreto de empresa, retorna null.

Criterio de confianza que se pide a Gemini:
  high   → fuente es CSIRT, CMF, Bleeping Computer, Security Affairs,
            o comunicado oficial de la empresa
  medium → prensa generalista con detalles técnicos mínimos
  low    → blog, foro, estimación sin fuente — NO agregar al store
"""
from __future__ import annotations

import asyncio
import json
import logging
import re
from typing import Optional

import httpx

from config import GEMINI_API_KEY, GEMINI_MODEL

logger = logging.getLogger(__name__)

_GEMINI_URL = f"https://generativelanguage.googleapis.com/v1beta/models/{GEMINI_MODEL}:generateContent"

_GEMINI_GAP = 8.0   # segundos entre llamadas — free tier = 10 RPM → ~6s mínimo

_SYSTEM_PROMPT = """Eres un analista de ciberseguridad especializado en filtraciones de datos en Latinoamérica.

Tu tarea es analizar el texto de un artículo de noticias y extraer información estructurada sobre filtraciones de datos de empresas.

REGLAS ESTRICTAS:
1. Solo extrae hechos EXPLÍCITAMENTE mencionados en el texto. No infieren ni supongas.
2. Si el artículo no describe una filtración concreta de datos de clientes/usuarios, retorna null.
3. Para pwn_count: solo incluye números que el artículo mencione explícitamente como registros/cuentas afectadas. Si no hay número explícito, pon null.
4. Para data_types: solo incluye tipos de datos que el artículo mencione explícitamente (ej: "correos electrónicos", "RUT", "contraseñas", "tarjetas de crédito").
5. confirmed_facts debe ser un resumen objetivo de 1-2 oraciones de lo que el artículo confirma.
6. unconfirmed debe mencionar qué aspectos son inciertos o no confirmados según el artículo.
7. confidence:
   - "high": el artículo es de bleepingcomputer.com, securityaffairs.com, csirt.gob.cl, therecord.media, o es un comunicado oficial
   - "medium": prensa generalista con detalles específicos
   - "low": blog, foro, o información vaga sin fuente clara

Responde ÚNICAMENTE con JSON válido o la palabra null. Sin texto adicional."""

_USER_TEMPLATE = """Artículo:
URL fuente: {url}
Confianza de la fuente: {source_confidence}

Texto:
{text}

Extrae la información de filtración de datos. Responde con este JSON exacto o con null:
{{
  "company_name": "string",
  "domain": "string (ej: empresa.cl)",
  "country": "string",
  "incident_date": "YYYY-MM",
  "data_types": ["string"],
  "confirmed_facts": "string",
  "unconfirmed": "string",
  "pwn_count": null_o_número_entero,
  "confidence": "high|medium|low",
  "is_chile_related": true_o_false
}}"""


async def extract_incident(
    client: httpx.AsyncClient,
    article_text: str,
    source_url: str,
    source_confidence: str,
    gemini_sem: "asyncio.Semaphore | None" = None,
) -> Optional[dict]:
    """
    Usa Gemini para extraer datos estructurados del artículo.
    Retorna None si Gemini falla, si el artículo no es relevante,
    o si la confianza es "low".
    """
    if not GEMINI_API_KEY:
        logger.warning("[breach-scraper] GEMINI_API_KEY no configurada — extracción omitida")
        return None

    prompt = _USER_TEMPLATE.format(
        url=source_url,
        source_confidence=source_confidence,
        text=article_text[:3500],
    )

    # Serializar todas las llamadas a Gemini + esperar _GEMINI_GAP entre ellas
    # para mantenerse bajo el límite de 10 RPM del free tier.
    # El semáforo se crea en run_scraper (dentro del event loop activo) y se pasa aquí.
    sem = gemini_sem if gemini_sem is not None else asyncio.Semaphore(1)
    async with sem:
        _retry_delays = [10, 20]   # 429: espera 10s luego 20s antes de rendirse
        resp = None
        for attempt in range(len(_retry_delays) + 1):
            try:
                resp = await client.post(
                    _GEMINI_URL,
                    params={"key": GEMINI_API_KEY},
                    json={
                        "system_instruction": {"parts": [{"text": _SYSTEM_PROMPT}]},
                        "contents": [{"parts": [{"text": prompt}]}],
                        "generationConfig": {
                            "temperature":     0.0,
                            "maxOutputTokens": 512,
                        },
                    },
                    timeout=30.0,
                )
            except Exception as exc:
                logger.warning("[breach-scraper] Gemini request error: %s", exc)
                return None

            if resp.status_code == 429:
                # Detectar si es créditos agotados (no es rate limit recuperable)
                try:
                    err_body = resp.json()
                    err_msg = err_body.get("error", {}).get("message", "")
                    if "prepayment" in err_msg.lower() or "credits" in err_msg.lower():
                        logger.error(
                            "[breach-scraper] Gemini: créditos agotados. "
                            "Obtén una clave GRATUITA en https://aistudio.google.com/apikey "
                            "y actualiza GEMINI_API_KEY en server/.env"
                        )
                        return None
                except Exception:
                    pass
                if attempt < len(_retry_delays):
                    wait = _retry_delays[attempt]
                    logger.warning(
                        "[breach-scraper] Gemini 429 — esperando %ds (intento %d/%d)",
                        wait, attempt + 1, len(_retry_delays),
                    )
                    await asyncio.sleep(wait)
                    continue
                else:
                    logger.warning("[breach-scraper] Gemini 429 persistente — saltando artículo")
                    return None
            break

        # Delay mínimo entre llamadas para no superar los 10 RPM del free tier
        await asyncio.sleep(_GEMINI_GAP)

    try:
        if resp.status_code != 200:
            logger.warning("[breach-scraper] Gemini status %s", resp.status_code)
            return None

        raw = resp.json()
        text = raw["candidates"][0]["content"]["parts"][0]["text"].strip()

        if text.lower() == "null" or not text:
            return None

        # Limpiar posibles markdown fences que Gemini a veces agrega
        text = re.sub(r"^```json\s*", "", text)
        text = re.sub(r"```$",        "", text.strip())

        incident = json.loads(text)

        # Filtros de calidad
        if not incident.get("is_chile_related"):
            return None
        if incident.get("confidence") == "low":
            return None
        if not incident.get("domain") or not incident.get("company_name"):
            return None
        if not incident.get("incident_date"):
            return None

        # Añadir fuente
        incident["sources"] = [source_url]

        # Normalizar domain: minúsculas, sin www
        domain = incident["domain"].lower().strip()
        if domain.startswith("www."):
            domain = domain[4:]
        incident["domain"] = domain

        # Generar id reproducible
        date_part = incident["incident_date"][:7].replace("-", "")
        safe_domain = domain.replace(".", "_")
        incident["id"] = f"{safe_domain}-{date_part}"

        return incident

    except json.JSONDecodeError as exc:
        logger.debug("[breach-scraper] JSON parse error: %s", exc)
        return None
    except Exception as exc:
        logger.warning("[breach-scraper] Gemini error: %s", exc)
        return None
