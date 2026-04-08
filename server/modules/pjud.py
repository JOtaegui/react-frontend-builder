"""
Módulo: PJUD — Poder Judicial de Chile
Consulta causas judiciales públicas por nombre de parte.

URLs reales confirmadas:
  Civil:   https://oficinajudicialvirtual.pjud.cl/causas/civiles/index.php
  Penal:   https://oficinajudicialvirtual.pjud.cl/causas/penales/index.php
  Laboral: https://oficinajudicialvirtual.pjud.cl/causas/laborales/index.php
  Familia: https://oficinajudicialvirtual.pjud.cl/causas/familia/index.php
  Cobranza: https://oficinajudicialvirtual.pjud.cl/causas/cobranza/index.php

Cada endpoint acepta POST con campo `conparte` (nombre del involucrado).
"""
from __future__ import annotations

import asyncio
import re
import time
import logging
from dataclasses import dataclass

from bs4 import BeautifulSoup

from config import TIMEOUT_PJUD
from modules.base import BaseModule, QueryContext, ModuleResult
from utils.scraping import parsear_tabla, detectar_bloqueo, get_with_retry, limpiar_rut

logger = logging.getLogger(__name__)

OJV_BASE = "https://oficinajudicialvirtual.pjud.cl"

@dataclass
class TipoCausa:
    codigo: str
    label: str
    url: str

TIPOS = [
    TipoCausa("C", "Civil",    f"{OJV_BASE}/causas/civiles/index.php"),
    TipoCausa("P", "Penal",    f"{OJV_BASE}/causas/penales/index.php"),
    TipoCausa("L", "Laboral",  f"{OJV_BASE}/causas/laborales/index.php"),
    TipoCausa("F", "Familia",  f"{OJV_BASE}/causas/familia/index.php"),
    TipoCausa("B", "Cobranza", f"{OJV_BASE}/causas/cobranza/index.php"),
]


class PjudModule(BaseModule):
    name    = "pjud"
    timeout = TIMEOUT_PJUD

    async def run(self, context: QueryContext) -> ModuleResult:
        start = time.time()
        try:
            # Correr Civil y Penal en paralelo primero (más relevantes)
            # Laboral, Familia y Cobranza también pero con menos prioridad
            tareas = [
                self._buscar_tipo(tipo, context.nombre)
                for tipo in TIPOS
            ]
            resultados_por_tipo = await asyncio.gather(*tareas, return_exceptions=True)

            causas: list[dict] = []
            for res in resultados_por_tipo:
                if isinstance(res, list):
                    causas.extend(res)

            # Si hay RUT y no encontramos nada, intentar búsqueda por RUT
            if not causas and context.rut:
                causas = await self._buscar_por_rut(context.rut)

            if not causas:
                return self._result({}, 0, start)

            return self._result({"pjud": causas}, len(causas), start)

        except Exception as exc:
            return self._error_result(str(exc), start)

    async def _buscar_tipo(self, tipo: TipoCausa, nombre: str) -> list[dict]:
        """Busca causas de un tipo específico por nombre de parte."""
        try:
            resp = await self.client.post(
                tipo.url,
                data={
                    "conparte":   nombre,
                    "tipoCausa":  tipo.codigo,
                    "buscar":     "Buscar",
                    "page":       "1",
                },
                timeout=self.timeout,
            )
            if resp.status_code != 200 or detectar_bloqueo(resp.text):
                return []

            return self._parsear(resp.text, tipo.label)

        except Exception as e:
            logger.debug(f"[pjud] {tipo.label} falló: {e}")
            return []

    async def _buscar_por_rut(self, rut: str) -> list[dict]:
        """Búsqueda por RUT — más precisa."""
        rut_limpio = limpiar_rut(rut)
        causas = []
        for tipo in TIPOS[:2]:  # Solo civil y penal por RUT
            try:
                resp = await self.client.post(
                    tipo.url,
                    data={"rut": rut_limpio, "buscar": "Buscar"},
                    timeout=self.timeout,
                )
                if resp.status_code == 200:
                    causas.extend(self._parsear(resp.text, tipo.label))
            except Exception as e:
                logger.debug(f"[pjud] RUT {tipo.label} falló: {e}")
        return causas

    def _parsear(self, html: str, tipo_default: str) -> list[dict]:
        """
        Parsea la tabla de causas de OJV.
        Estructura típica: ROL | Tribunal | Caratulado | Materia | Estado | Fecha
        """
        soup = BeautifulSoup(html, "lxml")
        causas = []

        # Intentar parsear con columnas conocidas
        COLS = ["rol", "tribunal", "caratulado", "materia", "estado", "fecha"]
        for tabla in soup.find_all("table"):
            filas = parsear_tabla(tabla, columnas=COLS)
            for fila in filas:
                rol = fila.get("rol", "").strip()
                # El ROL debe tener formato NNN-AAAA o C-NNN-AAAA
                if not re.search(r"\d{1,6}-\d{4}", rol):
                    continue
                causas.append({
                    "rol":      rol,
                    "tribunal": (fila.get("tribunal") or "").strip()[:100],
                    "materia":  (fila.get("materia") or fila.get("caratulado") or tipo_default)[:100],
                    "estado":   (fila.get("estado") or "").strip()[:50] or None,
                    "fecha":    (fila.get("fecha") or "").strip()[:20] or None,
                })
            if causas:
                return causas[:15]

        # Fallback: buscar patrones ROL directamente en el HTML
        ROL_RE = re.compile(r"\b[A-Z]?-?\d{1,6}-\d{4}\b")
        for match in ROL_RE.finditer(html):
            rol = match.group()
            # Tomar contexto cercano para extraer tribunal
            inicio = max(0, match.start() - 200)
            contexto = html[inicio: match.end() + 200]
            causas.append({
                "rol":      rol,
                "tribunal": "—",
                "materia":  tipo_default,
                "estado":   None,
                "fecha":    None,
            })
            if len(causas) >= 10:
                break

        return causas