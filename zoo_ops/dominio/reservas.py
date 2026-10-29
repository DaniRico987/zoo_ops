"""
Sistema de reservas atómicas para recursos del zoológico.
Recursos: cuidadores, vehículos, equipos.
Una reserva atómica: o se crean TODAS o no se crea ninguna.
Orden determinista para evitar deadlocks.
"""

import copy
from dataclasses import dataclass, field
from typing import Dict, List, Tuple, Optional
from enum import Enum, auto
from zoo_ops.dominio.errores import ReservaAtomicaFallida, ReservaInvalida
from zoo_ops.dominio.entidades import Mundo
from zoo_ops.dominio.plan import PlanEjecucion, exigir_plan_valido


# ============================================================================
# Tipos de recurso
# ============================================================================

class TipoRecurso(Enum):
    """Tipos de recursos reservables."""
    CUIDADOR = auto()
    VEHICULO = auto()
    EQUIPO = auto()


# ============================================================================
# Reserva
# ============================================================================

@dataclass(frozen=True)
class Reserva:
    """Reserva de un recurso para una tarea en un intervalo de tiempo."""
    recurso_tipo: TipoRecurso
    recurso_id: str
    tarea_id: str
    desde: int  # tiempo simulado inclusive
    hasta: int  # tiempo simulado exclusive
    
    def __post_init__(self):
        if self.desde >= self.hasta:
            raise ReservaInvalida(
                recurso=f"{self.recurso_tipo.name}:{self.recurso_id}",
                desde=self.desde,
                hasta=self.hasta,
                mensaje=f"desde ({self.desde}) debe ser < hasta ({self.hasta})"
            )
    
    def solapa_con(self, otra: 'Reserva') -> bool:
        """Verifica si esta reserva se solapa con otra (mismo recurso)."""
        if self.recurso_tipo != otra.recurso_tipo or self.recurso_id != otra.recurso_id:
            return False
        # Intervalos [desde, hasta) se solapan si: a.desde < b.hasta y b.desde < a.hasta
        return self.desde < otra.hasta and otra.desde < self.hasta


# ============================================================================
# Registro de reservas
# ============================================================================

