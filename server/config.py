"""
Config — todas las constantes y variables de entorno en un solo lugar.
Usa un archivo .env local para sobreescribir valores en desarrollo.
"""
from __future__ import annotations
import os
from dotenv import load_dotenv

load_dotenv()

# ── General ──────────────────────────────────────────────────────────────────
APP_NAME    = "OSINT Chile Backend"
APP_VERSION = "0.1.0"
DEBUG       = os.getenv("DEBUG", "false").lower() == "true"

# ── CORS (tu frontend en desarrollo) ────────────────────────────────────────
CORS_ORIGINS: list[str] = [
    "http://localhost:5173",   # Vite dev
    "http://localhost:3000",
    "http://localhost:8080",
]

# ── Timeouts por módulo (segundos) ──────────────────────────────────────────
# Cada módulo usa su propio timeout para no bloquear a los demás.
TIMEOUT_NRYF           = int(os.getenv("TIMEOUT_NRYF",           "20"))
TIMEOUT_SERVEL         = int(os.getenv("TIMEOUT_SERVEL",          "15"))
TIMEOUT_SII            = int(os.getenv("TIMEOUT_SII",             "15"))
TIMEOUT_EMPRESAS       = int(os.getenv("TIMEOUT_EMPRESAS",        "15"))
TIMEOUT_PJUD           = int(os.getenv("TIMEOUT_PJUD",            "20"))
TIMEOUT_DIARIO_OFICIAL = int(os.getenv("TIMEOUT_DIARIO_OFICIAL",  "15"))
TIMEOUT_EMAILS         = int(os.getenv("TIMEOUT_EMAILS",          "18"))
TIMEOUT_INSTITUCIONES  = int(os.getenv("TIMEOUT_INSTITUCIONES",   "18"))
TIMEOUT_HIBP           = int(os.getenv("TIMEOUT_HIBP",            "10"))

# ── HTTP headers comunes (simula browser real) ───────────────────────────────
DEFAULT_HEADERS: dict[str, str] = {
    "User-Agent": (
        "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/123.0.0.0 Safari/537.36"
    ),
    "Accept-Language": "es-CL,es;q=0.9,en;q=0.8",
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
}

# ── APIs externas ────────────────────────────────────────────────────────────
HIBP_API_KEY = os.getenv("HIBP_API_KEY", "")   # requerida para HIBP
HIBP_API_URL = "https://haveibeenpwned.com/api/v3"
BRAVE_SEARCH_API_KEY = os.getenv("BRAVE_SEARCH_API_KEY", "")
BRAVE_SEARCH_API_URL = "https://api.search.brave.com/res/v1/web/search"
FRONTEND_URL = os.getenv("FRONTEND_URL", "http://localhost:5173")
GOOGLE_OAUTH_CLIENT_ID = os.getenv("GOOGLE_OAUTH_CLIENT_ID", "")
GOOGLE_OAUTH_CLIENT_SECRET = os.getenv("GOOGLE_OAUTH_CLIENT_SECRET", "")
GOOGLE_OAUTH_REDIRECT_URI = os.getenv(
    "GOOGLE_OAUTH_REDIRECT_URI",
    "http://localhost:8000/api/auth/gmail/callback",
)
EMAIL_EXTRACTION_PROVIDER = os.getenv("EMAIL_EXTRACTION_PROVIDER", "none").strip().lower()
GEMINI_API_KEY = os.getenv("GEMINI_API_KEY", "")
GEMINI_MODEL = os.getenv("GEMINI_MODEL", "gemini-2.5-flash")
GOOGLE_OAUTH_SCOPES = [
    "openid",
    "email",
    "https://www.googleapis.com/auth/gmail.readonly",
]

# ── Fuentes chilenas ─────────────────────────────────────────────────────────
NRYF_BASE_URL    = "https://www.nombrerutyfirma.com"
SERVEL_API_URL   = "https://api.servel.cl/api/padron-electoral"   # puede cambiar
SII_BASE_URL     = "https://zeus.sii.cl/cvc/stc/stc.html"
EMPRESAS_API_URL = "https://apis.digital.gob.cl/sbif-empresas"   # SBIF/CMF
PJUD_BASE_URL    = "https://oficinajudicialvirtual.pjud.cl"
DO_SEARCH_URL    = "https://www.diariooficial.interior.gob.cl/publicaciones/search"
