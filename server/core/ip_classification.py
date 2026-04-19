from __future__ import annotations

import asyncio
import logging
import re
from ipaddress import ip_address
from typing import Any, Iterable, Mapping, Optional, Protocol

import httpx

HEADER_IP_NAMES = ("received", "x-originating-ip", "x-forwarded-for", "x-sender-ip", "x-client-ip", "x-real-ip")
CHILE_COUNTRY_ALIASES = {"cl", "chl", "chile", "republic of chile"}
logger = logging.getLogger(__name__)


class SenderIpEvidence(Protocol):
    company_name: str
    primary_domain: str
    from_addresses: set[str]
    message_count: int
    header_ips: set[str]
    header_ip_countries: set[str]
    header_ip_chile_matches: set[str]
    is_chilean: bool
    country: str
    confidence: float
    tags: set[str]


def extract_header_ips(headers_by_name: Mapping[str, list[str]]) -> list[str]:
    ips: set[str] = set()
    for header_name in HEADER_IP_NAMES:
        for value in headers_by_name.get(header_name, []):
            ips.update(_extract_public_ips_from_text(value))
    return sorted(ips)


def country_is_chile(value: str) -> bool:
    normalized = re.sub(r"[^a-z]", " ", value.strip().lower())
    compact = " ".join(normalized.split())
    return compact in CHILE_COUNTRY_ALIASES or " chile " in f" {compact} "


async def enrich_senders_with_header_ip_country(aggregates: Mapping[str, SenderIpEvidence]) -> None:
    all_ips = sorted({ip for sender in aggregates.values() for ip in sender.header_ips})
    if not all_ips:
        logger.info("[email-ip-debug] No se detectaron IPs publicas en headers de los correos analizados")
        return
    ips_to_lookup = all_ips[:200]

    timeout = httpx.Timeout(8.0, connect=4.0)
    async with httpx.AsyncClient(timeout=timeout, follow_redirects=True) as client:
        results = await asyncio.gather(
            *[_fetch_ip_country(client, ip) for ip in ips_to_lookup],
            return_exceptions=True,
        )

    country_by_ip: dict[str, str] = {}
    for ip, result in zip(ips_to_lookup, results):
        if isinstance(result, Exception) or not result:
            continue
        country_by_ip[ip] = result

    for sender_domain, sender in sorted(aggregates.items(), key=lambda item: item[0]):
        sender_company = getattr(sender, "company_name", "desconocido")
        sender_from_addresses = sorted(getattr(sender, "from_addresses", set()))
        sender_main_from = sender_from_addresses[0] if sender_from_addresses else "(sin correo remitente visible)"
        sender_ip_rows: list[str] = []
        for ip in sorted(sender.header_ips):
            country = country_by_ip.get(ip)
            sender_ip_rows.append(f"    - {ip} | pais: {country or 'desconocido'}")
            if not country:
                continue
            sender.header_ip_countries.add(country)
            if country_is_chile(country):
                sender.header_ip_chile_matches.add(ip)

        if sender_ip_rows:
            block = "\n".join(
                [
                    "[email-ip-debug]",
                    f"  remitente: {sender_main_from}",
                    f"  empresa: {sender_company}",
                    f"  dominio: {sender_domain}",
                    f"  mensajes_analizados: {sender.message_count}",
                    "  ips_en_cabeceras:",
                    *sender_ip_rows,
                ]
            )
            logger.info(block)
        else:
            block = "\n".join(
                [
                    "[email-ip-debug]",
                    f"  remitente: {sender_main_from}",
                    f"  empresa: {sender_company}",
                    f"  dominio: {sender_domain}",
                    f"  mensajes_analizados: {sender.message_count}",
                    "  ips_en_cabeceras: (sin IP publica detectable)",
                ]
            )
            logger.info(block)

        if sender.header_ip_chile_matches:
            sender.is_chilean = True
            sender.country = "Chile"
            sender.confidence = max(sender.confidence, 0.88)
            sender.tags.add("ip-chile")

        if sender.header_ips:
            resume_block = "\n".join(
                [
                    "[email-ip-debug-resumen]",
                    f"  dominio: {sender_domain}",
                    f"  pais_remitente_inferido: {sender.country}",
                    f"  ip_chile_detectadas: {', '.join(sorted(sender.header_ip_chile_matches)) or '(ninguna)'}",
                    f"  paises_detectados_en_ips: {', '.join(sorted(sender.header_ip_countries)) or '(desconocido)'}",
                ]
            )
            logger.info(resume_block)


