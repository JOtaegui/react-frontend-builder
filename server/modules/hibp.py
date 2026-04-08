"""
Módulo: HaveIBeenPwned (HIBP)
Verifica si emails encontrados han aparecido en filtraciones de datos.

API: https://haveibeenpwned.com/api/v3/breachedaccount/{email}
Documentación: https://haveibeenpwned.com/API/v3

Notas:
- Requiere API key (plan gratuito disponible para uso no comercial)
- Rate limit: 1 request/1500ms — respetamos con delay entre requests
- Solo corre si hay emails encontrados en Wave 1
- IMPORTANTE: sin API key devuelve resultados vacíos (no falla)
"""
from __future__ import annotations

import asyncio
import time
import logging
from typing import Optional

from config import HIBP_API_KEY, HIBP_API_URL, TIMEOUT_HIBP
from modules.base import BaseModule, QueryContext, ModuleResult

logger = logging.getLogger(__name__)

RATE_LIMIT_DELAY = 1.6  # segundos entre requests (HIBP pide >= 1.5s)


class HibpModule(BaseModule):
    name = "hibp"
    timeout = TIMEOUT_HIBP

    async def run(self, context: QueryContext) -> ModuleResult:
        start = time.time()

        if not context.emails_encontrados:
            return self._result({}, 0, start)

        if not HIBP_API_KEY:
            logger.info("[hibp] Sin API key — módulo deshabilitado")
            return self._result(
                {"hibp": [], "_warning": "HIBP_API_KEY no configurada"},
                0,
                start,
            )

        resultados = []
        total_leaks = 0

        for i, email in enumerate(context.emails_encontrados[:5]):  # máximo 5 emails
            if i > 0:
                await asyncio.sleep(RATE_LIMIT_DELAY)  # respetar rate limit

            resultado = await self._verificar_email(email)
            if resultado:
                resultados.append(resultado)
                total_leaks += len(resultado.get("breaches", []))

        if not resultados:
            return self._result({}, 0, start)

        return self._result(
            {"hibp": resultados},
            total_leaks,
            start,
        )

    async def _verificar_email(self, email: str) -> Optional[dict]:
        """Consulta HIBP para un email específico."""
        url = f"{HIBP_API_URL}/breachedaccount/{email}"
        try:
            resp = await self.client.get(
                url,
                headers={
                    "hibp-api-key": HIBP_API_KEY,
                    "user-agent":   "OSINT-Chile-Research-Tool",
                },
                params={"truncateResponse": "false"},
                timeout=self.timeout,
            )

            if resp.status_code == 404:
                # 404 = email no encontrado en ningún breach (buena noticia)
                return {
                    "email":    email,
                    "breaches": [],
                    "pwned":    False,
                }

            if resp.status_code == 401:
                logger.error("[hibp] API key inválida o expirada")
                return None

            if resp.status_code == 429:
                logger.warning("[hibp] Rate limit alcanzado")
                await asyncio.sleep(5)
                return None

            if resp.status_code != 200:
                logger.warning(f"[hibp] Status inesperado {resp.status_code} para {email}")
                return None

            breaches_raw = resp.json()
            breaches = [
                {
                    "source":      b.get("Name", "Desconocido"),
                    "data_types":  b.get("DataClasses", []),
                    "breach_date": b.get("BreachDate"),
                }
                for b in breaches_raw
            ]

            return {
                "email":   email,
                "breaches": breaches,
                "pwned":    len(breaches) > 0,
            }

        except Exception as e:
            logger.warning(f"[hibp] Error verificando {email}: {e}")
            return None
