from __future__ import annotations

from dataclasses import dataclass
import re

PLATE_PATTERN = re.compile(r"\b([A-Z]{4}[-.\s]?\d{2}|[A-Z]{2}[-.\s]?\d{4})\b", re.IGNORECASE)
COMMON_SPANISH_BIGRAMS = {
    "de",
    "la",
    "el",
    "al",
    "en",
    "un",
    "tu",
    "su",
    "mi",
    "se",
    "te",
    "le",
}
COMMON_NON_PLATE_WORDS = {
    "hora",
    "fecha",
    "cita",
    "club",
    "folio",
    "orden",
    "turno",
    "pago",
    "pase",
    "sala",
    "mesa",
    "tipo",
    "ruta",
}
PLATE_CONTEXT_KEYWORDS = (
    "patente",
    "placa",
    "ppu",
    "vehiculo",
    "vehículo",
    "automovil",
    "automóvil",
    "auto",
    "camioneta",
    "moto",
    "motocicleta",
    "seguro",
    "soap",
    "poliza",
    "póliza",
    "certificado",
    "revision tecnica",
    "revisión técnica",
    "permiso de circulacion",
    "permiso de circulación",
    "tag",
    "siniestro",
    "cobertura",
    "deducible",
    "inscripcion",
    "inscripción",
    "padron",
    "padrón",
)
WEAK_FALSE_POSITIVE_HINTS = (
    "codigo",
    "código",
    "token",
    "otp",
    "clave",
    "pedido",
    "orden",
    "seguimiento",
)
MEDIUM_PLATE_CONTEXT_KEYWORDS = (
    "vehiculo",
    "vehículo",
    "automovil",
    "automóvil",
    "auto",
    "camioneta",
    "moto",
    "motocicleta",
    "seguro",
    "soap",
    "poliza",
    "póliza",
    "certificado",
    "revision tecnica",
    "revisión técnica",
    "permiso de circulacion",
    "permiso de circulación",
    "siniestro",
    "cobertura",
    "deducible",
    "inscripcion",
    "inscripción",
    "padron",
    "padrón",
)


@dataclass(frozen=True)
class PlateMatch:
    plate: str
    evidence: str


def extract_chilean_plates(content: str) -> list[str]:
    return [match.plate for match in extract_chilean_plate_matches(content)]


def extract_chilean_plate_matches(content: str) -> list[PlateMatch]:
    if not content:
        return []

    found: list[PlateMatch] = []
    seen: set[str] = set()
    for match in PLATE_PATTERN.finditer(content):
        raw_match = match.group(1)
        normalized = _normalize_plate(raw_match)
        if not normalized or normalized in seen:
            continue
        start = max(0, match.start() - 120)
        end = min(len(content), match.end() + 120)
        window = content[start:end]
        if not _is_valid_plate_candidate(raw_match, normalized, window):
            continue
        if not _is_likely_plate_context(window):
            continue
        if _plate_format(normalized) == "legacy" and not _has_explicit_plate_marker(window):
            continue

        seen.add(normalized)
        found.append(PlateMatch(plate=normalized, evidence=_compact_snippet(window, normalized)))

    return found[:5]


def select_primary_plate(values: list[str]) -> str | None:
    if not values:
        return None
    return min(values, key=lambda value: (_plate_priority(value), len(value), value))


def _normalize_plate(value: str) -> str | None:
    compact = re.sub(r"[^A-Z0-9]", "", value.upper())
    if re.fullmatch(r"[A-Z]{4}\d{2}", compact):
        return compact
    if re.fullmatch(r"[A-Z]{2}\d{4}", compact):
        return compact
    return None


