"""Composición de generación y ranking para proponer planes."""

from dataclasses import dataclass
from typing import Optional, Tuple

from zoo_ops.dominio.entidades import Mundo
from zoo_ops.dominio.errores import ErrorDominio
from zoo_ops.dominio.reservas import RegistroReservas
from zoo_ops.asignacion.candidatos import Descartado, generar_candidatos
from zoo_ops.asignacion.puntaje import (
    Perfil, Pesos, Puntuado, perfil_de_tarea, puntuar_candidatos,
)


@dataclass(frozen=True)
class Propuesta:
    """Alternativas puntuadas para revisión y confirmación externa."""

    tarea_id: str
    perfil: Perfil
    ranking: Tuple[Puntuado, ...]
    descartados: Tuple[Descartado, ...]


def proponer_planes(
    mundo: Mundo,
    registro_reservas: RegistroReservas,
    tarea_id: str,
    ahora: int,
    animales_transportados: Tuple[str, ...] = (),
    permitir_vehiculos: bool = True,
    max_combinaciones: int = 2000,
    perfil: Optional[Perfil] = None,
    pesos: Optional[Pesos] = None,
) -> Propuesta:
    """Genera y puntúa alternativas, sin confirmar ni ejecutar ninguna."""
    tarea = mundo.tareas.get(tarea_id)
    if tarea is None:
        raise ErrorDominio(f"La tarea {tarea_id} no existe en el mundo")
    perfil_elegido = perfil if perfil is not None else perfil_de_tarea(tarea)
    resultado = generar_candidatos(
        mundo,
        registro_reservas,
        tarea_id,
        ahora,
        animales_transportados,
        permitir_vehiculos,
        max_combinaciones,
    )
    ranking = puntuar_candidatos(
        mundo,
        tarea_id,
        resultado.candidatos,
        perfil=perfil_elegido,
        pesos=pesos,
    )
    return Propuesta(
        tarea_id=tarea_id,
        perfil=perfil_elegido,
        ranking=ranking,
        descartados=resultado.descartados,
    )
