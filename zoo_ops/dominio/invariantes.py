"""
Verificación de invariantes del sistema zoo-ops.
Función principal verificar_invariantes(mundo, registro, registro_eventos, estado_inicial)
que retorna tupla (violaciones, no_verificadas).
"""

from dataclasses import dataclass
from collections import Counter
from typing import List, Dict, Optional, Tuple
from zoo_ops.dominio.entidades import (
    Mundo, Animal, Tarea, Recinto, EstadoAnimal, EstadoTarea,
    nodo_de_ubicacion,
)
from zoo_ops.dominio.reservas import (
    RegistroReservas, paquete_de_reservas,
)
from zoo_ops.dominio.eventos import reconstruir_estado, verificar_reconstruccion, RegistroEventos
from zoo_ops.dominio.catalogos import ESPECIES_CATALOGO
from zoo_ops.dominio.enums import EstadoCuidador, EstadoVehiculo
from zoo_ops.dominio.plan import (
    validar_capacidad_vehiculo, validar_ruta_terrestre,
    cubre_requisitos_cuidadores,
)


@dataclass(frozen=True)
class ViolacionInvariante:
    """Representa una violación de invariante encontrada."""
    invariante: str  # nombre/identificador de la invariante
    entidad_tipo: str  # tipo de entidad involucrada
    entidad_id: str  # ID de la entidad
    detalle: str  # descripción del problema


@dataclass(frozen=True)
class NoVerificada:
    """Representa una invariante no verificada (requiere contexto adicional)."""
    invariante: str  # nombre/identificador de la invariante
    motivo: str  # por qué no se verifica


# ============================================================================
# Invariante 1: Cuidador tiene habilidades/certificaciones requeridas para su tarea
# ============================================================================

def _verificar_invariante_1_habilidades_cuidador(mundo: Mundo) -> List[ViolacionInvariante]:
    """
    Invariante 1: El conjunto de cuidadores asignados cubre requisitos de tarea.
    """
    violaciones = []
    
    for tarea in mundo.tareas.values():
        if tarea.estado in {EstadoTarea.ASIGNADA, EstadoTarea.EN_CURSO, EstadoTarea.PAUSADA}:
            cuidadores = []
            for cuidador_id in tarea.cuidadores_asignados:
                cuidador = mundo.cuidadores.get(cuidador_id)
                if not cuidador:
                    violaciones.append(ViolacionInvariante(
                        invariante="INV-1-habilidades-certificaciones",
                        entidad_tipo="Tarea",
                        entidad_id=tarea.id,
                        detalle=f"Cuidador asignado {cuidador_id} no existe"
                    ))
                    continue
                cuidadores.append(cuidador)
            for error in cubre_requisitos_cuidadores(tarea, cuidadores):
                violaciones.append(ViolacionInvariante(
                    invariante="INV-1-habilidades-certificaciones",
                    entidad_tipo="Tarea",
                    entidad_id=tarea.id,
                    detalle=error,
                ))
    
    return violaciones


# ============================================================================
# Invariante 2: No hay solapamiento de reservas en el mismo recurso
# ============================================================================

def _verificar_invariante_2_solapamiento_reservas(
    mundo: Mundo, 
    registro: RegistroReservas
) -> List[ViolacionInvariante]:
    """
    Invariante 2: Ningún recurso tiene dos reservas que se solapen en el tiempo.
    """
    violaciones = []
    
    for (recurso_tipo, recurso_id), reservas in registro.reservas_por_recurso().items():
        # Verificar pares de reservas
        for i, r1 in enumerate(reservas):
            for r2 in reservas[i+1:]:
                if r1.solapa_con(r2):
                    violaciones.append(ViolacionInvariante(
                        invariante="INV-2-solapamiento-reservas",
                        entidad_tipo=recurso_tipo.name,
                        entidad_id=recurso_id,
                        detalle=(
                            f"Solapamiento: tarea {r1.tarea_id} [{r1.desde}, {r1.hasta}) "
                            f"con tarea {r2.tarea_id} [{r2.desde}, {r2.hasta})"
                        )
                    ))
    
    return violaciones


# ============================================================================
# Invariante 3: Un cuidador tiene como máximo una tarea activa
# ============================================================================

