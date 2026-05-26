"""
breach_crossref.py — Cruce de empresas del historial de navegación con filtraciones.

Fuente única: HIBP domain search (haveibeenpwned.com/api/v3)
  GET /api/v3/breaches?domain={domain}
  - Endpoint público, sin API key requerida.
  - Mantiene base de datos propia verificada y auditada.
  - Solo se muestra lo que HIBP confirma — no se agrega ningún dato externo.

Pipeline:
  1. Recibe lista de empresas del historial del navegador (browser_companies)
  2. Opcionalmente recibe dominios del análisis de correo (email_domains)
  3. Para los top N por riesgo → consulta HIBP por dominio
  4. Calcula riesgo compuesto: browser_risk × in_email × breach_count
  5. Devuelve lista ordenada por riesgo compuesto

Base legal:
  - Art. 22 Ley 21.719 — supresión reforzada si empresa tuvo filtración
  - Art. 11 — derecho de acceso
"""
from __future__ import annotations

import asyncio
import logging
from typing import Optional

import httpx

from .breach_scraper import get_incidents_by_domain

logger = logging.getLogger(__name__)

HIBP_PUBLIC_URL     = "https://haveibeenpwned.com/api/v3/breaches"
DEFAULT_MAX_DOMAINS = 9999  # sin límite — se consultan todos los dominios
_COMPOSITE_ORDER    = {"critical": 0, "high": 1, "medium": 2, "low": 3}


# ── Perfil de datos: qué tiene la empresa sobre el usuario ───────────────────

# Palabras clave HIBP que corresponden a cada tipo detectado en emails (ES)
_EMAIL_TYPE_HIBP_KEYWORDS: dict[str, list[str]] = {
    "nombre":    ["name", "first name", "last name", "full name", "names"],
    "direccion": ["address", "physical address", "geographic", "location"],
    "rut":       ["government issued id", "national registration", "identity document",
                  "tax identification", "government id", "national id"],
    "telefono":  ["phone", "mobile phone", "telephone"],
    "pago":      ["credit card", "financial", "payment", "bank account",
                  "partial credit card", "credit cards"],
    "pedido":    ["purchase", "purchases", "order", "shopping"],
    "cuenta":    ["password", "credential", "username", "account", "email address",
                  "email addresses", "auth token"],
    "patente":   ["vehicle", "vehicle detail", "car"],
}

# Datos que se infieren si tenemos el sender_type pero no email_data
_SENDER_TYPE_INFERRED: dict[str, list[str]] = {
    "bank":       ["nombre", "rut", "cuenta", "pago"],
    "fintech":    ["nombre", "rut", "cuenta", "pago"],
    "retail":     ["nombre", "direccion", "pago", "pedido"],
    "ecommerce":  ["nombre", "direccion", "pago", "pedido"],
    "health":     ["nombre", "rut"],
    "government": ["nombre", "rut", "direccion"],
    "telecom":    ["nombre", "rut", "direccion", "telefono"],
    "insurance":  ["nombre", "rut", "pago"],
    "education":  ["nombre", "rut"],
    "logistics":  ["nombre", "direccion", "pedido"],
    "airline":    ["nombre", "rut", "pedido", "pago"],
    "food":       ["nombre", "direccion", "pedido"],
    "news":       ["nombre", "cuenta"],
}

# Etiquetas en español para mostrar al usuario
_DATA_TYPE_LABELS: dict[str, str] = {
    "nombre":    "Nombre completo",
    "direccion": "Dirección física",
    "rut":       "RUT / identidad",
    "telefono":  "Número de teléfono",
    "pago":      "Datos de pago / tarjeta",
    "pedido":    "Historial de compras",
    "cuenta":    "Contraseña / credenciales",
    "patente":   "Patente / vehículo",
}


def _intersect_with_breach(email_types: list[str], breach_data_classes: list[str]) -> list[str]:
    """
    Retorna qué tipos de datos del usuario (detectados en email) coinciden con
    los DataClasses expuestos en el breach (según HIBP).
    """
    if not breach_data_classes:
        return []
    hibp_text = " ".join(breach_data_classes).lower()
    exposed = []
    for dtype in email_types:
        keywords = _EMAIL_TYPE_HIBP_KEYWORDS.get(dtype, [])
        if any(kw in hibp_text for kw in keywords):
            exposed.append(dtype)
    return exposed


