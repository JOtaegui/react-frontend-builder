from __future__ import annotations

import re

PLATE_CONTEXT_PATTERNS = [
    r"(?i)(?:patente|placa|ppu|vehiculo|automovil|auto)\s*(?:del|de|:|#)?\s*([A-Z]{4}[-\s]?\d{2})\b",
    r"(?i)(?:patente|placa|ppu|vehiculo|automovil|auto)\s*(?:del|de|:|#)?\s*([A-Z]{2}[-\s]?\d{4})\b",
]


def extract_chilean_plates(content: str) -> list[str]:
    if not content:
        return []

    found: list[str] = []
    seen: set[str] = set()
    for pattern in PLATE_CONTEXT_PATTERNS:
        for match in re.findall(pattern, content.upper()):
            normalized = _normalize_plate(match)
            if normalized and normalized not in seen:
                seen.add(normalized)
                found.append(normalized)
    return found[:5]


def select_primary_plate(values: list[str]) -> str | None:
    return values[0] if values else None


def _normalize_plate(value: str) -> str | None:
    compact = re.sub(r"[^A-Z0-9]", "", value.upper())
    if re.fullmatch(r"[A-Z]{4}\d{2}", compact):
        return compact
    if re.fullmatch(r"[A-Z]{2}\d{4}", compact):
        return compact
    return None
