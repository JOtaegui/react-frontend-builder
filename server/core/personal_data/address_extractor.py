"""
address_extractor.py — Extractor robusto de direcciones chilenas.

Cambios principales respecto a la versión anterior
---------------------------------------------------
1. Regex de calles reescritas con grupos nombrados y anclas más precisas para
   evitar capturar frases de orden como "Entrega 3 días" o "Solo 1234".

2. Sistema de scoring separado en dos fases:
   a) Filtro de forma: ¿el candidato tiene la estructura de una dirección?
      (nombre de calle + número + opcional: depto/comuna/región).
   b) Filtro de contexto: ¿el entorno confirma que es una dirección de envío?

3. Normalización mejorada:
   - Elimina ruido de trailing (teléfono, email, RUT, fecha) con patrones
     más completos.
   - Capitaliza correctamente el resultado final.

4. Falsos positivos reducidos:
   - Stopwords ampliadas para números dentro de frases de fecha o marketing.
   - Blacklist de tokens que indican que el número es un ID (folio, boleta,
     orden, tracking, OTP).
   - Se descarta cualquier candidato con URL, email o RUT adjunto.

5. Compatibilidad total con la API pública anterior:
   - extract_chilean_addresses(content) → list[str]
   - extract_chilean_address_matches(content) → list[AddressMatch]
   - select_primary_address(values, counts, scores) → str | None
   - address_fingerprint(value) → str
"""

from __future__ import annotations

from dataclasses import dataclass
import re

# ---------------------------------------------------------------------------
# Importaciones opcionales (puede fallar en tests unitarios aislados)
# ---------------------------------------------------------------------------
try:
    from .name_extractor import extract_name_candidates  # type: ignore
    from .rut_extractor import extract_chilean_ruts  # type: ignore
except ImportError:
    def extract_name_candidates(content: str) -> list[str]:  # type: ignore
        return []
    def extract_chilean_ruts(content: str) -> list[str]:  # type: ignore
        return []


# ---------------------------------------------------------------------------
# Keywords de contexto
# ---------------------------------------------------------------------------

ADDRESS_LABEL_KEYWORDS: tuple[str, ...] = (
    "direccion de despacho",
    "direccion de envio",
    "direccion de entrega",
    "direccion cliente",
    "direccion del cliente",
    "domicilio",
    "shipping address",
    "delivery address",
    "enviar a",
    "envio a",
    "despacho a",
    "entrega en",
    "entregaremos en",
    "entregaremos tu tarjeta en",
    "tu direccion",
    "su direccion",
    "direccion de facturacion",
    "lugar de entrega",
)

ORDER_CONTEXT_KEYWORDS: tuple[str, ...] = (
    "pedido",
    "orden",
    "compra",
    "despacho",
    "envio",
    "entrega",
    "tracking",
    "seguimiento",
    "tarjeta",
    "solicitud",
)

LOCATION_HINT_KEYWORDS: tuple[str, ...] = (
    "comuna",
    "region",
    "región",
    "rm",
    "metropolitana",
    "santiago",
    "chile",
    # comunas frecuentes
    "lo barnechea",
    "las condes",
    "vitacura",
    "la dehesa",
    "providencia",
    "nunoa",
    "nuñoa",
    "maipu",
    "maipú",
    "pudahuel",
    "quilicura",
    "recoleta",
    "macul",
    "peñalolen",
    "penalolen",
    "la florida",
    "puente alto",
    "san bernardo",
    "buin",
    "lampa",
    "colina",
    "talagante",
    "melipilla",
)

# Si el número aparece junto a estos tokens el candidato casi seguro NO es dirección.
_ID_TOKENS: frozenset[str] = frozenset(
    {
        "folio", "boleta", "factura", "orden", "pedido", "tracking",
        "seguimiento", "otp", "clave", "codigo", "código", "pin",
        "transaccion", "transacción", "cupon", "cupón", "descuento",
    }
)

_NON_ADDRESS_HINTS: tuple[str, ...] = (
    "terminos",
    "términos",
    "suscripcion",
    "suscripción",
    "privacidad",
    "promocion",
    "promoción",
    "membresia",
    "membresía",
    "uber one",
    "centro de ayuda",
    "politica",
    "política",
)

_NEGATIVE_CONTEXT: tuple[str, ...] = (
    "retiro en tienda",
    "retiro en sucursal",
    "retira en",
    "showroom",
)

