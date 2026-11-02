"""Tipos compartidos de la capa de asignación."""

from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING

from zoo_ops.dominio.plan import PlanEjecucion

if TYPE_CHECKING:
    from zoo_ops.asignacion.tiempos import Estimacion


@dataclass(frozen=True)
class Candidato:
    """Un plan viable junto con su estimación temporal."""

    plan: PlanEjecucion
    estimacion: Estimacion
