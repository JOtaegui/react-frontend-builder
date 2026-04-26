from __future__ import annotations

import asyncio
import logging
import os
import re
import time
from bisect import bisect_right
from dataclasses import dataclass
from ipaddress import (
    IPv4Address,
    IPv4Network,
    IPv6Network,
    collapse_addresses,
    ip_address,
    summarize_address_range,
)
from pathlib import Path
from typing import Any, Iterable, Mapping, Optional, Protocol, Union

import httpx

HEADER_IP_NAMES = ("received", "x-originating-ip", "x-forwarded-for", "x-sender-ip", "x-client-ip", "x-real-ip")
CHILE_COUNTRY_ALIASES = {"cl", "chl", "chile", "republic of chile"}
LACNIC_DELEGATED_LATEST_URL = "https://ftp.lacnic.net/pub/stats/lacnic/delegated-lacnic-latest"
LACNIC_CACHE_TTL_SECONDS = 12 * 60 * 60
CHILE_IP_RANGES_CSV_ENV = "CHILE_IP_RANGES_CSV_PATH"
DEFAULT_CHILE_IP_RANGES_CSV_PATH = Path(__file__).resolve().parents[1] / "chile_ip_ranges.csv"
logger = logging.getLogger(__name__)
IpNetwork = Union[IPv4Network, IPv6Network]
_CHILE_IP_RANGE_INDEX_CACHE: Optional["ChileIpRangeIndex"] = None
_CHILE_IP_RANGE_INDEX_CACHE_TS = 0.0
_CHILE_IP_RANGE_INDEX_LOCK = asyncio.Lock()


@dataclass
class ChileIpRangeIndex:
    lacnic_source_date: str
    lacnic_ipv4_starts: list[int]
    lacnic_ipv4_ends: list[int]
    lacnic_ipv6_starts: list[int]
    lacnic_ipv6_ends: list[int]
    csv_source_path: Optional[str]
    csv_rows_loaded: int
    csv_ipv4_starts: list[int]
    csv_ipv4_ends: list[int]
    csv_ipv6_starts: list[int]
    csv_ipv6_ends: list[int]


