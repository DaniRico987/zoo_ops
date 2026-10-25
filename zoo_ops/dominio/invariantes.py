"""
Verificación de invariantes del sistema zoo-ops.
Función principal verificar_invariantes(mundo, registro, registro_eventos, estado_inicial)
que retorna tupla (violaciones, no_verificadas).
"""

from dataclasses import dataclass
from typing import List, Dict, Set, Optional, Tuple
from zoo_ops.dominio.entidades import (
    Mundo, Cuidador, Animal, Vehiculo, Tarea, Recinto, Arista,
    EstadoCuidador, EstadoAnimal, EstadoVehiculo, EstadoTarea, EstadoIncidente,
    HabilidadRequerida
)
from zoo_ops.dominio.enums import (
    Habilidad, Certificacion, TipoVehiculo, Medio, MedioPermitido
)
from zoo_ops.dominio.reservas import RegistroReservas, Reserva, TipoRecurso
from zoo_ops.dominio.eventos import reconstruir_estado, verificar_reconstruccion, RegistroEventos
from zoo_ops.dominio.catalogos import Especie, ESPECIES_CATALOGO


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
    Invariante 1: Ningún cuidador está asignado a una tarea para la que le falte
    una certificación o nivel de habilidad requerido.
    """
    violaciones = []
    
    for tarea in mundo.tareas.values():
        if tarea.estado in {EstadoTarea.ASIGNADA, EstadoTarea.EN_CURSO, EstadoTarea.PAUSADA}:
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

                # Verificar habilidades
                for hab_req in tarea.habilidades_requeridas:
                    nivel = cuidador.habilidades.get(hab_req.habilidad, 0)
                    if nivel < hab_req.nivel_minimo:
                        violaciones.append(ViolacionInvariante(
                            invariante="INV-1-habilidades-certificaciones",
                            entidad_tipo="Cuidador",
                            entidad_id=cuidador.id,
                            detalle=(
                                f"Falta habilidad {hab_req.habilidad.name}: "
                                f"nivel {nivel} < {hab_req.nivel_minimo} "
                                f"para tarea {tarea.id}"
                            )
                        ))

                # Verificar certificaciones
                for cert in tarea.certificaciones_requeridas:
                    if cert not in cuidador.certificaciones:
                        violaciones.append(ViolacionInvariante(
                            invariante="INV-1-habilidades-certificaciones",
                            entidad_tipo="Cuidador",
                            entidad_id=cuidador.id,
                            detalle=f"Falta certificación {cert.name} para tarea {tarea.id}"
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
    
    for (recurso_tipo, recurso_id), reservas in registro._reservas_por_recurso.items():
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
# Invariante 4: Vehículo no supera capacidad (NO VERIFICADA)
# ============================================================================

def _no_verificada_invariante_4() -> NoVerificada:
    """
    INV-4 no verificada: requiere plan de ejecución (cuidadores, vehículo y ruta),
    que se definirá junto con el motor de asignación.
    """
    return NoVerificada(
        invariante="INV-4-capacidad-vehiculo",
        motivo="requiere plan de ejecución (cuidadores, vehículo y ruta), que se definirá junto con el motor de asignación"
    )


# ============================================================================
# Invariante 5: Jeep solo por aristas que permitan jeep (NO VERIFICADA)
# ============================================================================

def _no_verificada_invariante_5() -> NoVerificada:
    """
    INV-5 no verificada: requiere plan de ejecución (cuidadores, vehículo y ruta),
    que se definirá junto con el motor de asignación.
    """
    return NoVerificada(
        invariante="INV-5-jeep-aristas-validas",
        motivo="requiere plan de ejecución (cuidadores, vehículo y ruta), que se definirá junto con el motor de asignación"
    )


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
    
    # Invariante 4: NO VERIFICADA
    no_verificadas.append(_no_verificada_invariante_4())
    
    # Invariante 5: NO VERIFICADA
    no_verificadas.append(_no_verificada_invariante_5())
    
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