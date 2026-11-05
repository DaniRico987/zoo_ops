"""Operaciones compuestas de asignación, desasignación y ciclo de planes."""

from dataclasses import replace
from typing import Callable, List, Tuple

from zoo_ops.dominio.entidades import (
    EfectoAnimal, Incidente, MomentoEfecto, Mundo, Tarea,
)
from zoo_ops.dominio.enums import (
    EstadoAnimal, EstadoCuidador, EstadoIncidente, EstadoTarea,
    EstadoVehiculo, TipoIncidente,
)
from zoo_ops.dominio.errores import (
    ErrorDominio, TiempoRetrocede, TransicionInvalida,
)
from zoo_ops.dominio.eventos import (
    Evento, RegistroEventos, TipoEvento, aplicar_evento, crear_evento,
    incidente_a_datos_extra, plan_a_datos_extra, tarea_a_datos_extra,
)
from zoo_ops.dominio.estados import (
    TRANSICIONES_ANIMAL, ejecutar_transicion,
    validar_transicion_animal_extra,
)
from zoo_ops.dominio.plan import PlanEjecucion, exigir_plan_valido
from zoo_ops.dominio.reservas import (
    RegistroReservas, liberar_reservas_tarea, paquete_de_reservas,
    reservar_atomico,
)


def abrir_incidente(
    mundo: Mundo,
    registro_eventos: RegistroEventos,
    incidente: Incidente,
    tareas: List[Tarea],
    tiempo: int,
    causa: str,
) -> List[Evento]:
    """Crea un incidente y sus tareas en una transacción reconstruible."""
    if tiempo < mundo.tiempo_actual:
        raise TiempoRetrocede(mundo.tiempo_actual, tiempo)
    if not isinstance(incidente, Incidente):
        raise ErrorDominio("incidente debe ser una instancia de Incidente")
    if not isinstance(incidente.id, str):
        raise ErrorDominio("El id del incidente debe ser texto")
    if incidente.id in mundo.incidentes:
        raise ErrorDominio(f"El incidente {incidente.id} ya existe en el mundo")
    if incidente.estado != EstadoIncidente.ABIERTO:
        raise ErrorDominio("Un incidente nuevo debe estar ABIERTO")
    if not isinstance(tareas, (list, tuple)):
        raise ErrorDominio("tareas debe ser una lista o tupla de Tarea")
    if any(not isinstance(tarea, Tarea) for tarea in tareas):
        raise ErrorDominio("Cada elemento de tareas debe ser una instancia de Tarea")

    if any(not isinstance(tarea.id, str) for tarea in tareas):
        raise ErrorDominio("El id de cada tarea debe ser texto")
    if any(
        any(not isinstance(dependencia, str) for dependencia in tarea.dependencias)
        for tarea in tareas
    ):
        raise ErrorDominio("Cada id de dependencia debe ser texto")
    ids_tareas = [tarea.id for tarea in tareas]
    ids_nuevos = set(ids_tareas)
    if len(ids_nuevos) != len(ids_tareas):
        raise ErrorDominio("No se permiten ids de tarea duplicados")
    if ids_nuevos.intersection(mundo.tareas):
        duplicados = sorted(ids_nuevos.intersection(mundo.tareas))
        raise ErrorDominio(f"Ya existen tareas en el mundo: {duplicados}")
    if any(tarea.estado != EstadoTarea.PENDIENTE for tarea in tareas):
        raise ErrorDominio("Toda tarea nueva debe estar PENDIENTE")
    if any(tarea.cuidadores_asignados for tarea in tareas):
        raise ErrorDominio("Una tarea nueva no puede tener cuidadores asignados")
    if any(
        tarea.incidente_origen not in (None, incidente.id)
        for tarea in tareas
    ):
        raise ErrorDominio(
            "El incidente_origen de cada tarea nueva debe ser el incidente creado"
        )
    if incidente.tipo in {
        TipoIncidente.ESCAPE_TERRESTRE, TipoIncidente.ESCAPE_AEREO,
    } and incidente.animal_relacionado not in mundo.animales:
        raise ErrorDominio(
            "Un incidente de escape requiere un animal_relacionado existente"
        )

    for tarea in tareas:
        dependencias_ausentes = set(tarea.dependencias) - set(mundo.tareas) - ids_nuevos
        if dependencias_ausentes:
            raise ErrorDominio(
                f"La tarea {tarea.id} tiene dependencias inexistentes: "
                f"{sorted(dependencias_ausentes)}"
            )

    tareas_nuevas = {tarea.id: tarea for tarea in tareas}
    tareas_por_id = {**mundo.tareas, **tareas_nuevas}
    visitadas = set()
    en_visita = set()

    def visitar(tarea_id: str) -> None:
        if tarea_id in en_visita:
            raise ErrorDominio("Las dependencias de las tareas nuevas forman un ciclo")
        if tarea_id in visitadas:
            return
        en_visita.add(tarea_id)
        for dependencia_id in tareas_por_id[tarea_id].dependencias:
            if dependencia_id in tareas_por_id:
                visitar(dependencia_id)
        en_visita.remove(tarea_id)
        visitadas.add(tarea_id)

    for tarea_id in sorted(tareas_nuevas):
        visitar(tarea_id)

    incidente_nuevo = replace(
        incidente, tareas_generadas=frozenset(ids_tareas),
    )
    tareas_nuevas_ajustadas = tuple(
        replace(tarea, incidente_origen=incidente.id)
        for tarea in tareas
    )
    mundo_antes = mundo.instantanea()
    eventos_antes = registro_eventos.instantanea()
    eventos = []
    try:
        entidades = [
            ("Incidente", incidente_nuevo.id, "ABIERTO",
             incidente_a_datos_extra(incidente_nuevo)),
        ]
        entidades.extend(
            ("Tarea", tarea.id, "PENDIENTE", tarea_a_datos_extra(tarea))
            for tarea in sorted(tareas_nuevas_ajustadas, key=lambda item: item.id)
        )
        for entidad_tipo, entidad_id, estado, datos_extra in entidades:
            evento = crear_evento(
                registro_eventos,
                momento=tiempo,
                tipo=TipoEvento.CREACION_ENTIDAD,
                entidad_tipo=entidad_tipo,
                entidad_id=entidad_id,
                estado_antes="",
                estado_despues=estado,
                causa=causa,
                datos_extra=datos_extra,
            )
            registro_eventos.validar_anexo(evento)
            aplicar_evento(mundo, evento)
            mundo.tiempo_actual = tiempo
            registro_eventos.anexar(evento)
            eventos.append(evento)
    except Exception:
        mundo.restaurar(mundo_antes)
        registro_eventos.restaurar(eventos_antes)
        raise
    return eventos


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