def _all_breach_data_classes(breaches: list[dict]) -> list[str]:
    """Une todos los data_types de todos los breaches sin duplicar."""
    seen: set[str] = set()
    result: list[str] = []
    for b in breaches:
        for dt in b.get("data_types", []):
            if dt.lower() not in seen:
                seen.add(dt.lower())
                result.append(dt)
    return result


def _build_data_profile(
    domain: str,
    email_sender: Optional[dict],
    breaches: list[dict],
) -> dict:
    """
    Construye el perfil de datos expuestos para una empresa:
    - Qué datos tiene la empresa sobre el usuario (de análisis de email o inferido)
    - Cuál de esos datos quedó expuesto en el breach
    """
    if email_sender:
        raw_types = email_sender.get("personal_data_types", [])
        source = "email_analysis"
        sender_type = email_sender.get("sender_type", "")
        sample_subjects = email_sender.get("sample_subjects", [])[:3]
    else:
        raw_types = []
        source = "none"
        sender_type = ""
        sample_subjects = []

    # Si no hay tipos detectados pero sabemos el sender_type, inferir
    if not raw_types and sender_type:
        raw_types = _SENDER_TYPE_INFERRED.get(sender_type, [])
        if raw_types:
            source = "inferred"

    all_breach_classes = _all_breach_data_classes(breaches)
    exposed = _intersect_with_breach(raw_types, all_breach_classes) if breaches else []

    return {
        "has_email_data":        email_sender is not None,
        "data_types":            raw_types,
        "data_type_labels":      [_DATA_TYPE_LABELS.get(t, t) for t in raw_types],
        "source":                source,
        "sender_type":           sender_type,
        "sample_subjects":       sample_subjects,
        "your_exposed_data":     exposed,
        "your_exposed_labels":   [_DATA_TYPE_LABELS.get(t, t) for t in exposed],
        "breach_data_classes":   all_breach_classes,
    }


# ── Riesgo compuesto ──────────────────────────────────────────────────────────

def _composite_risk(browser_risk: str, also_in_email: bool, breach_count: int) -> str:
    has_breach = breach_count > 0
    if has_breach and (also_in_email or browser_risk == "high"):
        return "critical"
    if has_breach:
        return "high"
    if also_in_email and browser_risk == "high":
        return "high"
    if also_in_email or browser_risk == "high":
        return "medium"
    if browser_risk == "medium":
        return "medium"
    return "low"


def _recommended_action(composite_risk: str, has_breach: bool) -> str:
    if composite_risk == "critical":
        return "Solicitar baja urgente — Art. 22 Ley 21.719 (filtración de datos)"
    if composite_risk == "high":
        return "Solicitar baja — Art. 11 Ley 21.719 (acceso y supresión)"
    if composite_risk == "medium":
        return "Revisar datos almacenados y considerar solicitud de acceso"
    return "Monitorear — bajo riesgo actual"


def _legal_basis(composite_risk: str, has_breach: bool, also_in_email: bool) -> list[str]:
    bases: list[str] = []
    if has_breach:
        bases.append("Art. 22 Ley 21.719 — supresión reforzada por filtración")
    if also_in_email:
        bases.append("Art. 11 Ley 21.719 — derecho de acceso")
    if composite_risk in ("critical", "high"):
        bases.append("Art. 14 Ley 21.719 — 30 días corridos para responder")
    return bases


# ── Consulta HIBP ─────────────────────────────────────────────────────────────

def _strip_html(text: str) -> str:
    import re
    return re.sub(r"<[^>]+>", "", text).strip()


async def _fetch_hibp_breaches(client: httpx.AsyncClient, domain: str) -> list[dict]:
    """
    Consulta HIBP por dominio. Devuelve [] en cualquier error o si no hay breaches.
    Solo retorna lo que HIBP confirma — sin agregar ni inferir nada.
    """
    try:
        resp = await client.get(
            HIBP_PUBLIC_URL,
            params={"domain": domain},
            headers={"user-agent": "OSINT-Chile-Privacy-Tool"},
            timeout=10.0,
        )
        if resp.status_code == 200:
            return [
                {
                    "name":        b.get("Name", ""),
                    "domain":      b.get("Domain", domain),
                    "breach_date": b.get("BreachDate"),
                    "pwn_count":   b.get("PwnCount", 0),
                    "data_types":  b.get("DataClasses", []),
                    "description": _strip_html(b.get("Description", "")),
                    "source":      "hibp",
                }
                for b in resp.json()
            ]
        return []
    except Exception as exc:
        logger.debug("[breach-crossref] HIBP error para %s: %s", domain, exc)
        return []