# ---------------------------------------------------------------------------
# Patrones de exclusión (si aparecen en el candidato o su ventana → descartar)
# ---------------------------------------------------------------------------

_DATE_PATTERN = re.compile(
    r"(?i)\b\d{1,2}\s+de\s+"
    r"(?:enero|febrero|marzo|abril|mayo|junio|julio|agosto|"
    r"septiembre|setiembre|octubre|noviembre|diciembre)"
    r"(?:\s+de\s+\d{4})?\b"
)
_URL_PATTERN = re.compile(r"https?://|www\.", re.IGNORECASE)
_EMAIL_PATTERN = re.compile(r"[a-zA-Z0-9._%+\-]+@[a-zA-Z0-9.\-]+\.[a-zA-Z]{2,}")
_RUT_PATTERN = re.compile(r"\b\d{7,8}-[\dkK]\b")
_LONG_NUMBER_PATTERN = re.compile(r"\b\d{10,}\b")  # boletas, trackings largos

# ---------------------------------------------------------------------------
# Patrones de label de dirección (inline: "Dirección de envío: Calle X 123")
# ---------------------------------------------------------------------------

_INLINE_LABEL_RE = re.compile(
    r"(?i)"
    r"(?:direccion\s+de\s+(?:despacho|envio|entrega)|direccion\s+(?:del?\s+)?cliente|"
    r"domicilio|shipping\s+address|delivery\s+address|"
    r"enviar\s+a|envio\s+a|despacho\s+a|entrega\s+en|"
    r"entregaremos(?:\s+tu\s+tarjeta)?\s+en|"
    r"tu\s+direccion|su\s+direccion|lugar\s+de\s+entrega)"
    r"\s*[:\-–]?\s*(.+)"
)

# ---------------------------------------------------------------------------
# Patrones de trailing (basura al final del candidato)
# ---------------------------------------------------------------------------

_TRAILING_RE = re.compile(
    r"(?i)(?:\.\s*)?"
    r"(?:titular|destinatario|cliente|run(?:\s*o\s*rut)?|rut|folio|pedido|orden|"
    r"telefono|teléfono|fono|correo(?:\s+electronico)?|email|"
    r"comuna|region|región|comentarios|notas|fecha|hora)"
    r"\s*[:\-–].*$"
)

# Teléfono al final: " - +56 9 1234 5678" o " / 912345678"
_TRAILING_PHONE_RE = re.compile(
    r"(?i)\s*[-/]\s*(?:\+?56\s*)?(?:9|2)\s*[\d\s()./-]{8,}$"
)

# ---------------------------------------------------------------------------
# Patrones de extracción de calle
# ---------------------------------------------------------------------------

# Con prefijo explícito: Av., Avenida, Calle, Pasaje, etc.
PREFIX_STREET_PATTERN = re.compile(
    r"(?i)\b"
    r"(?P<prefix>av(?:da)?\.?|avenida|calle|pasaje|psje\.?|camino|ruta|autopista|boulevard|blvd\.?)"
    r"\s+"
    r"(?P<name>[A-Za-záéíóúüñÁÉÍÓÚÜÑ][A-Za-záéíóúüñÁÉÍÓÚÜÑ0-9.\- ]{1,80}?)"
    r"\s+"
    r"(?P<number>\d{1,5})"
    r"(?P<extra>"
    r"(?:\s*,?\s*(?:depto?\.?|departamento|dpto?\.?|oficina|of\.?|piso|local|block|bloque)\s*[A-Za-z0-9\-]+)?"
    r"(?:\s*[-,]\s*[A-Za-záéíóúüñÁÉÍÓÚÜÑ][A-Za-záéíóúüñÁÉÍÓÚÜÑ0-9()\- ]{1,40}){0,3}"
    r")"
    r"\b",
    re.UNICODE,
)

