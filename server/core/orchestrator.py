"""
Orchestrator — núcleo del sistema.

Decisiones de diseño:
- asyncio.gather con return_exceptions=True → si un módulo falla, los demás siguen
- Los módulos corren en paralelo (máximo beneficio para fuentes independientes)
- Dependencias: HIBP necesita emails, por eso corre en una segunda oleada
- Logging estructurado de cada módulo: nombre, duración, hallazgos o error
"""
from __future__ import annotations

import asyncio
import logging
import unicodedata
import re
import time
from typing import Any, List, Optional, Set, Type

import httpx

from config import (
    DEFAULT_HEADERS,
)
from models.schemas import (
    OSINTFuentes, OSINTResumen, OSINTResponse, ModuleError,
    NRYFEntry, ServelEntry, SIIEntry, EmpresaEntry, PjudEntry,
    DiarioOficialEntry, EmailEntry, HibpResult, InstitucionEntry,
)
from modules.base import QueryContext, ModuleResult, BaseModule

# ── Importar módulos ─────────────────────────────────────────────────────────
from modules.nryf import NRYFModule
from modules.servel import ServelModule
from modules.sii import SIIModule
from modules.empresas import EmpresasModule
from modules.pjud import PjudModule
from modules.diario_oficial import DiarioOficialModule
from modules.emails_publicos import EmailsPublicosModule
from modules.instituciones_publicas import InstitucionesPublicasModule
from modules.hibp import HibpModule

logger = logging.getLogger(__name__)


def _normalizar(nombre: str) -> str:
    """Quita tildes, pasa a lowercase, colapsa espacios."""
    nfkd = unicodedata.normalize("NFKD", nombre)
    sin_tildes = "".join(c for c in nfkd if not unicodedata.combining(c))
    return re.sub(r"\s+", " ", sin_tildes.lower().strip())


# ── Módulos de primera oleada (independientes entre sí) ─────────────────────
WAVE_1_MODULES: List[Type[BaseModule]] = [
    NRYFModule,
    ServelModule,
    SIIModule,
    EmpresasModule,
    PjudModule,
    DiarioOficialModule,
    EmailsPublicosModule,
]


async def run_search(
    nombre: str,
    rut: Optional[str] = None,
    email: Optional[str] = None,
) -> OSINTResponse:
    """
    Punto de entrada principal del sistema.
    1. Construye el contexto
    2. Corre Wave 1 en paralelo
    3. Extrae emails de los resultados
    4. Corre Wave 2 (HIBP) con los emails encontrados
    5. Ensambla y devuelve la respuesta
    """
    t0 = time.time()
    context = QueryContext(
        nombre=nombre.strip(),
        nombre_normalizado=_normalizar(nombre),
        rut=rut,
        email=email,
    )

    logger.info(f"Iniciando búsqueda: '{nombre}' | rut={rut}")

    # ── Shared HTTP client (reusado por todos los módulos) ───────────────────
    async with httpx.AsyncClient(
        headers=DEFAULT_HEADERS,
        follow_redirects=True,
        timeout=30.0,
    ) as client:

        # ── Wave 1: todas las fuentes chilenas en paralelo ───────────────────
        wave1_tasks = [
            _run_module(module_cls(), context, client)
            for module_cls in WAVE_1_MODULES
        ]
        wave1_results: list[ModuleResult] = await asyncio.gather(*wave1_tasks)

        instituciones_result = await _run_module(InstitucionesPublicasModule(), context, client)
        wave1_results.append(instituciones_result)

        # Extraer emails de resultados de wave 1 para HIBP
        emails = _extract_emails(wave1_results, email)
        context.emails_encontrados = emails

        # ── Wave 2: HIBP (necesita emails) ───────────────────────────────────
        hibp_result = None
        if emails:
            hibp_result = await _run_module(HibpModule(), context, client)

    # ── Ensamblar respuesta ──────────────────────────────────────────────────
    all_results = wave1_results + ([hibp_result] if hibp_result else [])
    response = _assemble_response(nombre, rut, context, all_results)

    logger.info(
        f"Búsqueda completada en {int((time.time()-t0)*1000)}ms | "
        f"hallazgos={response.resumen.total_hallazgos}"
    )
    return response


