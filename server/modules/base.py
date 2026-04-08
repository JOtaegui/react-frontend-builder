"""
BaseModule — contrato que todo módulo OSINT debe cumplir.

Para agregar un nuevo módulo:
1. Crea un archivo en modules/
2. Hereda de BaseModule
3. Implementa `run(self, context: QueryContext) -> ModuleResult`
4. Regístralo en el orchestrator

El aislamiento de fallos está en el orchestrator, no aquí.
Cada módulo debe fallar rápido con una excepción clara.
"""
from __future__ import annotations

import time
import logging
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import Any, Optional

logger = logging.getLogger(__name__)


@dataclass
class QueryContext:
    """
    Todo lo que un módulo necesita para correr.
    Se construye una vez en el orchestrator y se pasa a todos los módulos.
    """
    nombre: str                          # Nombre completo ingresado
    nombre_normalizado: str              # Lowercase, sin tildes, sin dobles espacios
    rut: Optional[str] = None           # Opcional — si el usuario lo proveyó
    email: Optional[str] = None         # Opcional — si el usuario lo proveyó
    # Se va llenando durante la ejecución (algunos módulos dependen de otros)
    emails_encontrados: list[str] = field(default_factory=list)


@dataclass  
class ModuleResult:
    """
    Lo que devuelve un módulo al orchestrator.
    `data` es un dict libre — el orchestrator lo mergea en OSINTFuentes.
    `hallazgos` es el conteo para el resumen.
    """
    module_name: str
    success: bool
    data: dict[str, Any] = field(default_factory=dict)
    hallazgos: int = 0
    error: Optional[str] = None
    duration_ms: int = 0


class BaseModule(ABC):
    """Clase base para todos los módulos OSINT."""

    name: str = "base"          # Sobreescribir en cada subclase
    timeout: int = 15           # Sobreescribir con el valor de config

    @abstractmethod
    async def run(self, context: QueryContext) -> ModuleResult:
        """
        Ejecuta la búsqueda del módulo.
        - Nunca debe capturar todas las excepciones silenciosamente.
        - Lanza excepciones — el orchestrator las captura y marca el módulo como fallido.
        - Usa self.timeout para controlar requests HTTP.
        """
        ...

    def _result(
        self,
        data: dict[str, Any],
        hallazgos: int,
        start: float,
    ) -> ModuleResult:
        """Helper para construir un ModuleResult exitoso."""
        return ModuleResult(
            module_name=self.name,
            success=True,
            data=data,
            hallazgos=hallazgos,
            duration_ms=int((time.time() - start) * 1000),
        )

    def _error_result(self, error: str, start: float) -> ModuleResult:
        """Helper para construir un ModuleResult fallido."""
        logger.warning(f"[{self.name}] falló: {error}")
        return ModuleResult(
            module_name=self.name,
            success=False,
            error=error,
            duration_ms=int((time.time() - start) * 1000),
        )