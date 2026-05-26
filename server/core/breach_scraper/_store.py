"""
_store.py — Persistencia de incidentes en server/data/cl_incidents.json

Cada incidente tiene:
  id              str   — "{domain}-{YYYY-MM}" único
  domain          str   — dominio raíz de la empresa
  company_name    str   — nombre legible
  incident_date   str   — "YYYY-MM" (mes de ocurrencia)
  data_types      list  — tipos de datos expuestos confirmados
  confirmed_facts str   — qué está confirmado por fuentes
  unconfirmed     str   — qué NO está confirmado (números estimados, etc.)
  pwn_count       int|null — registros afectados si fue publicado oficialmente
  confidence      str   — "high" | "medium" | "low"
  sources         list  — URLs de fuentes primarias
  scraped_at      str   — ISO timestamp de cuándo fue agregado
  verified_manually bool — si fue revisado por un humano

Regla de calidad:
  - confidence="high"   → fuente es CSIRT, CMF, Bleeping Computer, Security Affairs,
                          o comunicado oficial de la empresa
  - confidence="medium" → prensa generalista con detalles técnicos mínimos
  - confidence="low"    → blog, foro, tweet — solo para tracking, no mostrar al usuario
"""
from __future__ import annotations

import json
import logging
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional

from ._hardcoded import KNOWN_CL_INCIDENTS, get_hardcoded_by_domain

logger = logging.getLogger(__name__)

_STORE_PATH = Path(__file__).parent.parent.parent / "data" / "cl_incidents.json"


def _load_raw() -> list[dict]:
    try:
        return json.loads(_STORE_PATH.read_text(encoding="utf-8"))
    except Exception:
        return []


def _save_raw(incidents: list[dict]) -> None:
    _STORE_PATH.parent.mkdir(parents=True, exist_ok=True)
    _STORE_PATH.write_text(
        json.dumps(incidents, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )


def _merge_with_hardcoded(scraped: list[dict]) -> list[dict]:
    """
    Combina incidentes scrapeados con la lista hardcoded.
    Si el mismo (domain, YYYY-MM) aparece en ambas fuentes, prevalece el scrapeado
    (puede tener datos más recientes o completos), pero se fusionan las sources.
    """
    # Índice de los scrapeados por clave de deduplicación
    scraped_keys: set[str] = {
        f"{i.get('domain')}|{i.get('incident_date','')[:7]}" for i in scraped
    }

    merged = list(scraped)
    for hc in KNOWN_CL_INCIDENTS:
        key = f"{hc.get('domain')}|{hc.get('incident_date','')[:7]}"
        if key not in scraped_keys:
            merged.append(hc)

    return merged


def load_incidents(min_confidence: str = "medium") -> list[dict]:
    """
    Carga todos los incidentes (scrapeados + hardcoded) con confianza >= min_confidence.
    Orden: high → medium → low.
    """
    order = {"high": 0, "medium": 1, "low": 2}
    cutoff = order.get(min_confidence, 1)
    all_inc = _merge_with_hardcoded(_load_raw())
    return sorted(
        [i for i in all_inc if order.get(i.get("confidence", "low"), 2) <= cutoff],
        key=lambda i: order.get(i.get("confidence", "low"), 2),
    )


def get_by_domain(domain: str) -> list[dict]:
    """
    Devuelve todos los incidentes para un dominio específico.
    Combina scrapeados + hardcoded.
    """
    scraped  = [i for i in _load_raw() if i.get("domain") == domain]
    hardcoded = get_hardcoded_by_domain(domain)

    # Deduplicar: si el scraper ya tiene el mismo (domain, mes), no duplicar
    scraped_keys = {i.get("incident_date", "")[:7] for i in scraped}
    extra = [h for h in hardcoded if h.get("incident_date", "")[:7] not in scraped_keys]

    return scraped + extra


def upsert_incident(incident: dict) -> bool:
    """
    Inserta o actualiza un incidente.
    Clave de deduplicación: (domain, incident_date).
    Retorna True si fue insertado/actualizado, False si era idéntico.
    """
    incidents = _load_raw()

    key_domain = incident.get("domain", "")
    key_date   = incident.get("incident_date", "")[:7]  # YYYY-MM

    for i, existing in enumerate(incidents):
        if (existing.get("domain") == key_domain and
                existing.get("incident_date", "")[:7] == key_date):
            # Solo actualizar si la confianza nueva es mayor o hay datos nuevos
            if incident.get("confidence") != existing.get("confidence") or \
               len(incident.get("sources", [])) > len(existing.get("sources", [])):
                incidents[i] = {**existing, **incident}
                _save_raw(incidents)
                return True
            return False  # ya existe, nada cambió

    # Nuevo incidente
    incident.setdefault("scraped_at", datetime.now(timezone.utc).isoformat())
    incident.setdefault("verified_manually", False)
    incidents.append(incident)
    _save_raw(incidents)
    return True


def stats() -> dict:
    all_inc = _merge_with_hardcoded(_load_raw())
    scraped = _load_raw()
    return {
        "total":        len(all_inc),
        "high":         sum(1 for i in all_inc if i.get("confidence") == "high"),
        "medium":       sum(1 for i in all_inc if i.get("confidence") == "medium"),
        "low":          sum(1 for i in all_inc if i.get("confidence") == "low"),
        "scraped":      len(scraped),
        "hardcoded":    len(KNOWN_CL_INCIDENTS),
        "domains":      sorted({i["domain"] for i in all_inc if i.get("domain")}),
        "last_scraped": max(
            (i.get("scraped_at", "") for i in scraped), default=None
        ),
    }
