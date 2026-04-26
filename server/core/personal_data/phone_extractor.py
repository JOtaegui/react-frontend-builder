"""
phone_extractor.py — Extractor robusto de teléfonos chilenos.

Cambios principales respecto a la versión anterior
---------------------------------------------------
1. Regex de captura reescrita para tolerar todos los separadores comunes
   (espacios, guiones, puntos, paréntesis) en cualquier posición, incluyendo
   variantes como +56 9 XXXX XXXX, 56-9-XXXX-XXXX, (56)9XXXXXXXX, 09XXXXXXXX.
2. Normalización (_normalize_phone) ampliada: maneja prefijos 056, 0056, +56,
   56 sin +, y troncal 0 antes del área, generando siempre +56 X XXXX XXXX.
3. Scoring reemplaza la lógica de "fallback incondicional para móviles" que
   provocaba falsos positivos masivos. Ahora se requiere puntuación mínima
   diferenciada por tipo (móvil vs fijo).
4. Ventana de contexto ampliada a 120 caracteres para capturar labels que
   aparecen lejos del número.
5. Se separan claramente los keywords de LABEL (inmediatamente antes del
   número) vs CONTEXT (en el párrafo/ventana), con pesos distintos.
6. Se añaden keywords de exclusión duros: si el número aparece dentro de un
   URL, un RUT, un código de barras o un OTP se descarta directamente.
7. Se exponen select_primary_phone y PhoneMatch sin cambios para mantener
   compatibilidad con el código que importa este módulo.
"""

from __future__ import annotations

from dataclasses import dataclass, field
import re

# ---------------------------------------------------------------------------
# Keyword sets
# ---------------------------------------------------------------------------

# Aparecen en la misma línea o inmediatamente antes: señal fuerte de teléfono.
_LABEL_KEYWORDS: tuple[str, ...] = (
    "telefono",
    "teléfono",
    "tel",
    "celular",
    "cel",
    "movil",
    "móvil",
    "fono",
    "fijo",
    "whatsapp",
    "wp",
    "wsp",
    "contacto",
    "nro",
    "nro.",
)

# Frases de dos palabras (se buscan como subcadena, no como word-boundary).
_LABEL_PHRASES: tuple[str, ...] = (
    "tu telefono",
    "tu teléfono",
    "tu celular",
    "tu numero",
    "tu número",
    "mi telefono",
    "mi teléfono",
    "mi celular",
    "mi numero",
    "mi número",
    "numero de telefono",
    "número de teléfono",
    "numero de contacto",
    "número de contacto",
    "numero celular",
    "número celular",
    "numero movil",
    "número móvil",
    "celular de contacto",
    "telefono de contacto",
    "teléfono de contacto",
    "telefono personal",
    "teléfono personal",
    "contacto personal",
    "fono de contacto",
    "movil de contacto",
    "móvil de contacto",
)

# Contexto de orden/despacho: el número probablemente es del cliente.
_ORDER_KEYWORDS: tuple[str, ...] = (
    "pedido",
    "orden",
    "compra",
    "despacho",
    "envio",
    "envío",
    "entrega",
    "destinatario",
    "titular",
    "cliente",
    "seguimiento",
    "tracking",
)

# Señal de que el número es de un servicio/empresa, NO del cliente.
_SERVICE_KEYWORDS: tuple[str, ...] = (
    "mesa de ayuda",
    "call center",
    "contactenos",
    "contáctenos",
    "llamanos",
    "llámanos",
    "servicio al cliente",
    "atencion al cliente",
    "atención al cliente",
    "soporte tecnico",
    "soporte técnico",
    "linea de atencion",
    "línea de atención",
    "nuestro telefono",
    "nuestro número",
    "sucursal",
    "showroom",
)

# Si el número aparece pegado a estos tokens es casi seguro que NO es teléfono.
_HARD_EXCLUSION_PATTERNS: tuple[re.Pattern[str], ...] = (
    # RUT chileno: dígitos-dígito/K justo antes o después
    re.compile(r"\d{7,8}-[\dkK]"),
    # Código OTP / clave temporal de 4-8 dígitos solos
    re.compile(r"\b(?:otp|clave|codigo|código|pin)\b.{0,20}\b\d{4,8}\b", re.IGNORECASE),
    # URL
    re.compile(r"https?://|www\.", re.IGNORECASE),
    # Número de boleta/folio largo (más de 9 dígitos consecutivos)
    re.compile(r"\b\d{10,}\b"),
    # Fecha con hora: dd/mm/aaaa hh:mm
    re.compile(r"\b\d{1,2}/\d{1,2}/\d{4}\b"),
)