def _verificar_invariante_3_una_tarea_activa(mundo: Mundo) -> List[ViolacionInvariante]:
    """
    Invariante 3: Un cuidador tiene como máximo una tarea en estados
    asignada, en_curso o pausada.
    """
    violaciones = []
    estados_activos = {EstadoTarea.ASIGNADA, EstadoTarea.EN_CURSO, EstadoTarea.PAUSADA}
    
    tareas_por_cuidador: Dict[str, List[Tarea]] = {}
    for tarea in mundo.tareas.values():
        if tarea.estado in estados_activos:
            for cuidador_id in set(tarea.cuidadores_asignados):
                tareas_por_cuidador.setdefault(cuidador_id, []).append(tarea)
    
    for cuidador_id, tareas in tareas_por_cuidador.items():
        if len(tareas) > 1:
            violaciones.append(ViolacionInvariante(
                invariante="INV-3-una-tarea-activa",
                entidad_tipo="Cuidador",
                entidad_id=cuidador_id,
                detalle=f"Tiene {len(tareas)} tareas activas: {[t.id for t in tareas]}"
            ))
    
    return violaciones


# ============================================================================
# Invariante 4: El vehículo del plan no supera su capacidad
# ============================================================================

def _verificar_invariante_4_capacidad_vehiculo(
    mundo: Mundo,
) -> List[ViolacionInvariante]:
    """Comprueba las capacidades de personas y animales de cada plan activo."""
    violaciones = []
    estados_activos = {
        EstadoTarea.ASIGNADA, EstadoTarea.EN_CURSO, EstadoTarea.PAUSADA,
    }
    for tarea in mundo.tareas.values():
        if tarea.estado not in estados_activos:
            continue
        plan = mundo.planes.get(tarea.id)
        if plan is None or plan.vehiculo_id is None:
            continue
        vehiculo = mundo.vehiculos.get(plan.vehiculo_id)
        if vehiculo is None:
            violaciones.append(ViolacionInvariante(
                invariante="INV-4-capacidad-vehiculo",
                entidad_tipo="PlanEjecucion",
                entidad_id=tarea.id,
                detalle=f"El vehículo {plan.vehiculo_id} no existe",
            ))
            continue
        for error in validar_capacidad_vehiculo(
            vehiculo, plan.cuidadores, plan.animales_transportados,
        ):
            violaciones.append(ViolacionInvariante(
                invariante="INV-4-capacidad-vehiculo",
                entidad_tipo="PlanEjecucion",
                entidad_id=tarea.id,
                detalle=error,
            ))
    return violaciones


# ============================================================================
# Invariante 5: Las rutas terrestres utilizan aristas transitables
# ============================================================================

def _verificar_invariante_5_ruta_jeep(mundo: Mundo) -> List[ViolacionInvariante]:
    """Comprueba la ruta terrestre definida por cada plan activo."""
    violaciones = []
    estados_activos = {
        EstadoTarea.ASIGNADA, EstadoTarea.EN_CURSO, EstadoTarea.PAUSADA,
    }
    for tarea in mundo.tareas.values():
        if tarea.estado not in estados_activos:
            continue
        plan = mundo.planes.get(tarea.id)
        if plan is None or plan.vehiculo_id is None:
            continue
        vehiculo = mundo.vehiculos.get(plan.vehiculo_id)
        if vehiculo is None:
            violaciones.append(ViolacionInvariante(
                invariante="INV-5-jeep-aristas-validas",
                entidad_tipo="PlanEjecucion",
                entidad_id=tarea.id,
                detalle=f"El vehículo {plan.vehiculo_id} no existe",
            ))
            continue
        for error in validar_ruta_terrestre(
            mundo,
            tarea,
            plan,
            verificar_origen=tarea.estado == EstadoTarea.ASIGNADA,
        ):
            violaciones.append(ViolacionInvariante(
                invariante="INV-5-jeep-aristas-validas",
                entidad_tipo="PlanEjecucion",
                entidad_id=tarea.id,
                detalle=error,
            ))
    return violaciones


