"""
Módulo: Diario Oficial de Chile
Busca menciones en publicaciones oficiales.

Fuente: https://www.diariooficial.interior.gob.cl
        API de búsqueda de publicaciones

Contenido típico:
- Nombramientos de cargos públicos
- Constitución de empresas
- Notificaciones judiciales
- Decretos y resoluciones
"""
from __future__ import annotations

import time
import logging
import re
from typing import List, Union

from bs4 import BeautifulSoup

from config import DO_SEARCH_URL, TIMEOUT_DIARIO_OFICIAL
from modules.base import BaseModule, QueryContext, ModuleResult

logger = logging.getLogger(__name__)

DO_BASE = "https://www.diariooficial.interior.gob.cl"
DO_API  = f"{DO_BASE}/api/publicaciones/buscar"


class DiarioOficialModule(BaseModule):
    name = "diario_oficial"
    timeout = TIMEOUT_DIARIO_OFICIAL

    async def run(self, context: QueryContext) -> ModuleResult:
        start = time.time()

        try:
            resultados = await self._buscar(context.nombre)

            if not resultados:
                return self._result({}, 0, start)

            return self._result(
                {"diario_oficial": resultados},
                len(resultados),
                start,
            )

        except Exception as exc:
            return self._error_result(str(exc), start)

    async def _buscar(self, nombre: str) -> List[dict]:
        """Busca en el Diario Oficial por nombre."""

        # Intento 1: API JSON
        try:
            resp = await self.client.get(
                DO_API,
                params={"q": nombre, "per_page": 10},
                timeout=self.timeout,
            )
            if resp.status_code == 200:
                data = resp.json()
                resultados = self._parsear_api(data)
                if resultados:
                    return resultados
        except Exception as e:
            logger.debug(f"[diario_oficial] API falló: {e}")

        # Intento 2: Scraping del buscador web
        try:
            resp = await self.client.get(
                DO_SEARCH_URL,
                params={"q": nombre, "page": 1},
                timeout=self.timeout,
            )
            if resp.status_code == 200:
                return self._parsear_html(resp.text)
        except Exception as e:
            logger.debug(f"[diario_oficial] Scraping falló: {e}")

        return []

    def _parsear_api(self, data: Union[dict, list]) -> List[dict]:
        """Parsea respuesta JSON de la API del Diario Oficial."""
        items = (
            data if isinstance(data, list)
            else data.get("data", data.get("publicaciones", data.get("results", [])))
        )
        resultados = []
        for item in items[:10]:
            url = item.get("url") or item.get("link") or ""
            if url and not url.startswith("http"):
                url = f"{DO_BASE}{url}"

            resultados.append({
                "titulo":      item.get("titulo") or item.get("title") or item.get("nombre", "Sin título"),
                "url":         url,
                "descripcion": item.get("descripcion") or item.get("extracto") or item.get("summary"),
            })
        return [r for r in resultados if r["titulo"] != "Sin título" or r["url"]]

    def _parsear_html(self, html: str) -> List[dict]:
        """Parsea resultados del buscador web del Diario Oficial."""
        soup = BeautifulSoup(html, "html.parser")
        resultados = []

        # El DO usa una estructura de lista de resultados
        items = (
            soup.find_all("div", class_=re.compile(r"result|item|publicacion", re.I))
            or soup.find_all("li", class_=re.compile(r"result|item", re.I))
            or soup.find_all("article")
        )

        for item in items[:10]:
            # Extraer enlace y título
            a_tag = item.find("a", href=True)
            if not a_tag:
                continue

            href = a_tag.get("href", "")
            titulo = a_tag.get_text(strip=True)
            if not titulo:
                titulo = item.find(["h2", "h3", "h4", "strong"])
                titulo = titulo.get_text(strip=True) if titulo else "Sin título"

            # URL absoluta
            url = href if href.startswith("http") else f"{DO_BASE}{href}"

            # Descripción/extracto
            desc_tag = item.find("p") or item.find("span", class_=re.compile(r"desc|extract|resumen", re.I))
            descripcion = desc_tag.get_text(strip=True)[:200] if desc_tag else None

            if titulo and url:
                resultados.append({
                    "titulo": titulo[:150],
                    "url": url,
                    "descripcion": descripcion,
                })

        return resultados
