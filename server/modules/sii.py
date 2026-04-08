"""
Módulo: SII — Estado Tributario
Consulta el Servicio de Impuestos Internos para datos tributarios públicos.

Fuente: https://zeus.sii.cl/cvc/stc/stc.html (requiere RUT)
         https://www.sii.cl/servicios_online/1047.html (alternativa)

Notas:
- SII solo funciona con RUT — sin RUT no hay búsqueda posible
- Los datos disponibles sin autenticación son limitados:
  nombre contribuyente, actividad económica, inicio de actividades, IVA
"""
from __future__ import annotations

import time
import logging
from typing import Optional

from bs4 import BeautifulSoup

from config import SII_BASE_URL, TIMEOUT_SII
from modules.base import BaseModule, QueryContext, ModuleResult

logger = logging.getLogger(__name__)

SII_CVC_URL    = "https://zeus.sii.cl/cvc_cgi/stc/getstc"
SII_OPCION_URL = "https://zeus.sii.cl/cvc/stc/stc.html"


class SIIModule(BaseModule):
    name = "sii"
    timeout = TIMEOUT_SII

    async def run(self, context: QueryContext) -> ModuleResult:
        start = time.time()

        if not context.rut:
            # Sin RUT no hay datos útiles en SII
            logger.info("[sii] Saltando — se requiere RUT")
            return self._result({}, 0, start)

        try:
            rut, dv = self._separar_rut(context.rut)
            data = await self._consultar_sii(rut, dv)

            if not data:
                return self._result({}, 0, start)

            return self._result({"sii": data}, 1, start)

        except Exception as exc:
            return self._error_result(str(exc), start)

    async def _consultar_sii(self, rut: str, dv: str) -> Optional[dict]:
        """POST al endpoint público de SII."""
        try:
            resp = await self.client.post(
                SII_CVC_URL,
                data={"RUT": rut, "DV": dv.upper(), "PRG": "STC", "OPC": "NOR"},
                timeout=self.timeout,
            )
            if resp.status_code != 200:
                return None

            soup = BeautifulSoup(resp.text, "html.parser")
            return self._parsear_html(soup)

        except Exception as e:
            logger.debug(f"[sii] Error al consultar: {e}")
            return None

    def _parsear_html(self, soup: BeautifulSoup) -> Optional[dict]:
        """
        Parsea la respuesta HTML de SII.
        La página devuelve una tabla con: Nombre, Actividad, Inicio Actividades, IVA.
        """
        datos: dict = {}

        # SII usa tablas con clase específica
        tablas = soup.find_all("table")
        for tabla in tablas:
            for fila in tabla.find_all("tr"):
                texto = fila.get_text(separator="|", strip=True).lower()
                celdas = [td.get_text(strip=True) for td in fila.find_all("td")]

                if len(celdas) < 2:
                    continue

                if "nombre" in texto or "razón" in texto:
                    datos["nombre"] = celdas[-1]
                elif "actividad" in texto or "giro" in texto:
                    datos["actividad"] = celdas[-1]
                elif "inicio" in texto and "actividad" in texto:
                    datos["inicio_actividades"] = celdas[-1]
                elif "iva" in texto or "contribuyente" in texto:
                    datos["contribuyente_iva"] = True

        return datos if datos.get("nombre") or datos.get("actividad") else None

    def _separar_rut(self, rut: str) -> tuple[str, str]:
        """Separa cuerpo y dígito verificador del RUT."""
        rut = rut.replace(".", "").strip()
        if "-" in rut:
            cuerpo, dv = rut.split("-", 1)
        else:
            cuerpo, dv = rut[:-1], rut[-1]
        return cuerpo, dv
