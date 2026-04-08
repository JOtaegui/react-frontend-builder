"""
Módulo: SERVEL — Padrón Electoral
URL oficial de consulta: https://ww1.servel.cl/padron-electoral/

Sin RUT la búsqueda es muy poco confiable — SERVEL no tiene buscador por nombre.
Con RUT se puede verificar si la persona está inscrita y su mesa/local.
"""
from __future__ import annotations

import re
import time
import logging
from typing import Optional

from bs4 import BeautifulSoup

from config import TIMEOUT_SERVEL
from modules.base import BaseModule, QueryContext, ModuleResult
from utils.scraping import limpiar_rut, separar_rut, detectar_bloqueo

logger = logging.getLogger(__name__)

SERVEL_CONSULTA = "https://ww1.servel.cl/padron-electoral/"
# API alternativa (puede estar disponible en elecciones)
SERVEL_API      = "https://api.servel.cl/api/padron-electoral/consulta"


class ServelModule(BaseModule):
    name    = "servel"
    timeout = TIMEOUT_SERVEL

    async def run(self, context: QueryContext) -> ModuleResult:
        start = time.time()

        if not context.rut:
            logger.info("[servel] Sin RUT — no es posible consultar el padrón")
            return self._result({}, 0, start)

        try:
            rut_limpio = limpiar_rut(context.rut)
            data = await self._consultar(rut_limpio, context.nombre)

            if not data:
                return self._result({}, 0, start)

            return self._result({"servel": data}, 1, start)

        except Exception as exc:
            return self._error_result(str(exc), start)

    async def _consultar(self, rut: str, nombre_fallback: str) -> Optional[dict]:
        """Intenta API JSON, luego scraping web."""

        # Intento 1: API JSON de SERVEL
        cuerpo, dv = separar_rut(rut)
        try:
            resp = await self.client.get(
                SERVEL_API,
                params={"rut": cuerpo, "dv": dv},
                timeout=self.timeout,
            )
            if resp.status_code == 200:
                data = resp.json()
                parsed = self._parsear_json(data, nombre_fallback, rut)
                if parsed:
                    return parsed
        except Exception as e:
            logger.debug(f"[servel] API JSON falló: {e}")

        # Intento 2: formulario web
        try:
            # GET inicial para obtener cookies/token
            resp_get = await self.client.get(SERVEL_CONSULTA, timeout=self.timeout)
            cookies  = resp_get.cookies

            # Extraer token CSRF si existe
            soup_get = BeautifulSoup(resp_get.text, "lxml")
            token_input = soup_get.find("input", {"name": re.compile(r"token|csrf|_token", re.I)})
            extra_data  = {}
            if token_input:
                extra_data[token_input["name"]] = token_input.get("value", "")

            # POST con RUT
            resp_post = await self.client.post(
                SERVEL_CONSULTA,
                data={"run": cuerpo, "dv": dv, "submit": "Consultar", **extra_data},
                cookies=cookies,
                timeout=self.timeout,
            )

            if resp_post.status_code == 200 and not detectar_bloqueo(resp_post.text):
                return self._parsear_html(resp_post.text, nombre_fallback, rut)

        except Exception as e:
            logger.debug(f"[servel] Scraping falló: {e}")

        return None

    def _parsear_json(self, data: dict, nombre_fallback: str, rut: str) -> Optional[dict]:
        if not data or not isinstance(data, dict):
            return None
        nombre = (
            data.get("nombreCompleto")
            or data.get("nombre")
            or data.get("name")
            or nombre_fallback
        )
        return {
            "nombre":          nombre,
            "rut":             rut,
            "circunscripcion": data.get("circunscripcion") or data.get("comuna"),
            "region":          data.get("region"),
            "mesa":            str(data.get("mesa") or ""),
            "local":           data.get("local") or data.get("establecimiento"),
            "direccion_local": data.get("direccion") or data.get("direccionLocal"),
        }

    def _parsear_html(self, html: str, nombre_fallback: str, rut: str) -> Optional[dict]:
        soup = BeautifulSoup(html, "lxml")
        datos: dict = {"nombre": nombre_fallback, "rut": rut}

        # Mapa de keywords a campos
        CAMPOS = {
            "nombre":          ["nombre", "name"],
            "circunscripcion": ["circunscripción", "circunscripcion", "comuna"],
            "region":          ["región", "region"],
            "mesa":            ["mesa"],
            "local":           ["local", "establecimiento", "colegio"],
            "direccion_local": ["dirección", "direccion", "address"],
        }

        # Buscar en tablas
        for fila in soup.find_all("tr"):
            celdas = [td.get_text(strip=True) for td in fila.find_all(["td", "th"])]
            if len(celdas) < 2:
                continue
            clave_raw = celdas[0].lower()
            valor     = celdas[-1]
            for campo, aliases in CAMPOS.items():
                if any(a in clave_raw for a in aliases):
                    datos[campo] = valor
                    break

        # Buscar en pares clave:valor en párrafos/spans
        for elem in soup.find_all(["p", "span", "div", "li"]):
            texto = elem.get_text(strip=True)
            for campo, aliases in CAMPOS.items():
                for alias in aliases:
                    pattern = re.compile(rf"{alias}[:\s]+(.+)", re.I)
                    match = pattern.search(texto)
                    if match and campo not in datos:
                        datos[campo] = match.group(1).strip()[:100]

        # Verificar que encontramos algo útil más allá del fallback
        campos_encontrados = [k for k in datos if k not in ("nombre", "rut") and datos[k]]
        if not campos_encontrados:
            return None

        return datos
