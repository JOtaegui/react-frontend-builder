"""
_readers.py — Abstracción de lectores de historial de navegador (multiplataforma).

Detecta automáticamente el sistema operativo (macOS, Windows o Linux) y resuelve
la ruta correcta del historial de cada navegador. Para agregar un navegador:
  1. Crea una subclase de ChromiumHistoryReader (o BaseHistoryReader si el
     esquema es distinto, como Firefox).
  2. Define OS_SUBPATH con la ruta relativa por sistema operativo.
  3. Regístrala en REGISTRY al final del archivo.

Cada lector devuelve una lista de dicts con las mismas claves:
  url, title, visit_count, last_visit_time   (last_visit_time en microsegundos,
  época de Chrome: 1601-01-01 o Unix según navegador — ver _convert_timestamp)
"""
from __future__ import annotations

import os
import platform
import shutil
import sqlite3
import tempfile
from abc import ABC, abstractmethod
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional

# ── Detección de sistema operativo ───────────────────────────────────────────
# platform.system() → 'Darwin' (macOS), 'Windows', 'Linux'
OS_NAME = platform.system()


def chromium_base_dir() -> Optional[Path]:
    """Directorio base donde los navegadores Chromium guardan sus datos, según SO."""
    if OS_NAME == "Darwin":
        return Path.home() / "Library" / "Application Support"
    if OS_NAME == "Windows":
        local = os.environ.get("LOCALAPPDATA")
        return Path(local) if local else Path.home() / "AppData" / "Local"
    if OS_NAME == "Linux":
        return Path.home() / ".config"
    return None


def firefox_profiles_dir() -> Optional[Path]:
    """Carpeta de perfiles de Firefox, según SO."""
    if OS_NAME == "Darwin":
        return Path.home() / "Library" / "Application Support" / "Firefox" / "Profiles"
    if OS_NAME == "Windows":
        appdata = os.environ.get("APPDATA")
        base = Path(appdata) if appdata else Path.home() / "AppData" / "Roaming"
        return base / "Mozilla" / "Firefox" / "Profiles"
    if OS_NAME == "Linux":
        return Path.home() / ".mozilla" / "firefox"
    return None


# ── Clase base ────────────────────────────────────────────────────────────────

class BaseHistoryReader(ABC):
    """Interfaz común para todos los lectores de historial."""

    # Copia temporal multiplataforma (en Windows /tmp no existe).
    TMP_COPY = Path(tempfile.gettempdir()) / "osint_history_tmp.db"

    @property
    @abstractmethod
    def browser_name(self) -> str:
        """Nombre del navegador (para logs y errores)."""

    @property
    @abstractmethod
    def history_db_path(self) -> Path:
        """Ruta al archivo SQLite de historial en el SO actual."""

    def chromium_profile_dir(self) -> Optional[Path]:
        """Carpeta de perfil Chromium (donde viven 'Web Data' y 'Login Data').
        None si el navegador no es Chromium (Firefox, Safari)."""
        return None

    def read_raw(self, limit: int = 5000) -> list[dict]:
        db = self._copy_db()
        return self._query(db, limit)

    def timestamp_to_iso(self, raw_ts: int) -> Optional[str]:
        return self._convert_timestamp(raw_ts)

    # ── Hooks para subclases ──────────────────────────────────────────────────

    def _convert_timestamp(self, raw_ts: int) -> Optional[str]:
        """Por defecto época de Chrome (microsegundos desde 1601-01-01)."""
        _CHROME_EPOCH_OFFSET_US = 11_644_473_600_000_000
        try:
            if raw_ts <= 0:
                return None
            unix_s = (raw_ts - _CHROME_EPOCH_OFFSET_US) / 1_000_000
            return datetime.fromtimestamp(unix_s, tz=timezone.utc).isoformat()
        except Exception:
            return None

    def _query(self, db_path: Path, limit: int) -> list[dict]:
        """Consulta por defecto — compatible con Chrome y la mayoría de Chromium."""
        conn = sqlite3.connect(str(db_path), check_same_thread=False)
        conn.row_factory = sqlite3.Row
        try:
            cursor = conn.execute(
                """
                SELECT url, title, visit_count, last_visit_time
                FROM urls
                WHERE visit_count > 0
                  AND (url LIKE 'http://%' OR url LIKE 'https://%')
                ORDER BY visit_count DESC
                LIMIT ?
                """,
                (limit,),
            )
            return [dict(r) for r in cursor.fetchall()]
        finally:
            conn.close()

    # ── Privado ───────────────────────────────────────────────────────────────

    def _copy_db(self) -> Path:
        path = self.history_db_path
        if not path or not path.exists():
            raise FileNotFoundError(
                f"No se encontró el historial de {self.browser_name} en este equipo "
                f"({OS_NAME}).\n  Ruta esperada: {path}\n"
                f"Asegúrate de tener {self.browser_name} instalado y de haberlo usado."
            )
        try:
            shutil.copy2(str(path), str(self.TMP_COPY))
        except PermissionError as exc:
            raise PermissionError(
                f"No se pudo leer el historial de {self.browser_name} (archivo en uso). "
                f"Cierra {self.browser_name} por completo e inténtalo de nuevo."
            ) from exc
        return self.TMP_COPY


