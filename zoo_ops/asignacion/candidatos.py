"""Generación pura y determinista de alternativas de ejecución."""

from dataclasses import dataclass
from itertools import combinations
from math import comb
from typing import Optional, Tuple

from zoo_ops.dominio.entidades import (
    Cuidador, Mundo, Tarea, nodo_de_ubicacion,
)
from zoo_ops.dominio.enums import (
    Certificacion, EstadoCuidador, EstadoEquipo, EstadoTarea,
    EstadoVehiculo, Habilidad, TipoEquipo,
)
from zoo_ops.dominio.errores import ErrorDominio, TiempoRetrocede
from zoo_ops.dominio.plan import (
    PlanEjecucion, cubre_requisitos_cuidadores, validar_plan,
)
from zoo_ops.dominio.reservas import (
    RegistroReservas, paquete_de_reservas,
)
from zoo_ops.asignacion.tiempos import (
    Estimacion, construir_plan, estimar_plan, tiempo_llegada_cuidador,
    tiempo_vehiculo_a_destino,
)


@dataclass(frozen=True)
class Candidato:
    """Un plan viable junto con su estimación temporal."""

    plan: PlanEjecucion
    estimacion: Estimacion


@dataclass(frozen=True)
class Descartado:
    """Motivo y detalle por el que no se genera una alternativa."""

    motivo: str
    detalle: Tuple[str, ...]


@dataclass(frozen=True)
class ResultadoCandidatos:
    """Candidatos válidos y motivos de descarte, en orden determinista."""

    candidatos: Tuple[Candidato, ...]
    descartados: Tuple[Descartado, ...]


def _id_activo_cuidador(mundo: Mundo) -> set[str]:
    estados_activos = {
        EstadoTarea.ASIGNADA, EstadoTarea.EN_CURSO, EstadoTarea.PAUSADA,
    }
    return {
        cuidador_id
        for tarea in mundo.tareas.values()
        if tarea.estado in estados_activos
        for cuidador_id in (
            set(tarea.cuidadores_asignados)
            | set(
                mundo.planes[tarea.id].cuidadores
                if tarea.id in mundo.planes else ()
            )
        )
    }


def _cubre_habilidad(
    cuidadores: Tuple[Cuidador, ...],
    habilidad: Habilidad,
    nivel: int,
) -> bool:
    return max(
        (cuidador.habilidades.get(habilidad, 0) for cuidador in cuidadores),
        default=0,
    ) >= nivel


def _equipo_voraz(
    elegibles: Tuple[Tuple[int, Cuidador], ...],
    cantidad: int,
    tarea: Tarea,
    certificacion_vehiculo: Optional[Certificacion],
) -> Tuple[Cuidador, ...]:
    seleccionados = []

    for requisito in tarea.habilidades_requeridas:
        if not _cubre_habilidad(
            tuple(seleccionados), requisito.habilidad, requisito.nivel_minimo,
        ):
            elegido = next(
                (
                    cuidador for _, cuidador in elegibles
                    if cuidador not in seleccionados
                    and cuidador.habilidades.get(requisito.habilidad, 0)
                    >= requisito.nivel_minimo
                ),
                None,
            )
            if elegido is None:
                return ()
            seleccionados.append(elegido)

    certificaciones = sorted(
        tarea.certificaciones_requeridas,
        key=lambda certificacion: certificacion.name,
    )
    if certificacion_vehiculo is not None:
        certificaciones.append(certificacion_vehiculo)
    for certificacion in certificaciones:
        if not any(
            certificacion in cuidador.certificaciones
            for cuidador in seleccionados
        ):
            elegido = next(
                (
                    cuidador for _, cuidador in elegibles
                    if cuidador not in seleccionados
                    and certificacion in cuidador.certificaciones
                ),
                None,
            )
            if elegido is None:
                return ()
            seleccionados.append(elegido)

    for _, cuidador in elegibles:
        if len(seleccionados) >= cantidad:
            break
        if cuidador not in seleccionados:
            seleccionados.append(cuidador)
    if len(seleccionados) != cantidad:
        return ()
    return tuple(seleccionados)


def _seleccionar_equipos(
    mundo: Mundo,
    tarea: Tarea,
) -> Tuple[Optional[Tuple[str, ...]], Optional[Descartado]]:
    seleccionados = []
    cantidades = {}
    for tipo in tarea.equipos_requeridos:
        cantidades[tipo] = cantidades.get(tipo, 0) + 1

    for tipo, cantidad in sorted(
        cantidades.items(), key=lambda item: item[0].name,
    ):
        disponibles = sorted(
            (
                equipo.id for equipo in mundo.equipos.values()
                if equipo.tipo == tipo
                and equipo.estado == EstadoEquipo.DISPONIBLE
            )
        )
        if len(disponibles) < cantidad:
            return None, Descartado(
                "sin_equipo",
                (
                    f"Se requieren {cantidad} equipos de tipo {tipo.name}; "
                    f"solo hay {len(disponibles)} disponibles",
                ),
            )
        seleccionados.extend(disponibles[:cantidad])
    return tuple(seleccionados), None