async def _run_module(
    module: BaseModule,
    context: QueryContext,
    client: httpx.AsyncClient,
) -> ModuleResult:
    """
    Wrapper que aísla el fallo de un módulo individual.
    Inyecta el cliente HTTP en el módulo antes de correrlo.
    """
    import time
    start = time.time()
    try:
        # Inyectar cliente compartido
        module.client = client  # type: ignore[attr-defined]
        result = await asyncio.wait_for(
            module.run(context),
            timeout=module.timeout + 5,  # margen sobre el timeout del módulo
        )
        logger.info(
            f"[{module.name}] ✓ {result.hallazgos} hallazgos "
            f"en {result.duration_ms}ms"
        )
        return result
    except asyncio.TimeoutError:
        msg = f"Timeout después de {module.timeout}s"
        logger.warning(f"[{module.name}] ✗ {msg}")
        return ModuleResult(
            module_name=module.name,
            success=False,
            error=msg,
            duration_ms=int((time.time() - start) * 1000),
        )
    except Exception as exc:
        msg = str(exc)
        logger.error(f"[{module.name}] ✗ Error inesperado: {msg}", exc_info=True)
        return ModuleResult(
            module_name=module.name,
            success=False,
            error=msg,
            duration_ms=int((time.time() - start) * 1000),
        )


def _extract_emails(results: List[ModuleResult], seed_email: Optional[str]) -> List[str]:
    """Recolecta emails de cualquier módulo que los haya encontrado."""
    emails: Set[str] = set()
    if seed_email:
        emails.add(seed_email.lower())
    for r in results:
        for e in r.data.get("emails", []):
            emails.add(e.lower())
    return list(emails)


def _assemble_response(
    nombre: str,
    rut: Optional[str],
    context: QueryContext,
    results: List[ModuleResult],
) -> OSINTResponse:
    """Construye OSINTResponse a partir de los ModuleResult."""

    fuentes = OSINTFuentes()
    fuentes_con_datos: List[str] = []
    total_hallazgos = 0
    module_errors: List[str] = []

    for r in results:
        if not r.success:
            module_errors.append(f"{r.module_name}: {r.error}")
            continue

        total_hallazgos += r.hallazgos
        data = r.data

        if r.module_name == "nryf" and data.get("nryf_nombre"):
            fuentes.nryf_nombre = [NRYFEntry(**e) for e in data["nryf_nombre"]]
            if data.get("nryf_rut"):
                fuentes.nryf_rut = NRYFEntry(**data["nryf_rut"])
            fuentes_con_datos.append("NombreRutYFirma")

        elif r.module_name == "servel" and data.get("servel"):
            fuentes.servel = ServelEntry(**data["servel"])
            fuentes_con_datos.append("SERVEL")

        elif r.module_name == "sii" and data.get("sii"):
            fuentes.sii = SIIEntry(**data["sii"])
            fuentes_con_datos.append("SII")

        elif r.module_name == "empresas" and data.get("empresas"):
            fuentes.empresas = [EmpresaEntry(**e) for e in data["empresas"]]
            fuentes_con_datos.append("Empresas")

        elif r.module_name == "pjud" and data.get("pjud"):
            fuentes.pjud = [PjudEntry(**e) for e in data["pjud"]]
            fuentes_con_datos.append("PJUD")

        elif r.module_name == "diario_oficial" and data.get("diario_oficial"):
            fuentes.diario_oficial = [DiarioOficialEntry(**e) for e in data["diario_oficial"]]
            fuentes_con_datos.append("Diario Oficial")

        elif r.module_name == "emails_publicos" and data.get("emails_publicos"):
            fuentes.emails_publicos = [EmailEntry(**e) for e in data["emails_publicos"]]
            fuentes_con_datos.append("Emails")

        elif r.module_name == "instituciones_publicas" and data.get("instituciones_relacionadas"):
            fuentes.instituciones_relacionadas = [InstitucionEntry(**e) for e in data["instituciones_relacionadas"]]
            fuentes_con_datos.append("Instituciones")

        elif r.module_name == "hibp" and data.get("hibp"):
            fuentes.hibp = [HibpResult(**h) for h in data["hibp"]]
            fuentes_con_datos.append("HIBP")

    # Advertencia si hubo errores
    advertencia = None
    if module_errors:
        advertencia = f"Módulos con error: {', '.join(module_errors)}"
        logger.warning(advertencia)

    resumen = OSINTResumen(
        total_hallazgos=total_hallazgos,
        fuentes_con_datos=fuentes_con_datos,
        tiene_antecedentes_judiciales=len(fuentes.pjud) > 0,
        tiene_actividad_empresarial=len(fuentes.empresas) > 0 or fuentes.sii is not None,
        inscrito_servel=fuentes.servel is not None,
        emails_encontrados=context.emails_encontrados,
        total_leaks=sum(len(h.breaches) for h in fuentes.hibp),
        advertencia=advertencia,
    )

    return OSINTResponse(
        query=nombre,
        rut=rut,
        fuentes=fuentes,
        resumen=resumen,
    )