def _exigir_tarea_y_plan(
    mundo: Mundo,
    tarea_id: str,
    estado_requerido: EstadoTarea,
) -> Tuple[Tarea, PlanEjecucion]:
    tarea = mundo.tareas.get(tarea_id)
    if tarea is None:
        raise ErrorDominio(f"La tarea {tarea_id} no existe en el mundo")
    if tarea.estado != estado_requerido:
        raise ErrorDominio(
            f"La tarea {tarea_id} debe estar {estado_requerido.name}; "
            f"está {tarea.estado.name}"
        )
    plan = mundo.planes.get(tarea_id)
    if plan is None:
        raise ErrorDominio(f"La tarea {tarea_id} no tiene un plan registrado")
    return tarea, plan


def _exigir_estado_recursos(
    mundo: Mundo,
    plan: PlanEjecucion,
    estado_cuidador: EstadoCuidador,
    estado_vehiculo: EstadoVehiculo,
) -> None:
    for cuidador_id in plan.cuidadores:
        cuidador = mundo.cuidadores.get(cuidador_id)
        if cuidador is None:
            raise ErrorDominio(f"El cuidador {cuidador_id} no existe en el mundo")
        if cuidador.estado != estado_cuidador:
            raise ErrorDominio(
                f"El cuidador {cuidador_id} debe estar {estado_cuidador.name}; "
                f"está {cuidador.estado.name}"
            )
    if plan.vehiculo_id is not None:
        vehiculo = mundo.vehiculos.get(plan.vehiculo_id)
        if vehiculo is None:
            raise ErrorDominio(
                f"El vehículo {plan.vehiculo_id} no existe en el mundo"
            )
        if vehiculo.estado != estado_vehiculo:
            raise ErrorDominio(
                f"El vehículo {plan.vehiculo_id} debe estar "
                f"{estado_vehiculo.name}; está {vehiculo.estado.name}"
            )


def _efectos_en_momento(
    tarea: Tarea,
    momento: MomentoEfecto,
) -> Tuple[EfectoAnimal, ...]:
    """Obtiene los efectos del momento conservando su orden declarado."""
    return tuple(
        efecto for efecto in tarea.efectos
        if efecto.momento == momento
    )