def _reservas_disponibles(
    registro_reservas: RegistroReservas,
    plan: PlanEjecucion,
) -> bool:
    return all(
        registro_reservas.verificar_disponibilidad(
            reserva.recurso_tipo,
            reserva.recurso_id,
            reserva.desde,
            reserva.hasta,
        )
        for reserva in paquete_de_reservas(plan)
    )


def _acumular_descartado(
    acumulados: dict[
        Tuple[str, Optional[str]],
        Tuple[int, list[str]],
    ],
    motivo: str,
    vehiculo_id: Optional[str],
    detalle: str,
    ocurrencias: int = 1,
) -> None:
    clave = (motivo, vehiculo_id)
    cantidad, ejemplos = acumulados.get(clave, (0, []))
    acumulados[clave] = (
        cantidad + ocurrencias,
        (ejemplos + [detalle])[:3],
    )


def _materializar_descartados(
    acumulados: dict[
        Tuple[str, Optional[str]],
        Tuple[int, list[str]],
    ],
) -> Tuple[Descartado, ...]:
    descartados = []
    for (motivo, vehiculo_id), (cantidad, ejemplos) in sorted(
        acumulados.items(),
        key=lambda item: (item[0][0], item[0][1] or ""),
    ):
        detalle = []
        if vehiculo_id is not None:
            detalle.append(f"vehículo: {vehiculo_id}")
        detalle.append(f"ocurrencias: {cantidad}")
        detalle.extend(f"ejemplo: {ejemplo}" for ejemplo in ejemplos)
        descartados.append(Descartado(motivo, tuple(detalle)))
    return tuple(descartados)


