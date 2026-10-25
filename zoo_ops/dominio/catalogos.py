"""
Catálogos y datos semilla del dominio de zoo-ops.
Contiene las definiciones estáticas de especies, habilidades, certificaciones, etc.
"""

from dataclasses import dataclass, field
from typing import Dict, List, Optional
from zoo_ops.dominio.enums import (
    TipoRecinto, Medio, Peligrosidad, TipoVehiculo, TipoEquipo,
    Habilidad, Certificacion, TipoSensor
)
# Sensor se define en entidades.py; no se usa en este módulo


@dataclass(frozen=True)
class Especie:
    """
    Definición de una especie animal.
    Valores de diseño para simulación; no son datos reales de manejo animal.
    """
    nombre: str
    medio: Medio
    peligrosidad: Peligrosidad
    requiere_tranquilizante: bool
    habilidad_requerida: Habilidad
    nivel_minimo_habilidad: int
    tipo_vehiculo_traslado: TipoVehiculo
    minimo_personas_traslado: int
    tipo_recinto_requerido: TipoRecinto


# Catálogo de especies inicial (semilla)
ESPECIES_CATALOGO: Dict[str, Especie] = {
    "jaguar": Especie(
        nombre="Jaguar",
        medio=Medio.TERRESTRE,
        peligrosidad=Peligrosidad.ALTA,
        requiere_tranquilizante=True,
        habilidad_requerida=Habilidad.MANEJO_FELINOS,
        nivel_minimo_habilidad=4,
        tipo_vehiculo_traslado=TipoVehiculo.CAMION_TRASLADO,
        minimo_personas_traslado=3,
        tipo_recinto_requerido=TipoRecinto.ABIERTO,
    ),
    "mono_aullador": Especie(
        nombre="Mono aullador",
        medio=Medio.TERRESTRE,
        peligrosidad=Peligrosidad.MEDIA,
        requiere_tranquilizante=False,
        habilidad_requerida=Habilidad.MANEJO_PRIMATES,
        nivel_minimo_habilidad=3,
        tipo_vehiculo_traslado=TipoVehiculo.JEEP,
        minimo_personas_traslado=2,
        tipo_recinto_requerido=TipoRecinto.ABIERTO,
    ),
    "tapir": Especie(
        nombre="Tapir",
        medio=Medio.TERRESTRE,
        peligrosidad=Peligrosidad.BAJA,
        requiere_tranquilizante=True,
        habilidad_requerida=Habilidad.MANEJO_UNGULADOS,
        nivel_minimo_habilidad=3,
        tipo_vehiculo_traslado=TipoVehiculo.CAMION_TRASLADO,
        minimo_personas_traslado=3,
        tipo_recinto_requerido=TipoRecinto.ABIERTO,
    ),
    "guacamaya_roja": Especie(
        nombre="Guacamaya roja",
        medio=Medio.AEREO,
        peligrosidad=Peligrosidad.MEDIA,
        requiere_tranquilizante=False,
        habilidad_requerida=Habilidad.MANEJO_AVES,
        nivel_minimo_habilidad=3,
        tipo_vehiculo_traslado=TipoVehiculo.JEEP,
        minimo_personas_traslado=2,
        tipo_recinto_requerido=TipoRecinto.AVIARIO,
    ),
    "pirarucu": Especie(
        nombre="Pirarucu",
        medio=Medio.ACUATICO,
        peligrosidad=Peligrosidad.BAJA,
        requiere_tranquilizante=False,
        habilidad_requerida=Habilidad.MANEJO_ACUATICO,
        nivel_minimo_habilidad=3,
        tipo_vehiculo_traslado=TipoVehiculo.JEEP,
        minimo_personas_traslado=2,
        tipo_recinto_requerido=TipoRecinto.ACUARIO,
    ),
}


@dataclass(frozen=True)
class DefinicionHabilidad:
    """Definición de una habilidad del catálogo."""
    habilidad: Habilidad
    descripcion: str
    requiere_certificacion: Optional[Certificacion] = None