def _verificar_invariante_9_planes_consistentes(
    mundo: Mundo,
) -> List[ViolacionInvariante]:
    """Comprueba que todos los planes apunten a entidades existentes."""
    violaciones = []
    for plan in mundo.planes.values():
        if plan.tarea_id not in mundo.tareas:
            violaciones.append(ViolacionInvariante(
                invariante="INV-9-planes-consistentes",
                entidad_tipo="PlanEjecucion",
                entidad_id=plan.tarea_id,
                detalle=f"La tarea {plan.tarea_id} no existe",
            ))
        for cuidador_id in plan.cuidadores:
            if cuidador_id not in mundo.cuidadores:
                violaciones.append(ViolacionInvariante(
                    invariante="INV-9-planes-consistentes",
                    entidad_tipo="PlanEjecucion",
                    entidad_id=plan.tarea_id,
                    detalle=f"El cuidador {cuidador_id} no existe",
                ))
        if (
            plan.vehiculo_id is not None
            and plan.vehiculo_id not in mundo.vehiculos
        ):
            violaciones.append(ViolacionInvariante(
                invariante="INV-9-planes-consistentes",
                entidad_tipo="PlanEjecucion",
                entidad_id=plan.tarea_id,
                detalle=f"El vehículo {plan.vehiculo_id} no existe",
            ))
        for equipo_id in plan.equipos:
            if equipo_id not in mundo.equipos:
                violaciones.append(ViolacionInvariante(
                    invariante="INV-9-planes-consistentes",
                    entidad_tipo="PlanEjecucion",
                    entidad_id=plan.tarea_id,
                    detalle=f"El equipo {equipo_id} no existe",
                ))
    return violaciones


def _verificar_invariante_10_tarea_plan(
    mundo: Mundo,
) -> List[ViolacionInvariante]:
    """Comprueba que cada tarea activa tenga el plan y cuidadores asignados."""
    violaciones = []
    estados_activos = {
        EstadoTarea.ASIGNADA, EstadoTarea.EN_CURSO, EstadoTarea.PAUSADA,
    }
    for tarea in mundo.tareas.values():
        if tarea.estado not in estados_activos:
            continue
        plan = mundo.planes.get(tarea.id)
        if plan is None:
            violaciones.append(ViolacionInvariante(
                invariante="INV-10-tarea-plan",
                entidad_tipo="Tarea",
                entidad_id=tarea.id,
                detalle=f"La tarea activa {tarea.id} no tiene un plan de ejecución",
            ))
        elif tarea.cuidadores_asignados != plan.cuidadores:
            violaciones.append(ViolacionInvariante(
                invariante="INV-10-tarea-plan",
                entidad_tipo="Tarea",
                entidad_id=tarea.id,
                detalle=(
                    f"Los cuidadores asignados a la tarea {tarea.id} no "
                    "coinciden con los del plan"
                ),
            ))
    return violaciones


def _verificar_invariante_11_reservas_plan(
    mundo: Mundo,
    registro: RegistroReservas,
) -> List[ViolacionInvariante]:
    """Compara reservas de tareas activas con el paquete de cada plan."""
    violaciones = []
    estados_activos = {
        EstadoTarea.ASIGNADA, EstadoTarea.EN_CURSO, EstadoTarea.PAUSADA,
    }
    todas_las_reservas = registro.todas_las_reservas()
    for tarea in mundo.tareas.values():
        if tarea.estado not in estados_activos:
            continue
        plan = mundo.planes.get(tarea.id)
        if plan is None:
            continue
        esperadas = Counter(paquete_de_reservas(plan))
        existentes = Counter(
            reserva for reserva in todas_las_reservas
            if reserva.tarea_id == tarea.id
        )
        for reserva, cantidad in (esperadas - existentes).items():
            for _ in range(cantidad):
                violaciones.append(ViolacionInvariante(
                    invariante="INV-11-reservas-plan",
                    entidad_tipo="Reserva",
                    entidad_id=reserva.recurso_id,
                    detalle=f"Falta la reserva esperada {reserva}",
                ))
        for reserva, cantidad in (existentes - esperadas).items():
            for _ in range(cantidad):
                violaciones.append(ViolacionInvariante(
                    invariante="INV-11-reservas-plan",
                    entidad_tipo="Reserva",
                    entidad_id=reserva.recurso_id,
                    detalle=f"Sobra la reserva no prevista {reserva}",
                ))

    for reserva in todas_las_reservas:
        if reserva.tarea_id not in mundo.tareas:
            violaciones.append(ViolacionInvariante(
                invariante="INV-11-reservas-plan",
                entidad_tipo="Reserva",
                entidad_id=reserva.recurso_id,
                detalle=(
                    f"La reserva de {reserva.recurso_tipo.name}:"
                    f"{reserva.recurso_id} referencia la tarea inexistente "
                    f"{reserva.tarea_id}"
                ),
            ))
    return violaciones


