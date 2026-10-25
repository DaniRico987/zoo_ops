"""
Enumeraciones base para el dominio de zoo-ops.
"""

from enum import Enum, auto, IntEnum


class TipoNodo(Enum):
    """Tipos de nodos en el grafo del zoológico."""
    RECINTO = auto()
    CRUCE = auto()
    HELIPUERTO = auto()
    CLINICA = auto()
    GARAJE = auto()
    BODEGA = auto()


class TipoRecinto(Enum):
    """Tipos de recinto según el medio."""
    ABIERTO = auto()
    AVIARIO = auto()
    ACUARIO = auto()


class Medio(Enum):
    """Medios de desplazamiento o hábitat."""
    TERRESTRE = auto()
    AEREO = auto()
    ACUATICO = auto()


class Peligrosidad(Enum):
    """Niveles de peligrosidad de las especies."""
    BAJA = auto()
    MEDIA = auto()
    ALTA = auto()


class TipoVehiculo(Enum):
    """Tipos de vehículos disponibles."""
    JEEP = auto()
    HELICOPTERO = auto()
    CAMION_TRASLADO = auto()


class TipoEquipo(Enum):
    """Tipos de equipo reservable."""
    DARDOS_TRANQUILIZANTES = auto()
    RED_CAPTURA = auto()
    RED_AVES = auto()
    JAULA_PORTATIL = auto()
    CONTENEDOR_OXIGENADO = auto()


class Habilidad(Enum):
    """Habilidades de los cuidadores."""
    REPARACION = auto()
    MANEJO_FELINOS = auto()
    MANEJO_PRIMATES = auto()
    MANEJO_UNGULADOS = auto()
    MANEJO_AVES = auto()
    MANEJO_ACUATICO = auto()
    MANTENIMIENTO_SISTEMAS = auto()
    PRIMEROS_AUXILIOS = auto()
    VETERINARIA_BASICA = auto()
    CONDUCCION = auto()


class Certificacion(Enum):
    """Certificaciones de los cuidadores."""
    JEEP = auto()
    HELICOPTERO = auto()
    TRANQUILIZANTE = auto()
    CAMION_TRASLADO = auto()


class EstadoCuidador(Enum):
    """Estados posibles de un cuidador."""
    FUERA_DE_TURNO = auto()
    DISPONIBLE = auto()
    ASIGNADO = auto()
    EN_CAMINO = auto()
    EJECUTANDO = auto()
    PAUSADO = auto()
    DESCANSANDO = auto()


class EstadoAnimal(Enum):
    """Estados posibles de un animal."""
    EN_RECINTO = auto()
    ESCAPADO = auto()
    LOCALIZADO = auto()
    TRANQUILIZADO = auto()
    EN_TRASLADO = auto()
    EN_CLINICA = auto()
    EN_OBSERVACION = auto()


class EstadoVehiculo(Enum):
    """Estados posibles de un vehículo."""
    DISPONIBLE = auto()
    RESERVADO = auto()
    EN_RUTA = auto()
    EN_USO = auto()
    EN_MANTENIMIENTO = auto()


class EstadoTarea(Enum):
    """Estados posibles de una tarea."""
    PENDIENTE = auto()
    BLOQUEADA = auto()
    ASIGNADA = auto()
    EN_CURSO = auto()
    PAUSADA = auto()
    COMPLETADA = auto()
    FALLIDA = auto()
    CANCELADA = auto()


class EstadoIncidente(Enum):
    """Estados posibles de un incidente."""
    ABIERTO = auto()
    EN_RESPUESTA = auto()
    CONTENIDO = auto()
    CERRADO = auto()


class TipoIncidente(Enum):
    """Tipos de incidente."""
    ESCAPE_TERRESTRE = auto()
    ESCAPE_AEREO = auto()
    FALLA_SOPORTE_VITAL = auto()


class TipoSensor(Enum):
    """Tipos de sensor en acuarios."""
    TEMPERATURA = auto()
    OXIGENO_DISUELTO = auto()
    PH = auto()


class MedioPermitido(Enum):
    """Medios de transporte permitidos en una arista."""
    PIE = auto()
    JEEP = auto()


class PrioridadTarea(IntEnum):
    """Niveles de prioridad de tareas."""
    BAJA = 1
    MEDIA = 2
    ALTA = 3
    CRITICA = 4