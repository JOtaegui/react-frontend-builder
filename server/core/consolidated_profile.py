"""
consolidated_profile.py — cruce ponderado de datos personales entre remitentes.

Construye el perfil más probable del usuario verificando cruzadamente los
datos personales que cada empresa menciona en sus correos. Para cada uno de
los 5 tipos (nombre, RUT, dirección, teléfono, patente):

1. Canonicaliza y fusiona variantes ("Juan Otaegui" / "JUAN PABLO OTAEGUI" /
   "Juan Otaegui A." votan por el mismo candidato; teléfonos a formato +56;
   RUT validado por dígito verificador; patentes a formato compacto).
2. Cada remitente vota con un peso según su confiabilidad como fuente:
   banco/gobierno pesan más que retail, y mucho más que newsletters o
   sospechosos de data broker. Varios remitentes del mismo dominio
   normalizado cuentan como UNA sola fuente independiente.
3. Bonus por autenticación SPF/DKIM del dominio y por recencia del último
   correo visto (los datos viejos pesan menos: direcciones y teléfonos cambian).
4. Refuerzo cruzado: el nombre que calza con el local-part del correo
   analizado recibe bonus, y los candidatos de otros tipos respaldados por
   las mismas empresas que el nombre ganador se refuerzan.
5. Devuelve por tipo el candidato primario con su nivel de confianza
   (alta/media/baja), las empresas que lo respaldan y hasta 2 alternativas.
"""
from __future__ import annotations

import re
import unicodedata
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Callable, Iterable, Optional

from core.personal_data.address_extractor import address_fingerprint
from core.personal_data.phone_extractor import _normalize_phone as normalize_phone
from core.personal_data.plate_extractor import _normalize_plate as normalize_plate
from core.personal_data.rut_extractor import _normalize_rut as normalize_rut

from models.schemas import (
    ConsolidatedCandidate,
    ConsolidatedDataPoint,
    ConsolidatedUserProfile,
    EmailSearchTargets,
    IdentifiedSender,
)

# Peso base por tipo de remitente: qué tan confiable es como fuente de datos
# personales verificados (un banco valida identidad; un newsletter no).
SENDER_TYPE_WEIGHTS: dict[str, float] = {
    "banco": 3.0,
    "gobierno": 3.0,
    "fintech": 2.5,
    "seguros": 2.5,
    "salud": 2.5,
    "educacion": 2.0,
    "telecom": 2.0,
    "marketplace": 1.5,
    "retail": 1.5,
    "viajes": 1.2,
    "saas": 1.2,
    "servicio_digital": 1.0,
    "newsletter": 0.5,
    "marketing": 0.5,
}
DEFAULT_TYPE_WEIGHT = 1.0
RELIABLE_WEIGHT_THRESHOLD = 1.5
MAX_ALTERNATIVES = 2
MAX_SUPPORTING_COMPANIES = 8


@dataclass
class _Candidate:
    display: str
    score: float = 0.0
    # peso máximo aportado por cada dominio independiente (para contar
    # cuántas fuentes confiables respaldan al candidato)
    domain_weights: dict[str, float] = field(default_factory=dict)
    companies: list[str] = field(default_factory=list)
    last_seen: Optional[str] = None
    name_tokens: tuple[str, ...] = ()

    @property
    def sources(self) -> int:
        return len(self.domain_weights)

    def add_vote(self, domain: str, weight: float, company: str, last_seen: Optional[str]) -> None:
        # un mismo dominio normalizado vota una sola vez por candidato
        if domain in self.domain_weights:
            self.domain_weights[domain] = max(self.domain_weights[domain], weight)
        else:
            self.domain_weights[domain] = weight
            self.score += weight
        if company not in self.companies:
            self.companies.append(company)
        self.last_seen = _max_iso(self.last_seen, last_seen)

    def absorb(self, other: "_Candidate") -> None:
        for domain, weight in other.domain_weights.items():
            if domain in self.domain_weights:
                self.domain_weights[domain] = max(self.domain_weights[domain], weight)
            else:
                self.domain_weights[domain] = weight
                self.score += weight
        for company in other.companies:
            if company not in self.companies:
                self.companies.append(company)
        self.last_seen = _max_iso(self.last_seen, other.last_seen)