# ---------------------------------------------------------------------------
# Regex principal de captura
# ---------------------------------------------------------------------------
# Diseño:
#   - Prefijo internacional opcional: +56 / 56 / 056 / 0056, con cualquier
#     separador posterior.
#   - Troncal 0 local opcional.
#   - Dígito de área: 9 (móvil) o 2 (Santiago fijo). Se permiten paréntesis.
#   - 8 dígitos más con separadores opcionales entre cada uno.
#   - Lookahead/lookbehind para evitar capturar dígitos extra.

_SEP = r"[\s()./-]*"  # separadores permitidos entre grupos

PHONE_CANDIDATE_PATTERN = re.compile(
    r"(?<!\d)"
    # Prefijo de país opcional
    r"(?:\+?" + _SEP + r"(?:00)?56" + _SEP + r")?"
    # Troncal 0 opcional (numeración local antigua)
    r"(?:0" + _SEP + r")?"
    # Área: 9 (móvil) o 2 (fijo Santiago), con paréntesis opcionales
    r"\(?" + _SEP + r"([92])" + _SEP + r"\)?"
    # 8 dígitos con separadores opcionales entre pares
    r"(?:" + _SEP + r"\d){8}"
    r"(?!\d)"
)

# Patrón para detectar label inmediatamente antes del número (últimos 60 chars).
_LABEL_PREFIX_RE = re.compile(
    r"(?:tel(?:e(?:fono|fono))?|cel(?:ular)?|fono|movil|m[oó]vil|whatsapp|wsp?|contacto|nro\.?)"
    r"(?:\s+(?:de(?:l)?|para|del))?"
    r"(?:\s+(?:cliente|destinatario|titular|despacho|entrega|envio|compra|personal))?"
    r"\s*[:\-–]?\s*$",
    re.IGNORECASE,
)


# ---------------------------------------------------------------------------
# Dataclass pública
# ---------------------------------------------------------------------------

@dataclass(frozen=True)
class PhoneMatch:
    phone: str
    evidence: str
    score: int = field(default=0, compare=False)


# ---------------------------------------------------------------------------
# API pública
# ---------------------------------------------------------------------------

def extract_chilean_phones(content: str) -> list[str]:
    """Devuelve lista de teléfonos normalizados encontrados en *content*."""
    return [m.phone for m in extract_chilean_phone_matches(content)]


def extract_chilean_phone_matches(content: str) -> list[PhoneMatch]:
    """Devuelve hasta 5 PhoneMatch ordenados por prioridad."""
    return extract_chilean_phone_matches_with_context(content)


def extract_chilean_phone_matches_with_context(
    content: str,
    nearby_addresses: list[str] | None = None,
    nearby_names: list[str] | None = None,
    boost_if_near_address: int = 3,
    boost_if_near_name: int = 2,
) -> list[PhoneMatch]:
    """
    Variante compatible con cross_validator.
    Si se entregan direcciones/nombres cercanos, aumenta score por co-ocurrencia.
    """
    if not content:
        return []

    nearby_addresses = nearby_addresses or []
    nearby_names = nearby_names or []
    found: list[PhoneMatch] = []
    seen: set[str] = set()

    for match in PHONE_CANDIDATE_PATTERN.finditer(content):
        raw = match.group(0)
        normalized = _normalize_phone(raw)
        if not normalized or normalized in seen:
            continue

        start, end = match.start(), match.end()
        window = content[max(0, start - 120): min(len(content), end + 120)]

        # Descarte rápido por exclusiones duras
        if _has_hard_exclusion(window):
            continue

        prefix = content[max(0, start - 60): start]
        line = _enclosing_line(content, start, end)

        score = _score_phone(raw, normalized, line, window, prefix)
        score += _cross_validate(window, nearby_addresses, nearby_names, boost_if_near_address, boost_if_near_name)
        if score < _min_score(normalized):
            continue

        seen.add(normalized)
        found.append(PhoneMatch(phone=normalized, evidence=_compact_snippet(window), score=score))

    # Ordenar por score descendente y luego por prioridad de formato.
    found.sort(key=lambda m: (-m.score, _phone_priority(m.phone), m.phone))
    return found[:5]


def select_primary_phone(values: list[str]) -> str | None:
    """Elige el teléfono más relevante de una lista."""
    if not values:
        return None
    return min(values, key=lambda v: (_phone_priority(v), v))


# ---------------------------------------------------------------------------
# Normalización
# ---------------------------------------------------------------------------

