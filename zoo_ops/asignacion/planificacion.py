"""Planificación global de tareas pendientes sin mutar el mundo recibido."""

from dataclasses import dataclass
from types import MappingProxyType
from typing import Any, Mapping, Optional, Tuple

from zoo_ops.dominio.entidades import Mundo, Tarea
from zoo_ops.dominio.enums import EstadoTarea, PrioridadTarea
from zoo_ops.dominio.errores import ErrorDominio, TiempoRetrocede
from zoo_ops.dominio.eventos import RegistroEventos
from zoo_ops.dominio.operaciones import asignar_plan
from zoo_ops.dominio.plan import PlanEjecucion
from zoo_ops.dominio.reservas import (
    RegistroReservas, Reserva, paquete_de_reservas,
)
from zoo_ops.asignacion.puntaje import Perfil, Puntuado, perfil_de_tarea
from zoo_ops.asignacion.propuesta import Propuesta, proponer_planes


_ORDEN_PERFILES = (
    Perfil.EMERGENCIA,
    Perfil.RUTINA,
    Perfil.MANTENIMIENTO,
)


@dataclass(frozen=True)
class Asignacion:
    """Una propuesta seleccionada para una tarea."""

    tarea_id: str
    puntuado: Puntuado


@dataclass(frozen=True)
class NoAsignada:
    """Una tarea lista que no recibió una propuesta global."""

    tarea_id: str
    motivo: str
    detalle: Tuple[str, ...]


@dataclass(frozen=True)
class ResultadoGlobal:
    """Resultado inmutable de una planificación global por niveles."""

    asignaciones: Tuple[Asignacion, ...]
    no_asignadas: Tuple[NoAsignada, ...]
    estrategia_por_nivel: Mapping[Perfil, str]
    nodos_explorados: int


def peso_prioridad(tarea: Tarea) -> int:
    """Devuelve peso creciente según el orden BAJA, MEDIA, ALTA y CRITICA."""
    prioridades = tuple(sorted(PrioridadTarea))
    try:
        return prioridades.index(tarea.prioridad_base) + 1
    except ValueError as exc:
        raise ErrorDominio(
            f"Prioridad inválida en la tarea {tarea.id}"
        ) from exc


def _perfil_planificador(
    tarea: Tarea,
    perfil_explicito: Optional[Perfil],
    perfiles_por_tipo: Optional[Mapping[str, Perfil]],
) -> Perfil:
    if perfil_explicito is not None:
        return perfil_explicito
    return perfil_de_tarea(tarea, perfiles_por_tipo)


def tareas_listas(mundo: Mundo) -> Tuple[Tarea, ...]:
    """Devuelve tareas pendientes con dependencias completas y sin plan."""
    orden_perfil = {
        perfil: indice for indice, perfil in enumerate(_ORDEN_PERFILES)
    }
    listas = [
        tarea
        for tarea in mundo.tareas.values()
        if tarea.estado == EstadoTarea.PENDIENTE
        and tarea.id not in mundo.planes
        and all(
            dependencia in mundo.tareas
            and mundo.tareas[dependencia].estado == EstadoTarea.COMPLETADA
            for dependencia in tarea.dependencias
        )
    ]
    return tuple(sorted(
        listas,
        key=lambda tarea: (
            orden_perfil[perfil_de_tarea(tarea)],
            -peso_prioridad(tarea),
            -tarea.urgencia,
            tarea.id,
        ),
    ))


def _planes_conflictivos(
    reservas_a: Tuple[Reserva, ...],
    reservas_b: Tuple[Reserva, ...],
) -> bool:
    return any(
        reserva_a.solapa_con(reserva_b)
        for reserva_a in reservas_a
        for reserva_b in reservas_b
    )


