"""
Módulo: Registro de Empresas
Consulta el registro público de empresas usando la API del Estado de Chile.

Fuentes:
- https://apis.digital.gob.cl (API REST pública — sin auth)
- Registro de Empresas y Sociedades (RES) del Ministerio de Economía

Notas:
- La API de empresas del gobierno permite búsqueda por nombre de razón social
- Para personas naturales: buscar empresas donde la persona sea representante/socio
- Sin RUT es búsqueda por nombre de empresa (menos precisa)
"""
from __future__ import annotations

import time
import logging
from typing import List, Union

from bs4 import BeautifulSoup

from config import TIMEOUT_EMPRESAS
from modules.base import BaseModule, QueryContext, ModuleResult

logger = logging.getLogger(__name__)

# API pública del gobierno de Chile
EMPRESAS_API = "https://apis.digital.gob.cl/res/empresas"
# Alternativa: Registro de Comercio SRCeI
SRCEI_URL    = "https://www.registrodeempresasysociedades.cl"
# SRCeI API búsqueda
SRCEI_SEARCH = "https://api.registrodeempresasysociedades.cl/empresas"


class EmpresasModule(BaseModule):
    name = "empresas"
    timeout = TIMEOUT_EMPRESAS

    async def run(self, context: QueryContext) -> ModuleResult:
        start = time.time()
        empresas: List[dict] = []

        try:
            # Búsqueda 1: API digital.gob.cl por nombre
            empresas_nombre = await self._buscar_por_nombre(context.nombre)
            empresas.extend(empresas_nombre)

            # Búsqueda 2: Si hay RUT, buscar empresas del contribuyente
            if context.rut:
                empresas_rut = await self._buscar_por_rut(context.rut)
                # Deduplicar
                ruts_existentes = {e.get("rut_empresa") for e in empresas}
                for e in empresas_rut:
                    if e.get("rut_empresa") not in ruts_existentes:
                        empresas.append(e)

            if not empresas:
                return self._result({}, 0, start)

            return self._result({"empresas": empresas}, len(empresas), start)

        except Exception as exc:
            return self._error_result(str(exc), start)

    async def _buscar_por_nombre(self, nombre: str) -> List[dict]:
        """
        Busca en el Registro de Empresas por nombre/razón social.
        Útil para encontrar empresas que llevan el nombre de la persona.
        """
        # Intentar con apellidos (más preciso que nombre completo)
        partes = nombre.strip().split()
        # Para una persona "Juan Ignacio Pérez Silva", intentar con apellido
        query = " ".join(partes[-2:]) if len(partes) >= 2 else nombre

        try:
            resp = await self.client.get(
                SRCEI_SEARCH,
                params={"q": query, "limit": 20},
                timeout=self.timeout,
            )
            if resp.status_code == 200:
                data = resp.json()
                return self._parsear_api_srcei(data)
        except Exception as e:
            logger.debug(f"[empresas] API SRCeI falló: {e}")

        # Fallback: API digital.gob.cl
        try:
            resp = await self.client.get(
                EMPRESAS_API,
                params={"nombre": query},
                timeout=self.timeout,
            )
            if resp.status_code == 200:
                data = resp.json()
                return self._parsear_api_digital(data)
        except Exception as e:
            logger.debug(f"[empresas] API digital.gob.cl falló: {e}")

        return []

    async def _buscar_por_rut(self, rut: str) -> List[dict]:
        """
        Busca empresas asociadas a un RUT específico (como representante o socio).
        """
        rut_limpio = rut.replace(".", "").replace(" ", "")
        try:
            resp = await self.client.get(
                SRCEI_SEARCH,
                params={"rut": rut_limpio, "limit": 20},
                timeout=self.timeout,
            )
            if resp.status_code == 200:
                return self._parsear_api_srcei(resp.json())
        except Exception as e:
            logger.debug(f"[empresas] Búsqueda por RUT falló: {e}")

        return []

    def _parsear_api_srcei(self, data: Union[dict, list]) -> List[dict]:
        """Parsea respuesta de la API del Registro de Empresas."""
        items = data if isinstance(data, list) else data.get("data", data.get("empresas", []))
        resultados = []
        for item in items[:20]:
            resultados.append({
                "razon_social": item.get("razon_social") or item.get("nombre", "Sin nombre"),
                "rut_empresa":  item.get("rut") or item.get("rut_empresa"),
                "tipo":         item.get("tipo") or item.get("tipo_empresa"),
                "estado":       item.get("estado") or item.get("vigencia", "Vigente"),
            })
        return resultados

    def _parsear_api_digital(self, data: Union[dict, list]) -> List[dict]:
        """Parsea respuesta de api.digital.gob.cl."""
        items = data if isinstance(data, list) else data.get("hits", data.get("results", []))
        resultados = []
        for item in items[:20]:
            source = item.get("_source", item)
            resultados.append({
                "razon_social": source.get("nombre") or source.get("razon_social", ""),
                "rut_empresa":  source.get("rut"),
                "tipo":         source.get("tipo"),
                "estado":       source.get("estado", "Vigente"),
            })
        return [r for r in resultados if r["razon_social"]]
