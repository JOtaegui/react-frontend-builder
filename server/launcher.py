"""
launcher.py — Entry point for the standalone macOS app.

Responsibilities:
- Resolve paths correctly whether running from source or PyInstaller bundle
- Load .env from ~/.emailanalyzer/.env (user-editable)
- Initialize the app data directory (DB, logs)
- Start uvicorn on localhost:8787
- Open the browser after a short delay
"""
from __future__ import annotations

import os
import sys
import threading
import time
import webbrowser
from pathlib import Path

APP_PORT = 8787
APP_DATA_DIR = Path.home() / ".emailanalyzer"


def _bundle_dir() -> Path:
    """Directory where bundled Python modules and static assets live."""
    if getattr(sys, "frozen", False):
        return Path(sys._MEIPASS)  # type: ignore[attr-defined]
    return Path(__file__).parent


def _bootstrap() -> None:
    bundle = _bundle_dir()

    # Make sure our server package is importable
    bundle_str = str(bundle)
    if bundle_str not in sys.path:
        sys.path.insert(0, bundle_str)

    # User-facing data directory (writable, survives app updates)
    APP_DATA_DIR.mkdir(parents=True, exist_ok=True)

    # Credenciales base del repo (OAuth), bundleadas dentro del .app
    repo_env = bundle / ".env"
    if repo_env.exists():
        os.environ.setdefault("REPO_DOTENV_PATH", str(repo_env))

    # Override personal del usuario (SMTP, etc.) en ~/.emailanalyzer/.env
    env_file = APP_DATA_DIR / ".env"
    if env_file.exists():
        os.environ["DOTENV_PATH"] = str(env_file)

    # SQLite DB in app data dir
    os.environ.setdefault("DB_PATH", str(APP_DATA_DIR / "osint_chile.db"))

    # Static frontend (bundled inside the app)
    dist_path = bundle / "dist"
    if dist_path.exists():
        os.environ["STATIC_DIST_PATH"] = str(dist_path)

    # OAuth callback must match what's registered in Google Cloud Console
    os.environ.setdefault(
        "GOOGLE_OAUTH_REDIRECT_URI",
        f"http://localhost:{APP_PORT}/api/auth/gmail/callback",
    )
    # Frontend origin for postMessage in the OAuth popup
    os.environ.setdefault("FRONTEND_URL", f"http://localhost:{APP_PORT}")


def _open_browser() -> None:
    time.sleep(2.0)
    webbrowser.open(f"http://localhost:{APP_PORT}")


def main() -> None:
    _bootstrap()

    t = threading.Thread(target=_open_browser, daemon=True)
    t.start()

    import uvicorn  # imported after bootstrap so sys.path is ready

    uvicorn.run(
        "main:app",
        host="127.0.0.1",
        port=APP_PORT,
        log_level="info",
    )


if __name__ == "__main__":
    main()