# ── Lector Chromium genérico (Chrome, Brave, Edge, Canary) ────────────────────

class ChromiumHistoryReader(BaseHistoryReader):
    """
    Lector para navegadores basados en Chromium. Las subclases solo definen
    `browser_name` y `OS_SUBPATH`: la ruta relativa al archivo History desde el
    directorio base de cada SO. Ojo: en macOS no existe el segmento "User Data"
    y en Linux los nombres de carpeta cambian.
    """

    OS_SUBPATH: dict[str, str] = {}

    @property
    def history_db_path(self) -> Path:
        base = chromium_base_dir()
        sub = self.OS_SUBPATH.get(OS_NAME)
        if base is None or not sub:
            # SO no soportado: devolver ruta vacía → _copy_db dará error claro
            return Path(sub or "navegador-no-soportado")
        return base.joinpath(*sub.split("/"))

    def chromium_profile_dir(self) -> Optional[Path]:
        # 'Web Data' y 'Login Data' son archivos hermanos de 'History' dentro
        # de la carpeta del perfil (ej. .../Default).
        base = chromium_base_dir()
        sub = self.OS_SUBPATH.get(OS_NAME)
        if base is None or not sub:
            return None
        return base.joinpath(*sub.split("/")).parent


class ChromeHistoryReader(ChromiumHistoryReader):
    browser_name = "Google Chrome"
    OS_SUBPATH = {
        "Darwin":  "Google/Chrome/Default/History",
        "Windows": "Google/Chrome/User Data/Default/History",
        "Linux":   "google-chrome/Default/History",
    }


class ChromeCanaryHistoryReader(ChromiumHistoryReader):
    browser_name = "Chrome Canary"
    OS_SUBPATH = {
        "Darwin":  "Google/Chrome Canary/Default/History",
        "Windows": "Google/Chrome SxS/User Data/Default/History",
        "Linux":   "google-chrome-unstable/Default/History",
    }


class BraveHistoryReader(ChromiumHistoryReader):
    browser_name = "Brave"
    OS_SUBPATH = {
        "Darwin":  "BraveSoftware/Brave-Browser/Default/History",
        "Windows": "BraveSoftware/Brave-Browser/User Data/Default/History",
        "Linux":   "BraveSoftware/Brave-Browser/Default/History",
    }


class EdgeHistoryReader(ChromiumHistoryReader):
    browser_name = "Microsoft Edge"
    OS_SUBPATH = {
        "Darwin":  "Microsoft Edge/Default/History",
        "Windows": "Microsoft/Edge/User Data/Default/History",
        "Linux":   "microsoft-edge/Default/History",
    }


# ── Firefox (esquema y rutas propios) ─────────────────────────────────────────

class FirefoxHistoryReader(BaseHistoryReader):
    """Firefox usa moz_places con timestamps en microsegundos Unix."""

    browser_name = "Firefox"

    @property
    def history_db_path(self) -> Path:
        profiles_root = firefox_profiles_dir()
        if profiles_root and profiles_root.exists():
            # Preferir el perfil por defecto; si no, el primero con places.sqlite
            candidates = sorted(profiles_root.iterdir())
            for profile_dir in candidates:
                if profile_dir.name.endswith((".default-release", ".default")):
                    candidate = profile_dir / "places.sqlite"
                    if candidate.exists():
                        return candidate
            for profile_dir in candidates:
                candidate = profile_dir / "places.sqlite"
                if candidate.exists():
                    return candidate
        return (profiles_root or Path("firefox-no-encontrado")) / "default" / "places.sqlite"

    def _query(self, db_path: Path, limit: int) -> list[dict]:
        conn = sqlite3.connect(str(db_path), check_same_thread=False)
        conn.row_factory = sqlite3.Row
        try:
            cursor = conn.execute(
                """
                SELECT url, title, visit_count, last_visit_date AS last_visit_time
                FROM moz_places
                WHERE visit_count > 0
                  AND (url LIKE 'http://%' OR url LIKE 'https://%')
                ORDER BY visit_count DESC
                LIMIT ?
                """,
                (limit,),
            )
            return [dict(r) for r in cursor.fetchall()]
        finally:
            conn.close()

    def _convert_timestamp(self, raw_ts: int) -> Optional[str]:
        """Firefox usa microsegundos Unix (no época 1601)."""
        try:
            if not raw_ts:
                return None
            return datetime.fromtimestamp(raw_ts / 1_000_000, tz=timezone.utc).isoformat()
        except Exception:
            return None