@dataclass
class RegistroReservas:
    """
    Registro de reservas por recurso.
    Mantiene reservas ordenadas por tiempo para detección eficiente de solapamientos.
    """
    _reservas_por_recurso: Dict[Tuple[TipoRecurso, str], List[Reserva]] = field(default_factory=dict)

    def instantanea(self) -> Dict[Tuple[TipoRecurso, str], List[Reserva]]:
        """Devuelve una copia profunda de las reservas por recurso."""
        return copy.deepcopy(self._reservas_por_recurso)

    def todas_las_reservas(self) -> List[Reserva]:
        """Devuelve copias de todas las reservas del registro."""
        return copy.deepcopy([
            reserva
            for reservas in self._reservas_por_recurso.values()
            for reserva in reservas
        ])

    def reservas_por_recurso(
        self,
    ) -> Dict[Tuple[TipoRecurso, str], List[Reserva]]:
        """Devuelve una copia del mapa de reservas por recurso."""
        return copy.deepcopy(self._reservas_por_recurso)

    def restaurar(
        self,
        instantanea: Dict[Tuple[TipoRecurso, str], List[Reserva]],
    ) -> None:
        """Restaura las reservas sin reemplazar esta instancia."""
        if not isinstance(instantanea, dict):
            raise TypeError("instantanea debe ser un diccionario de reservas")
        self._reservas_por_recurso = copy.deepcopy(instantanea)
    
    def _clave(self, recurso_tipo: TipoRecurso, recurso_id: str) -> Tuple[TipoRecurso, str]:
        return (recurso_tipo, recurso_id)
    
    def _consultar_lista(
        self,
        recurso_tipo: TipoRecurso,
        recurso_id: str,
    ) -> List[Reserva]:
        """Consulta reservas sin crear una entrada para recursos desconocidos."""
        return self._reservas_por_recurso.get(
            self._clave(recurso_tipo, recurso_id),
            [],
        )

    def _obtener_lista(self, recurso_tipo: TipoRecurso, recurso_id: str) -> List[Reserva]:
        clave = self._clave(recurso_tipo, recurso_id)
        if clave not in self._reservas_por_recurso:
            self._reservas_por_recurso[clave] = []
        return self._reservas_por_recurso[clave]
    
    def verificar_disponibilidad(
        self, 
        recurso_tipo: TipoRecurso, 
        recurso_id: str, 
        desde: int, 
        hasta: int,
        excluir_tarea: Optional[str] = None
    ) -> bool:
        """
        Verifica si un recurso está disponible en el intervalo [desde, hasta).
        Opcionalmente excluye reservas de una tarea específica (para reprogramación).
        """
        reservas = self._consultar_lista(recurso_tipo, recurso_id)
        nueva = Reserva(recurso_tipo, recurso_id, "_temp_", desde, hasta)
        
        for reserva in reservas:
            if excluir_tarea and reserva.tarea_id == excluir_tarea:
                continue
            if nueva.solapa_con(reserva):
                return False
        return True
    
    def agregar_reserva(self, reserva: Reserva) -> None:
        """Agrega una reserva (asume que ya se verificó disponibilidad)."""
        reservas = self._obtener_lista(reserva.recurso_tipo, reserva.recurso_id)
        # Validar que no se solapa con reservas existentes
        for existente in reservas:
            if reserva.solapa_con(existente):
                raise ReservaInvalida(
                    recurso=f"{reserva.recurso_tipo.name}:{reserva.recurso_id}",
                    desde=reserva.desde,
                    hasta=reserva.hasta,
                    mensaje=f"Solapamiento con reserva existente de tarea {existente.tarea_id}"
                )
        reservas.append(reserva)
        # Mantener ordenado por 'desde' para consultas eficientes
        reservas.sort(key=lambda r: r.desde)
    
    def liberar_reservas_de_tarea(self, tarea_id: str) -> List[Reserva]:
        """Libera todas las reservas de una tarea y las retorna."""
        liberadas = []
        for clave, reservas in list(self._reservas_por_recurso.items()):
            nuevas = [r for r in reservas if r.tarea_id != tarea_id]
            liberadas.extend([r for r in reservas if r.tarea_id == tarea_id])
            if nuevas:
                self._reservas_por_recurso[clave] = nuevas
            else:
                del self._reservas_por_recurso[clave]
        return liberadas
    
    def obtener_reservas_de_tarea(self, tarea_id: str) -> List[Reserva]:
        """Obtiene todas las reservas de una tarea."""
        resultado = []
        for reservas in self._reservas_por_recurso.values():
            resultado.extend([r for r in reservas if r.tarea_id == tarea_id])
        return resultado
    
    def obtener_reservas_recurso(self, recurso_tipo: TipoRecurso, recurso_id: str) -> List[Reserva]:
        """Obtiene todas las reservas de un recurso."""
        return list(self._consultar_lista(recurso_tipo, recurso_id))
    
    def limpiar(self) -> None:
        """Limpia todas las reservas (para tests)."""
        self._reservas_por_recurso.clear()
    
    def eliminar_reserva(self, reserva: Reserva) -> bool:
        """
        Elimina una reserva específica del registro.
        
        Args:
            reserva: Reserva a eliminar
            
        Returns:
            True si se eliminó, False si no se encontró
        """
        clave = self._clave(reserva.recurso_tipo, reserva.recurso_id)
        if clave not in self._reservas_por_recurso:
            return False
        
        reservas = self._reservas_por_recurso[clave]
        for i, r in enumerate(reservas):
            if (r.tarea_id == reserva.tarea_id and 
                r.desde == reserva.desde and 
                r.hasta == reserva.hasta):
                del reservas[i]
                return True
        return False


# ============================================================================
# Funciones de reserva atómica
# ============================================================================

def _orden_determinista_recursos(reservas: List[Reserva]) -> List[Reserva]:
    """
    Ordena las reservas de forma determinista para evitar deadlocks.
    Orden: por tipo de recurso, luego por ID de recurso, luego por desde.
    """
    def clave_orden(r: Reserva) -> Tuple[int, str, int]:
        return (r.recurso_tipo.value, r.recurso_id, r.desde)
    
    return sorted(reservas, key=clave_orden)