def _seleccion_voraz(
    tareas: Tuple[Tarea, ...],
    rankings: Mapping[str, Tuple[Puntuado, ...]],
    reservas_por_candidato: Mapping[Puntuado, Tuple[Reserva, ...]],
) -> Tuple[Puntuado, ...]:
    ordenadas = sorted(
        tareas,
        key=lambda tarea: (
            -peso_prioridad(tarea),
            len(rankings[tarea.id]),
            tarea.id,
        ),
    )
    elegidos = []
    reservas_elegidas: list[Reserva] = []
    for tarea in ordenadas:
        for puntuado in rankings[tarea.id]:
            reservas_candidato = reservas_por_candidato[puntuado]
            if not _planes_conflictivos(
                reservas_candidato,
                tuple(reservas_elegidas),
            ):
                elegidos.append(puntuado)
                reservas_elegidas.extend(reservas_candidato)
                break
    return tuple(elegidos)


def _seleccion_exacta(
    tareas: Tuple[Tarea, ...],
    rankings: Mapping[str, Tuple[Puntuado, ...]],
    reservas_por_candidato: Mapping[Puntuado, Tuple[Reserva, ...]],
    max_nodos: int,
) -> Tuple[Tuple[Puntuado, ...], int, bool]:
    ordenadas = tuple(sorted(
        tareas,
        key=lambda tarea: (
            -peso_prioridad(tarea),
            len(rankings[tarea.id]),
            tarea.id,
        ),
    ))
    mejor_objetivo = (-1, float("-inf"))
    mejor_seleccion: Tuple[Puntuado, ...] = ()
    actual: list[Puntuado] = []
    reservas_actuales: list[Reserva] = []
    nodos = 0
    excedido = False

    prioridades_restantes = [0] * (len(ordenadas) + 1)
    puntajes_restantes = [0.0] * (len(ordenadas) + 1)
    for indice in range(len(ordenadas) - 1, -1, -1):
        ranking = rankings[ordenadas[indice].id]
        prioridades_restantes[indice] = (
            prioridades_restantes[indice + 1]
            + peso_prioridad(ordenadas[indice])
        )
        puntajes_restantes[indice] = (
            puntajes_restantes[indice + 1]
            + max(puntuado.puntaje for puntuado in ranking)
        )

    def buscar(indice: int, prioridad_actual: int, puntaje_actual: float) -> None:
        nonlocal nodos, excedido, mejor_objetivo, mejor_seleccion
        nodos += 1
        if nodos > max_nodos:
            excedido = True
            return
        cota = (
            prioridad_actual + prioridades_restantes[indice],
            puntaje_actual + puntajes_restantes[indice],
        )
        if mejor_objetivo >= cota:
            return
        if indice == len(ordenadas):
            objetivo = (prioridad_actual, puntaje_actual)
            if objetivo > mejor_objetivo:
                mejor_objetivo = objetivo
                mejor_seleccion = tuple(actual)
            return

        tarea = ordenadas[indice]
        for puntuado in rankings[tarea.id]:
            reservas_candidato = reservas_por_candidato[puntuado]
            if _planes_conflictivos(
                reservas_candidato,
                tuple(reservas_actuales),
            ):
                continue
            actual.append(puntuado)
            reservas_actuales.extend(reservas_candidato)
            buscar(
                indice + 1,
                prioridad_actual + peso_prioridad(tarea),
                puntaje_actual + puntuado.puntaje,
            )
            del reservas_actuales[-len(reservas_candidato):]
            actual.pop()
            if excedido:
                return

        buscar(indice + 1, prioridad_actual, puntaje_actual)

    buscar(0, 0, 0.0)
    return mejor_seleccion, nodos, excedido


def _resumen_descartados(propuesta: Propuesta) -> Tuple[str, ...]:
    return tuple(
        f"{descartado.motivo}: {'; '.join(descartado.detalle)}"
        for descartado in propuesta.descartados
    )


