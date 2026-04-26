"""
cross_validator.py — Verificación cruzada de datos de contacto en emails chilenos.

Propósito
---------
Este módulo orquesta los extractores de dirección y teléfono para obtener
resultados más precisos cuando ambos aparecen en el mismo email.

La idea central es simple pero poderosa:
  "Una señal débil de dirección + una señal débil de teléfono en la misma
   zona del texto = una señal fuerte de que ambos son reales."

Algoritmo
---------
1. Primera pasada rápida sin cruce: extraer teléfonos y direcciones
   independientemente con sus scores base.
2. Segunda pasada con cruce: volver a puntuar cada candidato usando como
   contexto los candidatos de la otra entidad.
3. Resolver ambigüedades: si hay múltiples teléfonos o direcciones,
   preferir los que co-ocurren en la misma ventana de texto.
4. Calcular confianza global: refleja qué tan consistente es la evidencia.

API pública
-----------
    extract_contact_info(content, name_hints?) → ContactInfo
    ContactInfo.address   → str | None
    ContactInfo.phone     → str | None
    ContactInfo.confidence → float   (0.0 – 1.0)
    ContactInfo.details   → dict     (scores, evidencias, candidatos rechazados)

Compatibilidad
--------------
Funciona como módulo standalone. Si los extractores individuales están en el
mismo paquete, importarlos directamente es preferible para evitar re-parsear.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Any

# ---------------------------------------------------------------------------
# Importaciones de los extractores
# ---------------------------------------------------------------------------
try:
    from .phone_extractor import (  # type: ignore
        extract_chilean_phone_matches_with_context,
        PhoneMatch,
    )
    from .address_extractor import (  # type: ignore
        extract_chilean_address_matches_with_context,
        AddressMatch,
    )
except ImportError:
    from phone_extractor import (
        extract_chilean_phone_matches_with_context,
        PhoneMatch,
    )
    from address_extractor import (
        extract_chilean_address_matches_with_context,
        AddressMatch,
    )


# ---------------------------------------------------------------------------
# Dataclass de resultado
# ---------------------------------------------------------------------------

@dataclass
class ContactInfo:
    """
    Resultado consolidado de la extracción de datos de contacto.

    Atributos
    ---------
    address    : Dirección de envío primaria, o None si no se encontró.
    phone      : Teléfono primario, o None si no se encontró.
    confidence : Float entre 0.0 y 1.0 que refleja la certeza global.
                 - 0.8–1.0: dirección Y teléfono encontrados con buena evidencia.
                 - 0.5–0.79: solo uno encontrado con buena evidencia, o ambos débiles.
                 - 0.2–0.49: candidatos encontrados pero con poca evidencia.
                 - 0.0: nada encontrado.
    details    : Diccionario con candidatos descartados, scores y evidencias.
    """
    address: str | None
    phone: str | None
    confidence: float
    details: dict[str, Any] = field(default_factory=dict)

    def __repr__(self) -> str:
        return (
            f"ContactInfo(\n"
            f"  address={self.address!r},\n"
            f"  phone={self.phone!r},\n"
            f"  confidence={self.confidence:.2f}\n"
            f")"
        )


# ---------------------------------------------------------------------------
# API pública principal
# ---------------------------------------------------------------------------

def extract_contact_info(
    content: str,
    name_hints: list[str] | None = None,
    *,
    min_confidence: float = 0.0,
) -> ContactInfo:
    """
    Extrae dirección y teléfono de un email (plain text o HTML limpio).

    Parámetros
    ----------
    content       : Texto del email (HTML debe venir pre-limpiado o como text/plain).
    name_hints    : Nombres de persona ya conocidos (ej: del campo "To:" del email).
                    Mejoran el scoring cuando aparecen cerca de la dirección o teléfono.
    min_confidence: Si la confianza calculada está por debajo de este umbral,
                    address y phone se devuelven como None aunque existan candidatos.

    Devuelve
    --------
    ContactInfo con los mejores candidatos y la confianza calculada.
    """
    if not content:
        return ContactInfo(address=None, phone=None, confidence=0.0)

    content = _preprocess(content)
    name_hints = name_hints or []

    # ── Pasada 1: extracción independiente ───────────────────────────────
    raw_phones = extract_chilean_phone_matches_with_context(
        content, nearby_names=name_hints
    )
    raw_addresses = extract_chilean_address_matches_with_context(
        content, nearby_names=name_hints
    )

    # ── Pasada 2: extracción cruzada ──────────────────────────────────────
    phone_values = [m.phone for m in raw_phones]
    address_values = [m.address for m in raw_addresses]

    crossed_phones = extract_chilean_phone_matches_with_context(
        content,
        nearby_addresses=address_values,
        nearby_names=name_hints,
    )
    crossed_addresses = extract_chilean_address_matches_with_context(
        content,
        nearby_phones=phone_values,
        nearby_names=name_hints,
    )

    # ── Resolución de ambigüedad por co-ocurrencia ────────────────────────
    best_phone, best_address = _resolve_best_pair(
        crossed_phones, crossed_addresses, content
    )

    # ── Confianza global ──────────────────────────────────────────────────
    confidence = _compute_confidence(best_phone, best_address, crossed_phones, crossed_addresses)

    # ── Armar details ─────────────────────────────────────────────────────
    details: dict[str, Any] = {
        "phone_candidates": [
            {"phone": m.phone, "score": m.score, "evidence": m.evidence[:80]}
            for m in crossed_phones
        ],
        "address_candidates": [
            {"address": m.address, "score": m.score, "evidence": m.evidence[:80]}
            for m in crossed_addresses
        ],
        "co_occurrence_boost_applied": best_phone is not None and best_address is not None,
    }

    # Aplicar umbral mínimo
    if confidence < min_confidence:
        return ContactInfo(
            address=None, phone=None, confidence=confidence, details=details
        )

    return ContactInfo(
        address=best_address.address if best_address else None,
        phone=best_phone.phone if best_phone else None,
        confidence=confidence,
        details=details,
    )


# ---------------------------------------------------------------------------
# Resolución del mejor par (dirección, teléfono)
# ---------------------------------------------------------------------------

def _resolve_best_pair(
    phones: list[PhoneMatch],
    addresses: list[AddressMatch],
    content: str,
) -> tuple[PhoneMatch | None, AddressMatch | None]:
    """
    Elige el par (teléfono, dirección) que maximiza la co-ocurrencia en el texto.

    Estrategia:
    1. Si hay un único teléfono y una única dirección → par directo.
    2. Si hay múltiples de alguno → buscar el par con mayor solapamiento
       de ventana en el texto original.
    3. Fallback: tomar el de mayor score individual.
    """
    if not phones and not addresses:
        return None, None
    if not phones:
        return None, max(addresses, key=lambda a: a.score)
    if not addresses:
        return max(phones, key=lambda p: p.score), None

    if len(phones) == 1 and len(addresses) == 1:
        return phones[0], addresses[0]

    # Buscar par con mayor co-ocurrencia
    best_score = -1
    best_p: PhoneMatch = phones[0]
    best_a: AddressMatch = addresses[0]

    for p in phones:
        for a in addresses:
            cooc = _cooccurrence_score(p, a, content)
            combined = p.score + a.score + cooc
            if combined > best_score:
                best_score = combined
                best_p = p
                best_a = a

    return best_p, best_a


def _cooccurrence_score(p: PhoneMatch, a: AddressMatch, content: str) -> int:
    """
    Calcula cuánto se solapan las ventanas de evidencia de teléfono y dirección.
    Si el número del teléfono aparece en la evidencia de la dirección o viceversa,
    suma puntos.
    """
    score = 0
    phone_digits = re.sub(r"\D", "", p.phone)[-8:]
    addr_fragment = _nt(a.address[:20])

    if phone_digits and phone_digits in re.sub(r"\D", "", a.evidence):
        score += 4
    if addr_fragment and addr_fragment in _nt(p.evidence):
        score += 4

    # Proximidad en el texto: si ambas evidencias comparten palabras únicas
    p_words = set(re.findall(r"[a-záéíóúüñ]{4,}", _nt(p.evidence)))
    a_words = set(re.findall(r"[a-záéíóúüñ]{4,}", _nt(a.evidence)))
    shared = p_words & a_words - _COMMON_WORDS
    score += min(len(shared), 3)  # máximo 3 puntos por palabras compartidas

    return score


_COMMON_WORDS: frozenset[str] = frozenset({
    "para", "este", "esta", "como", "donde", "cuando", "tiene",
    "numero", "datos", "cliente", "correo", "contacto",
})


# ---------------------------------------------------------------------------
# Cálculo de confianza
# ---------------------------------------------------------------------------

def _compute_confidence(
    best_phone: PhoneMatch | None,
    best_address: AddressMatch | None,
    all_phones: list[PhoneMatch],
    all_addresses: list[AddressMatch],
) -> float:
    """
    Calcula un score de confianza 0.0–1.0.

    Factores:
    - Ambos encontrados con score alto → alta confianza.
    - Solo uno encontrado → confianza media.
    - Múltiples candidatos en conflicto → penalización.
    - Scores bajos → confianza baja.
    """
    if not best_phone and not best_address:
        return 0.0

    raw = 0.0

    # Contribución del teléfono
    if best_phone:
        phone_conf = min(best_phone.score / 10.0, 1.0)
        raw += phone_conf * 0.45

    # Contribución de la dirección
    if best_address:
        addr_conf = min(best_address.score / 12.0, 1.0)
        raw += addr_conf * 0.45

    # Bonus por co-ocurrencia (ambos presentes)
    if best_phone and best_address:
        raw += 0.15

    # Penalización por ambigüedad (muchos candidatos → menos certeza)
    if len(all_phones) > 2:
        raw *= 0.90
    if len(all_addresses) > 2:
        raw *= 0.90

    return round(min(raw, 1.0), 3)


# ---------------------------------------------------------------------------
# Pre-procesamiento
# ---------------------------------------------------------------------------

def _preprocess(content: str) -> str:
    """
    Limpieza básica del contenido:
    - Elimina tags HTML simples.
    - Normaliza saltos de línea y espacios múltiples.
    - Decodifica entidades HTML comunes.
    """
    # Eliminar tags HTML
    content = re.sub(r"<[^>]{1,200}>", " ", content)

    # Entidades HTML frecuentes
    _HTML_ENTITIES = {
        "&nbsp;": " ", "&amp;": "&", "&lt;": "<", "&gt;": ">",
        "&quot;": '"', "&#39;": "'", "&aacute;": "á", "&eacute;": "é",
        "&iacute;": "í", "&oacute;": "ó", "&uacute;": "ú",
        "&ntilde;": "ñ", "&Aacute;": "Á", "&Eacute;": "É",
        "&Iacute;": "Í", "&Oacute;": "Ó", "&Uacute;": "Ú",
        "&Ntilde;": "Ñ", "&#xA0;": " ",
    }
    for entity, char in _HTML_ENTITIES.items():
        content = content.replace(entity, char)

    # Normalizar saltos de línea y espacios
    content = re.sub(r"\r\n|\r", "\n", content)
    content = re.sub(r"[ \t]+", " ", content)
    content = re.sub(r"\n{3,}", "\n\n", content)

    return content.strip()


def _nt(value: str) -> str:
    return (
        value.lower()
        .replace("á", "a").replace("é", "e").replace("í", "i")
        .replace("ó", "o").replace("ú", "u").replace("ü", "u")
        .replace("ñ", "n")
    )


# ---------------------------------------------------------------------------
# CLI rápido para pruebas
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    import sys

    _SAMPLE = """
    Estimado cliente,

    Tu pedido #98234 ha sido confirmado.

    Datos de despacho:
    Nombre: María González López
    Dirección de envío: Av. Apoquindo 4501, Depto 802, Las Condes
    Teléfono: +56 9 8812 3456
    Comuna: Las Condes, Región Metropolitana

    El envío llegará en 3-5 días hábiles.

    Si tienes consultas, escríbenos a soporte@tienda.cl
    o llama a nuestra línea de atención: 600 700 8000

    ¡Gracias por tu compra!
    """

    source = sys.argv[1] if len(sys.argv) > 1 else _SAMPLE
    if source != _SAMPLE and len(source) < 200:
        try:
            with open(source, encoding="utf-8") as fh:
                source = fh.read()
        except FileNotFoundError:
            pass

    result = extract_contact_info(source, name_hints=["María González"])
    print(result)
    print("\n── Candidatos ──")
    for pc in result.details.get("phone_candidates", []):
        print(f"  TEL  score={pc['score']:>3}  {pc['phone']}  [{pc['evidence'][:60]}]")
    for ac in result.details.get("address_candidates", []):
        print(f"  DIR  score={ac['score']:>3}  {ac['address']}  [{ac['evidence'][:60]}]")