def generar_candidatos(
    mundo: Mundo,
    registro_reservas: RegistroReservas,
    tarea_id: str,
    ahora: int,
    animales_transportados: Tuple[str, ...] = (),
    permitir_vehiculos: bool = True,
    max_combinaciones: int = 2000,
) -> ResultadoCandidatos:
    """Genera planes candidatos sin modificar el mundo ni el registro."""
    if ahora < mundo.tiempo_actual:
        raise TiempoRetrocede(mundo.tiempo_actual, ahora)

    tarea = mundo.tareas.get(tarea_id)
    if tarea is None:
        raise ErrorDominio(f"La tarea {tarea_id} no existe en el mundo")
    if tarea.estado != EstadoTarea.PENDIENTE:
        raise ErrorDominio(
            f"La tarea {tarea_id} debe estar PENDIENTE; "
            f"está {tarea.estado.name}"
        )

    activos = _id_activo_cuidador(mundo)
    cuidadores_base = tuple(
        sorted(
            (
                cuidador for cuidador in mundo.cuidadores.values()
                if cuidador.estado == EstadoCuidador.DISPONIBLE
                and nodo_de_ubicacion(cuidador.ubicacion) in mundo.nodos
                and cuidador.id not in activos
            ),
            key=lambda cuidador: cuidador.id,
        )
    )
    cantidad = max(1, tarea.personas_minimas)
    descartes_acumulados = {}
    candidatos = []

    if tarea.vehiculo_requerido is not None:
        vehiculos = tuple(
            sorted(
                (
                    vehiculo
                    for vehiculo in mundo.vehiculos.values()
                    if vehiculo.tipo == tarea.vehiculo_requerido
                    and vehiculo.estado == EstadoVehiculo.DISPONIBLE
                ),
                key=lambda vehiculo: vehiculo.id,
            )
        )
        if not vehiculos:
            _acumular_descartado(
                descartes_acumulados,
                "sin_vehiculo",
                None,
                f"No hay vehículos DISPONIBLES de tipo {tarea.vehiculo_requerido.name}",
            )
            return ResultadoCandidatos(
                (),
                _materializar_descartados(descartes_acumulados),
            )
        opciones_vehiculo = vehiculos
    else:
        vehiculos_disponibles = tuple(
            sorted(
                (
                    vehiculo
                    for vehiculo in mundo.vehiculos.values()
                    if permitir_vehiculos
                    and vehiculo.estado == EstadoVehiculo.DISPONIBLE
                ),
                key=lambda vehiculo: vehiculo.id,
            )
        )
        opciones_vehiculo = (
            vehiculos_disponibles
            if animales_transportados
            else (None,) + vehiculos_disponibles
        )
        if not opciones_vehiculo:
            _acumular_descartado(
                descartes_acumulados,
                "sin_vehiculo",
                None,
                "Los animales transportados requieren un vehículo disponible",
            )
            return ResultadoCandidatos(
                (),
                _materializar_descartados(descartes_acumulados),
            )

    for vehiculo in opciones_vehiculo:
        vehiculo_id = vehiculo.id if vehiculo is not None else None
        viaje_vehiculo = (
            tiempo_vehiculo_a_destino(
                mundo, vehiculo, tarea.nodo_destino,
            )
            if vehiculo is not None
            else None
        )
        if vehiculo is not None and viaje_vehiculo is None:
            _acumular_descartado(
                descartes_acumulados,
                "sin_ruta",
                vehiculo_id,
                "No existe una ruta del vehículo hasta el destino",
            )
            continue
        if vehiculo is not None and cantidad > vehiculo.capacidad_personas:
            _acumular_descartado(
                descartes_acumulados,
                "capacidad",
                vehiculo_id,
                f"Admite {vehiculo.capacidad_personas} personas; se requieren {cantidad}",
            )
            continue

        tiempos = {}
        ubicacion_objetivo = (
            vehiculo.ubicacion if vehiculo is not None else tarea.nodo_destino
        )
        for cuidador in cuidadores_base:
            tiempo = tiempo_llegada_cuidador(
                mundo, cuidador, ubicacion_objetivo,
            )
            if tiempo is not None:
                tiempos[cuidador.id] = tiempo
        elegibles = tuple(
            sorted(
                (
                    (tiempos[cuidador.id], cuidador)
                    for cuidador in cuidadores_base
                    if cuidador.id in tiempos
                ),
                key=lambda item: (item[0], item[1].id),
            )
        )
        if len(elegibles) < cantidad:
            _acumular_descartado(
                descartes_acumulados,
                "pocos_cuidadores",
                vehiculo_id,
                f"Solo {len(elegibles)} cuidadores pueden llegar; se requieren {cantidad}",
            )
            continue

        equipos, descarte_equipo = _seleccionar_equipos(mundo, tarea)
        if descarte_equipo is not None:
            _acumular_descartado(
                descartes_acumulados,
                descarte_equipo.motivo,
                vehiculo_id,
                "; ".join(descarte_equipo.detalle),
            )
            continue

        fallo_cobertura_voraz = False
        if comb(len(elegibles), cantidad) <= max_combinaciones:
            equipos_cuidadores = (
                tuple(cuidador for _, cuidador in combinacion)
                for combinacion in combinations(elegibles, cantidad)
            )
        else:
            equipo_voraz = _equipo_voraz(
                elegibles,
                cantidad,
                tarea,
                vehiculo.certificacion_requerida if vehiculo is not None else None,
            )
            fallo_cobertura_voraz = not equipo_voraz
            equipos_cuidadores = iter((equipo_voraz,) if equipo_voraz else ())

        hubo_sin_cobertura = fallo_cobertura_voraz
        cantidad_sin_cobertura = int(fallo_cobertura_voraz)
        for equipo in equipos_cuidadores:
            ids_cuidadores = tuple(
                sorted(cuidador.id for cuidador in equipo)
            )
            errores_cobertura = cubre_requisitos_cuidadores(tarea, equipo)
            if vehiculo is not None and not any(
                vehiculo.certificacion_requerida in cuidador.certificaciones
                for cuidador in equipo
            ):
                errores_cobertura.append(
                    f"El equipo no cubre la certificación "
                    f"{vehiculo.certificacion_requerida.name} del vehículo"
                )
            if errores_cobertura:
                hubo_sin_cobertura = True
                cantidad_sin_cobertura += 1
                continue

            estimacion = estimar_plan(
                mundo,
                tarea,
                ids_cuidadores,
                vehiculo_id,
                ahora,
                tiempos_cuidadores=tiempos,
                viaje_vehiculo=viaje_vehiculo,
            )
            if estimacion is None:
                _acumular_descartado(
                    descartes_acumulados,
                    "plan_invalido",
                    vehiculo_id,
                    "No se pudo estimar una ruta para el equipo seleccionado",
                )
                continue
            plan = construir_plan(
                estimacion,
                tarea,
                ids_cuidadores,
                vehiculo_id,
                equipos or (),
                animales_transportados,
            )
            errores_plan = validar_plan(mundo, plan)
            if errores_plan:
                _acumular_descartado(
                    descartes_acumulados,
                    "plan_invalido",
                    vehiculo_id,
                    "; ".join(sorted(errores_plan)),
                )
                continue
            if not _reservas_disponibles(registro_reservas, plan):
                _acumular_descartado(
                    descartes_acumulados,
                    "reserva_ocupada",
                    vehiculo_id,
                    f"Hay reservas solapadas para el equipo {ids_cuidadores}",
                )
                continue
            candidatos.append(Candidato(plan, estimacion))

        if hubo_sin_cobertura:
            _acumular_descartado(
                descartes_acumulados,
                "sin_cobertura",
                vehiculo_id,
                f"{cantidad_sin_cobertura} combinaciones no cubren los requisitos de habilidades o certificaciones",
                cantidad_sin_cobertura,
            )

    candidatos.sort(
        key=lambda candidato: (
            candidato.estimacion.hasta,
            candidato.plan.cuidadores,
            candidato.plan.vehiculo_id or "",
        )
    )
    return ResultadoCandidatos(
        tuple(candidatos),
        _materializar_descartados(descartes_acumulados),
    )