class SenderIpEvidence(Protocol):
    company_name: str
    primary_domain: str
    from_addresses: set[str]
    message_count: int
    header_ips: set[str]
    header_ip_countries: set[str]
    header_ip_chile_matches: set[str]
    header_ip_details: dict[str, dict[str, Any]]
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
    range_index = ChileIpRangeIndex(
        lacnic_source_date="desconocida",
        lacnic_ipv4_starts=[],
        lacnic_ipv4_ends=[],
        lacnic_ipv6_starts=[],
        lacnic_ipv6_ends=[],
        csv_source_path=None,
        csv_rows_loaded=0,
        csv_ipv4_starts=[],
        csv_ipv4_ends=[],
        csv_ipv6_starts=[],
        csv_ipv6_ends=[],
    )
    range_cache_hit = False

    timeout = httpx.Timeout(8.0, connect=4.0)
    async with httpx.AsyncClient(timeout=timeout, follow_redirects=True) as client:
        results = await asyncio.gather(
            *[_fetch_ip_country(client, ip) for ip in ips_to_lookup],
            return_exceptions=True,
        )
        range_index, range_cache_hit = await _load_chile_ip_range_index(client)

    country_by_ip: dict[str, str] = {}
    for ip, result in zip(ips_to_lookup, results):
        if isinstance(result, Exception) or not result:
            continue
        country_by_ip[ip] = result

    lacnic_active = bool(range_index.lacnic_ipv4_starts or range_index.lacnic_ipv6_starts)
    csv_active = bool(range_index.csv_ipv4_starts or range_index.csv_ipv6_starts)
    if lacnic_active or csv_active:
        logger.info(
            "[email-ip-debug] Rangos CL cargados | lacnic=%s (snapshot=%s) | csv=%s (rows=%s path=%s) | cache=%s",
            "activo" if lacnic_active else "no",
            range_index.lacnic_source_date,
            "activo" if csv_active else "no",
            range_index.csv_rows_loaded,
            range_index.csv_source_path or "-",
            "si" if range_cache_hit else "no",
        )
    else:
        logger.info("[email-ip-debug] Rangos CL no disponibles (LACNIC/CSV); usando solo pais por RDAP")

    for sender_domain, sender in sorted(aggregates.items(), key=lambda item: item[0]):
        sender_company = getattr(sender, "company_name", "desconocido")
        sender_from_addresses = sorted(getattr(sender, "from_addresses", set()))
        sender_main_from = sender_from_addresses[0] if sender_from_addresses else "(sin correo remitente visible)"
        sender_ip_rows: list[str] = []
        for ip in sorted(sender.header_ips):
            country_rdap = country_by_ip.get(ip)
            range_criterion = _classify_ip_chile_range(ip, range_index)
            is_chilean_by_range = range_criterion is not None
            if range_criterion:
                country = "Chile"
                criterion = range_criterion
            elif country_rdap:
                country = country_rdap
                criterion = "rdap"
            else:
                country = None
                criterion = "sin-datos"

            sender_ip_rows.append(f"    - {ip} | pais: {country or 'desconocido'} | criterio: {criterion}")

            if country:
                sender.header_ip_countries.add(country)
            is_chilean_ip = is_chilean_by_range or (country and country_is_chile(country))
            if is_chilean_ip:
                sender.header_ip_chile_matches.add(ip)
            sender.header_ip_details[ip] = {
                "ip": ip,
                "country": country,
                "is_chilean": bool(is_chilean_ip),
                "criterion": criterion,
            }

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
                    f"  rango_cl_lacnic: {'activo' if lacnic_active else 'no_disponible'} (snapshot={range_index.lacnic_source_date})",
                    f"  rango_cl_csv: {'activo' if csv_active else 'no_disponible'} (rows={range_index.csv_rows_loaded})",
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


def _classify_ip_chile_range(
    ip_value: str,
    range_index: ChileIpRangeIndex,
) -> Optional[str]:
    try:
        parsed_ip = ip_address(ip_value)
    except ValueError:
        return None

    ip_int = int(parsed_ip)
    if parsed_ip.version == 4:
        if _ip_in_sorted_ranges(ip_int, range_index.csv_ipv4_starts, range_index.csv_ipv4_ends):
            return "rango-cl-csv"
        if _ip_in_sorted_ranges(ip_int, range_index.lacnic_ipv4_starts, range_index.lacnic_ipv4_ends):
            return "rango-cl-lacnic"
        return None
    if _ip_in_sorted_ranges(ip_int, range_index.csv_ipv6_starts, range_index.csv_ipv6_ends):
        return "rango-cl-csv"
    if _ip_in_sorted_ranges(ip_int, range_index.lacnic_ipv6_starts, range_index.lacnic_ipv6_ends):
        return "rango-cl-lacnic"
    return None


def _ip_in_sorted_ranges(ip_int: int, starts: list[int], ends: list[int]) -> bool:
    if not starts:
        return False
    idx = bisect_right(starts, ip_int) - 1
    return idx >= 0 and ip_int <= ends[idx]


def _merge_numeric_ranges(ranges: list[tuple[int, int]]) -> list[tuple[int, int]]:
    if not ranges:
        return []
    ordered = sorted(ranges, key=lambda item: (item[0], item[1]))
    merged: list[tuple[int, int]] = []
    start, end = ordered[0]
    for nxt_start, nxt_end in ordered[1:]:
        if nxt_start <= end + 1:
            end = max(end, nxt_end)
            continue
        merged.append((start, end))
        start, end = nxt_start, nxt_end
    merged.append((start, end))
    return merged


def _range_bounds_to_index(ranges: list[tuple[int, int]]) -> tuple[list[int], list[int]]:
    starts = [start for start, _ in ranges]
    ends = [end for _, end in ranges]
    return starts, ends


