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
from zoo_ops.dominio.errores import ErrorDominio
from zoo_ops.dominio.plan import (
    PlanEjecucion, cubre_requisitos_cuidadores, validar_plan,
)
from zoo_ops.dominio.reservas import (
    RegistroReservas, TipoRecurso, paquete_de_reservas,
)
from zoo_ops.asignacion.tiempos import (
    Estimacion, construir_plan, estimar_plan, tiempo_llegada_cuidador,
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


def _esta_disponible_sin_mutar(
    registro_reservas: RegistroReservas,
    claves_reservadas: set[Tuple[TipoRecurso, str]],
    recurso_tipo: TipoRecurso,
    recurso_id: str,
    desde: int,
    hasta: int,
) -> bool:
    # El registro crea una lista vacía al consultar una clave inexistente.
    # Esa clave, por definición, no tiene reservas que puedan solaparse.
    if (recurso_tipo, recurso_id) not in claves_reservadas:
        return True
    return registro_reservas.verificar_disponibilidad(
        recurso_tipo, recurso_id, desde, hasta,
    )


def _reservas_disponibles(
    registro_reservas: RegistroReservas,
    plan: PlanEjecucion,
) -> bool:
    claves_reservadas = set(registro_reservas.reservas_por_recurso())
    return all(
        _esta_disponible_sin_mutar(
            registro_reservas,
            claves_reservadas,
            reserva.recurso_tipo,
            reserva.recurso_id,
            reserva.desde,
            reserva.hasta,
        )
        for reserva in paquete_de_reservas(plan)
    )


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
    descartados = []
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
            return ResultadoCandidatos(
                (),
                (Descartado(
                    "sin_vehiculo",
                    (
                        f"No hay vehículos DISPONIBLES de tipo "
                        f"{tarea.vehiculo_requerido.name}",
                    ),
                ),),
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
            descartados.append(Descartado(
                "sin_vehiculo",
                ("Los animales transportados requieren un vehículo disponible",),
            ))
            return ResultadoCandidatos((), tuple(descartados))

    for vehiculo in opciones_vehiculo:
        vehiculo_id = vehiculo.id if vehiculo is not None else None
        if vehiculo is not None and cantidad > vehiculo.capacidad_personas:
            descartados.append(Descartado(
                "capacidad",
                (
                    f"El vehículo {vehiculo.id} admite "
                    f"{vehiculo.capacidad_personas} personas; se requieren "
                    f"{cantidad}",
                ),
            ))
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
            descartados.append(Descartado(
                "pocos_cuidadores",
                (
                    f"Solo {len(elegibles)} cuidadores pueden llegar; "
                    f"se requieren {cantidad}",
                    *( (f"vehículo: {vehiculo_id}",) if vehiculo_id else () ),
                ),
            ))
            continue

        equipos, descarte_equipo = _seleccionar_equipos(mundo, tarea)
        if descarte_equipo is not None:
            descartados.append(descarte_equipo)
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
                mundo, tarea, ids_cuidadores, vehiculo_id, ahora,
            )
            if estimacion is None:
                descartados.append(Descartado(
                    "plan_invalido",
                    ("No se pudo estimar una ruta para el equipo seleccionado",),
                ))
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
                descartados.append(
                    Descartado("plan_invalido", tuple(sorted(errores_plan)))
                )
                continue
            if not _reservas_disponibles(registro_reservas, plan):
                descartados.append(Descartado(
                    "reserva_ocupada",
                    (f"Hay reservas solapadas para el equipo {ids_cuidadores}",),
                ))
                continue
            candidatos.append(Candidato(plan, estimacion))

        if hubo_sin_cobertura:
            descartados.append(Descartado(
                "sin_cobertura",
                (
                    f"{cantidad_sin_cobertura} combinaciones no cubren los "
                    "requisitos de habilidades o certificaciones",
                    *( (f"vehículo: {vehiculo_id}",) if vehiculo_id else () ),
                ),
            ))

    candidatos.sort(
        key=lambda candidato: (
            candidato.estimacion.hasta,
            candidato.plan.cuidadores,
            candidato.plan.vehiculo_id or "",
        )
    )
    return ResultadoCandidatos(
        tuple(candidatos),
        tuple(descartados),
    )