# Catálogo de habilidades
HABILIDADES_CATALOGO: Dict[Habilidad, DefinicionHabilidad] = {
    Habilidad.REPARACION: DefinicionHabilidad(
        habilidad=Habilidad.REPARACION,
        descripcion="Reparación de infraestructura y equipos",
    ),
    Habilidad.MANEJO_FELINOS: DefinicionHabilidad(
        habilidad=Habilidad.MANEJO_FELINOS,
        descripcion="Manejo seguro de félidos",
        requiere_certificacion=Certificacion.TRANQUILIZANTE,
    ),
    Habilidad.MANEJO_PRIMATES: DefinicionHabilidad(
        habilidad=Habilidad.MANEJO_PRIMATES,
        descripcion="Manejo seguro de primates",
    ),
    Habilidad.MANEJO_UNGULADOS: DefinicionHabilidad(
        habilidad=Habilidad.MANEJO_UNGULADOS,
        descripcion="Manejo seguro de ungulados",
        requiere_certificacion=Certificacion.TRANQUILIZANTE,
    ),
    Habilidad.MANEJO_AVES: DefinicionHabilidad(
        habilidad=Habilidad.MANEJO_AVES,
        descripcion="Manejo seguro de aves",
    ),
    Habilidad.MANEJO_ACUATICO: DefinicionHabilidad(
        habilidad=Habilidad.MANEJO_ACUATICO,
        descripcion="Manejo seguro de fauna acuática",
    ),
    Habilidad.MANTENIMIENTO_SISTEMAS: DefinicionHabilidad(
        habilidad=Habilidad.MANTENIMIENTO_SISTEMAS,
        descripcion="Mantenimiento de sistemas de soporte vital",
    ),
    Habilidad.PRIMEROS_AUXILIOS: DefinicionHabilidad(
        habilidad=Habilidad.PRIMEROS_AUXILIOS,
        descripcion="Primeros auxilios básicos",
    ),
    Habilidad.VETERINARIA_BASICA: DefinicionHabilidad(
        habilidad=Habilidad.VETERINARIA_BASICA,
        descripcion="Conocimientos veterinarios básicos",
    ),
    Habilidad.CONDUCCION: DefinicionHabilidad(
        habilidad=Habilidad.CONDUCCION,
        descripcion="Conducción de vehículos",
        requiere_certificacion=Certificacion.JEEP,
    ),
}


@dataclass(frozen=True)
class DefinicionCertificacion:
    """Definición de una certificación del catálogo."""
    certificacion: Certificacion
    descripcion: str
    vehiculos_asociados: List[TipoVehiculo] = field(default_factory=list)


# Catálogo de certificaciones
CERTIFICACIONES_CATALOGO: Dict[Certificacion, DefinicionCertificacion] = {
    Certificacion.JEEP: DefinicionCertificacion(
        certificacion=Certificacion.JEEP,
        descripcion="Certificación para conducir jeep",
        vehiculos_asociados=[TipoVehiculo.JEEP],
    ),
    Certificacion.HELICOPTERO: DefinicionCertificacion(
        certificacion=Certificacion.HELICOPTERO,
        descripcion="Certificación para pilotar helicóptero",
        vehiculos_asociados=[TipoVehiculo.HELICOPTERO],
    ),
    Certificacion.TRANQUILIZANTE: DefinicionCertificacion(
        certificacion=Certificacion.TRANQUILIZANTE,
        descripcion="Certificación para uso de tranquilizantes",
        vehiculos_asociados=[],
    ),
    Certificacion.CAMION_TRASLADO: DefinicionCertificacion(
        certificacion=Certificacion.CAMION_TRASLADO,
        descripcion="Certificación para conducir camión de traslado",
        vehiculos_asociados=[TipoVehiculo.CAMION_TRASLADO],
    ),
}


@dataclass(frozen=True)
class DefinicionEquipo:
    """Definición de un tipo de equipo reservable."""
    tipo: TipoEquipo
    descripcion: str
    especies_compatibles: List[str] = field(default_factory=list)


# Catálogo de equipos
EQUIPOS_CATALOGO: Dict[TipoEquipo, DefinicionEquipo] = {
    TipoEquipo.DARDOS_TRANQUILIZANTES: DefinicionEquipo(
        tipo=TipoEquipo.DARDOS_TRANQUILIZANTES,
        descripcion="Dardos con tranquilizante para animales grandes",
        especies_compatibles=["jaguar", "tapir"],
    ),
    TipoEquipo.RED_CAPTURA: DefinicionEquipo(
        tipo=TipoEquipo.RED_CAPTURA,
        descripcion="Red de captura para animales terrestres medianos",
        especies_compatibles=["mono_aullador"],
    ),
    TipoEquipo.RED_AVES: DefinicionEquipo(
        tipo=TipoEquipo.RED_AVES,
        descripcion="Red especializada para captura de aves",
        especies_compatibles=["guacamaya_roja"],
    ),
    TipoEquipo.JAULA_PORTATIL: DefinicionEquipo(
        tipo=TipoEquipo.JAULA_PORTATIL,
        descripcion="Jaula portátil para transporte de animales",
        especies_compatibles=["mono_aullador", "guacamaya_roja"],
    ),
    TipoEquipo.CONTENEDOR_OXIGENADO: DefinicionEquipo(
        tipo=TipoEquipo.CONTENEDOR_OXIGENADO,
        descripcion="Contenedor con oxígeno para transporte acuático",
        especies_compatibles=["pirarucu"],
    ),
}


def obtener_especie(nombre: str) -> Especie:
    """Obtiene una especie del catálogo por nombre (clave)."""
    if nombre not in ESPECIES_CATALOGO:
        raise ValueError(f"Especie no encontrada en catálogo: {nombre}")
    return ESPECIES_CATALOGO[nombre]


def listar_especies() -> List[Especie]:
    """Lista todas las especies del catálogo."""
    return list(ESPECIES_CATALOGO.values())