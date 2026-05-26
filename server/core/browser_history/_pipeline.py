"""
_pipeline.py — Pipeline de análisis de historial de navegación.

Orquesta las etapas en orden sin contener lógica propia:
  1. Leer filas crudas del DB del navegador  (_readers.py)
  2. Normalizar dominios y acumular por dominio raíz
  3. Clasificar y enriquecer cada dominio     (_data.py + _patterns.py)
  4. Calcular riesgo, datos probables y tags
  5. Ordenar el resultado final

Para modificar el comportamiento de una etapa, edita el módulo correspondiente.
Este archivo solo define el flujo — no la lógica.
"""
from __future__ import annotations

import logging
from typing import Optional
from urllib.parse import urlparse

from ._autofill import AutofillSnapshot
from ._login_data import LoginDataSnapshot
from ._data import IGNORE_DOMAINS, KNOWN_COMPANIES
from ._patterns import ACTIVITY_FLAGS, detect_activity
from ._readers import BaseHistoryReader

logger = logging.getLogger(__name__)

# ── Constantes de ordenación ──────────────────────────────────────────────────
_RISK_ORDER = {"high": 0, "medium": 1, "low": 2}

# ── Tipos de datos por categoría de empresa (complementan actividad detectada) ─
# Los datos_types de KNOWN_COMPANIES ya vienen del _data.py.
# Esta tabla añade datos derivados del TIPO de empresa para empresas desconocidas.
_TYPE_DATA_TYPES: dict[str, list[str]] = {
    "banca":              ["RUT", "datos financieros", "historial de transacciones"],
    "fintech":            ["RUT", "datos financieros"],
    "afp":                ["RUT", "datos financieros", "historial laboral"],
    "salud":              ["RUT", "datos de salud"],
    "telecomunicaciones": ["RUT", "dirección", "historial de llamadas"],
    "data_broker":        ["nombre", "RUT", "dirección", "teléfono"],
    "gobierno":           ["RUT"],
}


# ── Etapa 1: normalización de dominio ─────────────────────────────────────────

def _extract_host(url: str) -> Optional[str]:
    try:
        parsed = urlparse(url)
        host = (parsed.netloc or parsed.path).lower().split(":")[0]
        if host.startswith("www."):
            host = host[4:]
        return host or None
    except Exception:
        return None


def _root_domain(domain: str) -> str:
    """
    Colapsa subdominios al dominio raíz.
    Maneja correctamente .com.cl, .gob.cl, .org.cl, .co.uk, etc.
    """
    parts = domain.split(".")
    if len(parts) <= 2:
        return domain
    penultimate = parts[-2]
    if penultimate in ("com", "org", "gob", "net", "co", "edu"):
        return ".".join(parts[-3:])
    return ".".join(parts[-2:])


# ── Etapa 2: acumulación por dominio ─────────────────────────────────────────

def _accumulate(rows: list[dict]) -> dict[str, dict]:
    """Agrupa las URLs crudas por dominio raíz, acumulando visitas y flags."""
    domain_data: dict[str, dict] = {}

    for row in rows:
        host = _extract_host(row["url"])
        if not host:
            continue
        root = _root_domain(host)
        if root in IGNORE_DOMAINS:
            continue

        parsed = urlparse(row["url"])
        activity = detect_activity(parsed.path + "?" + (parsed.query or ""))

        if root not in domain_data:
            domain_data[root] = {
                "domain":             root,
                "visit_count":        0,
                "last_visit_chrome":  0,
                **{flag: False for flag in ACTIVITY_FLAGS},
            }

        entry = domain_data[root]
        entry["visit_count"] += row["visit_count"]
        if row["last_visit_time"] > entry["last_visit_chrome"]:
            entry["last_visit_chrome"] = row["last_visit_time"]
        for flag in ACTIVITY_FLAGS:
            if activity.get(flag):
                entry[flag] = True

    return domain_data


# ── Etapa 3: clasificación ────────────────────────────────────────────────────

# Qué tipos de datos de autofill son relevantes según la actividad detectada.
# Para agregar un nuevo cruce actividad → tipo de dato: añade aquí.
_ACTIVITY_TO_AUTOFILL: dict[str, list[str]] = {
    "login_detected":    ["email", "username"],
    "signup_detected":   ["email", "nombre", "telefono", "rut", "direccion"],
    "checkout_detected": ["direccion", "rut", "telefono"],
    "profile_detected":  ["nombre", "telefono", "direccion"],
}

_AUTOFILL_SLOT_MAP = {
    "email":     ("Email",     lambda af: af.emails),
    "nombre":    ("Nombre",    lambda af: af.nombres),
    "telefono":  ("Teléfono",  lambda af: af.telefonos),
    "direccion": ("Dirección", lambda af: af.direcciones),
    "rut":       ("RUT",       lambda af: af.ruts),
    "patente":   ("Patente",   lambda af: af.patentes),
    "username":  ("Usuario",   lambda af: af.usernames),
}