def planificar(
    mundo: Mundo,
    registro_reservas: RegistroReservas,
    ahora: int,
    max_nodos: int = 50_000,
    max_candidatos_por_tarea: int = 10,
    **opciones: Any,
) -> ResultadoGlobal:
    """Calcula propuestas sin mutar el mundo ni el registro recibidos."""
    if "animales_transportados" in opciones:
        raise ErrorDominio(
            "planificar no admite la opción animales_transportados"
        )
    if ahora < mundo.tiempo_actual:
        raise TiempoRetrocede(mundo.tiempo_actual, ahora)
    if (
        not isinstance(max_nodos, int)
        or isinstance(max_nodos, bool)
        or max_nodos < 1
    ):
        raise ErrorDominio("max_nodos debe ser un entero positivo")
    if (
        not isinstance(max_candidatos_por_tarea, int)
        or isinstance(max_candidatos_por_tarea, bool)
        or max_candidatos_por_tarea < 1
    ):
        raise ErrorDominio("max_candidatos_por_tarea debe ser un entero positivo")

    mundo_trabajo = mundo.instantanea()
    reservas_trabajo = RegistroReservas()
    reservas_trabajo.restaurar(registro_reservas.instantanea())
    eventos_trabajo = RegistroEventos()
    perfiles_por_tipo = opciones.get("perfiles_por_tipo")
    perfil_explicito = opciones.get("perfil")

    asignaciones = []
    no_asignadas = []
    estrategias = {}
    nodos_explorados = 0
    tareas_iniciales = tareas_listas(mundo_trabajo)

    for perfil_nivel in _ORDEN_PERFILES:
        tareas_nivel = tuple(
            tarea
            for tarea in tareas_iniciales
            if _perfil_planificador(
                tarea, perfil_explicito, perfiles_por_tipo,
            ) == perfil_nivel
        )
        rankings: dict[str, Tuple[Puntuado, ...]] = {}
        for tarea in tareas_nivel:
            opciones_propuesta = dict(opciones)
            if opciones_propuesta.get("perfil") is None:
                opciones_propuesta["perfil"] = perfil_nivel
            propuesta = proponer_planes(
                mundo_trabajo,
                reservas_trabajo,
                tarea.id,
                ahora,
                **opciones_propuesta,
            )
            ranking = propuesta.ranking[:max_candidatos_por_tarea]
            if ranking:
                rankings[tarea.id] = ranking
            else:
                no_asignadas.append(NoAsignada(
                    tarea.id,
                    "sin_candidatos",
                    _resumen_descartados(propuesta),
                ))

        tareas_con_candidatos = tuple(
            tarea for tarea in tareas_nivel if tarea.id in rankings
        )
        if tareas_con_candidatos:
            reservas_por_candidato = {
                puntuado: tuple(
                    paquete_de_reservas(puntuado.candidato.plan)
                )
                for ranking in rankings.values()
                for puntuado in ranking
            }
            seleccion_exacta, nodos, excedido = _seleccion_exacta(
                tareas_con_candidatos,
                rankings,
                reservas_por_candidato,
                max_nodos,
            )
            nodos_explorados += nodos
            if excedido:
                elegidos = _seleccion_voraz(
                    tareas_con_candidatos,
                    rankings,
                    reservas_por_candidato,
                )
                estrategias[perfil_nivel] = "voraz"
            else:
                elegidos = seleccion_exacta
                estrategias[perfil_nivel] = "exacta"
        else:
            elegidos = ()
            estrategias[perfil_nivel] = "exacta"

        elegidos_por_tarea = {
            puntuado.candidato.plan.tarea_id: puntuado
            for puntuado in elegidos
        }
        for tarea in tareas_nivel:
            puntuado = elegidos_por_tarea.get(tarea.id)
            if puntuado is None:
                if tarea.id in rankings:
                    no_asignadas.append(NoAsignada(
                        tarea.id,
                        "recursos_comprometidos",
                        ("Los candidatos entran en conflicto con planes elegidos",),
                    ))
                continue
            asignar_plan(
                mundo_trabajo,
                eventos_trabajo,
                reservas_trabajo,
                puntuado.candidato.plan,
                ahora,
                "planificacion",
            )
            asignaciones.append(Asignacion(tarea.id, puntuado))

    return ResultadoGlobal(
        asignaciones=tuple(asignaciones),
        no_asignadas=tuple(no_asignadas),
        estrategia_por_nivel=MappingProxyType(estrategias),
        nodos_explorados=nodos_explorados,
    )