def _validar_efectos_animales(
    mundo: Mundo,
    tarea: Tarea,
    momento: MomentoEfecto,
) -> Tuple[EfectoAnimal, ...]:
    """Valida de antemano una secuencia de efectos sin mutar ni consumir IDs."""
    efectos = _efectos_en_momento(tarea, momento)
    estados_simulados: dict[str, EstadoAnimal] = {}
    for efecto in efectos:
        animal = mundo.animales.get(efecto.animal_id)
        if animal is None:
            raise ErrorDominio(
                f"El animal {efecto.animal_id} del efecto de la tarea "
                f"{tarea.id} no existe en el mundo"
            )
        if not isinstance(efecto.estado, EstadoAnimal):
            raise ErrorDominio(
                f"El efecto de la tarea {tarea.id} tiene un estado animal inválido"
            )

        estado_actual = estados_simulados.get(efecto.animal_id, animal.estado)
        permitidos = TRANSICIONES_ANIMAL.get(estado_actual, frozenset())
        if efecto.estado not in permitidos:
            raise TransicionInvalida(
                entidad=f"Animal:{efecto.animal_id}",
                estado_actual=estado_actual.name,
                estado_intentado=efecto.estado.name,
                mensaje="transición del efecto no permitida",
            )

        error_extra = validar_transicion_animal_extra(
            animal,
            estado_actual,
            efecto.estado,
            mundo,
            efecto.recinto_destino,
        )
        if error_extra:
            raise TransicionInvalida(
                entidad=f"Animal:{efecto.animal_id}",
                estado_actual=estado_actual.name,
                estado_intentado=efecto.estado.name,
                mensaje=error_extra,
            )
        estados_simulados[efecto.animal_id] = efecto.estado
    return efectos


def _aplicar_efectos_animales(
    mundo: Mundo,
    registro_eventos: RegistroEventos,
    efectos: Tuple[EfectoAnimal, ...],
    tiempo: int,
    causa: str,
) -> List[Evento]:
    """Aplica secuencialmente efectos ya validados mediante eventos de dominio."""
    eventos = []
    for efecto in efectos:
        parametros = {}
        if efecto.recinto_destino is not None:
            parametros["recinto_destino"] = efecto.recinto_destino
        eventos.append(ejecutar_transicion(
            mundo,
            registro_eventos,
            "Animal",
            efecto.animal_id,
            efecto.estado,
            tiempo,
            causa,
            **parametros,
        ))
    return eventos


def _exigir_reloj_monotono(mundo: Mundo, tiempo: int) -> None:
    if tiempo < mundo.tiempo_actual:
        raise TiempoRetrocede(mundo.tiempo_actual, tiempo)


def _ejecutar_con_reversion(
    mundo: Mundo,
    registro_eventos: RegistroEventos,
    registro_reservas: RegistroReservas,
    accion: Callable[[], List[Evento]],
) -> List[Evento]:
    mundo_antes = mundo.instantanea()
    eventos_antes = registro_eventos.instantanea()
    reservas_antes = registro_reservas.instantanea()
    try:
        return accion()
    except Exception:
        mundo.restaurar(mundo_antes)
        registro_eventos.restaurar(eventos_antes)
        registro_reservas.restaurar(reservas_antes)
        raise


def iniciar_ejecucion(
    mundo: Mundo,
    registro_eventos: RegistroEventos,
    registro_reservas: RegistroReservas,
    tarea_id: str,
    tiempo: int,
    causa: str,
) -> List[Evento]:
    """Inicia el desplazamiento de los recursos asignados a una tarea."""
    tarea, plan = _exigir_tarea_y_plan(
        mundo, tarea_id, EstadoTarea.ASIGNADA,
    )
    _exigir_reloj_monotono(mundo, tiempo)
    if not plan.desde <= tiempo < plan.hasta:
        raise ErrorDominio(
            f"El inicio debe ocurrir en la ventana [{plan.desde}, {plan.hasta})"
        )
    _exigir_estado_recursos(
        mundo, plan, EstadoCuidador.ASIGNADO, EstadoVehiculo.RESERVADO,
    )
    efectos_animales = _validar_efectos_animales(
        mundo, tarea, MomentoEfecto.AL_INICIAR,
    )

    def iniciar() -> List[Evento]:
        eventos = [ejecutar_transicion(
            mundo, registro_eventos, "Tarea", tarea.id,
            EstadoTarea.EN_CURSO, tiempo, causa,
        )]
        for cuidador_id in plan.cuidadores:
            eventos.append(ejecutar_transicion(
                mundo, registro_eventos, "Cuidador", cuidador_id,
                EstadoCuidador.EN_CAMINO, tiempo, causa,
            ))
        if plan.vehiculo_id is not None:
            eventos.append(ejecutar_transicion(
                mundo, registro_eventos, "Vehiculo", plan.vehiculo_id,
                EstadoVehiculo.EN_RUTA, tiempo, causa,
            ))
        eventos.extend(_aplicar_efectos_animales(
            mundo, registro_eventos, efectos_animales, tiempo, causa,
        ))
        return eventos

    return _ejecutar_con_reversion(
        mundo, registro_eventos, registro_reservas, iniciar,
    )


