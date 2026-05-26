"""
_autofill.py — Lee los datos de autofill guardados en Chrome Web Data.

Dos fuentes complementarias:
  1. tabla `autofill`            — (field_name, value, count) global, sin dominio
  2. tabla `address_type_tokens` — perfil estructurado (nombre, email, tel, dirección)
                                   con códigos de tipo de Chrome ServerFieldType

Limitación conocida: `autofill` no tiene columna de dominio.
El pipeline cruza estos valores con la actividad detectada en cada empresa
para determinar qué datos probablemente recibieron.

Para agregar nuevos patrones de field name: edita FIELD_CLASSIFIERS.
Para agregar nuevos códigos de tipo Chrome: edita ADDRESS_TYPE_CODES.
"""
from __future__ import annotations

import shutil
import sqlite3
from dataclasses import dataclass, field
from pathlib import Path
from typing import Optional

WEB_DATA_PATH = (
    Path.home()
    / "Library" / "Application Support"
    / "Google" / "Chrome" / "Default" / "Web Data"
)
WEB_DATA_TMP = Path("/tmp/chrome_webdata_osint_tmp.db")

# ── Mapeo de nombre de campo HTML → categoría de dato ─────────────────────────
# Para agregar una categoría nueva: añade una clave y sus patrones.
# Los patrones se comparan en lowercase con `in` (substring match).
FIELD_CLASSIFIERS: dict[str, list[str]] = {
    "email":    ["email", "mail", "correo", "emailaddress", "resolvinginput"],
    "rut":      ["rut", "run", "rutclient", "input-rut", "company_rut",
                 "beneficiario_rut", "bankrut", "cedula", "nrocliente"],
    "telefono": ["phone", "tel", "telefono", "celular", "mobile", "fono",
                 "phonenumber", "movil"],
    "nombre":   ["nombre", "firstname", "lastname", "apellido", "fullname",
                 "beneficiario_nombre", "accountholder", "name"],
    "direccion":["address", "direccion", "street", "calle", "domicilio",
                 "company_address", "location", "eventlocation"],
    "patente":  ["placa", "patente", "plate", "input-placa", "matricula"],
    "username": ["username", "user", "login"],
    "rut_empresa": ["company_rut", "rut_empresa", "bankrut"],
}

# ── Códigos Chrome ServerFieldType → categoría semántica ──────────────────────
# Fuente: chromium/src/components/autofill/core/browser/field_types.h
ADDRESS_TYPE_CODES: dict[int, str] = {
    3:   "nombre",    # NAME_FIRST
    4:   "nombre",    # NAME_MIDDLE
    5:   "nombre",    # NAME_LAST
    7:   "nombre",    # NAME_FULL
    9:   "email",     # EMAIL_ADDRESS
    14:  "telefono",  # PHONE_HOME_WHOLE_NUMBER
    30:  "direccion", # ADDRESS_HOME_STREET_ADDRESS (legacy LINE1)
    31:  "direccion", # ADDRESS_HOME_LINE2
    32:  "direccion", # ADDRESS_HOME_APT_NUM
    35:  "ciudad",    # ADDRESS_HOME_CITY
    36:  "region",    # ADDRESS_HOME_STATE
    37:  "cod_postal",# ADDRESS_HOME_ZIP
    38:  "pais",      # ADDRESS_HOME_COUNTRY
    60:  "telefono",  # PHONE_HOME_CITY_AND_NUMBER
    77:  "nombre",    # NAME_LAST_SECOND
    79:  "nombre",    # NAME_LAST_FIRST
}


@dataclass
class AutofillSnapshot:
    """
    Resumen de datos personales encontrados en Chrome Web Data.

    emails / nombres / telefonos / direcciones / ruts / patentes:
        valores únicos encontrados en los formularios del usuario.
    tipos_encontrados:
        set de categorías con al menos un valor (para cruce rápido en el pipeline).
    disponible:
        False si Web Data no existe o no se pudo leer.
    """
    emails:     list[str] = field(default_factory=list)
    nombres:    list[str] = field(default_factory=list)
    telefonos:  list[str] = field(default_factory=list)
    direcciones:list[str] = field(default_factory=list)
    ruts:       list[str] = field(default_factory=list)
    patentes:   list[str] = field(default_factory=list)
    usernames:  list[str] = field(default_factory=list)
    tipos_encontrados: set[str] = field(default_factory=set)
    disponible: bool = True

    def has(self, tipo: str) -> bool:
        return tipo in self.tipos_encontrados


# ── Clasificación de field names ──────────────────────────────────────────────