def _verificar_invariante_12_estados_plan(
    mundo: Mundo,
) -> List[ViolacionInvariante]:
    """Comprueba que los estados de los recursos concuerdan con la tarea."""
    violaciones = []
    estados_activos = {
        EstadoTarea.ASIGNADA, EstadoTarea.EN_CURSO, EstadoTarea.PAUSADA,
    }
    estados_cuidador_no_validos = {
        EstadoCuidador.DISPONIBLE,
        EstadoCuidador.DESCANSANDO,
        EstadoCuidador.FUERA_DE_TURNO,
    }

    for tarea in mundo.tareas.values():
        if tarea.estado not in estados_activos:
            continue
        plan = mundo.planes.get(tarea.id)
        if plan is None:
            continue

        for cuidador_id in plan.cuidadores:
            cuidador = mundo.cuidadores.get(cuidador_id)
            if cuidador is None:
                continue
            estado_invalido = (
                cuidador.estado != EstadoCuidador.ASIGNADO
                if tarea.estado == EstadoTarea.ASIGNADA
                else cuidador.estado in estados_cuidador_no_validos
            )
            if estado_invalido:
                violaciones.append(ViolacionInvariante(
                    invariante="INV-12-estados-plan",
                    entidad_tipo="Cuidador",
                    entidad_id=cuidador_id,
                    detalle=(
                        f"El cuidador del plan de {tarea.id} está "
                        f"{cuidador.estado.name}, incompatible con "
                        f"la tarea {tarea.estado.name}"
                    ),
                ))

        if plan.vehiculo_id is None:
            continue
        vehiculo = mundo.vehiculos.get(plan.vehiculo_id)
        if vehiculo is None:
            continue
        estado_vehiculo_invalido = (
            vehiculo.estado != EstadoVehiculo.RESERVADO
            if tarea.estado == EstadoTarea.ASIGNADA
            else vehiculo.estado in {
                EstadoVehiculo.DISPONIBLE,
                EstadoVehiculo.EN_MANTENIMIENTO,
            }
        )
        if estado_vehiculo_invalido:
            violaciones.append(ViolacionInvariante(
                invariante="INV-12-estados-plan",
                entidad_tipo="Vehiculo",
                entidad_id=plan.vehiculo_id,
                detalle=(
                    f"El vehículo del plan de {tarea.id} está "
                    f"{vehiculo.estado.name}, incompatible con "
                    f"la tarea {tarea.estado.name}"
                ),
            ))
    return violaciones


def _verificar_invariante_13_ubicacion_destino(
    mundo: Mundo,
) -> List[ViolacionInvariante]:
    """Comprueba ubicaciones al ejecutar en destino según el plan."""
    violaciones = []
    estados_activos = {
        EstadoTarea.ASIGNADA, EstadoTarea.EN_CURSO, EstadoTarea.PAUSADA,
    }
    for tarea in mundo.tareas.values():
        if tarea.estado not in estados_activos:
            continue
        plan = mundo.planes.get(tarea.id)
        if plan is None:
            continue
        for cuidador_id in plan.cuidadores:
            cuidador = mundo.cuidadores.get(cuidador_id)
            if (
                cuidador is not None
                and cuidador.estado == EstadoCuidador.EJECUTANDO
                and nodo_de_ubicacion(cuidador.ubicacion) != tarea.nodo_destino
            ):
                violaciones.append(ViolacionInvariante(
                    invariante="INV-13-ubicacion-destino",
                    entidad_tipo="Cuidador",
                    entidad_id=cuidador_id,
                    detalle=(
                        f"El cuidador está en {cuidador.ubicacion}, no en "
                        f"el destino {tarea.nodo_destino} de la tarea {tarea.id}"
                    ),
                ))
        if plan.vehiculo_id is None:
            continue
        vehiculo = mundo.vehiculos.get(plan.vehiculo_id)
        if (
            vehiculo is not None
            and vehiculo.estado == EstadoVehiculo.EN_USO
            and vehiculo.ubicacion != tarea.nodo_destino
        ):
            violaciones.append(ViolacionInvariante(
                invariante="INV-13-ubicacion-destino",
                entidad_tipo="Vehiculo",
                entidad_id=plan.vehiculo_id,
                detalle=(
                    f"El vehículo está en {vehiculo.ubicacion}, no en el "
                    f"destino {tarea.nodo_destino} de la tarea {tarea.id}"
                ),
            ))
    return violaciones


# ============================================================================
# Invariante 6: Animal en recinto que admite su especie
# ============================================================================