def build_consolidated_profile(
    senders: list[IdentifiedSender],
    email_address: Optional[str] = None,
    search_targets: Optional[EmailSearchTargets] = None,
) -> Optional[ConsolidatedUserProfile]:
    if not senders:
        return None

    weights = {id(sender): _sender_weight(sender) for sender in senders}

    names = _collect_candidates(senders, weights, _name_variants)
    names = _merge_name_clusters(names)
    _apply_local_part_bonus(names, email_address)

    ruts = _collect_candidates(senders, weights, _rut_variants)
    addresses = _collect_candidates(senders, weights, _address_variants)
    phones = _collect_candidates(senders, weights, _phone_variants)
    plates = _collect_candidates(senders, weights, _plate_variants)

    best_name = max(names.values(), key=lambda c: c.score) if names else None
    if best_name:
        # refuerzo cruzado: candidatos respaldados por las mismas empresas
        # que el nombre ganador son más creíbles (misma cuenta de cliente)
        winner_domains = set(best_name.domain_weights)
        for pool in (ruts, addresses, phones, plates):
            for candidate in pool.values():
                if winner_domains & set(candidate.domain_weights):
                    candidate.score *= 1.1

    # Un valor que el propio usuario ingresó como objetivo de búsqueda es dato
    # confirmado por él mismo: si ese valor aparece entre los candidatos, debe
    # ganar aunque otro tenga más peso por fuentes.
    if search_targets is not None:
        _apply_target_boost(names, search_targets.nombre, _name_matches_target)
        _apply_target_boost(ruts, search_targets.rut, lambda v, t: normalize_rut(v) == normalize_rut(t))
        _apply_target_boost(addresses, search_targets.direccion, _address_matches_target)
        _apply_target_boost(phones, search_targets.telefono, _phone_matches_target)
        _apply_target_boost(plates, search_targets.patente, lambda v, t: normalize_plate(v) == normalize_plate(t))

    profile = ConsolidatedUserProfile(
        name=_to_data_point(names),
        rut=_to_data_point(ruts),
        address=_to_data_point(addresses),
        phone=_to_data_point(phones),
        plate=_to_data_point(plates),
    )

    # Tras ganar, el valor confirmado por el usuario se marca con confianza alta.
    if search_targets is not None:
        _confirm_with_targets(profile, search_targets)

    if not any([profile.name, profile.rut, profile.address, profile.phone, profile.plate]):
        return None
    return profile


def _apply_target_boost(pool: dict[str, _Candidate], target, matches) -> None:
    """Hace ganar al candidato que coincide con el dato declarado por el usuario."""
    if not target or not str(target).strip():
        return
    for candidate in pool.values():
        try:
            if matches(candidate.display, str(target)):
                candidate.score *= 100.0
        except Exception:
            continue


def _confirm_with_targets(profile: ConsolidatedUserProfile, targets: EmailSearchTargets) -> None:
    """Eleva a confianza alta los datos que coinciden con lo que el usuario
    declaró como propio en los parámetros de búsqueda."""
    checks = [
        (profile.name, targets.nombre, _name_matches_target),
        (profile.rut, targets.rut, lambda v, t: normalize_rut(v) == normalize_rut(t)),
        (profile.address, targets.direccion, _address_matches_target),
        (profile.phone, targets.telefono, _phone_matches_target),
        (profile.plate, targets.patente, lambda v, t: normalize_plate(v) == normalize_plate(t)),
    ]
    for point, target, matches in checks:
        if not point or not target or not str(target).strip():
            continue
        try:
            confirmed = matches(point.value, str(target))
        except Exception:
            confirmed = False
        if confirmed:
            point.confidence_level = "alta"
            point.confidence = max(point.confidence, 0.95)


