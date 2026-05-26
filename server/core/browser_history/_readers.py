"""
_readers.py — Abstracción de lectores de historial de navegador.

Para agregar un nuevo navegador:
  1. Crea una subclase de BaseHistoryReader.
  2. Implementa `history_db_path` y opcionalmente `_convert_timestamp`.
  3. Regístrala en REGISTRY al final del archivo.
  4. El endpoint acepta ?browser=nombre automáticamente.

Cada lector devuelve una lista de dicts con las mismas claves:
  url, title, visit_count, last_visit_time   (last_visit_time en microsegundos,
  época de Chrome: 1601-01-01 o Unix según navegador — ver _convert_timestamp)
"""
from __future__ import annotations

import shutil
import sqlite3
from abc import ABC, abstractmethod
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional

# ── Clase base ────────────────────────────────────────────────────────────────

class BaseHistoryReader(ABC):
    """Interfaz común para todos los lectores de historial."""

    TMP_COPY = Path("/tmp/osint_history_tmp.db")

    # ── API pública ──────────────────────────────────────────────────────────

    @property
    @abstractmethod
    def browser_name(self) -> str:
        """Nombre del navegador (para logs y errores)."""

    @property
    @abstractmethod
    def history_db_path(self) -> Path:
        """Ruta al archivo SQLite de historial."""

    def read_raw(self, limit: int = 5000) -> list[dict]:
        """
        Copia el DB a /tmp (evita bloqueo del navegador abierto) y lo consulta.
        Devuelve lista de dicts: url, title, visit_count, last_visit_time.
        """
        db = self._copy_db()
        return self._query(db, limit)

    def timestamp_to_iso(self, raw_ts: int) -> Optional[str]:
        """Convierte el timestamp nativo del navegador a ISO 8601 UTC."""
        return self._convert_timestamp(raw_ts)

    # ── Hooks para subclases ──────────────────────────────────────────────────

    def _convert_timestamp(self, raw_ts: int) -> Optional[str]:
        """
        Por defecto asume época de Chrome (microsegundos desde 1601-01-01).
        Sobreescribe en subclases que usen otra época (Firefox: segundos Unix × 1e6).
        """
        _CHROME_EPOCH_OFFSET_US = 11_644_473_600_000_000
        try:
            if raw_ts <= 0:
                return None
            unix_s = (raw_ts - _CHROME_EPOCH_OFFSET_US) / 1_000_000
            return datetime.fromtimestamp(unix_s, tz=timezone.utc).isoformat()
        except Exception:
            return None

    def _query(self, db_path: Path, limit: int) -> list[dict]:
        """
        Consulta SQL por defecto — compatible con Chrome y la mayoría de Chromium.
        Sobreescribe si el esquema es diferente (ej. Firefox usa moz_places).
        """
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
        if not path.exists():
            raise FileNotFoundError(
                f"No se encontró el historial de {self.browser_name} en:\n  {path}\n"
                f"Asegúrate de tener {self.browser_name} instalado."
            )
        shutil.copy2(str(path), str(self.TMP_COPY))
        return self.TMP_COPY


# ── Implementaciones concretas ────────────────────────────────────────────────

class ChromeHistoryReader(BaseHistoryReader):
    @property
    def browser_name(self) -> str:
        return "Google Chrome"

    @property
    def history_db_path(self) -> Path:
        return (
            Path.home()
            / "Library" / "Application Support"
            / "Google" / "Chrome" / "Default" / "History"
        )


class ChromeCanaryHistoryReader(BaseHistoryReader):
    @property
    def browser_name(self) -> str:
        return "Chrome Canary"

    @property
    def history_db_path(self) -> Path:
        return (
            Path.home()
            / "Library" / "Application Support"
            / "Google" / "Chrome Canary" / "Default" / "History"
        )


class BraveHistoryReader(BaseHistoryReader):
    @property
    def browser_name(self) -> str:
        return "Brave"

    @property
    def history_db_path(self) -> Path:
        return (
            Path.home()
            / "Library" / "Application Support"
            / "BraveSoftware" / "Brave-Browser" / "Default" / "History"
        )


class EdgeHistoryReader(BaseHistoryReader):
    @property
    def browser_name(self) -> str:
        return "Microsoft Edge"

    @property
    def history_db_path(self) -> Path:
        return (
            Path.home()
            / "Library" / "Application Support"
            / "Microsoft Edge" / "Default" / "History"
        )


class FirefoxHistoryReader(BaseHistoryReader):
    """
    Firefox usa moz_places con timestamps en microsegundos Unix (no época Chrome).
    El esquema SQL y la conversión son distintos.
    """

    @property
    def browser_name(self) -> str:
        return "Firefox"

    @property
    def history_db_path(self) -> Path:
        # Firefox puede tener varios perfiles — tomamos el primero que exista
        profiles_root = Path.home() / "Library" / "Application Support" / "Firefox" / "Profiles"
        if profiles_root.exists():
            for profile_dir in sorted(profiles_root.iterdir()):
                candidate = profile_dir / "places.sqlite"
                if candidate.exists():
                    return candidate
        return profiles_root / "default" / "places.sqlite"  # fallback para el error

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


# ── Registro de lectores disponibles ─────────────────────────────────────────
# Para registrar un nuevo navegador: añade una entrada aquí.
# La clave es el valor que acepta el query param ?browser= del endpoint.

REGISTRY: dict[str, type[BaseHistoryReader]] = {
    "chrome":        ChromeHistoryReader,
    "chrome-canary": ChromeCanaryHistoryReader,
    "brave":         BraveHistoryReader,
    "edge":          EdgeHistoryReader,
    "firefox":       FirefoxHistoryReader,
}


def get_reader(browser: str) -> BaseHistoryReader:
    """
    Fábrica de lectores.  browser es el slug del ?browser= query param.
    Lanza ValueError con la lista de opciones válidas si no se reconoce.
    """
    cls = REGISTRY.get(browser.lower())
    if cls is None:
        valid = ", ".join(REGISTRY.keys())
        raise ValueError(f"Navegador '{browser}' no soportado. Opciones: {valid}")
    return cls()