def llegar_a_destino(
    mundo: Mundo,
    registro_eventos: RegistroEventos,
    registro_reservas: RegistroReservas,
    tarea_id: str,
    tiempo: int,
    causa: str,
) -> List[Evento]:
    """Registra la llegada y sitúa los recursos en el destino de la tarea."""
    tarea, plan = _exigir_tarea_y_plan(
        mundo, tarea_id, EstadoTarea.EN_CURSO,
    )
    _exigir_reloj_monotono(mundo, tiempo)
    _exigir_estado_recursos(
        mundo, plan, EstadoCuidador.EN_CAMINO, EstadoVehiculo.EN_RUTA,
    )

    def llegar() -> List[Evento]:
        eventos = []
        for cuidador_id in plan.cuidadores:
            eventos.append(ejecutar_transicion(
                mundo, registro_eventos, "Cuidador", cuidador_id,
                EstadoCuidador.EJECUTANDO, tiempo, causa,
                ubicacion=tarea.nodo_destino,
            ))
        if plan.vehiculo_id is not None:
            eventos.append(ejecutar_transicion(
                mundo, registro_eventos, "Vehiculo", plan.vehiculo_id,
                EstadoVehiculo.EN_USO, tiempo, causa,
                ubicacion=tarea.nodo_destino,
            ))
        return eventos

    return _ejecutar_con_reversion(
        mundo, registro_eventos, registro_reservas, llegar,
    )


def _finalizar_ejecucion(
    mundo: Mundo,
    registro_eventos: RegistroEventos,
    registro_reservas: RegistroReservas,
    tarea_id: str,
    tiempo: int,
    causa: str,
    estado_final: EstadoTarea,
) -> List[Evento]:
    tarea, plan = _exigir_tarea_y_plan(
        mundo, tarea_id, EstadoTarea.EN_CURSO,
    )
    _exigir_reloj_monotono(mundo, tiempo)
    _exigir_estado_recursos(
        mundo, plan, EstadoCuidador.EJECUTANDO, EstadoVehiculo.EN_USO,
    )
    efectos_animales = (
        _validar_efectos_animales(mundo, tarea, MomentoEfecto.AL_COMPLETAR)
        if estado_final == EstadoTarea.COMPLETADA
        else ()
    )

    def finalizar() -> List[Evento]:
        eventos = [ejecutar_transicion(
            mundo, registro_eventos, "Tarea", tarea_id,
            estado_final, tiempo, causa,
        )]
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
        eventos.extend(_aplicar_efectos_animales(
            mundo, registro_eventos, efectos_animales, tiempo, causa,
        ))
        return eventos

    return _ejecutar_con_reversion(
        mundo, registro_eventos, registro_reservas, finalizar,
    )


def completar_plan(
    mundo: Mundo,
    registro_eventos: RegistroEventos,
    registro_reservas: RegistroReservas,
    tarea_id: str,
    tiempo: int,
    causa: str,
) -> List[Evento]:
    """Completa una tarea llegada a destino y libera sus recursos."""
    return _finalizar_ejecucion(
        mundo, registro_eventos, registro_reservas, tarea_id, tiempo, causa,
        EstadoTarea.COMPLETADA,
    )


def fallar_plan(
    mundo: Mundo,
    registro_eventos: RegistroEventos,
    registro_reservas: RegistroReservas,
    tarea_id: str,
    tiempo: int,
    causa: str,
) -> List[Evento]:
    """Marca como fallida una tarea llegada a destino y libera sus recursos."""
    return _finalizar_ejecucion(
        mundo, registro_eventos, registro_reservas, tarea_id, tiempo, causa,
        EstadoTarea.FALLIDA,
    )
