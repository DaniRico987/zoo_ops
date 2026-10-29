"""Pruebas de estimación temporal del paquete de asignación."""

import math
import copy

import pytest

from zoo_ops.dominio.entidades import Arista, Cuidador, Mundo, Nodo, Vehiculo
from zoo_ops.dominio.enums import (
    Certificacion, EstadoCuidador, EstadoVehiculo, MedioPermitido, TipoNodo,
    TipoVehiculo,
)
from zoo_ops.dominio.errores import ErrorDominio
from zoo_ops.dominio.catalogos import ESPECIES_CATALOGO
from zoo_ops.dominio.entidades import Equipo, Tarea
from zoo_ops.dominio.enums import EstadoEquipo, TipoEquipo
from zoo_ops.dominio.plan import PlanEjecucion
from zoo_ops.asignacion.tiempos import (
    TIEMPO_PREPARACION_HELICOPTERO, construir_plan, distancia_recta,
    estimar_plan, segundos_de_viaje, tiempo_llegada_cuidador,
    tiempo_vehiculo_a_destino,
)


def _mundo_base():
    nodos = {
        "a": Nodo("a", TipoNodo.GARAJE, 0, 0, 0),
        "b": Nodo("b", TipoNodo.CRUCE, 3, 4, 0),
        "c": Nodo("c", TipoNodo.RECINTO, 3, 4, 12),
        "d": Nodo("d", TipoNodo.CRUCE, 3, 0, 0),
    }
    aristas = {
        ("a", "b"): Arista(
            "a", "b", 5, frozenset({MedioPermitido.PIE, MedioPermitido.JEEP}),
        ),
        ("b", "c"): Arista(
            "b", "c", 12, frozenset({MedioPermitido.PIE, MedioPermitido.JEEP}),
        ),
        ("a", "d"): Arista(
            "a", "d", 3, frozenset({MedioPermitido.PIE, MedioPermitido.JEEP}),
        ),
        ("d", "b"): Arista(
            "d", "b", 5, frozenset({MedioPermitido.PIE, MedioPermitido.JEEP}),
        ),
    }
    return Mundo(nodos=nodos, aristas=aristas)


def test_segundos_de_viaje_redondea_hacia_arriba():
    assert segundos_de_viaje(10, 3) == 4
    assert segundos_de_viaje(10, 2) == 5
    assert segundos_de_viaje(0.1 + 0.2, 0.1) == 3


@pytest.mark.parametrize("velocidad", [0, -1])
def test_segundos_de_viaje_rechaza_velocidad_no_positiva(velocidad):
    with pytest.raises(ErrorDominio, match="velocidad"):
        segundos_de_viaje(10, velocidad)


def test_distancia_recta_usa_las_tres_coordenadas():
    assert distancia_recta(_mundo_base(), "a", "c") == 13.0


def test_tiempo_llegada_cuidador_calcula_recorrido_a_pie():
    mundo = _mundo_base()
    cuidador = Cuidador(
        "c1", "Cuidador", velocidad_base=2, ubicacion=("a",),
        estado=EstadoCuidador.DISPONIBLE,
    )

    assert tiempo_llegada_cuidador(mundo, cuidador, "b") == 3


@pytest.mark.parametrize(
    "ubicacion",
    [(), ("a", "b", 0.5)],
)
def test_tiempo_llegada_cuidador_no_estima_ubicaciones_no_nodales(ubicacion):
    mundo = _mundo_base()
    cuidador = Cuidador("c1", "Cuidador", ubicacion=ubicacion)

    assert tiempo_llegada_cuidador(mundo, cuidador, "b") is None


def test_tiempo_llegada_cuidador_devuelve_none_si_no_hay_ruta():
    mundo = _mundo_base()
    cuidador = Cuidador("c1", "Cuidador", ubicacion=("c",))

    assert tiempo_llegada_cuidador(mundo, cuidador, "a") is None


def test_tiempo_llegada_cuidador_devuelve_none_con_velocidad_no_positiva():
    mundo = _mundo_base()
    cuidador = Cuidador("c1", "Cuidador", velocidad_base=0, ubicacion=("a",))

    assert tiempo_llegada_cuidador(mundo, cuidador, "b") is None


@pytest.mark.parametrize(
    ("tipo", "certificacion"),
    [
        (TipoVehiculo.JEEP, Certificacion.JEEP),
        (TipoVehiculo.CAMION_TRASLADO, Certificacion.CAMION_TRASLADO),
    ],
)
def test_tiempo_vehiculo_por_red_vial(tipo, certificacion):
    mundo = _mundo_base()
    vehiculo = Vehiculo(
        "v1", tipo, 5, 4, 2,
        certificacion, "a", EstadoVehiculo.DISPONIBLE,
    )

    assert tiempo_vehiculo_a_destino(mundo, vehiculo, "b") == (("a", "b"), 1)


def test_tiempo_vehiculo_helicoptero_incluye_preparacion():
    mundo = _mundo_base()
    vehiculo = Vehiculo(
        "v1", TipoVehiculo.HELICOPTERO, 5, 4, 2,
        Certificacion.HELICOPTERO, "a", EstadoVehiculo.DISPONIBLE,
    )

    ruta, tiempo = tiempo_vehiculo_a_destino(mundo, vehiculo, "c")

    assert ruta == ()
    assert tiempo == TIEMPO_PREPARACION_HELICOPTERO + math.ceil(13 / 5)
    assert tiempo_vehiculo_a_destino(
        mundo, vehiculo, "c", preparacion=10,
    ) == ((), 13)


