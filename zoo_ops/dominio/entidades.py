"""
Entidades del dominio de zoo-ops.
Dataclasses inmutables (frozen) para las entidades principales.
Mundo es un agregado mutable que centraliza las mutaciones de sus colecciones.
"""
import copy
from dataclasses import dataclass, field
from typing import Dict, List, Optional, Set, Tuple, Union, TYPE_CHECKING
from zoo_ops.dominio.enums import (
    TipoNodo, TipoRecinto, Medio, Peligrosidad, TipoVehiculo, TipoEquipo,
    Habilidad, Certificacion, EstadoCuidador, EstadoAnimal, EstadoVehiculo,
    EstadoEquipo,
    EstadoTarea, EstadoIncidente, TipoIncidente, TipoSensor, MedioPermitido,
    PrioridadTarea
)
from zoo_ops.dominio.catalogos import Especie
from zoo_ops.dominio.errores import ErrorDominio

if TYPE_CHECKING:
    from zoo_ops.dominio.plan import PlanEjecucion


# ============================================================================
# Estructuras básicas del grafo
# ============================================================================

@dataclass(frozen=True)
class Nodo:
    """Nodo en el grafo del zoológico."""
    id: str
    tipo: TipoNodo
    x: float
    y: float
    z: float = 0.0


@dataclass(frozen=True)
class Arista:
    """Arista dirigida entre dos nodos."""
    origen: str  # id del nodo origen
    destino: str  # id del nodo destino
    distancia: float  # en metros
    medios_permitidos: frozenset[MedioPermitido] = field(default_factory=frozenset)
    bloqueada: bool = False


# ============================================================================
# Recintos y especies
# ============================================================================

@dataclass(frozen=True)
class Recinto:
    """Recinto del zoológico asociado a un nodo."""
    nodo_id: str
    tipo: TipoRecinto
    especies_admitidas: frozenset[str] = field(default_factory=frozenset)  # claves de especie
    capacidad: int = 0
    estado: str = "operativo"  # operativo, mantenimiento, cerrado


# ============================================================================
# Cuidadores
# ============================================================================

@dataclass(frozen=True)
class Cuidador:
    """Cuidador del zoológico."""
    id: str
    nombre: str
    # Habilidad -> nivel (1-5), fijas al crear
    habilidades: Dict[Habilidad, int] = field(default_factory=dict)
    certificaciones: frozenset[Certificacion] = field(default_factory=frozenset)
    velocidad_base: float = 1.0  # m/s caminando
    # Ubicación: (nodo_id,) o (arista_origen, arista_destino, progreso_0_a_1)
    ubicacion: Tuple = field(default_factory=tuple)
    estado: EstadoCuidador = EstadoCuidador.FUERA_DE_TURNO
    fatiga: int = 0  # 0-100
    turno: Optional[Tuple[int, int]] = None  # (inicio, fin) en segundos simulados


# ============================================================================
# Vehículos
# ============================================================================

@dataclass(frozen=True)
class Vehiculo:
    """Vehículo del zoológico."""
    id: str
    tipo: TipoVehiculo
    velocidad: float  # m/s
    capacidad_personas: int
    capacidad_animales: int  # en "unidades de animal" según tamaño
    certificacion_requerida: Certificacion
    ubicacion: str  # nodo_id donde está estacionado
    estado: EstadoVehiculo = EstadoVehiculo.DISPONIBLE


# ============================================================================
# Animales
# ============================================================================

@dataclass(frozen=True)
class IndicadoresSalud:
    """Indicadores de salud de un animal."""
    peso: float  # kg
    consumo_alimento: float  # % de lo esperado (0-100+)
    actividad: float  # 0-100


@dataclass(frozen=True)
class Animal:
    """Animal individual en el zoológico."""
    id: str
    especie: Especie
    recinto_origen: str  # id del recinto donde debería estar
    ubicacion: str  # nodo_id actual (o recinto_id si en_recinto)
    estado: EstadoAnimal = EstadoAnimal.EN_RECINTO
    salud: IndicadoresSalud = field(default_factory=lambda: IndicadoresSalud(0.0, 100.0, 50.0))


# ============================================================================
# Equipo reservable
# ============================================================================

