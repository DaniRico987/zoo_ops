"""
Sistema de reservas atómicas para recursos del zoológico.
Recursos: cuidadores, vehículos, equipos.
Una reserva atómica: o se crean TODAS o no se crea ninguna.
Orden determinista para evitar deadlocks.
"""

from dataclasses import dataclass, field
from typing import Dict, List, Set, Tuple, Optional, FrozenSet
from enum import Enum, auto
from zoo_ops.dominio.errores import (
    RecursosInvalidos, ReservaAtomicaFallida, ReservaInvalida,
)
from zoo_ops.dominio.entidades import Cuidador, Vehiculo, Equipo, Tarea, Mundo
from zoo_ops.dominio.enums import EstadoCuidador, EstadoEquipo, EstadoVehiculo


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
    
    def _clave(self, recurso_tipo: TipoRecurso, recurso_id: str) -> Tuple[TipoRecurso, str]:
        return (recurso_tipo, recurso_id)
    
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
        reservas = self._obtener_lista(recurso_tipo, recurso_id)
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
        for clave, reservas in self._reservas_por_recurso.items():
            nuevas = [r for r in reservas if r.tarea_id != tarea_id]
            liberadas.extend([r for r in reservas if r.tarea_id == tarea_id])
            self._reservas_por_recurso[clave] = nuevas
        return liberadas
    
    def obtener_reservas_de_tarea(self, tarea_id: str) -> List[Reserva]:
        """Obtiene todas las reservas de una tarea."""
        resultado = []
        for reservas in self._reservas_por_recurso.values():
            resultado.extend([r for r in reservas if r.tarea_id == tarea_id])
        return resultado
    
    def obtener_reservas_recurso(self, recurso_tipo: TipoRecurso, recurso_id: str) -> List[Reserva]:
        """Obtiene todas las reservas de un recurso."""
        return list(self._obtener_lista(recurso_tipo, recurso_id))
    
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
# Helpers para crear reservas desde tareas
# ============================================================================

def crear_reservas_para_tarea(
    tarea: Tarea,
    desde: int,
    hasta: int,
    cuidador_id: Optional[str] = None,
    vehiculo_id: Optional[str] = None,
    equipo_ids: Optional[List[str]] = None
) -> List[Reserva]:
    """
    Crea las reservas necesarias para una tarea.
    
    Args:
        tarea: Tarea para la que crear reservas
        desde: Inicio de la reserva (obligatorio)
        hasta: Fin de la reserva (exclusive) (obligatorio)
        cuidador_id: ID del cuidador asignado (opcional)
        vehiculo_id: ID del vehículo asignado (opcional)
        equipo_ids: Lista de IDs de equipos necesarios (opcional)
    
    Returns:
        Lista de reservas (no las crea en el registro, solo las construye)
    """
    if desde >= hasta:
        raise ReservaInvalida(
            recurso="intervalo",
            desde=desde,
            hasta=hasta,
            mensaje="desde debe ser < hasta"
        )
    
    reservas = []
    
    if cuidador_id:
        reservas.append(Reserva(
            recurso_tipo=TipoRecurso.CUIDADOR,
            recurso_id=cuidador_id,
            tarea_id=tarea.id,
            desde=desde,
            hasta=hasta
        ))
    
    if vehiculo_id:
        reservas.append(Reserva(
            recurso_tipo=TipoRecurso.VEHICULO,
            recurso_id=vehiculo_id,
            tarea_id=tarea.id,
            desde=desde,
            hasta=hasta
        ))
    
    if equipo_ids:
        for equipo_id in equipo_ids:
            reservas.append(Reserva(
                recurso_tipo=TipoRecurso.EQUIPO,
                recurso_id=equipo_id,
                tarea_id=tarea.id,
                desde=desde,
                hasta=hasta
            ))
    
    return reservas