def _extract_public_ips_from_text(value: str) -> set[str]:
    candidates: set[str] = set()
    tokens = re.split(r"[^0-9A-Za-z:.[\]_%\-]+", value or "")
    for token in tokens:
        if "." not in token and ":" not in token:
            continue
        candidate = token.strip("[]()<>;,\"' ")
        if not candidate:
            continue
        lowered = candidate.lower()
        if lowered.startswith("ipv6:") or lowered.startswith("ipv4:"):
            candidate = candidate.split(":", 1)[-1]
        if "%" in candidate:
            candidate = candidate.split("%", 1)[0]
        candidate = candidate.strip(".")
        if not candidate:
            continue
        try:
            parsed_ip = ip_address(candidate)
        except ValueError:
            continue
        if not parsed_ip.is_global:
            continue
        candidates.add(str(parsed_ip))
    return candidates


async def _fetch_ip_country(
    client: httpx.AsyncClient,
    ip_value: str,
) -> Optional[str]:
    try:
        response = await client.get(f"https://rdap.org/ip/{ip_value}")
        response.raise_for_status()
    except Exception:
        return None

    payload = response.json()
    return _extract_country_from_ip_rdap(payload)


def _extract_country_from_ip_rdap(payload: dict[str, Any]) -> Optional[str]:
    country = payload.get("country")
    if isinstance(country, str) and country.strip():
        normalized = _normalize_country_label(country)
        if normalized:
            return normalized

    entities = payload.get("entities") or []
    for entity in entities:
        candidate = _extract_vcard_value(entity.get("vcardArray"), "country-name")
        if candidate:
            normalized = _normalize_country_label(candidate)
            if normalized:
                return normalized
        candidate = _extract_vcard_country(entity.get("vcardArray"))
        if candidate:
            normalized = _normalize_country_label(candidate)
            if normalized:
                return normalized
    return None


def _extract_vcard_value(vcard_array: Any, field_name: str) -> Optional[str]:
    if not isinstance(vcard_array, list) or len(vcard_array) < 2:
        return None
    entries = vcard_array[1]
    if not isinstance(entries, list):
        return None
    for entry in entries:
        if not isinstance(entry, list) or len(entry) < 4:
            continue
        if str(entry[0]).lower() == field_name.lower():
            value = entry[3]
            if isinstance(value, str):
                return value.strip() or None
    return None


def _extract_vcard_country(vcard_array: Any) -> Optional[str]:
    if not isinstance(vcard_array, list) or len(vcard_array) < 2:
        return None
    entries = vcard_array[1]
    if not isinstance(entries, list):
        return None
    for entry in entries:
        if not isinstance(entry, list) or len(entry) < 4:
            continue
        if str(entry[0]).lower() != "adr":
            continue
        value = entry[3]
        if isinstance(value, list) and len(value) >= 7 and isinstance(value[6], str):
            candidate = value[6].strip()
            if candidate:
                return candidate
    return None


def _normalize_country_label(value: str) -> Optional[str]:
    cleaned = value.strip()
    if not cleaned:
        return None
    upper = cleaned.upper()
    if upper in {"CL", "CHL"}:
        return "Chile"
    if upper in {"US", "USA"}:
        return "Estados Unidos"
    if upper == "AR":
        return "Argentina"
    if upper == "BR":
        return "Brasil"
    if upper == "MX":
        return "Mexico"
    if upper == "ES":
        return "Espana"
    return cleaned
