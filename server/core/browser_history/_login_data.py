"""
_login_data.py — Lee contraseñas guardadas de Chrome (Login Data SQLite).

La tabla `logins` vincula origin_url ↔ username_value de forma exacta:
Chrome solo escribe un registro aquí cuando el usuario REALMENTE hizo login
y aceptó guardar la contraseña.  Esto confirma que ese email/usuario
fue enviado a ese dominio.

Las contraseñas (password_value) están cifradas con macOS Keychain → no se leen.
Solo usamos username_value, que está en texto plano.
"""
from __future__ import annotations

import shutil
import sqlite3
from dataclasses import dataclass, field
from pathlib import Path
from typing import Optional
from urllib.parse import urlparse

LOGIN_DATA_PATH = (
    Path.home()
    / "Library" / "Application Support"
    / "Google" / "Chrome" / "Default" / "Login Data"
)
LOGIN_DATA_TMP = Path("/tmp/chrome_logindata_osint_tmp.db")

# Época Chrome en microsegundos (1601-01-01)
_CHROME_EPOCH_US = 11_644_473_600_000_000


def _chrome_ts_to_iso(raw: int) -> Optional[str]:
    from datetime import datetime, timezone
    try:
        if raw <= 0:
            return None
        return datetime.fromtimestamp((raw - _CHROME_EPOCH_US) / 1e6, tz=timezone.utc).isoformat()
    except Exception:
        return None


@dataclass
class SavedLogin:
    """Un login guardado por Chrome para un dominio concreto."""
    domain:        str
    origin_url:    str
    username:      str           # email o usuario — en texto plano
    times_used:    int = 0
    last_used_iso: Optional[str] = None


@dataclass
class LoginDataSnapshot:
    """
    Mapa de dominio → logins guardados.

    by_domain[root_domain] = [SavedLogin, ...]
    disponible = False si Login Data no existe o no pudo leerse.
    """
    by_domain:  dict[str, list[SavedLogin]] = field(default_factory=dict)
    disponible: bool = True

    def get(self, domain: str) -> list[SavedLogin]:
        return self.by_domain.get(domain, [])

    def usernames_for(self, domain: str) -> list[str]:
        return [l.username for l in self.by_domain.get(domain, []) if l.username]


def _root_domain(url: str) -> Optional[str]:
    """Extrae el dominio raíz de una URL (igual que en _pipeline.py)."""
    try:
        host = urlparse(url).netloc.lower().split(":")[0]
        if host.startswith("www."):
            host = host[4:]
        parts = host.split(".")
        if len(parts) <= 2:
            return host or None
        penultimate = parts[-2]
        if penultimate in ("com", "org", "gob", "net", "co", "edu"):
            return ".".join(parts[-3:])
        return ".".join(parts[-2:])
    except Exception:
        return None


def read_chrome_login_data() -> LoginDataSnapshot:
    """
    Lee Login Data de Chrome y devuelve un LoginDataSnapshot.

    Si el archivo no existe o falla, devuelve snapshot vacío (disponible=False).
    """
    if not LOGIN_DATA_PATH.exists():
        return LoginDataSnapshot(disponible=False)

    try:
        shutil.copy2(str(LOGIN_DATA_PATH), str(LOGIN_DATA_TMP))
    except Exception:
        return LoginDataSnapshot(disponible=False)

    snap = LoginDataSnapshot()

    conn = sqlite3.connect(str(LOGIN_DATA_TMP), check_same_thread=False)
    conn.row_factory = sqlite3.Row
    try:
        cursor = conn.execute(
            """
            SELECT origin_url, username_value, times_used, date_last_used
            FROM logins
            WHERE username_value != ''
              AND blacklisted_by_user = 0
            ORDER BY times_used DESC
            """
        )
        for row in cursor.fetchall():
            origin  = row["origin_url"] or ""
            username = row["username_value"] or ""
            if not origin or not username:
                continue

            domain = _root_domain(origin)
            if not domain:
                continue

            login = SavedLogin(
                domain      = domain,
                origin_url  = origin,
                username    = username,
                times_used  = row["times_used"] or 0,
                last_used_iso = _chrome_ts_to_iso(row["date_last_used"] or 0),
            )
            snap.by_domain.setdefault(domain, []).append(login)

    except sqlite3.OperationalError:
        snap.disponible = False
    finally:
        conn.close()

    return snap