_DATA_ORDER = ["email", "nombre", "rut", "telefono", "direccion", "patente", "username"]


def _build_evidence_items(
    root: str,
    activity: dict[str, bool],
    autofill: AutofillSnapshot,
    login_data: LoginDataSnapshot,
    sender_type: str,
    is_chilean: bool,
) -> tuple[list[dict], list[dict]]:
    """
    Construye dos listas de evidencia con sus fuentes:

    confirmed  — datos ligados al dominio exacto (Login Data de Chrome).
                 Chrome solo guarda esto si el usuario realmente hizo login y
                 aceptó guardar la contraseña.  Fuente: "login_guardado"

    autofill_hints — datos que están en el autofill global de Chrome Y cuya
                 categoría coincide con la actividad detectada en este dominio.
                 No prueban que ese valor fue enviado aquí, pero es probable.
                 Fuente: "autofill_global"

    Ambas listas devuelven dicts con:
      { tipo, tipo_key, valores, fuente, evidencia }
    """

    # ── 1) Confirmados por Login Data (per-domain) ────────────────────────────
    confirmed: list[dict] = []
    saved_logins = login_data.get(root)
    if saved_logins:
        usernames = list(dict.fromkeys(l.username for l in saved_logins if l.username))
        uses_total = sum(l.times_used for l in saved_logins)
        confirmed.append({
            "tipo":      "Email / Usuario",
            "tipo_key":  "email",
            "valores":   usernames[:5],
            "fuente":    "login_guardado",
            "evidencia": f"contraseña guardada en Chrome · usado {uses_total}× en este sitio",
        })

    # ── 2) Indicios de autofill global (no per-domain) ───────────────────────
    autofill_hints: list[dict] = []
    if not autofill.disponible:
        return confirmed, autofill_hints

    # Tipos relevantes según actividad
    relevant: set[str] = set()
    for flag, tipos in _ACTIVITY_TO_AUTOFILL.items():
        if activity.get(flag):
            relevant.update(tipos)
    if sender_type in ("banca", "afp", "salud", "fintech", "telecomunicaciones"):
        relevant.add("rut")
    if not is_chilean:
        relevant.discard("rut")
        relevant.discard("patente")

    # Excluir tipos ya confirmados por Login Data para no duplicar email
    confirmed_keys = {c["tipo_key"] for c in confirmed}
    relevant -= confirmed_keys

    for tipo in sorted(relevant, key=lambda t: _DATA_ORDER.index(t) if t in _DATA_ORDER else 99):
        if tipo not in _AUTOFILL_SLOT_MAP:
            continue
        label, get_values = _AUTOFILL_SLOT_MAP[tipo]
        values = get_values(autofill)
        if not values:
            continue  # el usuario no tiene este dato en su autofill → no mostrar

        evidences = [
            flag.replace("_detected", "").replace("_", " ")
            for flag, tipos in _ACTIVITY_TO_AUTOFILL.items()
            if activity.get(flag) and tipo in tipos
        ]
        autofill_hints.append({
            "tipo":      label,
            "tipo_key":  tipo,
            "valores":   values[:5],
            "fuente":    "autofill_global",
            "evidencia": ("actividad de " + " + ".join(evidences)) if evidences else "tipo de empresa",
        })

    return confirmed, autofill_hints


def _classify_entry(
    root: str,
    entry: dict,
    reader: BaseHistoryReader,
    autofill: AutofillSnapshot,
    login_data: LoginDataSnapshot,
) -> dict:
    """
    Enriquece un dominio con metadatos de empresa, riesgo y evidencia de datos.

    Tres niveles de evidencia:
      confirmed_data   — Login Data: email real ingresado en este dominio exacto
      autofill_hints   — Autofill global: dato existe en Chrome, probable que se envió aquí
      probable_data_types — inferido por tipo de empresa / actividad en URL
    """
    known = KNOWN_COMPANIES.get(root)

    activity = {flag: entry[flag] for flag in ACTIVITY_FLAGS}

    # Metadatos de empresa
    company_name = known["company"] if known else _infer_name(root)
    sender_type  = known["type"]    if known else "desconocido"
    is_chilean   = known.get("is_chilean", root.endswith(".cl")) if known else root.endswith(".cl")
    country      = "Chile" if is_chilean else "Internacional"

    # Riesgo
    risk_level = _compute_risk(known, activity, entry["visit_count"])

    # Evidencia de datos (tres niveles)
    confirmed_data, autofill_hints = _build_evidence_items(
        root, activity, autofill, login_data, sender_type, is_chilean
    )

    # Tipos probables: inferidos, excluyendo los ya cubiertos por evidencia real
    covered_keys = {c["tipo_key"] for c in confirmed_data} | {h["tipo_key"] for h in autofill_hints}
    probable_data_types = [
        t for t in _infer_data_types(known, sender_type, activity)
        if t.lower() not in covered_keys
    ]

    # Tags
    tags = _build_tags(is_chilean, activity, sender_type, risk_level)
    if confirmed_data:
        tags.append("login confirmado")
    elif autofill_hints:
        tags.append("datos en autofill")

    return {
        "domain":              root,
        "primary_domain":      root,
        "company_name":        company_name,
        "sender_type":         sender_type,
        "country":             country,
        "is_chilean":          is_chilean,
        "visit_count":         entry["visit_count"],
        "last_visit_iso":      reader.timestamp_to_iso(entry["last_visit_chrome"]),
        **activity,
        "risk_level":          risk_level,
        "confirmed_data":      confirmed_data,       # Login Data: per-domain exacto
        "autofill_hints":      autofill_hints,        # Autofill global: probable
        "probable_data_types": probable_data_types,   # Solo inferencia
        "tags":                tags,
        "known":               known is not None,
        "autofill_available":  autofill.disponible,
        "login_data_available": login_data.disponible,
    }