def _name_matches_target(value: str, target: str) -> bool:
    vt, tt = _name_key_tokens(value), _name_key_tokens(target)
    if not vt or not tt:
        return False
    small, big = (vt, tt) if len(vt) <= len(tt) else (tt, vt)
    return all(tok in big for tok in small)


def _address_matches_target(value: str, target: str) -> bool:
    fv = address_fingerprint(_canonical_address(value))
    ft = address_fingerprint(_canonical_address(target))
    if fv and ft and (fv == ft):
        return True
    a = re.sub(r"[^a-z0-9]+", " ", _strip_accents(value).lower()).strip()
    b = re.sub(r"[^a-z0-9]+", " ", _strip_accents(target).lower()).strip()
    return bool(a) and bool(b) and (a in b or b in a)


def _phone_matches_target(value: str, target: str) -> bool:
    nv, nt = normalize_phone(value), normalize_phone(target)
    if nv and nt:
        return re.sub(r"\D", "", nv)[-8:] == re.sub(r"\D", "", nt)[-8:]
    return False


# ── Peso del remitente ───────────────────────────────────────────────────────

def _sender_weight(sender: IdentifiedSender) -> float:
    weight = SENDER_TYPE_WEIGHTS.get(sender.sender_type, DEFAULT_TYPE_WEIGHT)
    risk = sender.risk
    if risk.suspected_data_broker:
        weight *= 0.2
    if risk.suspicious_infrastructure:
        weight *= 0.3
    if risk.suspected_newsletter:
        weight *= 0.6
    if risk.aggressive_marketing:
        weight *= 0.6
    if _domain_authenticated(sender):
        weight *= 1.2
    weight *= _recency_factor(sender.evidence.last_seen if sender.evidence else None)
    return weight


def _domain_authenticated(sender: IdentifiedSender) -> bool:
    """SPF/DKIM alineado con el dominio del remitente → es quien dice ser."""
    base = sender.normalized_domain
    if not base:
        return False
    return any(domain == base or domain.endswith(f".{base}") for domain in sender.auth_domains)


def _recency_factor(last_seen: Optional[str]) -> float:
    moment = _parse_iso(last_seen)
    if moment is None:
        return 0.8
    days = (datetime.now(timezone.utc) - moment).days
    if days <= 180:
        return 1.0
    if days <= 730:
        return 0.85
    return 0.65


def _parse_iso(value: Optional[str]) -> Optional[datetime]:
    if not value:
        return None
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        return None
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=timezone.utc)
    return parsed


def _max_iso(current: Optional[str], candidate: Optional[str]) -> Optional[str]:
    a, b = _parse_iso(current), _parse_iso(candidate)
    if a is None:
        return candidate or current
    if b is None:
        return current
    return current if a >= b else candidate


# ── Recolección y canonicalización por tipo ──────────────────────────────────

def _collect_candidates(
    senders: list[IdentifiedSender],
    weights: dict[int, float],
    variants_of: Callable[[IdentifiedSender], Iterable[tuple]],
) -> dict[str, _Candidate]:
    """Agrupa valores por clave canónica; cada remitente vota una vez por clave.

    Las variantes pueden incluir un multiplicador opcional como tercer elemento
    para votar con peso reducido (ej. direcciones no primarias de un remitente).
    """
    candidates: dict[str, _Candidate] = {}
    for sender in senders:
        weight = weights[id(sender)]
        last_seen = sender.evidence.last_seen if sender.evidence else None
        seen_keys: set[str] = set()
        for variant in variants_of(sender):
            key, display = variant[0], variant[1]
            mult = variant[2] if len(variant) > 2 else 1.0
            candidate = candidates.get(key)
            if candidate is None:
                candidate = _Candidate(display=display)
                if key.startswith("name:"):
                    candidate.name_tokens = tuple(key[5:].split())
                candidates[key] = candidate
            elif len(display) > len(candidate.display):
                candidate.display = display
            if key not in seen_keys:
                candidate.add_vote(sender.normalized_domain, weight * mult, sender.company_name, last_seen)
                seen_keys.add(key)
    return candidates


