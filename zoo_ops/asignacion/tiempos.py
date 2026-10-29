"""Cálculos puros de distancias, duraciones y planes estimados."""

import math
from dataclasses import dataclass
from typing import Optional, Tuple

from zoo_ops.dominio.entidades import Cuidador, Mundo, Tarea, Vehiculo, nodo_de_ubicacion
from zoo_ops.dominio.enums import MedioPermitido, TipoVehiculo
from zoo_ops.dominio.errores import ErrorDominio
from zoo_ops.dominio.plan import PlanEjecucion
from zoo_ops.asignacion.grafo import ruta_mas_corta


TIEMPO_PREPARACION_HELICOPTERO = 120


@dataclass(frozen=True)
class Estimacion:
    """Tiempos calculados para construir un plan de ejecución."""

    ruta: Tuple[str, ...]
    espera_recogida: int
    viaje: int
    desde: int
    hasta: int

    @property
    def salida(self) -> int:
        """Instante de salida tras esperar a la recogida."""
        return self.desde + self.espera_recogida

    @property
    def llegada(self) -> int:
        """Instante de llegada después del viaje."""
        return self.salida + self.viaje

    @property
    def fin(self) -> int:
        """Instante de finalización de la tarea."""
        return self.hasta


def segundos_de_viaje(distancia: float, velocidad: float) -> int:
    """Redondea hacia arriba el viaje; distancia y velocidad usan unidades de arista, por segundo."""
    if velocidad <= 0:
        raise ErrorDominio("La velocidad debe ser mayor que cero")
    return math.ceil(round(distancia / velocidad, 9))


def distancia_recta(mundo: Mundo, a: str, b: str) -> float:
    """Calcula distancia euclídea tridimensional entre dos nodos existentes."""
    nodo_a = mundo.nodos.get(a)
    nodo_b = mundo.nodos.get(b)
    if nodo_a is None:
        raise ErrorDominio(f"El nodo {a} no existe en el mundo")
    if nodo_b is None:
        raise ErrorDominio(f"El nodo {b} no existe en el mundo")
    return math.sqrt(
        (nodo_a.x - nodo_b.x) ** 2
        + (nodo_a.y - nodo_b.y) ** 2
        + (nodo_a.z - nodo_b.z) ** 2
    )


def tiempo_llegada_cuidador(
    mundo: Mundo,
    cuidador: Cuidador,
    destino: str,
) -> Optional[int]:
    """Devuelve duración a pie en segundos; no estima ubicaciones sobre aristas."""
    origen = nodo_de_ubicacion(cuidador.ubicacion)
    if origen is None or cuidador.velocidad_base <= 0:
        return None
    resultado = ruta_mas_corta(mundo, origen, destino, MedioPermitido.PIE)
    if resultado is None:
        return None
    _, distancia = resultado
    return segundos_de_viaje(distancia, cuidador.velocidad_base)


def tiempo_vehiculo_a_destino(
    mundo: Mundo,
    vehiculo: Vehiculo,
    destino: str,
    preparacion: int = TIEMPO_PREPARACION_HELICOPTERO,
) -> Optional[Tuple[Tuple[str, ...], int]]:
    """Estima la ruta y duración del vehículo, incluida la preparación del helicóptero."""
    if vehiculo.velocidad <= 0:
        return None
    if vehiculo.tipo == TipoVehiculo.HELICOPTERO:
        distancia = distancia_recta(mundo, vehiculo.ubicacion, destino)
        return (), preparacion + segundos_de_viaje(
            distancia, vehiculo.velocidad,
        )

    resultado = ruta_mas_corta(
        mundo, vehiculo.ubicacion, destino, MedioPermitido.JEEP,
    )
    if resultado is None:
        return None
    ruta, distancia = resultado
    return ruta, segundos_de_viaje(distancia, vehiculo.velocidad)


def estimar_plan(
    mundo: Mundo,
    tarea: Tarea,
    cuidadores_ids: Tuple[str, ...],
    vehiculo_id: Optional[str],
    ahora: int,
    preparacion: int = TIEMPO_PREPARACION_HELICOPTERO,
) -> Optional[Estimacion]:
    """Estima espera y viaje sin modificar el mundo ni las entidades."""
    cuidadores = []
    for cuidador_id in cuidadores_ids:
        cuidador = mundo.cuidadores.get(cuidador_id)
        if cuidador is None:
            return None
        cuidadores.append(cuidador)
    if not cuidadores:
        return None

    if vehiculo_id is None:
        tiempos = [
            tiempo_llegada_cuidador(mundo, cuidador, tarea.nodo_destino)
            for cuidador in cuidadores
        ]
        if any(tiempo is None for tiempo in tiempos):
            return None
        espera_recogida = 0
        viaje = max(tiempos)
        ruta = ()
    else:
        vehiculo = mundo.vehiculos.get(vehiculo_id)
        if vehiculo is None:
            return None
        tiempos_recogida = [
            tiempo_llegada_cuidador(mundo, cuidador, vehiculo.ubicacion)
            for cuidador in cuidadores
        ]
        if any(tiempo is None for tiempo in tiempos_recogida):
            return None
        espera_recogida = max(tiempos_recogida)
        resultado_viaje = tiempo_vehiculo_a_destino(
            mundo, vehiculo, tarea.nodo_destino, preparacion,
        )
        if resultado_viaje is None:
            return None
        ruta, viaje = resultado_viaje

    duracion = max(
        1,
        espera_recogida + viaje + tarea.duracion_estimada,
    )
    return Estimacion(
        ruta=ruta,
        espera_recogida=espera_recogida,
        viaje=viaje,
        desde=ahora,
        hasta=ahora + duracion,
    )


def construir_plan(
    estimacion: Estimacion,
    tarea: Tarea,
    cuidadores_ids: Tuple[str, ...],
    vehiculo_id: Optional[str] = None,
    equipos: Tuple[str, ...] = (),
    animales_transportados: Tuple[str, ...] = (),
) -> PlanEjecucion:
    """Construye el plan inmutable a partir de una estimación y recursos elegidos."""
    return PlanEjecucion(
        tarea_id=tarea.id,
        cuidadores=tuple(cuidadores_ids),
        desde=estimacion.desde,
        hasta=estimacion.hasta,
        vehiculo_id=vehiculo_id,
        equipos=tuple(equipos),
        animales_transportados=tuple(animales_transportados),
        ruta=tuple(estimacion.ruta),
    )