def _infer_name(domain: str) -> str:
    return domain.split(".")[0].replace("-", " ").replace("_", " ").title()


def _compute_risk(
    known: Optional[dict],
    activity: dict[str, bool],
    visit_count: int,
) -> str:
    """
    Reglas de riesgo. Para agregar una regla nueva:
      - si depende de `known`: añade aquí.
      - si depende de actividad: añade a la sección de actividad.
    """
    base = known.get("risk", "low") if known else "low"

    if base == "high":
        return "high"

    has_sensitive_activity = (
        activity.get("login_detected")
        or activity.get("checkout_detected")
    )
    if base == "medium" and has_sensitive_activity:
        return "high"
    if base == "low" and has_sensitive_activity:
        return "medium"

    return base


def _infer_data_types(
    known: Optional[dict],
    sender_type: str,
    activity: dict[str, bool],
) -> list[str]:
    """
    Combina tres fuentes de datos probables:
      1. Los declarados explícitamente en KNOWN_COMPANIES[domain].data_types
      2. Los asociados al tipo de empresa (_TYPE_DATA_TYPES)
      3. Los inferidos por actividad detectada en URL
    """
    types: list[str] = []

    # Fuente 1: declarados en _data.py
    if known:
        types += known.get("data_types", [])

    # Fuente 2: por tipo de empresa (solo si es desconocida o no tiene data_types)
    if not (known and known.get("data_types")):
        types += _TYPE_DATA_TYPES.get(sender_type, [])

    # Fuente 3: por actividad en URL
    if activity.get("login_detected") or activity.get("signup_detected"):
        types += ["email", "contraseña"]
    if activity.get("checkout_detected"):
        types += ["dirección", "tarjeta de crédito", "RUT"]
    if activity.get("profile_detected"):
        types += ["nombre", "teléfono"]

    # Deduplicar manteniendo orden
    return list(dict.fromkeys(types))


def _build_tags(
    is_chilean: bool,
    activity: dict[str, bool],
    sender_type: str,
    risk_level: str,
) -> list[str]:
    """
    Para agregar un tag nuevo: añade una condición aquí.
    El nombre del tag es lo que ve el usuario en el frontend.
    """
    tags: list[str] = []
    if is_chilean:
        tags.append("chileno")
    if activity.get("login_detected"):
        tags.append("login")
    if activity.get("signup_detected"):
        tags.append("registro")
    if activity.get("checkout_detected"):
        tags.append("compra")
    if sender_type == "data_broker":
        tags.append("data broker")
    if risk_level == "high":
        tags.append("riesgo alto")
    return tags


# ── Etapa 4: ordenación ───────────────────────────────────────────────────────

def _sort(companies: list[dict]) -> list[dict]:
    """Primero alto riesgo, luego por visitas descendente."""
    return sorted(
        companies,
        key=lambda x: (_RISK_ORDER.get(x["risk_level"], 3), -x["visit_count"]),
    )


# ── Punto de entrada del pipeline ────────────────────────────────────────────

def run_pipeline(
    reader: BaseHistoryReader,
    limit: int = 5000,
    autofill: Optional[AutofillSnapshot] = None,
    login_data: Optional[LoginDataSnapshot] = None,
) -> list[dict]:
    """
    Ejecuta el pipeline completo de forma sincrónica.

    autofill:   datos globales de formularios (autofill table de Web Data)
    login_data: contraseñas guardadas por dominio (Login Data) → evidencia exacta
    """
    if autofill is None:
        autofill = AutofillSnapshot(disponible=False)
    if login_data is None:
        login_data = LoginDataSnapshot(disponible=False)

    rows        = reader.read_raw(limit)
    accumulated = _accumulate(rows)
    classified  = [
        _classify_entry(root, entry, reader, autofill, login_data)
        for root, entry in accumulated.items()
    ]
    return _sort(classified)