def _strip_accents(value: str) -> str:
    return "".join(c for c in unicodedata.normalize("NFD", value) if unicodedata.category(c) != "Mn")


def _name_key_tokens(value: str) -> tuple[str, ...]:
    cleaned = re.sub(r"[^a-z\s]", " ", _strip_accents(value).lower())
    return tuple(token for token in cleaned.split() if token)


def _name_variants(sender: IdentifiedSender) -> Iterable[tuple[str, str]]:
    for name in sender.personal_names:
        tokens = _name_key_tokens(name)
        if not tokens:
            continue
        yield f"name:{' '.join(tokens)}", " ".join(name.split())


def _rut_variants(sender: IdentifiedSender) -> Iterable[tuple[str, str]]:
    for rut in sender.personal_ruts:
        normalized = normalize_rut(rut)
        if normalized is None:
            # dígito verificador inválido → no es un RUT real, se descarta
            continue
        key = normalized.replace(".", "").replace("-", "").lower()
        yield f"rut:{key}", normalized


# abreviaciones comunes de tipo de calle: "Av. Providencia" y
# "Avenida Providencia" deben producir la misma huella
_ADDRESS_ABBREVIATIONS = {
    "av": "avenida",
    "avda": "avenida",
    "pje": "pasaje",
    "psje": "pasaje",
}


def _canonical_address(value: str) -> str:
    return " ".join(
        _ADDRESS_ABBREVIATIONS.get(token.lower().strip(".,"), token)
        for token in value.split()
    )


def _address_variants(sender: IdentifiedSender) -> Iterable[tuple[str, str, float]]:
    # La dirección primaria del remitente (elegida por contexto: "dirección de
    # envío", reincidencia, comuna) vota con peso completo; el resto de las
    # direcciones del mismo remitente suelen ser pies de página corporativos
    # o sucursales, por lo que votan con peso reducido.
    primary = sender.primary_personal_address
    primary_fp = None
    if primary:
        canonical = _canonical_address(primary)
        primary_fp = address_fingerprint(canonical) or canonical.lower().strip()
    for address in sender.personal_addresses:
        canonical = _canonical_address(address)
        fp = address_fingerprint(canonical) or canonical.lower().strip()
        mult = 1.0 if primary_fp is None or fp == primary_fp else 0.4
        yield f"addr:{fp}", address.strip(), mult


def _phone_variants(sender: IdentifiedSender) -> Iterable[tuple[str, str, float]]:
    # El teléfono primario del remitente (elegido por reincidencia y contexto:
    # etiqueta "tu teléfono", despacho, validación cruzada) vota con peso
    # completo; los demás del mismo remitente suelen ser call centers o líneas
    # de atención en la firma, por lo que votan con peso reducido.
    primary = sender.primary_personal_phone
    primary_digits = re.sub(r"\D", "", normalize_phone(primary) or primary or "") if primary else None
    for phone in sender.personal_phones:
        normalized = normalize_phone(phone)
        if not normalized:
            # no es un móvil/fijo chileno válido → se descarta (igual que RUT/patente)
            continue
        digits = re.sub(r"\D", "", normalized)
        mult = 1.0 if primary_digits is None or digits == primary_digits else 0.4
        yield f"phone:{digits}", normalized, mult


def _plate_variants(sender: IdentifiedSender) -> Iterable[tuple[str, str]]:
    for plate in sender.personal_plates:
        normalized = normalize_plate(plate)
        if normalized is None:
            # formato no chileno válido (LLNNNN / LLLLNN) → se descarta
            continue
        yield f"plate:{normalized}", normalized


# ── Fusión de variantes de nombre ────────────────────────────────────────────