def _networks_to_numeric_ranges(networks: list[IpNetwork]) -> tuple[list[tuple[int, int]], list[tuple[int, int]]]:
    ipv4_ranges: list[tuple[int, int]] = []
    ipv6_ranges: list[tuple[int, int]] = []
    for network in networks:
        start = int(network.network_address)
        end = int(network.broadcast_address)
        if network.version == 4:
            ipv4_ranges.append((start, end))
        else:
            ipv6_ranges.append((start, end))
    return _merge_numeric_ranges(ipv4_ranges), _merge_numeric_ranges(ipv6_ranges)


def _detect_separator(line: str) -> Optional[str]:
    if "\t" in line:
        return "\t"
    if ";" in line:
        return ";"
    if "," in line:
        return ","
    return None


def _split_range_line(line: str) -> list[str]:
    separator = _detect_separator(line)
    if separator:
        return [part.strip().strip('"').strip("'") for part in line.split(separator)]
    return [part.strip().strip('"').strip("'") for part in re.split(r"\s{2,}", line)]


def _load_chile_ranges_from_csv() -> tuple[list[tuple[int, int]], list[tuple[int, int]], int, Optional[str]]:
    candidates: list[Path] = []
    env_path = os.getenv(CHILE_IP_RANGES_CSV_ENV, "").strip()
    if env_path:
        candidates.append(Path(env_path).expanduser())
    candidates.append(DEFAULT_CHILE_IP_RANGES_CSV_PATH)

    seen: set[str] = set()
    deduped_candidates: list[Path] = []
    for path in candidates:
        normalized = str(path.resolve()) if path.exists() else str(path)
        if normalized in seen:
            continue
        seen.add(normalized)
        deduped_candidates.append(path)

    for path in deduped_candidates:
        if not path.exists() or not path.is_file():
            continue
        try:
            content = path.read_text(encoding="utf-8-sig")
        except Exception as exc:
            logger.warning("[email-ip-debug] No se pudo leer CSV de rangos CL en %s: %s", path, exc)
            continue

        ipv4_ranges: list[tuple[int, int]] = []
        ipv6_ranges: list[tuple[int, int]] = []
        valid_rows = 0
        for raw_line in content.splitlines():
            line = raw_line.strip()
            if not line or line.startswith("#"):
                continue
            parts = _split_range_line(line)
            if len(parts) < 2:
                continue

            start_raw, end_raw = parts[0], parts[1]
            try:
                start_ip = ip_address(start_raw)
                end_ip = ip_address(end_raw)
            except ValueError:
                continue
            if start_ip.version != end_ip.version:
                continue

            start_int = int(start_ip)
            end_int = int(end_ip)
            if end_int < start_int:
                start_int, end_int = end_int, start_int

            if start_ip.version == 4:
                ipv4_ranges.append((start_int, end_int))
            else:
                ipv6_ranges.append((start_int, end_int))
            valid_rows += 1

        return _merge_numeric_ranges(ipv4_ranges), _merge_numeric_ranges(ipv6_ranges), valid_rows, str(path)

    return [], [], 0, None