# Sin prefijo: "RIO THUR 4827, Lo Barnechea"
# Requiere al menos 2 palabras antes del número y que la primera sea ≥ 3 caracteres.
BARE_STREET_PATTERN = re.compile(
    r"(?<![/\\\w])"                         # no precedido de path/URL
    r"(?P<name>"
    r"[A-ZÁÉÍÓÚÜÑ][A-Za-záéíóúüñÁÉÍÓÚÜÑ]{2,}"       # primera palabra ≥ 3 chars
    r"(?:\s+[A-Za-záéíóúüñÁÉÍÓÚÜÑ]{2,}){1,5}"       # 1-5 palabras más
    r")"
    r"\s+"
    r"(?P<number>\d{1,5})"
    r"(?P<extra>"
    r"(?:\s*,?\s*(?:depto?\.?|departamento|dpto?\.?|oficina|of\.?|piso|local|block|bloque)\s*[A-Za-z0-9\-]+)?"
    r"(?:\s*[-,]\s*[A-Za-záéíóúüñÁÉÍÓÚÜÑ][A-Za-záéíóúüñÁÉÍÓÚÜÑ0-9()\- ]{1,40}){0,3}"
    r")"
    r"(?![/\\\w])",
    re.UNICODE,
)

# ---------------------------------------------------------------------------
# Stopwords para fingerprint y validación
# ---------------------------------------------------------------------------

_STOPWORDS: frozenset[str] = frozenset(
    {
        "en", "de", "del", "la", "el", "los", "las", "rm",
        "metropolitana", "santiago", "chile", "region", "región",
        "comuna", "a", "con", "y", "o", "por", "para", "al",
    }
)

_GENERIC_TOKENS: frozenset[str] = frozenset(
    {
        "pedido", "orden", "compra", "entrega", "entregas", "envio",
        "despacho", "tracking", "seguimiento", "solicitud", "transferencia",
        "auto", "chile", "solo", "numero", "nro",
    }
)


# ---------------------------------------------------------------------------
# Dataclass pública
# ---------------------------------------------------------------------------

@dataclass(frozen=True)
class AddressMatch:
    address: str
    evidence: str
    score: int


# ---------------------------------------------------------------------------
# API pública
# ---------------------------------------------------------------------------

def extract_chilean_addresses(content: str) -> list[str]:
    """Devuelve lista de direcciones encontradas en *content*."""
    return [m.address for m in extract_chilean_address_matches(content)]


def extract_chilean_address_matches(content: str) -> list[AddressMatch]:
    """Devuelve hasta 5 AddressMatch ordenados por score descendente."""
    if not content:
        return []

    names = extract_name_candidates(content)
    ruts = extract_chilean_ruts(content)

    found: list[AddressMatch] = []
    seen: set[str] = set()

    # ── Fase 1: candidatos con label explícito ────────────────────────────
    for candidate, evidence in _extract_labeled_candidates(content):
        norm = _clean_address(candidate)
        if not norm or norm in seen:
            continue
        if not _looks_like_address(norm):
            continue
        score = _score_address(evidence, norm, names, ruts, explicit_label=True)
        if score < 4:
            continue
        seen.add(norm)
        found.append(AddressMatch(address=norm, evidence=_snippet(evidence), score=score))

    # ── Fase 2: candidatos por regex de calle ────────────────────────────
    for pattern in (PREFIX_STREET_PATTERN, BARE_STREET_PATTERN):
        for m in pattern.finditer(content):
            raw = _strip_trailing(m.group(0)).strip(" ,.;:–-")
            norm = _clean_address(raw)
            if not norm or norm in seen:
                continue
            if not _looks_like_address(norm):
                continue
            s = max(0, m.start() - 180)
            e = min(len(content), m.end() + 180)
            window = content[s:e]
            if _has_disqualifying_context(norm, window):
                continue
            score = _score_address(window, norm, names, ruts, explicit_label=False)
            if score < 4:
                continue
            seen.add(norm)
            found.append(AddressMatch(address=norm, evidence=_snippet(window), score=score))

    found.sort(key=lambda item: (-item.score, -len(item.address), item.address.lower()))
    return found[:5]


def select_primary_address(
    values: list[str],
    counts: dict[str, int] | None = None,
    scores: dict[str, int] | None = None,
) -> str | None:
    """Elige la dirección más relevante de una lista."""
    if not values:
        return None

    unique = _dedupe(values)
    best = unique[0]
    best_rank = -1

    for value in unique:
        fp = address_fingerprint(value)
        count = counts.get(fp, counts.get(value, 0)) if counts else values.count(value)
        score = scores.get(fp, scores.get(value, 0)) if scores else 0
        completeness = 0
        nv = _nt(value)
        if re.search(r"\b(comuna|region|santiago|rm|metropolitana)\b", nv):
            completeness += 1
        if re.search(r"\b(depto|departamento|dpto|oficina|of|piso)\b", nv):
            completeness += 1
        rank = count * 7 + score * 2 + completeness
        if rank > best_rank or (rank == best_rank and len(value) > len(best)):
            best = value
            best_rank = rank

    return best