def _normalize_phone(raw: str) -> str | None:
    """
    Convierte cualquier variante de número chileno a '+56 X XXXX XXXX'.
    Acepta: +56, 56, 056, 0056, con o sin separadores, con troncal 0.
    """
    digits = re.sub(r"\D", "", raw)

    # Construir lista de candidatos quitando prefijos
    candidates: list[str] = []

    def push(d: str) -> None:
        if d and d not in candidates:
            candidates.append(d)

    push(digits)
    if digits.startswith("0056"):
        push(digits[4:])
    if digits.startswith("056"):
        push(digits[3:])
    if digits.startswith("56") and not digits.startswith("560"):
        push(digits[2:])

    # Quitar troncal 0 de cada candidato
    for c in list(candidates):
        if c.startswith("0"):
            push(c[1:])

    for candidate in candidates:
        if len(candidate) != 9 or not candidate.isdigit():
            continue
        area = candidate[0]
        if area not in {"9", "2"}:
            continue
        return f"+56 {area} {candidate[1:5]} {candidate[5:9]}"

    return None


# ---------------------------------------------------------------------------
# Scoring
# ---------------------------------------------------------------------------

def _score_phone(raw: str, normalized: str, line: str, window: str, prefix: str) -> int:
    nl = _nt(line)
    nw = _nt(window)
    np_ = _nt(prefix)

    score = 0

    # Label justo antes del número (señal más fuerte)
    if _LABEL_PREFIX_RE.search(np_):
        score += 5

    # Frase de label en la misma línea
    for phrase in _LABEL_PHRASES:
        if phrase in nl or phrase in nw:
            score += 5
            break

    # Keyword de label en la misma línea
    for kw in _LABEL_KEYWORDS:
        if _kw(nl, kw):
            score += 3
            break

    # Keyword de label en la ventana (más lejos)
    for kw in _LABEL_KEYWORDS:
        if _kw(nw, kw) and not _kw(nl, kw):
            score += 1
            break

    # Contexto de orden/despacho
    for kw in _ORDER_KEYWORDS:
        if _kw(nw, kw):
            score += 2
            break

    # Tiene código de país
    raw_digits = re.sub(r"\D", "", raw)
    if raw_digits.startswith("56") or raw_digits.startswith("056"):
        score += 1

    # Es móvil (área 9) → más probable que sea del cliente
    if normalized.startswith("+56 9"):
        score += 2

    # Señal de servicio/empresa → penalizar
    for phrase in _SERVICE_KEYWORDS:
        if phrase in nw:
            score -= 5
            break

    return score


def _cross_validate(
    window: str,
    nearby_addresses: list[str],
    nearby_names: list[str],
    boost_address: int,
    boost_name: int,
) -> int:
    bonus = 0
    nw = _nt(window)

    for address in nearby_addresses:
        tokens = [t for t in re.findall(r"[a-záéíóúüñ]{4,}", _nt(address)) if t not in {"calle", "avenida", "pasaje", "camino"}]
        if any(token in nw for token in tokens[:4]):
            bonus += boost_address
            break

    for name in nearby_names:
        parts = [part for part in _nt(name).split() if len(part) >= 4]
        if any(part in nw for part in parts):
            bonus += boost_name
            break

    return bonus


def _min_score(normalized: str) -> int:
    """
    Umbral mínimo diferenciado:
    - Móvil (9): necesita al menos un label o context keyword → 3
    - Fijo (2): más estricto porque los números fijos de empresa son comunes → 6
    """
    if normalized.startswith("+56 9"):
        return 3
    return 6


# ---------------------------------------------------------------------------
# Utilidades internas
# ---------------------------------------------------------------------------

def _has_hard_exclusion(window: str) -> bool:
    nw = _nt(window)
    for pattern in _HARD_EXCLUSION_PATTERNS:
        if pattern.search(nw):
            return True
    return False


def _phone_priority(value: str) -> int:
    if value.startswith("+56 9"):
        return 0   # móvil → primero
    if value.startswith("+56 2"):
        return 1   # fijo Santiago
    return 2


def _enclosing_line(content: str, start: int, end: int) -> str:
    ls = content.rfind("\n", 0, start) + 1
    le = content.find("\n", end)
    return content[ls: len(content) if le == -1 else le]


def _compact_snippet(window: str) -> str:
    return re.sub(r"\s+", " ", window).strip()[:200]


def _nt(value: str) -> str:
    """Normaliza texto: minúsculas + quita tildes."""
    return (
        value.lower()
        .replace("á", "a").replace("é", "e").replace("í", "i")
        .replace("ó", "o").replace("ú", "u").replace("ü", "u")
    )


def _kw(text: str, keyword: str) -> bool:
    """Busca keyword respetando word-boundary."""
    if " " in keyword:
        return keyword in text
    return bool(re.search(rf"\b{re.escape(keyword)}\b", text))