@dataclass(frozen=True)
class Equipo:
    """Equipo reservable (recurso)."""
    id: str
    tipo: TipoEquipo
    ubicacion: str  # nodo_id donde está guardado
    estado: EstadoEquipo = EstadoEquipo.DISPONIBLE


# ============================================================================
# Tareas
# ============================================================================

@dataclass(frozen=True)
class HabilidadRequerida:
    """Habilidad requerida para una tarea con nivel mínimo."""
    habilidad: Habilidad
    nivel_minimo: int


@dataclass(frozen=True)
class Tarea:
    """Tarea a realizar por un cuidador."""
    id: str
    tipo: str  # captura, traslado, reparacion, alimentacion, etc.
    prioridad_base: PrioridadTarea = PrioridadTarea.MEDIA
    urgencia: int = 0  # 0-100, se suma a prioridad_base para prioridad efectiva
    nodo_destino: str = ""
    duracion_estimada: int = 0  # segundos simulados
    habilidades_requeridas: Tuple[HabilidadRequerida, ...] = field(default_factory=tuple)
    certificaciones_requeridas: frozenset[Certificacion] = field(default_factory=frozenset)
    vehiculo_requerido: Optional[TipoVehiculo] = None
    equipos_requeridos: Tuple[TipoEquipo, ...] = field(default_factory=tuple)
    ventana_tiempo: Optional[Tuple[int, int]] = None  # (inicio, fin) opcional
    dependencias: frozenset[str] = field(default_factory=frozenset)  # ids de tareas
    interrumpible: bool = True
    estado: EstadoTarea = EstadoTarea.PENDIENTE
    incidente_origen: Optional[str] = None  # id del incidente que la generó
    cuidadores_asignados: Tuple[str, ...] = field(default_factory=tuple)
    personas_minimas: int = 1

    def __post_init__(self) -> None:
        """Exige que la tarea requiera al menos una persona."""
        if self.personas_minimas < 1:
            raise ErrorDominio("personas_minimas debe ser al menos 1")


# ============================================================================
# Incidentes
# ============================================================================

@dataclass(frozen=True)
class Incidente:
    """Incidente en el zoológico."""
    id: str
    tipo: TipoIncidente
    severidad: int  # 1-10
    ubicacion: str  # nodo_id
    estado: EstadoIncidente = EstadoIncidente.ABIERTO
    tareas_generadas: frozenset[str] = field(default_factory=frozenset)
    animal_relacionado: Optional[str] = None  # id del animal si es escape


# ============================================================================
# Sensores y lecturas (solo estructura de datos)
# ============================================================================

@dataclass(frozen=True)
class Sensor:
    """Sensor en un recinto (solo estructura)."""
    id: str
    tipo: TipoSensor
    recinto_id: str
    ubicacion: str = ""  # descripción dentro del recinto


@dataclass(frozen=True)
class Lectura:
    """Lectura de un sensor (solo estructura)."""
    sensor_id: str
    valor: float
    momento: int  # tiempo simulado en segundos


# ============================================================================
# Mundo / Estado global (para verificaciones)
# ============================================================================