def test_tiempo_vehiculo_devuelve_none_si_no_hay_camino():
    mundo = _mundo_base()
    mundo.aristas.clear()
    vehiculo = Vehiculo(
        "v1", TipoVehiculo.JEEP, 5, 4, 2,
        Certificacion.JEEP, "a", EstadoVehiculo.DISPONIBLE,
    )

    assert tiempo_vehiculo_a_destino(mundo, vehiculo, "b") is None


@pytest.mark.parametrize("velocidad", [0, -1])
def test_tiempo_vehiculo_devuelve_none_con_velocidad_no_positiva(velocidad):
    mundo = _mundo_base()
    vehiculo = Vehiculo(
        "v1", TipoVehiculo.JEEP, velocidad, 4, 2,
        Certificacion.JEEP, "a", EstadoVehiculo.DISPONIBLE,
    )

    assert tiempo_vehiculo_a_destino(mundo, vehiculo, "b") is None


def test_estimar_y_construir_plan_con_vehiculo():
    mundo = _mundo_base()
    mundo.cuidadores = {
        "c1": Cuidador(
            "c1", "Uno", velocidad_base=1, ubicacion=("a",),
            certificaciones=frozenset({Certificacion.CAMION_TRASLADO}),
        ),
        "c2": Cuidador(
            "c2", "Dos", velocidad_base=1, ubicacion=("b",),
            certificaciones=frozenset({Certificacion.CAMION_TRASLADO}),
        ),
    }
    mundo.vehiculos = {
        "v1": Vehiculo(
            "v1", TipoVehiculo.CAMION_TRASLADO, 5, 4, 2,
            Certificacion.CAMION_TRASLADO, "b",
        ),
    }
    mundo.equipos = {
        "e1": Equipo(
            "e1", TipoEquipo.DARDOS_TRANQUILIZANTES, "b",
            EstadoEquipo.DISPONIBLE,
        ),
    }
    tarea = Tarea(
        "t1", "traslado", nodo_destino="c", duracion_estimada=20,
        vehiculo_requerido=TipoVehiculo.CAMION_TRASLADO,
        equipos_requeridos=(TipoEquipo.DARDOS_TRANQUILIZANTES,),
        personas_minimas=2,
    )
    mundo_antes = copy.deepcopy(mundo)

    estimacion = estimar_plan(mundo, tarea, ("c1", "c2"), "v1", 50)

    assert mundo == mundo_antes
    assert estimacion is not None
    assert estimacion.ruta == ("b", "c")
    assert estimacion.espera_recogida == 5
    assert estimacion.viaje == 3
    assert (estimacion.desde, estimacion.hasta) == (50, 78)
    assert construir_plan(
        estimacion, tarea, ("c1", "c2"), "v1", ("e1",),
    ) == PlanEjecucion(
        tarea_id="t1", cuidadores=("c1", "c2"), desde=50, hasta=78,
        vehiculo_id="v1", equipos=("e1",), ruta=("b", "c"),
    )


def test_estimar_plan_usa_tiempos_precalculados_sin_cambiar_el_resultado():
    mundo = _mundo_base()
    mundo.cuidadores = {
        "c1": Cuidador("c1", "Uno", ubicacion=("a",)),
        "c2": Cuidador("c2", "Dos", ubicacion=("b",)),
    }
    mundo.vehiculos = {
        "v1": Vehiculo(
            "v1", TipoVehiculo.CAMION_TRASLADO, 5, 4, 2,
            Certificacion.CAMION_TRASLADO, "b",
        ),
    }
    tarea = Tarea("t1", "traslado", nodo_destino="c", duracion_estimada=20)

    normal = estimar_plan(mundo, tarea, ("c1", "c2"), "v1", 50)
    precalculado = estimar_plan(
        mundo,
        tarea,
        ("c1", "c2"),
        "v1",
        50,
        tiempos_cuidadores={"c1": 5, "c2": 0},
        viaje_vehiculo=(("b", "c"), 3),
    )

    assert normal == precalculado


def test_estimar_plan_sin_vehiculo_usa_maximo_de_tiempos_a_pie():
    mundo = _mundo_base()
    mundo.cuidadores = {
        "c1": Cuidador("c1", "Uno", velocidad_base=1, ubicacion=("a",)),
        "c2": Cuidador("c2", "Dos", velocidad_base=2, ubicacion=("b",)),
    }
    tarea = Tarea("t1", "tarea", nodo_destino="c", duracion_estimada=6)

    estimacion = estimar_plan(mundo, tarea, ("c1", "c2"), None, 100)

    assert estimacion is not None
    assert estimacion.ruta == ()
    assert estimacion.espera_recogida == 0
    assert estimacion.viaje == 17
    assert (estimacion.desde, estimacion.hasta) == (100, 123)
    assert estimacion.salida == 100
    assert estimacion.llegada == 117
    assert estimacion.fin == 123


def test_estimar_plan_devuelve_none_si_un_cuidador_no_puede_llegar():
    mundo = _mundo_base()
    mundo.cuidadores = {
        "c1": Cuidador("c1", "Uno", ubicacion=("a",)),
        "c2": Cuidador("c2", "Dos", ubicacion=("c",)),
    }
    tarea = Tarea("t1", "tarea", nodo_destino="b")

    assert estimar_plan(mundo, tarea, ("c1", "c2"), None, 0) is None


def test_estimar_plan_garantiza_intervalo_positivo_si_duracion_es_cero():
    mundo = _mundo_base()
    mundo.cuidadores = {
        "c1": Cuidador("c1", "Uno", ubicacion=("b",)),
    }
    tarea = Tarea("t1", "tarea", nodo_destino="b")

    estimacion = estimar_plan(mundo, tarea, ("c1",), None, 10)

    assert estimacion is not None
    assert estimacion.hasta > estimacion.desde