def reservar_para_tarea(
    mundo,  # Mundo con acceso de solo lectura a entidades
    registro: RegistroReservas,
    tarea: Tarea,
    paquete: List[Reserva],
) -> List[Reserva]:
    """
    Reserva un paquete de recursos para una tarea: valida los recursos implicados
    y reserva el paquete de forma atómica.

    Es la única vía pública para reservar en nombre de una tarea. El paquete se
    construye con `crear_reservas_para_tarea` (o a mano), y esta función extrae de
    él los IDs por `TipoRecurso` para validarlos contra la tarea y el mundo.

    Args:
        mundo: Estado del mundo (para validar recursos)
        registro: Registro de reservas
        tarea: Tarea para la que reservar
        paquete: Reservas a crear (todas deben pertenecer a `tarea.id`)

    Returns:
        Lista de reservas creadas (en orden determinista)

    Raises:
        RecursosInvalidos: Si el paquete no es coherente, está vacío teniendo la
            tarea requisitos, o los recursos no cumplen los requisitos
        ReservaAtomicaFallida: Si no se pueden reservar todos los recursos
    """
    if not paquete:
        if tarea.recursos_requeridos or tarea.certificaciones_requeridas:
            raise RecursosInvalidos([
                f"Paquete vacío para la tarea {tarea.id}, que declara recursos "
                "o certificaciones requeridas"
            ])
        return []

    ajenas = [r for r in paquete if r.tarea_id != tarea.id]
    if ajenas:
        raise RecursosInvalidos([
            f"Reserva de la tarea {r.tarea_id} no pertenece a la tarea {tarea.id}"
            for r in ajenas
        ])

    ids_cuidador = [
        r.recurso_id for r in paquete if r.recurso_tipo == TipoRecurso.CUIDADOR
    ]
    ids_vehiculo = [
        r.recurso_id for r in paquete if r.recurso_tipo == TipoRecurso.VEHICULO
    ]
    ids_equipo = [
        r.recurso_id for r in paquete if r.recurso_tipo == TipoRecurso.EQUIPO
    ]

    errores = []
    if len(ids_cuidador) > 1:
        errores.append(
            f"Una tarea admite un solo cuidador; se recibieron {sorted(ids_cuidador)}"
        )
    if len(ids_vehiculo) > 1:
        errores.append(
            f"Una tarea admite un solo vehículo; se recibieron {sorted(ids_vehiculo)}"
        )
    if errores:
        raise RecursosInvalidos(errores)

    errores = validar_recursos_para_tarea(
        tarea,
        mundo,
        cuidador_id=ids_cuidador[0] if ids_cuidador else None,
        vehiculo_id=ids_vehiculo[0] if ids_vehiculo else None,
        equipo_ids=ids_equipo or None,
    )
    if errores:
        raise RecursosInvalidos(errores)

    return reservar_atomico(registro, paquete)


def validar_recursos_para_tarea(
    tarea: Tarea,
    mundo: Mundo,
    cuidador_id: Optional[str] = None,
    vehiculo_id: Optional[str] = None,
    equipo_ids: Optional[List[str]] = None
) -> List[str]:
    """
    Valida que los recursos propuestos cumplen requisitos de la tarea.
    Retorna lista de errores (vacía si todo OK).
    """
    if not isinstance(mundo, Mundo):
        raise TypeError("mundo debe ser una instancia de Mundo")

    errores = []
    
    # Validar cuidador
    if cuidador_id:
        cuidador = mundo.cuidadores.get(cuidador_id)
        if not cuidador:
            errores.append(f"Cuidador {cuidador_id} no existe")
        else:
            # Verificar habilidades
            for hab_req in tarea.habilidades_requeridas:
                nivel = cuidador.habilidades.get(hab_req.habilidad, 0)
                if nivel < hab_req.nivel_minimo:
                    errores.append(
                        f"Cuidador {cuidador_id}: {hab_req.habilidad.name} nivel {nivel} < {hab_req.nivel_minimo}"
                    )
            # Verificar certificaciones
            for cert in tarea.certificaciones_requeridas:
                if cert not in cuidador.certificaciones:
                    errores.append(f"Cuidador {cuidador_id} falta certificación {cert.name}")
            # Verificar estado
            if cuidador.estado != EstadoCuidador.DISPONIBLE:
                errores.append(f"Cuidador {cuidador_id} no está disponible (estado: {cuidador.estado.name})")
    
    # Validar vehículo
    if vehiculo_id:
        vehiculo = mundo.vehiculos.get(vehiculo_id)
        if not vehiculo:
            errores.append(f"Vehículo {vehiculo_id} no existe")
        else:
            # Verificar certificación del cuidador para este vehículo
            if cuidador_id:
                cuidador = mundo.cuidadores.get(cuidador_id)
                if cuidador and vehiculo.certificacion_requerida not in cuidador.certificaciones:
                    errores.append(
                        f"Cuidador {cuidador_id} no tiene certificación {vehiculo.certificacion_requerida.name} "
                        f"para vehículo {vehiculo_id}"
                    )
            # Verificar estado
            if vehiculo.estado != EstadoVehiculo.DISPONIBLE:
                errores.append(f"Vehículo {vehiculo_id} no está disponible (estado: {vehiculo.estado.name})")
    
    # Validar equipos
    if equipo_ids:
        for equipo_id in equipo_ids:
            equipo = mundo.equipos.get(equipo_id)
            if not equipo:
                errores.append(f"Equipo {equipo_id} no existe")
            elif equipo.estado != EstadoEquipo.DISPONIBLE:
                errores.append(
                    f"Equipo {equipo_id} no está disponible "
                    f"(estado: {equipo.estado.name})"
                )
    
    return errores