async def _load_chile_ip_range_index(client: httpx.AsyncClient) -> tuple[ChileIpRangeIndex, bool]:
    global _CHILE_IP_RANGE_INDEX_CACHE, _CHILE_IP_RANGE_INDEX_CACHE_TS

    now = time.time()
    if _CHILE_IP_RANGE_INDEX_CACHE and (now - _CHILE_IP_RANGE_INDEX_CACHE_TS) < LACNIC_CACHE_TTL_SECONDS:
        return _CHILE_IP_RANGE_INDEX_CACHE, True

    async with _CHILE_IP_RANGE_INDEX_LOCK:
        now = time.time()
        if _CHILE_IP_RANGE_INDEX_CACHE and (now - _CHILE_IP_RANGE_INDEX_CACHE_TS) < LACNIC_CACHE_TTL_SECONDS:
            return _CHILE_IP_RANGE_INDEX_CACHE, True

        lacnic_networks: list[IpNetwork] = []
        lacnic_source_date = "desconocida"
        try:
            response = await client.get(LACNIC_DELEGATED_LATEST_URL)
            response.raise_for_status()
            payload = response.text
            lacnic_networks, lacnic_source_date = _parse_chile_networks_from_lacnic(payload)
            if not lacnic_networks:
                logger.warning("[email-ip-debug] Archivo LACNIC descargado pero sin rangos CL parseables")
        except Exception as exc:
            logger.warning("[email-ip-debug] No se pudo descargar rangos CL desde LACNIC: %s", exc)

        lacnic_ipv4_ranges, lacnic_ipv6_ranges = _networks_to_numeric_ranges(lacnic_networks)
        csv_ipv4_ranges, csv_ipv6_ranges, csv_rows, csv_source = _load_chile_ranges_from_csv()
        if not csv_source:
            logger.info(
                "[email-ip-debug] CSV de rangos CL no encontrado. Define %s o crea %s",
                CHILE_IP_RANGES_CSV_ENV,
                DEFAULT_CHILE_IP_RANGES_CSV_PATH,
            )

        lacnic_ipv4_starts, lacnic_ipv4_ends = _range_bounds_to_index(lacnic_ipv4_ranges)
        lacnic_ipv6_starts, lacnic_ipv6_ends = _range_bounds_to_index(lacnic_ipv6_ranges)
        csv_ipv4_starts, csv_ipv4_ends = _range_bounds_to_index(csv_ipv4_ranges)
        csv_ipv6_starts, csv_ipv6_ends = _range_bounds_to_index(csv_ipv6_ranges)

        _CHILE_IP_RANGE_INDEX_CACHE = ChileIpRangeIndex(
            lacnic_source_date=lacnic_source_date,
            lacnic_ipv4_starts=lacnic_ipv4_starts,
            lacnic_ipv4_ends=lacnic_ipv4_ends,
            lacnic_ipv6_starts=lacnic_ipv6_starts,
            lacnic_ipv6_ends=lacnic_ipv6_ends,
            csv_source_path=csv_source,
            csv_rows_loaded=csv_rows,
            csv_ipv4_starts=csv_ipv4_starts,
            csv_ipv4_ends=csv_ipv4_ends,
            csv_ipv6_starts=csv_ipv6_starts,
            csv_ipv6_ends=csv_ipv6_ends,
        )
        _CHILE_IP_RANGE_INDEX_CACHE_TS = time.time()
        return _CHILE_IP_RANGE_INDEX_CACHE, False


def _parse_chile_networks_from_lacnic(payload: str) -> tuple[list[IpNetwork], str]:
    ipv4_networks: list[IPv4Network] = []
    ipv6_networks: list[IPv6Network] = []
    source_date = "desconocida"

    for raw_line in payload.splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#"):
            continue

        parts = line.split("|")
        if len(parts) >= 7 and parts[0] == "2":
            source_date = parts[5] or source_date
            continue
        if len(parts) < 7:
            continue
        registry, cc, resource_type, start, value, date, status = parts[:7]

        if registry.lower() != "lacnic" or cc.upper() != "CL":
            continue
        if status.lower() not in {"allocated", "assigned"}:
            continue

        if resource_type == "ipv4":
            try:
                ipv4_start = IPv4Address(start)
                hosts = int(value)
                if hosts <= 0:
                    continue
                ipv4_end = IPv4Address(int(ipv4_start) + hosts - 1)
            except Exception:
                continue
            ipv4_networks.extend(summarize_address_range(ipv4_start, ipv4_end))
        elif resource_type == "ipv6":
            try:
                prefix_length = int(value)
                network = IPv6Network(f"{start}/{prefix_length}", strict=False)
            except Exception:
                continue
            ipv6_networks.append(network)

    collapsed_v4 = list(collapse_addresses(ipv4_networks))
    collapsed_v6 = list(collapse_addresses(ipv6_networks))
    all_networks: list[IpNetwork] = [
        *sorted(collapsed_v4, key=lambda net: (int(net.network_address), net.prefixlen)),
        *sorted(collapsed_v6, key=lambda net: (int(net.network_address), net.prefixlen)),
    ]
    return all_networks, source_date


