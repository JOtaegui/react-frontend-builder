from __future__ import annotations

import hashlib
import hmac
import json
import os
import secrets
import time
from urllib.parse import urlencode

import httpx

from config import (
    FRONTEND_URL,
    GOOGLE_OAUTH_CLIENT_ID,
    GOOGLE_OAUTH_CLIENT_SECRET,
    GOOGLE_OAUTH_REDIRECT_URI,
    GOOGLE_OAUTH_SCOPES,
)

GOOGLE_AUTH_URL = "https://accounts.google.com/o/oauth2/v2/auth"
GOOGLE_TOKEN_URL = "https://oauth2.googleapis.com/token"
GOOGLE_GMAIL_PROFILE_URL = "https://gmail.googleapis.com/gmail/v1/users/me/profile"
STATE_TTL_SECONDS = 600
_STATE_SECRET = os.getenv("GOOGLE_OAUTH_STATE_SECRET", GOOGLE_OAUTH_CLIENT_SECRET or "dev-gmail-oauth-state")


def gmail_oauth_is_configured() -> bool:
    return bool(GOOGLE_OAUTH_CLIENT_ID and GOOGLE_OAUTH_CLIENT_SECRET and GOOGLE_OAUTH_REDIRECT_URI)


def build_gmail_oauth_url() -> str:
    if not gmail_oauth_is_configured():
        raise ValueError("Google OAuth no esta configurado en el backend")

    state = _build_state()
    query = urlencode(
        {
            "client_id": GOOGLE_OAUTH_CLIENT_ID,
            "redirect_uri": GOOGLE_OAUTH_REDIRECT_URI,
            "response_type": "code",
            "scope": " ".join(GOOGLE_OAUTH_SCOPES),
            "access_type": "offline",
            "prompt": "consent",
            "include_granted_scopes": "true",
            "state": state,
        }
    )
    return f"{GOOGLE_AUTH_URL}?{query}"


async def exchange_gmail_code(code: str, state: str) -> dict[str, object]:
    if not gmail_oauth_is_configured():
        raise ValueError("Google OAuth no esta configurado en el backend")
    _validate_state(state)

    async with httpx.AsyncClient(timeout=httpx.Timeout(20.0, connect=10.0)) as client:
        token_response = await client.post(
            GOOGLE_TOKEN_URL,
            data={
                "code": code,
                "client_id": GOOGLE_OAUTH_CLIENT_ID,
                "client_secret": GOOGLE_OAUTH_CLIENT_SECRET,
                "redirect_uri": GOOGLE_OAUTH_REDIRECT_URI,
                "grant_type": "authorization_code",
            },
            headers={"Accept": "application/json"},
        )
        token_response.raise_for_status()
        token_payload = token_response.json()

        access_token = token_payload["access_token"]
        profile_response = await client.get(
            GOOGLE_GMAIL_PROFILE_URL,
            headers={"Authorization": f"Bearer {access_token}"},
        )
        profile_response.raise_for_status()
        profile_payload = profile_response.json()

    return {
        "access_token": access_token,
        "expires_in": token_payload.get("expires_in"),
        "scope": token_payload.get("scope"),
        "token_type": token_payload.get("token_type"),
        "email_address": profile_payload.get("emailAddress"),
    }


def build_gmail_popup_response_html(payload: dict[str, object]) -> str:
    safe_payload = json.dumps(payload)
    safe_origin = json.dumps(FRONTEND_URL)
    return f"""<!doctype html>
<html>
  <head>
    <meta charset="utf-8" />
    <title>Gmail conectado</title>
  </head>
  <body style="font-family: sans-serif; background: #0b1020; color: #f8fafc; display: grid; place-items: center; min-height: 100vh; margin: 0;">
    <div style="max-width: 32rem; padding: 2rem; text-align: center;">
      <h1 style="margin-bottom: 0.5rem;">Conexion completada</h1>
      <p style="opacity: 0.8;">Puedes cerrar esta ventana y volver al analisis.</p>
    </div>
    <script>
      (function () {{
        const payload = {safe_payload};
        const origin = {safe_origin};
        if (window.opener && typeof window.opener.postMessage === "function") {{
          window.opener.postMessage({{ type: "gmail-oauth-success", payload }}, origin);
        }}
        window.close();
      }})();
    </script>
  </body>
</html>"""


def build_gmail_popup_error_html(message: str) -> str:
    safe_message = json.dumps(message)
    safe_origin = json.dumps(FRONTEND_URL)
    return f"""<!doctype html>
<html>
  <head>
    <meta charset="utf-8" />
    <title>Error de Gmail OAuth</title>
  </head>
  <body style="font-family: sans-serif; background: #190b0b; color: #fef2f2; display: grid; place-items: center; min-height: 100vh; margin: 0;">
    <div style="max-width: 32rem; padding: 2rem; text-align: center;">
      <h1 style="margin-bottom: 0.5rem;">No se pudo conectar Gmail</h1>
      <p id="message" style="opacity: 0.9;"></p>
    </div>
    <script>
      (function () {{
        const message = {safe_message};
        const origin = {safe_origin};
        document.getElementById("message").textContent = message;
        if (window.opener && typeof window.opener.postMessage === "function") {{
          window.opener.postMessage({{ type: "gmail-oauth-error", message }}, origin);
        }}
      }})();
    </script>
  </body>
</html>"""


def _build_state() -> str:
    issued_at = int(time.time())
    nonce = secrets.token_urlsafe(24)
    payload = f"{issued_at}:{nonce}"
    signature = hmac.new(_STATE_SECRET.encode("utf-8"), payload.encode("utf-8"), hashlib.sha256).hexdigest()
    return f"{payload}:{signature}"


def _validate_state(state: str) -> None:
    try:
        issued_at_raw, nonce, signature = state.split(":", 2)
        issued_at = int(issued_at_raw)
    except ValueError as exc:
        raise ValueError("State OAuth invalido") from exc

    payload = f"{issued_at}:{nonce}"
    expected = hmac.new(_STATE_SECRET.encode("utf-8"), payload.encode("utf-8"), hashlib.sha256).hexdigest()
    if not hmac.compare_digest(signature, expected):
        raise ValueError("State OAuth no coincide")
    if int(time.time()) - issued_at > STATE_TTL_SECONDS:
        raise ValueError("State OAuth expirado")