def reservar_atomico(registro: RegistroReservas, paquete_reservas: List[Reserva]) -> List[Reserva]:
    """
    Reserva atómica: crea TODAS las reservas o NINGUNA.
    
    Args:
        registro: Registro de reservas donde operar
        paquete_reservas: Lista de reservas a crear
    
    Returns:
        Lista de reservas creadas (las mismas instancias)
    
    Raises:
        ReservaAtomicaFallida: Si alguna reserva falla (solapamiento con existentes o intra-paquete)
        ReservaInvalida: Si una reserva individual es inválida
    """
    if not paquete_reservas:
        return []
    
    # Orden determinista
    reservas_ordenadas = _orden_determinista_recursos(paquete_reservas)
    
    # (a) Detectar solapamientos intra-paquete (mismo recurso, intervalos que se cruzan)
    for i, r1 in enumerate(reservas_ordenadas):
        for r2 in reservas_ordenadas[i+1:]:
            if r1.solapa_con(r2):
                raise ReservaAtomicaFallida(
                    reservas_fallidas=[r1, r2],
                    mensaje=f"Solapamiento intra-paquete: {r1.recurso_tipo.name}:{r1.recurso_id} [{r1.desde}, {r1.hasta}) con [{r2.desde}, {r2.hasta})"
                )
    
    # (b) Comprobar disponibilidad contra el registro
    fallidas = []
    for reserva in reservas_ordenadas:
        if not registro.verificar_disponibilidad(
            reserva.recurso_tipo, 
            reserva.recurso_id, 
            reserva.desde, 
            reserva.hasta
        ):
            fallidas.append(reserva)
    
    if fallidas:
        raise ReservaAtomicaFallida(
            reservas_fallidas=fallidas,
            mensaje=f"{len(fallidas)} reserva(s) se solapan con existentes"
        )
    
    # (c) Inserción con reversión si algo falla
    insertadas = []
    try:
        for reserva in reservas_ordenadas:
            registro.agregar_reserva(reserva)
            insertadas.append(reserva)
    except Exception:
        # Rollback: eliminar todas las insertadas en esta operación
        for r in insertadas:
            registro.eliminar_reserva(r)
        raise
    
    return reservas_ordenadas


def liberar_reservas_tarea(registro: RegistroReservas, tarea_id: str) -> List[Reserva]:
    """Libera todas las reservas asociadas a una tarea."""
    return registro.liberar_reservas_de_tarea(tarea_id)


def verificar_disponibilidad_recurso(
    registro: RegistroReservas,
    recurso_tipo: TipoRecurso, 
    recurso_id: str, 
    desde: int, 
    hasta: int,
    excluir_tarea: Optional[str] = None
) -> bool:
    """Verifica disponibilidad de un recurso en un intervalo."""
    return registro.verificar_disponibilidad(recurso_tipo, recurso_id, desde, hasta, excluir_tarea)


# ============================================================================
# Reservas construidas a partir de un plan validado
# ============================================================================

def paquete_de_reservas(plan: PlanEjecucion) -> List[Reserva]:
    """Construye una reserva por cada recurso del plan y su intervalo."""
    reservas = [
        Reserva(TipoRecurso.CUIDADOR, cuidador_id, plan.tarea_id, plan.desde, plan.hasta)
        for cuidador_id in plan.cuidadores
    ]
    if plan.vehiculo_id is not None:
        reservas.append(
            Reserva(
                TipoRecurso.VEHICULO, plan.vehiculo_id, plan.tarea_id,
                plan.desde, plan.hasta,
            )
        )
    reservas.extend(
        Reserva(TipoRecurso.EQUIPO, equipo_id, plan.tarea_id, plan.desde, plan.hasta)
        for equipo_id in plan.equipos
    )
    return reservas


def reservar_plan(
    mundo: Mundo,
    registro: RegistroReservas,
    plan: PlanEjecucion,
) -> List[Reserva]:
    """Valida y reserva atómicamente todos los recursos definidos en un plan."""
    exigir_plan_valido(mundo, plan)
    return reservar_atomico(registro, paquete_de_reservas(plan))