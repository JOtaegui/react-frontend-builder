"""
_patterns.py — Patrones de URL que indican actividad con datos personales.

Para agregar un nuevo tipo de actividad:
  1. Define su lista de patrones aquí.
  2. Agrégalo a ACTIVITY_PATTERNS con un nombre de clave.
  3. El classifier lo detectará automáticamente sin más cambios.

Para agregar patrones a una categoría existente: solo añade el string a la lista.
Los patrones se compilan una vez al importar el módulo (no en cada request).
"""
from __future__ import annotations

import re

# ── Patrones por categoría ────────────────────────────────────────────────────
# Cada lista es un grupo semántico — se compila a un único Pattern por categoría.

_RAW_PATTERNS: dict[str, list[str]] = {
    "login": [
        r"/login", r"/signin", r"/sign-in", r"/ingresar", r"/acceso",
        r"/mi-cuenta", r"/micuenta", r"/account", r"/accounts",
        r"/auth(?!/callback)", r"/oauth", r"/session(?!s/new)", r"/sessions",
        r"/usuario", r"/dashboard", r"/panel", r"/inicio",
    ],
    "signup": [
        r"/signup", r"/sign-up", r"/register(?!ed)", r"/registro",
        r"/crear-cuenta", r"/crearcuenta", r"/nueva-cuenta",
        r"/join", r"/unirse", r"/registrarse",
    ],
    "checkout": [
        r"/checkout", r"/pago", r"/compra", r"/cart(?!/oon)",
        r"/carro", r"/carrito", r"/order", r"/pedido",
        r"/payment", r"/factura", r"/boleta", r"/despacho",
    ],
    "profile": [
        r"/profile", r"/perfil", r"/mis-datos", r"/misdatos",
        r"/datos-personales", r"/configuracion", r"/settings",
        r"/preferencias", r"/cuenta",
    ],
}

# Compilados una vez, reutilizados en cada URL
COMPILED_PATTERNS: dict[str, re.Pattern[str]] = {
    key: re.compile("|".join(patterns), re.IGNORECASE)
    for key, patterns in _RAW_PATTERNS.items()
}

# Nombres de los flags de actividad que se producen (usado por _classifier.py)
ACTIVITY_FLAGS: list[str] = [f"{key}_detected" for key in _RAW_PATTERNS]


def detect_activity(path_and_query: str) -> dict[str, bool]:
    """
    Recibe el path + query de una URL y devuelve un dict
    { "<categoria>_detected": bool } para cada categoría en COMPILED_PATTERNS.

    Es extensible: si agregas una clave en _RAW_PATTERNS aparece aquí automáticamente.
    """
    text = path_and_query.lower()
    return {
        f"{key}_detected": bool(pattern.search(text))
        for key, pattern in COMPILED_PATTERNS.items()
    }