def _verificar_invariante_6_animal_en_recinto_valido(mundo: Mundo) -> List[ViolacionInvariante]:
    """
    Invariante 6: Un animal no está en un recinto que no admite su especie.
    """
    violaciones = []
    
    # Mapa de especie -> clave del catálogo
    catalogo_especies = {v: k for k, v in ESPECIES_CATALOGO.items()}
    
    for animal in mundo.animales.values():
        if animal.estado == EstadoAnimal.EN_RECINTO:
            recinto = mundo.recintos.get(animal.ubicacion)
            if not recinto:
                violaciones.append(ViolacionInvariante(
                    invariante="INV-6-animal-recinto-valido",
                    entidad_tipo="Animal",
                    entidad_id=animal.id,
                    detalle=f"Animal en ubicación {animal.ubicacion} que no es un recinto conocido"
                ))
                continue
            
            # Verificar que el recinto admite la especie (usando clave del catálogo)
            clave_especie = catalogo_especies.get(animal.especie)
            if clave_especie is None:
                violaciones.append(ViolacionInvariante(
                    invariante="INV-6-animal-recinto-valido",
                    entidad_tipo="Animal",
                    entidad_id=animal.id,
                    detalle=f"Especie {animal.especie.nombre} no está en el catálogo de especies"
                ))
                continue
            
            if clave_especie not in recinto.especies_admitidas:
                violaciones.append(ViolacionInvariante(
                    invariante="INV-6-animal-recinto-valido",
                    entidad_tipo="Animal",
                    entidad_id=animal.id,
                    detalle=(
                        f"Animal {animal.especie.nombre} en recinto {recinto.nodo_id} "
                        f"que no admite esta especie (admite: {recinto.especies_admitidas})"
                    )
                ))
    
    return violaciones


# ============================================================================
# Invariante 7: Estado actual coincide con historial de eventos
# ============================================================================

def verificar_invariante_eventos(
    estado_inicial: Mundo,
    mundo_vivo: Mundo,
    registro_eventos: RegistroEventos,
) -> List[ViolacionInvariante]:
    """
    Verifica invariante 7 comparando el mundo vivo con el reconstruido a partir
    del estado INICIAL y de los eventos registrados.
    """
    violaciones = []
    
    mundo_reconstruido = reconstruir_estado(
        registro_eventos.obtener_todos(),
        estado_inicial
    )

    diferencias = verificar_reconstruccion(mundo_vivo, mundo_reconstruido)
    for diff in diferencias:
        violaciones.append(ViolacionInvariante(
            invariante="INV-7-eventos-coinciden",
            entidad_tipo="Mundo",
            entidad_id="global",
            detalle=diff
        ))
    
    return violaciones


# ============================================================================
# Invariante 8: Tarea no en_curso/completada con dependencias pendientes
# ============================================================================

def _verificar_invariante_8_dependencias_tarea(mundo: Mundo) -> List[ViolacionInvariante]:
    """
    Invariante 8: Ninguna tarea está en_curso o completada con dependencias pendientes.
    """
    violaciones = []
    estados_prohibidos = {EstadoTarea.EN_CURSO, EstadoTarea.COMPLETADA}
    
    for tarea in mundo.tareas.values():
        if tarea.estado in estados_prohibidos and tarea.dependencias:
            # Verificar cada dependencia
            for dep_id in tarea.dependencias:
                dep_tarea = mundo.tareas.get(dep_id)
                if not dep_tarea:
                    violaciones.append(ViolacionInvariante(
                        invariante="INV-8-dependencias-tarea",
                        entidad_tipo="Tarea",
                        entidad_id=tarea.id,
                        detalle=f"Dependencia {dep_id} no existe"
                    ))
                elif dep_tarea.estado != EstadoTarea.COMPLETADA:
                    violaciones.append(ViolacionInvariante(
                        invariante="INV-8-dependencias-tarea",
                        entidad_tipo="Tarea",
                        entidad_id=tarea.id,
                        detalle=(
                            f"Dependencia {dep_id} no completada "
                            f"(estado: {dep_tarea.estado.name})"
                        )
                    ))
    
    return violaciones


# ============================================================================
# Función principal
# ============================================================================