# ── Pipeline principal ────────────────────────────────────────────────────────

async def run_breach_crossref(
    browser_companies: list[dict],
    email_domains: Optional[list[str]] = None,
    email_senders: Optional[list[dict]] = None,
    max_domains: int = DEFAULT_MAX_DOMAINS,
) -> list[dict]:
    """
    Cruza empresas del historial con filtraciones HIBP y dominios de correo.

    email_senders: lista de objetos {primary_domain, personal_data_types,
                   sender_type, sample_subjects} del análisis de email.
    Para las empresas fuera del top max_domains no se consulta HIBP
    (evitar timeouts), pero sí se calcula composite_risk con email_domains.
    """
    email_domain_set: set[str] = set(email_domains or [])

    # Índice rápido domain → sender_profile para intersección de datos
    sender_map: dict[str, dict] = {}
    for s in (email_senders or []):
        d = s.get("primary_domain", "")
        if d:
            sender_map[d] = s
            # También agregar dominios extraídos del análisis a email_domain_set
            email_domain_set.add(d)

    _risk_ord = {"high": 0, "medium": 1, "low": 2}
    sorted_companies = sorted(
        browser_companies,
        key=lambda c: (_risk_ord.get(c.get("risk_level", "low"), 3), -c.get("visit_count", 0)),
    )
    to_query = sorted_companies[:max_domains]
    rest     = sorted_companies[max_domains:]

    async with httpx.AsyncClient() as client:
        semaphore = asyncio.Semaphore(15)

        async def _enrich(company: dict) -> dict:
            async with semaphore:
                domain        = company.get("domain", "")
                hibp_breaches = await _fetch_hibp_breaches(client, domain)
                # Incidentes scrapeados localmente (confianza medium+)
                local_breaches = [
                    {**inc, "source": "scraped_cl"}
                    for inc in get_incidents_by_domain(domain)
                ]
                # Merge: HIBP primero, local completa sin duplicar por nombre
                seen = {b["name"].lower() for b in hibp_breaches}
                extra = [b for b in local_breaches
                         if b.get("company_name", "").lower() not in seen]
                breaches = hibp_breaches + extra

                also_in_email = domain in email_domain_set
                composite = _composite_risk(
                    company.get("risk_level", "low"), also_in_email, len(breaches)
                )
                data_profile = _build_data_profile(
                    domain, sender_map.get(domain), breaches
                )
                return {
                    **company,
                    "also_in_email":      also_in_email,
                    "hibp_breaches":      breaches,
                    "breach_count":       len(breaches),
                    "has_breach":         len(breaches) > 0,
                    "composite_risk":     composite,
                    "recommended_action": _recommended_action(composite, len(breaches) > 0),
                    "legal_basis":        _legal_basis(composite, len(breaches) > 0, also_in_email),
                    "data_profile":       data_profile,
                    "hibp_checked":       True,
                }

        enriched = list(await asyncio.gather(*[_enrich(c) for c in to_query]))

    def _enrich_rest(c: dict) -> dict:
        domain        = c.get("domain", "")
        also_in_email = domain in email_domain_set
        # Aunque no consultamos HIBP, sí cruzamos con base local scrapeada
        local_breaches = [
            {**inc, "source": "scraped_cl"}
            for inc in get_incidents_by_domain(domain)
        ]
        composite = _composite_risk(c.get("risk_level", "low"), also_in_email, len(local_breaches))
        data_profile = _build_data_profile(domain, sender_map.get(domain), local_breaches)
        return {
            **c,
            "also_in_email":      also_in_email,
            "hibp_breaches":      local_breaches,
            "breach_count":       len(local_breaches),
            "has_breach":         len(local_breaches) > 0,
            "composite_risk":     composite,
            "recommended_action": _recommended_action(composite, len(local_breaches) > 0),
            "legal_basis":        _legal_basis(composite, len(local_breaches) > 0, also_in_email),
            "data_profile":       data_profile,
            "hibp_checked":       False,
        }

    all_results = enriched + [_enrich_rest(c) for c in rest]
    all_results.sort(
        key=lambda x: (
            _COMPOSITE_ORDER.get(x["composite_risk"], 4),
            -x["breach_count"],
            -x.get("visit_count", 0),
        )
    )
    return all_results
