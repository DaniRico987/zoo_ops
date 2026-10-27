"""Operaciones compuestas de asignación, desasignación y ciclo de planes."""

from typing import List

from zoo_ops.dominio.entidades import Mundo
from zoo_ops.dominio.enums import (
    EstadoCuidador, EstadoTarea, EstadoVehiculo,
)
from zoo_ops.dominio.errores import ErrorDominio, TiempoRetrocede
from zoo_ops.dominio.eventos import (
    Evento, RegistroEventos, TipoEvento, aplicar_evento, crear_evento,
    plan_a_datos_extra,
)
from zoo_ops.dominio.estados import ejecutar_transicion
from zoo_ops.dominio.plan import PlanEjecucion, exigir_plan_valido
from zoo_ops.dominio.reservas import (
    RegistroReservas, liberar_reservas_tarea, paquete_de_reservas,
    reservar_atomico,
)


def registrar_plan_con_evento(
    mundo: Mundo,
    registro_eventos: RegistroEventos,
    plan: PlanEjecucion,
    tiempo: int,
    causa: str,
) -> Evento:
    """Valida, registra y anexa atómicamente un plan como evento."""
    exigir_plan_valido(mundo, plan)
    if tiempo < mundo.tiempo_actual:
        raise TiempoRetrocede(mundo.tiempo_actual, tiempo)

    evento = crear_evento(
        registro_eventos,
        momento=tiempo,
        tipo=TipoEvento.PLAN_REGISTRADO,
        entidad_tipo="PlanEjecucion",
        entidad_id=plan.tarea_id,
        estado_antes="",
        estado_despues="",
        causa=causa,
        datos_extra=plan_a_datos_extra(plan),
    )
    registro_eventos.validar_anexo(evento)

    plan_existia = plan.tarea_id in mundo.planes
    tiempo_antes = mundo.tiempo_actual
    try:
        aplicar_evento(mundo, evento)
        mundo.tiempo_actual = tiempo
        registro_eventos.anexar(evento)
    except Exception:
        if not plan_existia and plan.tarea_id in mundo.planes:
            mundo.eliminar_plan(plan.tarea_id)
        mundo.tiempo_actual = tiempo_antes
        raise
    return evento


def liberar_plan_con_evento(
    mundo: Mundo,
    registro_eventos: RegistroEventos,
    tarea_id: str,
    tiempo: int,
    causa: str,
) -> Evento:
    """Libera y anexa atómicamente el plan de una tarea no activa."""
    if tarea_id not in mundo.planes:
        raise ErrorDominio(f"No existe un plan para la tarea {tarea_id}")
    tarea = mundo.tareas.get(tarea_id)
    if tarea is not None and tarea.estado in {
        EstadoTarea.ASIGNADA, EstadoTarea.EN_CURSO, EstadoTarea.PAUSADA,
    }:
        raise ErrorDominio(
            f"No se puede liberar el plan de la tarea activa {tarea_id}"
        )
    if tiempo < mundo.tiempo_actual:
        raise TiempoRetrocede(mundo.tiempo_actual, tiempo)

    evento = crear_evento(
        registro_eventos,
        momento=tiempo,
        tipo=TipoEvento.PLAN_LIBERADO,
        entidad_tipo="PlanEjecucion",
        entidad_id=tarea_id,
        estado_antes="",
        estado_despues="",
        causa=causa,
    )
    registro_eventos.validar_anexo(evento)

    plan_antes = mundo.planes[tarea_id]
    tiempo_antes = mundo.tiempo_actual
    try:
        aplicar_evento(mundo, evento)
        mundo.tiempo_actual = tiempo
        registro_eventos.anexar(evento)
    except Exception:
        if tarea_id not in mundo.planes:
            mundo.registrar_plan(plan_antes)
        mundo.tiempo_actual = tiempo_antes
        raise
    return evento


