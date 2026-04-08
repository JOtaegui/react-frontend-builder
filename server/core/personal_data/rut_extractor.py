from __future__ import annotations

import re


def extract_chilean_ruts(content: str) -> list[str]:
    if not content:
        return []

    found: list[str] = []
    seen: set[str] = set()
    for match in re.findall(r"\b\d{1,2}\.?\d{3}\.?\d{3}-[\dkK]\b", content):
        normalized = _normalize_rut(match)
        if normalized and normalized not in seen:
            seen.add(normalized)
            found.append(normalized)

    contextual_pattern = r"(?i)(?:rut|run|rol unico tributario|documento)\s*[:#]?\s*(\d{7,8}-[\dkK])"
    for match in re.findall(contextual_pattern, content):
        normalized = _normalize_rut(match)
        if normalized and normalized not in seen:
            seen.add(normalized)
            found.append(normalized)
    return found[:5]


def select_primary_rut(values: list[str]) -> str | None:
    return values[0] if values else None


def _normalize_rut(value: str) -> str | None:
    compact = re.sub(r"[^0-9kK]", "", value)
    if len(compact) < 8 or len(compact) > 9:
        return None
    body = compact[:-1]
    dv = compact[-1].upper()
    if not body.isdigit():
        return None
    if _compute_rut_dv(body) != dv:
        return None

    reversed_body = body[::-1]
    groups = [reversed_body[i:i + 3][::-1] for i in range(0, len(reversed_body), 3)][::-1]
    return f"{'.'.join(groups)}-{dv}"


def _compute_rut_dv(body: str) -> str:
    factors = [2, 3, 4, 5, 6, 7]
    total = 0
    for index, digit in enumerate(reversed(body)):
        total += int(digit) * factors[index % len(factors)]
    remainder = 11 - (total % 11)
    if remainder == 11:
        return "0"
    if remainder == 10:
        return "K"
    return str(remainder)