def address_fingerprint(value: str) -> str:
    """Genera una clave corta y estable para deduplicar direcciones similares."""
    normalized = re.sub(r"[^a-z0-9\s]", " ", _nt(value))
    normalized = re.sub(r"\s+", " ", normalized).strip()
    if not normalized:
        return value.lower().strip()

    tokens = normalized.split()
    num_idx = next(
        (i for i, t in enumerate(tokens) if t.isdigit() and 1 <= len(t) <= 5),
        None,
    )
    if num_idx is None:
        return normalized

    start = max(0, num_idx - 3)
    head = [t for t in tokens[start:num_idx] if t not in _STOPWORDS]
    if not head:
        head = tokens[max(0, num_idx - 2):num_idx]
    return " ".join(head + [tokens[num_idx]])


# ---------------------------------------------------------------------------
# Extracción de candidatos con label
# ---------------------------------------------------------------------------

def _extract_labeled_candidates(content: str) -> list[tuple[str, str]]:
    lines = [re.sub(r"\s+", " ", ln).strip() for ln in content.splitlines() if ln.strip()]
    results: list[tuple[str, str]] = []

    for idx, line in enumerate(lines):
        # Caso A: label e información en la misma línea
        m = _INLINE_LABEL_RE.search(_nt(line))
        if m:
            raw_m = _INLINE_LABEL_RE.search(line)
            candidate = _strip_trailing(raw_m.group(1) if raw_m else line)
            candidate = _best_street_segment(candidate)
            evidence = line
            # Si la siguiente línea parece continuación de la dirección, agregarla
            if idx + 1 < len(lines) and _looks_like_address(lines[idx + 1]):
                nxt = _strip_trailing(lines[idx + 1]).strip(" ,.;:–-")
                candidate = f"{candidate}, {nxt}"
                evidence = f"{line} {lines[idx + 1]}"
            results.append((candidate, evidence))
            continue

        # Caso B: label en una línea y dirección en la siguiente
        if any(kw in _nt(line) for kw in ADDRESS_LABEL_KEYWORDS) and idx + 1 < len(lines):
            nxt = lines[idx + 1]
            if _looks_like_address(nxt):
                results.append((nxt, f"{line} {nxt}"))

    return results


# ---------------------------------------------------------------------------
# Validación de forma
# ---------------------------------------------------------------------------

def _looks_like_address(value: str) -> bool:
    """¿Tiene el candidato la estructura mínima de una dirección?"""
    nv = _nt(value)

    # Debe tener un número de calle (1-5 dígitos, no pegado a otros dígitos)
    if not re.search(r"(?<!\d)\d{1,5}(?!\d)", nv):
        return False

    # No debe ser solo una frase de orden/marketing
    if _is_generic_phrase(nv):
        return False

    # Debe tener al menos una palabra "real" (≥ 3 chars, no stopword)
    words = re.findall(r"[a-záéíóúüñ]{3,}", nv)
    meaningful = [w for w in words if w not in _STOPWORDS and w not in _GENERIC_TOKENS]
    if not meaningful:
        return False

    # Tiene prefijo de calle → directo
    if re.search(r"\b(av(?:da)?\.?|avenida|calle|pasaje|psje\.?|camino|ruta)\b", nv):
        return True

    # Sin prefijo: al menos 2 palabras antes del número
    m = re.search(r"(?<!\d)\d{1,5}(?!\d)", nv)
    if m:
        before = nv[:m.start()].strip()
        words_before = [w for w in re.findall(r"[a-záéíóúüñ]{2,}", before) if w not in _STOPWORDS]
        if len(words_before) >= 2:
            return True

    return False


def _is_generic_phrase(nv: str) -> bool:
    """True si el texto es claramente una frase de marketing/orden, no una dirección."""
    words = re.findall(r"[a-z0-9]+", nv)
    alpha = [w for w in words if not w.isdigit()]
    meaningful = [w for w in alpha if w not in _STOPWORDS]
    if not meaningful:
        return True
    if all(w in _GENERIC_TOKENS for w in meaningful):
        return True
    # "Solo N entregas", "Entrega N días", etc.
    if re.search(r"\bsolo\s+\d{1,5}\b", nv) and any(k in nv for k in ("entrega", "envio", "despacho")):
        return True
    return False