@dataclass
class Mundo:
    """Estado completo del mundo simulado (agregado mutable).
    
    Las entidades son inmutables (frozen); Mundo centraliza las mutaciones
    de sus colecciones mediante métodos explícitos.
    """
    nodos: Dict[str, Nodo] = field(default_factory=dict)
    aristas: Dict[Tuple[str, str], Arista] = field(default_factory=dict)  # (origen, destino) -> Arista
    recintos: Dict[str, Recinto] = field(default_factory=dict)
    cuidadores: Dict[str, Cuidador] = field(default_factory=dict)
    vehiculos: Dict[str, Vehiculo] = field(default_factory=dict)
    animales: Dict[str, Animal] = field(default_factory=dict)
    equipos: Dict[str, Equipo] = field(default_factory=dict)
    tareas: Dict[str, Tarea] = field(default_factory=dict)
    incidentes: Dict[str, Incidente] = field(default_factory=dict)
    planes: Dict[str, "PlanEjecucion"] = field(default_factory=dict)
    sensores: Dict[str, Sensor] = field(default_factory=dict)
    lecturas: List[Lectura] = field(default_factory=list)
    tiempo_actual: int = 0  # reloj simulado en segundos

    def instantanea(self) -> "Mundo":
        """Devuelve una copia profunda del estado completo del mundo."""
        return copy.deepcopy(self)

    def restaurar(self, instantanea: "Mundo") -> None:
        """Restaura el contenido del mundo sin reemplazar esta instancia."""
        if not isinstance(instantanea, Mundo):
            raise TypeError("instantanea debe ser una instancia de Mundo")
        estado = copy.deepcopy(instantanea)
        for nombre in self.__dataclass_fields__:
            setattr(self, nombre, getattr(estado, nombre))
    
    # Métodos de mutación centralizados
    def sustituir_entidad(self, coleccion: str, entidad_id: str, entidad) -> None:
        """Sustituye una entidad en una colección (crea nueva instancia si no existe)."""
        if not hasattr(self, coleccion):
            raise ValueError(f"Colección desconocida: {coleccion}")
        getattr(self, coleccion)[entidad_id] = entidad
    
    def agregar_entidad(self, coleccion: str, entidad_id: str, entidad) -> None:
        """Agrega una entidad a una colección (falla si ya existe)."""
        if not hasattr(self, coleccion):
            raise ValueError(f"Colección desconocida: {coleccion}")
        collec = getattr(self, coleccion)
        if entidad_id in collec:
            raise ValueError(f"Entidad {entidad_id} ya existe en {coleccion}")
        collec[entidad_id] = entidad
    
    def eliminar_entidad(self, coleccion: str, entidad_id: str) -> None:
        """Elimina una entidad de una colección."""
        if not hasattr(self, coleccion):
            raise ValueError(f"Colección desconocida: {coleccion}")
        collec = getattr(self, coleccion)
        if entidad_id not in collec:
            raise KeyError(f"Entidad {entidad_id} no existe en {coleccion}")
        del collec[entidad_id]
    
    def obtener_entidad(self, coleccion: str, entidad_id: str):
        """Obtiene una entidad de una colección (None si no existe)."""
        if not hasattr(self, coleccion):
            raise ValueError(f"Colección desconocida: {coleccion}")
        return getattr(self, coleccion).get(entidad_id)

    def registrar_plan(self, plan: "PlanEjecucion") -> None:
        """Registra un plan de ejecución para su tarea."""
        self.agregar_entidad("planes", plan.tarea_id, plan)

    def eliminar_plan(self, tarea_id: str) -> None:
        """Elimina el plan asociado a una tarea."""
        self.eliminar_entidad("planes", tarea_id)


# ============================================================================
# Utilidades de ubicación
# ============================================================================

def esta_en_nodo(ubicacion: Tuple) -> bool:
    """Verifica si la ubicación es un nodo simple."""
    return nodo_de_ubicacion(ubicacion) is not None


def esta_en_arista(ubicacion: Tuple) -> bool:
    """Verifica si la ubicación es sobre una arista con progreso."""
    return len(ubicacion) == 3 and all(isinstance(x, str) for x in ubicacion[:2]) and isinstance(ubicacion[2], (int, float))


def obtener_nodo_actual(ubicacion: Tuple) -> Optional[str]:
    """Obtiene el nodo actual si la ubicación es un nodo, None si está en arista."""
    return nodo_de_ubicacion(ubicacion)


def obtener_arista_actual(ubicacion: Tuple) -> Optional[Tuple[str, str, float]]:
    """Obtiene (origen, destino, progreso) si está en arista."""
    if esta_en_arista(ubicacion):
        return (ubicacion[0], ubicacion[1], float(ubicacion[2]))
    return None


def ubicacion_en_nodo(nodo_id: str) -> Tuple[str]:
    """Representa la ubicación de un cuidador en un nodo."""
    return (nodo_id,)


def nodo_de_ubicacion(ubicacion: Tuple) -> Optional[str]:
    """Devuelve el nodo de una ubicación simple, o None si está sobre una arista."""
    if len(ubicacion) == 1 and isinstance(ubicacion[0], str):
        return ubicacion[0]
    return None