def asignar_plan(
    mundo: Mundo,
    registro_eventos: RegistroEventos,
    registro_reservas: RegistroReservas,
    plan: PlanEjecucion,
    tiempo: int,
    causa: str,
) -> List[Evento]:
    """Reserva los recursos y asigna la tarea de forma atómica."""
    if tiempo < mundo.tiempo_actual:
        raise TiempoRetrocede(mundo.tiempo_actual, tiempo)
    exigir_plan_valido(mundo, plan)

    mundo_antes = mundo.instantanea()
    eventos_antes = registro_eventos.instantanea()
    reservas_antes = registro_reservas.instantanea()
    eventos = []
    try:
        reservar_atomico(registro_reservas, paquete_de_reservas(plan))
        eventos.append(registrar_plan_con_evento(
            mundo, registro_eventos, plan, tiempo, causa,
        ))
        eventos.append(ejecutar_transicion(
            mundo, registro_eventos, "Tarea", plan.tarea_id,
            EstadoTarea.ASIGNADA, tiempo, causa,
        ))
        for cuidador_id in plan.cuidadores:
            eventos.append(ejecutar_transicion(
                mundo, registro_eventos, "Cuidador", cuidador_id,
                EstadoCuidador.ASIGNADO, tiempo, causa,
            ))
        if plan.vehiculo_id is not None:
            eventos.append(ejecutar_transicion(
                mundo, registro_eventos, "Vehiculo", plan.vehiculo_id,
                EstadoVehiculo.RESERVADO, tiempo, causa,
            ))
    except Exception:
        mundo.restaurar(mundo_antes)
        registro_eventos.restaurar(eventos_antes)
        registro_reservas.restaurar(reservas_antes)
        raise
    return eventos


def desasignar_plan(
    mundo: Mundo,
    registro_eventos: RegistroEventos,
    registro_reservas: RegistroReservas,
    tarea_id: str,
    tiempo: int,
    causa: str,
) -> List[Evento]:
    """Desasigna una tarea y libera su plan y recursos de forma atómica."""
    tarea = mundo.tareas.get(tarea_id)
    if tarea is None:
        raise ErrorDominio(f"La tarea {tarea_id} no existe en el mundo")
    if tarea.estado != EstadoTarea.ASIGNADA:
        raise ErrorDominio(
            f"Solo se puede desasignar una tarea ASIGNADA; "
            f"{tarea_id} está {tarea.estado.name}"
        )
    plan = mundo.planes.get(tarea_id)
    if plan is None:
        raise ErrorDominio(f"La tarea {tarea_id} no tiene un plan registrado")
    if tiempo < mundo.tiempo_actual:
        raise TiempoRetrocede(mundo.tiempo_actual, tiempo)

    mundo_antes = mundo.instantanea()
    eventos_antes = registro_eventos.instantanea()
    reservas_antes = registro_reservas.instantanea()
    eventos = []
    try:
        eventos.append(ejecutar_transicion(
            mundo, registro_eventos, "Tarea", tarea_id,
            EstadoTarea.PENDIENTE, tiempo, causa,
        ))
        for cuidador_id in plan.cuidadores:
            eventos.append(ejecutar_transicion(
                mundo, registro_eventos, "Cuidador", cuidador_id,
                EstadoCuidador.DISPONIBLE, tiempo, causa,
            ))
        if plan.vehiculo_id is not None:
            eventos.append(ejecutar_transicion(
                mundo, registro_eventos, "Vehiculo", plan.vehiculo_id,
                EstadoVehiculo.DISPONIBLE, tiempo, causa,
            ))
        liberar_reservas_tarea(registro_reservas, tarea_id)
        eventos.append(liberar_plan_con_evento(
            mundo, registro_eventos, tarea_id, tiempo, causa,
        ))
    except Exception:
        mundo.restaurar(mundo_antes)
        registro_eventos.restaurar(eventos_antes)
        registro_reservas.restaurar(reservas_antes)
        raise
    return eventos