def _is_likely_plate_context(window: str) -> bool:
    normalized_window = _normalize_text(window)
    keyword_hits = sum(1 for keyword in PLATE_CONTEXT_KEYWORDS if _contains_keyword(normalized_window, keyword))
    weak_hits = sum(1 for keyword in WEAK_FALSE_POSITIVE_HINTS if _contains_keyword(normalized_window, keyword))
    medium_hits = sum(1 for keyword in MEDIUM_PLATE_CONTEXT_KEYWORDS if _contains_keyword(normalized_window, keyword))

    if any(_contains_keyword(normalized_window, keyword) for keyword in ("patente", "ppu", "placa")):
        return True
    if medium_hits >= 2:
        return True
    return False


def _is_valid_plate_candidate(raw_value: str, normalized_value: str, window: str) -> bool:
    letters = normalized_value[:2]
    digits = normalized_value[2:] if len(normalized_value) == 6 else normalized_value[4:]
    raw_letters = re.sub(r"[^A-Za-z]", "", raw_value)
    has_explicit_marker = _has_explicit_plate_marker(window)

    if len(normalized_value) == 6:
        if letters.lower() in COMMON_SPANISH_BIGRAMS:
            return False
        if digits.startswith(("19", "20")):
            return False
        if raw_letters.islower():
            return False

    if _plate_format(normalized_value) == "modern":
        # Las patentes chilenas modernas (post-2007, LLLL##) usan un alfabeto
        # de consonantes: NUNCA contienen vocales. En los 5 sujetos, las 30
        # patentes confirmadas son solo-consonantes y el único candidato con
        # vocal era el FP "HORA17".
        if re.search(r"[AEIOU]", normalized_value[:4]):
            return False
        # Palabra común escrita como prosa ("Hora 17", "Pago 56"): se rechaza
        # SIEMPRE, incluso con marcador de patente en la ventana. En los 5
        # sujetos, "HORA17" se capturó ×2 porque el correo de agendamiento
        # mencionaba 'patente' en otra parte. Una patente real se escribe en
        # mayúsculas y sin espacio entre letras y dígitos.
        word_like = (
            raw_letters.lower() in COMMON_NON_PLATE_WORDS
            or _looks_like_common_word(raw_letters)
        )
        written_as_plate = raw_letters.isupper() and not re.search(r"\s", raw_value)
        if word_like and not written_as_plate:
            return False
        if raw_letters.lower() in COMMON_NON_PLATE_WORDS and not has_explicit_marker:
            return False
        if not raw_letters.isupper() and not has_explicit_marker:
            return False
        if _looks_like_common_word(raw_letters) and not has_explicit_marker:
            return False

    return True


def _normalize_text(value: str) -> str:
    return (
        value.lower()
        .replace("á", "a")
        .replace("é", "e")
        .replace("í", "i")
        .replace("ó", "o")
        .replace("ú", "u")
    )


def _compact_snippet(window: str, normalized_plate: str) -> str:
    compact = re.sub(r"\s+", " ", window).strip()
    compact = compact[:180].strip()
    if normalized_plate not in compact.upper():
        return compact
    return compact


def _plate_format(value: str) -> str:
    if re.fullmatch(r"[A-Z]{4}\d{2}", value):
        return "modern"
    if re.fullmatch(r"[A-Z]{2}\d{4}", value):
        return "legacy"
    return "unknown"


def _plate_priority(value: str) -> int:
    plate_format = _plate_format(value)
    if plate_format == "modern":
        return 0
    if plate_format == "legacy":
        return 1
    return 2


def _has_explicit_plate_marker(window: str) -> bool:
    normalized_window = _normalize_text(window)
    return any(_contains_keyword(normalized_window, marker) for marker in ("patente", "ppu", "placa"))


def _contains_keyword(text: str, keyword: str) -> bool:
    if " " in keyword:
        return keyword in text
    return re.search(rf"\b{re.escape(keyword)}\b", text) is not None


def _looks_like_common_word(raw_letters: str) -> bool:
    letters = raw_letters.lower()
    if letters in COMMON_NON_PLATE_WORDS:
        return True
    vowels = set("aeiou")
    vowel_count = sum(1 for char in letters if char in vowels)
    return len(letters) >= 4 and vowel_count >= 1 and letters.isalpha()