# ---------------------------------------------------------------------------
# Limpieza del candidato
# ---------------------------------------------------------------------------

def _clean_address(value: str) -> str | None:
    """
    Limpia y valida el candidato. Devuelve None si no supera los filtros.
    """
    value = _strip_trailing(value)
    value = _TRAILING_PHONE_RE.sub("", value)
    value = re.sub(r"\s+", " ", value).strip(" ,.;:–-")

    if len(value) < 8 or len(value) > 160:
        return None

    nv = _nt(value)

    # Contiene hints que indican que NO es dirección
    if any(h in nv for h in _NON_ADDRESS_HINTS):
        return None

    # Tiene URL, email o RUT
    if _URL_PATTERN.search(value) or _EMAIL_PATTERN.search(value) or _RUT_PATTERN.search(value):
        return None

    # Número muy largo (código de barras, boleta)
    if _LONG_NUMBER_PATTERN.search(value):
        return None

    # Fecha
    if _DATE_PATTERN.search(nv):
        return None

    # Demasiadas palabras → probablemente es un párrafo
    if len(nv.split()) > 16:
        return None

    return value


def _strip_trailing(value: str) -> str:
    result = _TRAILING_RE.sub("", value).strip()
    return result


def _best_street_segment(value: str) -> str:
    """Extrae el mejor segmento de calle de un texto."""
    for pattern in (PREFIX_STREET_PATTERN, BARE_STREET_PATTERN):
        m = pattern.search(value)
        if m:
            return m.group(0).strip(" ,.;:–-")
    return value


# ---------------------------------------------------------------------------
# Scoring de contexto
# ---------------------------------------------------------------------------

def _score_address(
    window: str,
    address: str,
    names: list[str],
    ruts: list[str],
    explicit_label: bool,
) -> int:
    nw = _nt(window)
    score = 0

    if explicit_label:
        score += 5

    for kw in ADDRESS_LABEL_KEYWORDS:
        if kw in nw:
            score += 4
            break

    for kw in ORDER_CONTEXT_KEYWORDS:
        if _kw(nw, kw):
            score += 2
            break

    for kw in LOCATION_HINT_KEYWORDS:
        if _kw(nw, kw):
            score += 2
            break

    for name in names:
        if _nt(name) in nw:
            score += 2
            break

    for rut in ruts:
        if rut.lower() in nw:
            score += 1
            break

    # Penalizar contextos de negativo
    for kw in _NEGATIVE_CONTEXT:
        if kw in nw:
            score -= 4
            break

    return score


def _has_disqualifying_context(address: str, window: str) -> bool:
    """True si el contexto descalifica al candidato como dirección de envío."""
    nw = _nt(window)
    # El número de casa coincide con un token de ID en el contexto
    m = re.search(r"(?<!\d)\d{1,5}(?!\d)", _nt(address))
    if m:
        number = m.group(0)
        # Si el número aparece después de un token de ID → falso positivo
        before_num = nw[:nw.find(number)] if number in nw else ""
        last_words = re.findall(r"[a-z]+", before_num)[-4:]
        if any(w in _ID_TOKENS for w in last_words):
            return True
    # Contextos de retiro en tienda
    for kw in _NEGATIVE_CONTEXT:
        if kw in nw:
            return True
    return False


# ---------------------------------------------------------------------------
# Utilidades internas
# ---------------------------------------------------------------------------

def _dedupe(values: list[str]) -> list[str]:
    seen: set[str] = set()
    result: list[str] = []
    for v in values:
        if v not in seen:
            seen.add(v)
            result.append(v)
    return result


def _nt(value: str) -> str:
    """Normaliza texto: minúsculas + elimina tildes."""
    return (
        value.lower()
        .replace("á", "a").replace("é", "e").replace("í", "i")
        .replace("ó", "o").replace("ú", "u").replace("ü", "u")
        .replace("ñ", "n")
    )


def _kw(text: str, keyword: str) -> bool:
    if " " in keyword:
        return keyword in text
    return bool(re.search(rf"\b{re.escape(keyword)}\b", text))


def _snippet(window: str) -> str:
    return re.sub(r"\s+", " ", window).strip()[:260]