async def _fetch_ip_country(
    client: httpx.AsyncClient,
    ip_value: str,
) -> Optional[str]:
    try:
        response = await client.get(f"https://rdap.org/ip/{ip_value}")
        response.raise_for_status()
        payload = response.json()
        country = _extract_country_from_ip_rdap(payload)
        if country:
            return country
    except Exception:
        pass

    # Fallback: geolocalización cuando RDAP no incluye país utilizable.
    try:
        fallback_response = await client.get(f"https://ipwho.is/{ip_value}")
        fallback_response.raise_for_status()
        fallback_payload = fallback_response.json()
        return _extract_country_from_geo_fallback(fallback_payload)
    except Exception:
        return None


def _extract_country_from_ip_rdap(payload: dict[str, Any]) -> Optional[str]:
    for key in ("country", "countryCode"):
        candidate = payload.get(key)
        if isinstance(candidate, str) and candidate.strip():
            normalized = _normalize_country_label(candidate)
            if normalized:
                return normalized

    deep_candidate = _find_country_like_value(payload)
    if deep_candidate:
        normalized = _normalize_country_label(deep_candidate)
        if normalized:
            return normalized

    for entity in _iter_rdap_entities(payload.get("entities")):
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


def _extract_country_from_geo_fallback(payload: dict[str, Any]) -> Optional[str]:
    if not isinstance(payload, dict):
        return None
    if payload.get("success") is False:
        return None

    for key in ("country", "country_name"):
        candidate = payload.get(key)
        if isinstance(candidate, str) and candidate.strip():
            normalized = _normalize_country_label(candidate)
            if normalized:
                return normalized

    for key in ("country_code", "countryCode"):
        candidate = payload.get(key)
        if isinstance(candidate, str) and candidate.strip():
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
        if isinstance(value, dict):
            for key in ("country-name", "country", "countryCode"):
                candidate_value = value.get(key)
                if isinstance(candidate_value, str) and candidate_value.strip():
                    return candidate_value.strip()
            label_value = value.get("label")
            if isinstance(label_value, str):
                extracted = _extract_country_from_label(label_value)
                if extracted:
                    return extracted
        if isinstance(value, str):
            extracted = _extract_country_from_label(value)
            if extracted:
                return extracted
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


def _iter_rdap_entities(entities: Any) -> Iterable[dict[str, Any]]:
    if not isinstance(entities, list):
        return
    stack: list[dict[str, Any]] = [entity for entity in entities if isinstance(entity, dict)]
    while stack:
        entity = stack.pop()
        yield entity
        nested = entity.get("entities")
        if isinstance(nested, list):
            stack.extend(item for item in nested if isinstance(item, dict))


def _find_country_like_value(value: Any, depth: int = 0) -> Optional[str]:
    if depth > 5:
        return None
    if isinstance(value, dict):
        for key in ("country", "countryCode", "country-name", "iso3166-1-alpha-2", "iso3166-1-alpha-3"):
            candidate = value.get(key)
            if isinstance(candidate, str) and candidate.strip():
                return candidate.strip()
        for nested in value.values():
            candidate = _find_country_like_value(nested, depth + 1)
            if candidate:
                return candidate
    elif isinstance(value, list):
        for item in value:
            candidate = _find_country_like_value(item, depth + 1)
            if candidate:
                return candidate
    return None


def _extract_country_from_label(label: str) -> Optional[str]:
    chunks = [part.strip() for part in re.split(r"[\n,;]", label or "") if part and part.strip()]
    for chunk in reversed(chunks):
        normalized = _normalize_country_label(chunk)
        if normalized:
            return normalized
        # Caso común: termina con código ISO ("... US")
        m = re.search(r"\b([A-Z]{2,3})\b", chunk.upper())
        if m:
            maybe_iso = _normalize_country_label(m.group(1))
            if maybe_iso:
                return maybe_iso
    return None