def _classify_field(name: str) -> Optional[str]:
    """Devuelve la categoría de un nombre de campo HTML, o None si no reconocido."""
    lower = name.lower().replace("-", "").replace("_", "")
    for category, patterns in FIELD_CLASSIFIERS.items():
        for p in patterns:
            if p.replace("-", "").replace("_", "") in lower:
                return category
    return None


# ── Lectura de Web Data ───────────────────────────────────────────────────────

def _copy_web_data() -> Optional[Path]:
    if not WEB_DATA_PATH.exists():
        return None
    shutil.copy2(str(WEB_DATA_PATH), str(WEB_DATA_TMP))
    return WEB_DATA_TMP


def _read_autofill_table(conn: sqlite3.Connection) -> dict[str, list[str]]:
    """
    Lee la tabla `autofill` → {categoría: [valores únicos]}.
    Filtra valores vacíos y puramente numéricos sin semántica.
    """
    result: dict[str, list[str]] = {cat: [] for cat in FIELD_CLASSIFIERS}
    seen: set[tuple[str, str]] = set()

    try:
        cursor = conn.execute(
            "SELECT name, value, count FROM autofill WHERE value != '' ORDER BY count DESC"
        )
        for row in cursor.fetchall():
            field_name, value, count = row
            if not value or len(value) < 2:
                continue
            category = _classify_field(field_name)
            if not category:
                continue
            key = (category, value)
            if key not in seen:
                seen.add(key)
                result[category].append(value)
    except sqlite3.OperationalError:
        pass  # tabla no existe en este esquema

    return result


def _read_address_profiles(conn: sqlite3.Connection) -> dict[str, list[str]]:
    """
    Lee `addresses` + `address_type_tokens` → {categoría: [valores]}.
    Usa los códigos Chrome ServerFieldType para clasificar.
    """
    result: dict[str, list[str]] = {}
    seen: set[tuple[str, str]] = set()

    try:
        cursor = conn.execute(
            """
            SELECT att.type, att.value
            FROM address_type_tokens att
            WHERE att.value IS NOT NULL AND att.value != ''
            """
        )
        for type_code, value in cursor.fetchall():
            category = ADDRESS_TYPE_CODES.get(type_code)
            if not category:
                continue
            key = (category, value)
            if key not in seen:
                seen.add(key)
                result.setdefault(category, []).append(value)
    except sqlite3.OperationalError:
        pass

    return result


# ── Punto de entrada ──────────────────────────────────────────────────────────

def read_chrome_autofill() -> AutofillSnapshot:
    """
    Lee Web Data de Chrome y devuelve un AutofillSnapshot con todos los
    datos personales encontrados en formularios del usuario.

    Si Web Data no existe o falla, devuelve un snapshot vacío (disponible=False)
    en lugar de lanzar excepción — el pipeline puede continuar sin autofill.
    """
    db_path = _copy_web_data()
    if not db_path:
        return AutofillSnapshot(disponible=False)

    conn = sqlite3.connect(str(db_path), check_same_thread=False)
    try:
        from_autofill = _read_autofill_table(conn)
        from_profile  = _read_address_profiles(conn)
    finally:
        conn.close()

    # Fusionar ambas fuentes
    def merge(*lists: list[str]) -> list[str]:
        seen: set[str] = set()
        out: list[str] = []
        for lst in lists:
            for v in lst:
                if v not in seen:
                    seen.add(v)
                    out.append(v)
        return out

    snap = AutofillSnapshot(
        emails      = merge(from_autofill.get("email", []),    from_profile.get("email", [])),
        nombres     = merge(from_autofill.get("nombre", []),   from_profile.get("nombre", [])),
        telefonos   = merge(from_autofill.get("telefono", []), from_profile.get("telefono", [])),
        direcciones = merge(from_autofill.get("direccion", []),from_profile.get("direccion", []),
                            [f"{c}, {r}" for c, r in zip(from_profile.get("ciudad", []),
                                                          from_profile.get("region", []))
                             if c or r]),
        ruts        = merge(from_autofill.get("rut", []),      from_autofill.get("rut_empresa", [])),
        patentes    = merge(from_autofill.get("patente", [])),
        usernames   = merge(from_autofill.get("username", [])),
    )

    # Construir set de tipos disponibles para cruce rápido
    if snap.emails:      snap.tipos_encontrados.add("email")
    if snap.nombres:     snap.tipos_encontrados.add("nombre")
    if snap.telefonos:   snap.tipos_encontrados.add("telefono")
    if snap.direcciones: snap.tipos_encontrados.add("direccion")
    if snap.ruts:        snap.tipos_encontrados.add("rut")
    if snap.patentes:    snap.tipos_encontrados.add("patente")
    if snap.usernames:   snap.tipos_encontrados.add("username")

    return snap