def _name_subsumes(big: tuple[str, ...], small: tuple[str, ...]) -> bool:
    """True si cada token de `small` calza con alguno de `big` (exacto o inicial)."""
    if not small or len(small) > len(big):
        return False
    remaining = list(big)
    for token in small:
        match = next(
            (t for t in remaining if t == token or (len(token) == 1 and t.startswith(token))),
            None,
        )
        if match is None:
            return False
        remaining.remove(match)
    return True


def _merge_name_clusters(candidates: dict[str, _Candidate]) -> dict[str, _Candidate]:
    """
    Fusiona nombres parciales en el más completo: "Juan Otaegui" y
    "Juan Otaegui A." suman sus votos a "Juan Pablo Otaegui" si son compatibles.
    """
    ordered = sorted(
        candidates.items(),
        key=lambda item: (-len(item[1].name_tokens), -item[1].score, item[0]),
    )
    clusters: dict[str, _Candidate] = {}
    for key, candidate in ordered:
        target = next(
            (cluster for cluster in clusters.values()
             if _name_subsumes(cluster.name_tokens, candidate.name_tokens)),
            None,
        )
        if target is None:
            clusters[key] = candidate
        else:
            target.absorb(candidate)
    return clusters


def _apply_local_part_bonus(candidates: dict[str, _Candidate], email_address: Optional[str]) -> None:
    """El nombre que aparece en el local-part del correo analizado gana credibilidad."""
    if not email_address or "@" not in email_address:
        return
    local_part = re.sub(r"[^a-z0-9]", "", _strip_accents(email_address.split("@")[0]).lower())
    if len(local_part) < 4:
        return
    for candidate in candidates.values():
        meaningful = [t for t in candidate.name_tokens if len(t) >= 3]
        if not meaningful:
            continue
        matched = [t for t in meaningful if t in local_part]
        if len(matched) >= min(2, len(meaningful)):
            candidate.score *= 1.25


# ── Construcción del resultado ───────────────────────────────────────────────

def _to_data_point(candidates: dict[str, _Candidate]) -> Optional[ConsolidatedDataPoint]:
    if not candidates:
        return None
    ranked = sorted(candidates.values(), key=lambda c: (-c.score, -c.sources, c.display))
    winner = ranked[0]
    total_score = sum(c.score for c in ranked) or 1.0

    # Margen frente al competidor directo, no frente a la suma de todos los
    # candidatos: los correos contienen muchos nombres, teléfonos y direcciones
    # de terceros (ejecutivos, call centers, oficinas) y esa cola de ruido no
    # debe diluir la confianza de un ganador respaldado por fuentes sólidas.
    runner_up_score = ranked[1].score if len(ranked) > 1 else 0.0
    margin = winner.score / (winner.score + runner_up_score) if winner.score > 0 else 0.0

    reliable_sources = sum(
        1 for weight in winner.domain_weights.values() if weight >= RELIABLE_WEIGHT_THRESHOLD
    )
    support_factor = 0.55 if winner.sources == 1 else 0.8 if winner.sources == 2 else 1.0
    confidence = round(min(margin * support_factor, 1.0), 2)

    if reliable_sources >= 2 and margin >= 0.6:
        level = "alta"
    elif winner.sources >= 2 or (reliable_sources >= 1 and margin >= 0.6):
        level = "media"
    else:
        level = "baja"

    alternatives = [
        ConsolidatedCandidate(
            value=candidate.display,
            sources=candidate.sources,
            score=round(candidate.score / total_score, 2),
            supporting_companies=candidate.companies[:MAX_SUPPORTING_COMPANIES],
        )
        for candidate in ranked[1 : 1 + MAX_ALTERNATIVES]
    ]

    return ConsolidatedDataPoint(
        value=winner.display,
        sources=winner.sources,
        confidence=confidence,
        confidence_level=level,
        supporting_companies=winner.companies[:MAX_SUPPORTING_COMPANIES],
        last_seen=winner.last_seen,
        alternatives=alternatives,
    )
