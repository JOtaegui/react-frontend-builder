from __future__ import annotations

import re

# Palabras clave que indican que un número es efectivamente un RUT personal
_RUT_LABEL_RE = re.compile(
    r"(?i)\b(?:rut|r\.u\.t|run|r\.u\.n|rol\s+unico|rol\s+único|"
    r"cedula|cédula|documento\s+de\s+identidad|id\s+tributari[oa])\b"
)

# Palabras clave de contexto personal que dan confianza (sin label directo)
_PERSONAL_CONTEXT_RE = re.compile(
    r"(?i)\b(?:nombre|cliente|titular|usuario|beneficiario|propietario|"
    r"apellido|nacimiento|fecha\s+de\s+nacimiento|afiliado|asegurado|"
    r"tomador|contratante|representante|trabajador|empleado)\b"
)

# Ventana de caracteres alrededor del match donde buscar contexto
_CONTEXT_WINDOW = 200

# El SII asigna RUT >= 50.000.000 a personas jurídicas (empresas). En la
# evaluación con 5 sujetos, 101/322 RUT detectados eran jurídicos y ninguno
# correspondía al titular: son el RUT del emisor en boletas/facturas.
_RUT_JURIDICO_MIN = 50_000_000
# Cuerpos bajo 1M son históricos/reservados; en correos son ruido (folios).
_RUT_NATURAL_MIN = 1_000_000


def is_rut_juridico(rut: str) -> bool:
    """True si el RUT pertenece a una persona jurídica (cuerpo >= 50M)."""
    body = re.sub(r"[^0-9]", "", rut)[:-1]
    return body.isdigit() and int(body) >= _RUT_JURIDICO_MIN


def extract_chilean_ruts(content: str) -> list[str]:
    """
    Extrae RUTs válidos del contenido.

    Un RUT se incluye si:
    - Tiene un label explícito cerca ("rut:", "run:", "cédula", etc.), O
    - Está en un contexto personal (nombre, titular, cliente, etc.), O
    - Aparece más de una vez en el contenido (alta confianza por repetición).

    RUTs que aparecen solos sin ningún contexto (probable ID de orden/transacción)
    son descartados para evitar falsos positivos.
    """
    if not content:
        return []

    scored: dict[str, int] = {}   # rut_normalizado → score máximo
    content_lower = content.lower()

    # ── 1) Patrón formateado con o sin puntos ─────────────────────────────
    for m in re.finditer(r"\b\d{1,2}\.?\d{3}\.?\d{3}-[\dkK]\b", content):
        normalized = _normalize_rut(m.group(0))
        if not normalized:
            continue
        score = _context_score(content, m.start(), m.end())
        # Bonus por repetición
        count = len(re.findall(re.escape(m.group(0)), content))
        if count >= 2:
            score += 3
        scored[normalized] = max(scored.get(normalized, 0), score)

    # ── 2) Patrón contextual con label ("rut: 12345678-9") ─────────────────
    for m in re.finditer(
        r"(?i)(?:rut|run|r\.u\.t|cedula|cédula|documento)\s*[:#/]?\s*(\d{7,8}-[\dkK])",
        content,
    ):
        normalized = _normalize_rut(m.group(1))
        if not normalized:
            continue
        # Tiene label explícito → siempre confiable
        scored[normalized] = max(scored.get(normalized, 0), 10)

    # ── 3) Patrón sin guion (111111111 → 9 dígitos) ────────────────────────
    # Solo con label explícito para evitar capturar números de orden/teléfono
    for m in re.finditer(
        r"(?i)(?:rut|run|r\.u\.t|cedula|cédula)\s*[:#/]?\s*(\d{8,9})\b",
        content,
    ):
        normalized = _normalize_rut(m.group(1))
        if not normalized:
            continue
        scored[normalized] = max(scored.get(normalized, 0), 10)

    # Filtrar: solo incluir RUTs con score >= 2 (tienen contexto o se repiten)
    MIN_SCORE = 2
    found = [rut for rut, score in scored.items() if score >= MIN_SCORE]

    # Ordenar por score descendente para que el más confiable quede primero
    found.sort(key=lambda r: -scored[r])
    return found[:5]


def _context_score(content: str, start: int, end: int) -> int:
    """
    Puntúa la confianza de un RUT según su contexto cercano.
    0 = sin contexto personal (probable falso positivo)
    """
    s = max(0, start - _CONTEXT_WINDOW)
    e = min(len(content), end + _CONTEXT_WINDOW)
    window = content[s:e]

    score = 0
    if _RUT_LABEL_RE.search(window):
        score += 8   # label explícito de RUT
    if _PERSONAL_CONTEXT_RE.search(window):
        score += 3   # contexto personal (nombre, cliente, etc.)
    return score


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
    # Solo RUT de persona natural: los jurídicos (>= 50M) son el RUT del
    # emisor de la boleta, no un dato personal del titular.
    if not (_RUT_NATURAL_MIN <= int(body) < _RUT_JURIDICO_MIN):
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