# ── Safari (solo macOS, esquema y época propios) ──────────────────────────────

class SafariHistoryReader(BaseHistoryReader):
    """
    Safari guarda el historial en ~/Library/Safari/History.db (solo macOS).
    El esquema separa items (history_items) de visitas (history_visits), y los
    timestamps usan CFAbsoluteTime: segundos desde 2001-01-01 (no la época Unix).
    Leerlo requiere que la app tenga 'Acceso completo al disco' en macOS.
    """

    browser_name = "Safari"

    # Segundos entre 1970-01-01 (Unix) y 2001-01-01 (CFAbsoluteTime).
    _CF_EPOCH_OFFSET = 978_307_200

    @property
    def history_db_path(self) -> Path:
        if OS_NAME != "Darwin":
            return Path("safari-solo-disponible-en-macos")
        return Path.home() / "Library" / "Safari" / "History.db"

    def _copy_db(self) -> Path:
        path = self.history_db_path
        if not path.exists():
            raise FileNotFoundError(
                "No se pudo acceder al historial de Safari.\n"
                "En macOS, Safari protege su historial: concede 'Acceso completo al disco' "
                "a la aplicación (o a la Terminal si la ejecutas desde ahí) en "
                "Configuración del Sistema → Privacidad y seguridad → Acceso completo al disco, "
                "y vuelve a intentarlo."
            )
        try:
            shutil.copy2(str(path), str(self.TMP_COPY))
        except PermissionError as exc:
            raise PermissionError(
                "Safari bloqueó la lectura de su historial. Concede 'Acceso completo al disco' "
                "a la aplicación en Configuración del Sistema → Privacidad y seguridad."
            ) from exc
        return self.TMP_COPY

    def _query(self, db_path: Path, limit: int) -> list[dict]:
        conn = sqlite3.connect(str(db_path), check_same_thread=False)
        conn.row_factory = sqlite3.Row
        try:
            cursor = conn.execute(
                """
                SELECT i.url                AS url,
                       v.title              AS title,
                       COUNT(v.id)          AS visit_count,
                       MAX(v.visit_time)    AS last_visit_time
                FROM history_items i
                JOIN history_visits v ON v.history_item = i.id
                WHERE i.url LIKE 'http://%' OR i.url LIKE 'https://%'
                GROUP BY i.id
                ORDER BY visit_count DESC
                LIMIT ?
                """,
                (limit,),
            )
            return [dict(r) for r in cursor.fetchall()]
        finally:
            conn.close()

    def _convert_timestamp(self, raw_ts) -> Optional[str]:
        """Safari usa CFAbsoluteTime (segundos desde 2001-01-01)."""
        try:
            if not raw_ts:
                return None
            unix_s = float(raw_ts) + self._CF_EPOCH_OFFSET
            return datetime.fromtimestamp(unix_s, tz=timezone.utc).isoformat()
        except Exception:
            return None


# ── Registro de lectores disponibles ─────────────────────────────────────────

REGISTRY: dict[str, type[BaseHistoryReader]] = {
    "chrome":        ChromeHistoryReader,
    "chrome-canary": ChromeCanaryHistoryReader,
    "brave":         BraveHistoryReader,
    "edge":          EdgeHistoryReader,
    "firefox":       FirefoxHistoryReader,
    "safari":        SafariHistoryReader,
}


def get_reader(browser: str) -> BaseHistoryReader:
    """Fábrica de lectores. `browser` es el slug del ?browser= del endpoint."""
    cls = REGISTRY.get(browser.lower())
    if cls is None:
        valid = ", ".join(REGISTRY.keys())
        raise ValueError(f"Navegador '{browser}' no soportado. Opciones: {valid}")
    return cls()