def verificar_invariantes(
    mundo: Mundo, 
    registro: RegistroReservas,
    registro_eventos: Optional[RegistroEventos] = None,
    estado_inicial: Optional[Mundo] = None,
) -> Tuple[List[ViolacionInvariante], List[NoVerificada]]:
    """
    Verifica todas las invariantes del sistema.
    
    Args:
        mundo: Estado actual del mundo
        registro: Registro de reservas (requerido para INV-2)
        registro_eventos: Registro de eventos opcional (para INV-7)
        estado_inicial: Estado inicial opcional; sin él INV-7 queda no verificada
    
    Returns:
        Tupla (violaciones, no_verificadas)
        - violaciones: lista de invariantes que fallan
        - no_verificadas: lista de invariantes que no se pueden verificar aún
    """
    todas_violaciones = []
    no_verificadas = []
    
    # Invariante 1: Habilidades y certificaciones
    todas_violaciones.extend(_verificar_invariante_1_habilidades_cuidador(mundo))
    
    # Invariante 2: Solapamiento reservas
    todas_violaciones.extend(_verificar_invariante_2_solapamiento_reservas(mundo, registro))
    
    # Invariante 3: Una tarea activa por cuidador
    todas_violaciones.extend(_verificar_invariante_3_una_tarea_activa(mundo))
    
    # Invariantes 4 y 5: planes de ejecución
    todas_violaciones.extend(_verificar_invariante_4_capacidad_vehiculo(mundo))
    todas_violaciones.extend(_verificar_invariante_5_ruta_jeep(mundo))
    
    # Invariante 6: Animal en recinto válido
    todas_violaciones.extend(_verificar_invariante_6_animal_en_recinto_valido(mundo))
    
    # Invariante 7: Eventos coinciden (requiere registro_eventos y estado_inicial)
    if registro_eventos is not None:
        if estado_inicial is None:
            no_verificadas.append(NoVerificada(
                invariante="INV-7-eventos-coinciden",
                motivo=(
                    "requiere el estado inicial del mundo; no puede inferirse "
                    "del estado vivo"
                ),
            ))
        else:
            todas_violaciones.extend(
                verificar_invariante_eventos(estado_inicial, mundo, registro_eventos)
            )
    
    # Invariante 8: Dependencias de tareas
    todas_violaciones.extend(_verificar_invariante_8_dependencias_tarea(mundo))

    # Invariante 9: Referencias de planes existentes
    todas_violaciones.extend(_verificar_invariante_9_planes_consistentes(mundo))

    # Invariante 10: Cada tarea activa conserva su plan y el equipo asignado.
    todas_violaciones.extend(_verificar_invariante_10_tarea_plan(mundo))

    # Invariante 11: Las reservas de cada plan activo coinciden exactamente.
    todas_violaciones.extend(
        _verificar_invariante_11_reservas_plan(mundo, registro)
    )

    # Invariante 12: Estados de cuidadores y vehículos según el plan.
    todas_violaciones.extend(_verificar_invariante_12_estados_plan(mundo))

    # Invariante 13: La ejecución activa ocurre en el nodo de destino.
    todas_violaciones.extend(
        _verificar_invariante_13_ubicacion_destino(mundo)
    )
    
    return todas_violaciones, no_verificadas


# ============================================================================
# Helpers para uso en tests
# ============================================================================

def formatear_violaciones(violaciones: List[ViolacionInvariante]) -> str:
    """Formatea lista de violaciones para mostrar."""
    if not violaciones:
        return "Sin violaciones"
    
    lineas = [f"Se encontraron {len(violaciones)} violación(es):"]
    for v in violaciones:
        lineas.append(f"  [{v.invariante}] {v.entidad_tipo}/{v.entidad_id}: {v.detalle}")
    return "\n".join(lineas)


def formatear_no_verificadas(no_verificadas: List[NoVerificada]) -> str:
    """Formatea lista de invariantes no verificadas."""
    if not no_verificadas:
        return "Todas las invariantes verificadas"
    
    lineas = [f"Invariantes no verificadas ({len(no_verificadas)}):"]
    for nv in no_verificadas:
        lineas.append(f"  [{nv.invariante}] {nv.motivo}")
    return "\n".join(lineas)


def assert_sin_violaciones(
    mundo: Mundo, 
    registro: RegistroReservas,
    registro_eventos: Optional[RegistroEventos] = None,
    estado_inicial: Optional[Mundo] = None,
) -> None:
    """Assert helper para tests: lanza AssertionError si hay violaciones."""
    violaciones, no_verificadas = verificar_invariantes(
        mundo, registro, registro_eventos, estado_inicial
    )
    if violaciones:
        raise AssertionError(formatear_violaciones(violaciones))