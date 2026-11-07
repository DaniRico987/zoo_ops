"""Composición de generación y ranking para proponer planes."""

from dataclasses import dataclass
from typing import Mapping, Optional, Tuple

from zoo_ops.dominio.entidades import Mundo
from zoo_ops.dominio.enums import EstadoAnimal, TipoVehiculo
from zoo_ops.dominio.errores import ErrorDominio
from zoo_ops.dominio.reservas import RegistroReservas
from zoo_ops.asignacion.candidatos import Descartado, generar_candidatos
from zoo_ops.asignacion.puntaje import (
    ESCALA_TIEMPO_SEGUNDOS, Perfil, Pesos, Puntuado, perfil_de_tarea,
    puntuar_candidatos,
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
    escala_tiempo_segundos: float = ESCALA_TIEMPO_SEGUNDOS,
    perfiles_por_tipo: Optional[Mapping[str, Perfil]] = None,
    tipos_vehiculo_excluidos: Optional[Tuple[TipoVehiculo, ...]] = None,
) -> Propuesta:
    """Genera y puntúa alternativas, sin confirmar ni ejecutar ninguna."""
    tarea = mundo.tareas.get(tarea_id)
    if tarea is None:
        raise ErrorDominio(f"La tarea {tarea_id} no existe en el mundo")
    animales = tuple(sorted(
        set(animales_transportados)
        | {
            efecto.animal_id
            for efecto in tarea.efectos
            if efecto.estado == EstadoAnimal.EN_TRASLADO
        }
    ))
    perfil_elegido = (
        perfil
        if perfil is not None
        else perfil_de_tarea(tarea, perfiles_por_tipo)
    )
    tipos_excluidos = (
        tipos_vehiculo_excluidos
        if tipos_vehiculo_excluidos is not None
        else (
            ()
            if perfil_elegido == Perfil.EMERGENCIA
            else (TipoVehiculo.HELICOPTERO,)
        )
    )
    resultado = generar_candidatos(
        mundo,
        registro_reservas,
        tarea_id,
        ahora,
        animales,
        permitir_vehiculos,
        max_combinaciones,
        tipos_excluidos,
    )
    ranking = puntuar_candidatos(
        mundo,
        tarea_id,
        resultado.candidatos,
        perfil=perfil_elegido,
        pesos=pesos,
        escala_tiempo_segundos=escala_tiempo_segundos,
    )
    return Propuesta(
        tarea_id=tarea_id,
        perfil=perfil_elegido,
        ranking=ranking,
        descartados=resultado.descartados,
    )
