"""Pruebas del ciclo de ejecución de un plan de tarea."""

import copy

import pytest
from hypothesis import given, settings, strategies as st

from zoo_ops.dominio.entidades import Arista, Cuidador, Mundo, Nodo, Tarea, Vehiculo
from zoo_ops.dominio.enums import (
    Certificacion, EstadoCuidador, EstadoTarea, EstadoVehiculo,
    MedioPermitido, TipoNodo, TipoVehiculo,
)
from zoo_ops.dominio.errores import ErrorDominio
from zoo_ops.dominio.eventos import (
    RegistroEventos, reconstruir_estado, verificar_reconstruccion,
)
from zoo_ops.dominio.invariantes import verificar_invariantes
from zoo_ops.dominio.operaciones import (
    asignar_plan, completar_plan, desasignar_plan, fallar_plan,
    iniciar_ejecucion, llegar_a_destino,
)
from zoo_ops.dominio.plan import PlanEjecucion
from zoo_ops.dominio.reservas import RegistroReservas, paquete_de_reservas


def _mundo_ciclo(
    tipo_vehiculo=TipoVehiculo.CAMION_TRASLADO,
    estado_tarea=EstadoTarea.PENDIENTE,
    estado_cuidador=EstadoCuidador.DISPONIBLE,
    estado_vehiculo=EstadoVehiculo.DISPONIBLE,
    plan_registrado=False,
):
    certificacion = (
        Certificacion.HELICOPTERO
        if tipo_vehiculo == TipoVehiculo.HELICOPTERO
        else Certificacion.CAMION_TRASLADO
    )
    tarea = Tarea(
        id="t1",
        tipo="traslado",
        nodo_destino="destino",
        personas_minimas=3,
        vehiculo_requerido=tipo_vehiculo,
        estado=estado_tarea,
        cuidadores_asignados=(
            ("c1", "c2", "c3")
            if estado_tarea != EstadoTarea.PENDIENTE else ()
        ),
    )
    return Mundo(
        tareas={"t1": tarea},
        cuidadores={
            f"c{i}": Cuidador(
                f"c{i}",
                f"Cuidador {i}",
                certificaciones=frozenset({certificacion}),
                estado=estado_cuidador,
                ubicacion=("garaje",),
            )
            for i in range(1, 4)
        },
        vehiculos={
            "v1": Vehiculo(
                "v1",
                tipo_vehiculo,
                10,
                4,
                2,
                certificacion,
                "garaje",
                estado_vehiculo,
            ),
        },
        nodos={
            "garaje": Nodo("garaje", TipoNodo.GARAJE, 0, 0),
            "destino": Nodo("destino", TipoNodo.RECINTO, 1, 1),
        },
        aristas={
            ("garaje", "destino"): Arista(
                "garaje", "destino", 10,
                frozenset({MedioPermitido.JEEP}),
            ),
        },
        planes={
            "t1": _plan(tipo_vehiculo=tipo_vehiculo),
        } if plan_registrado else {},
    )


def _plan(desde=5, hasta=100, tipo_vehiculo=TipoVehiculo.CAMION_TRASLADO):
    return PlanEjecucion(
        tarea_id="t1",
        cuidadores=("c1", "c2", "c3"),
        desde=desde,
        hasta=hasta,
        vehiculo_id="v1",
        ruta=(
            ("garaje", "destino")
            if tipo_vehiculo != TipoVehiculo.HELICOPTERO
            else ()
        ),
    )


def _assert_sin_violaciones(mundo, reservas):
    violaciones, _ = verificar_invariantes(mundo, reservas)
    assert violaciones == []


@pytest.mark.parametrize(
    ("tipo_vehiculo", "estado_final"),
    [
        (TipoVehiculo.CAMION_TRASLADO, EstadoTarea.COMPLETADA),
        (TipoVehiculo.HELICOPTERO, EstadoTarea.COMPLETADA),
        (TipoVehiculo.CAMION_TRASLADO, EstadoTarea.FALLIDA),
    ],
)
def test_ciclo_de_ejecucion_completo_reconstruible(tipo_vehiculo, estado_final):
    inicial = _mundo_ciclo(tipo_vehiculo)
    mundo = copy.deepcopy(inicial)
    eventos = RegistroEventos()
    reservas = RegistroReservas()
    plan = _plan(tipo_vehiculo=tipo_vehiculo)

    asignar_plan(mundo, eventos, reservas, plan, 1, "asignar")
    _assert_sin_violaciones(mundo, reservas)
    iniciar_ejecucion(mundo, eventos, reservas, "t1", 5, "salida")
    _assert_sin_violaciones(mundo, reservas)
    llegar_a_destino(mundo, eventos, reservas, "t1", 6, "llegada")
    _assert_sin_violaciones(mundo, reservas)
    operacion_terminal = (
        completar_plan if estado_final == EstadoTarea.COMPLETADA else fallar_plan
    )
    operacion_terminal(mundo, eventos, reservas, "t1", 7, "cierre")
    _assert_sin_violaciones(mundo, reservas)

    assert mundo.tareas["t1"].estado == estado_final
    assert mundo.planes == {"t1": plan}
    assert reservas.obtener_reservas_de_tarea("t1") == []
    assert all(
        cuidador.estado == EstadoCuidador.DISPONIBLE
        and cuidador.ubicacion == ("destino",)
        for cuidador in mundo.cuidadores.values()
    )
    assert mundo.vehiculos["v1"].estado == EstadoVehiculo.DISPONIBLE
    assert mundo.vehiculos["v1"].ubicacion == "destino"
    reconstruido = reconstruir_estado(eventos.obtener_todos(), inicial)
    assert verificar_reconstruccion(mundo, reconstruido) == []


def _preparar_estado(operacion):
    mundo = _mundo_ciclo()
    eventos = RegistroEventos()
    reservas = RegistroReservas()
    asignar_plan(mundo, eventos, reservas, _plan(), 1, "asignar")
    if operacion in {"llegar", "completar", "fallar"}:
        iniciar_ejecucion(mundo, eventos, reservas, "t1", 5, "salida")
    if operacion in {"completar", "fallar"}:
        llegar_a_destino(mundo, eventos, reservas, "t1", 6, "llegada")
    return mundo, eventos, reservas


@pytest.mark.parametrize(
    ("operacion", "fallo_en"),
    [
        ("iniciar", fallo_en) for fallo_en in range(1, 6)
    ] + [
        ("llegar", fallo_en) for fallo_en in range(1, 5)
    ] + [
        (operacion, fallo_en)
        for operacion in ("completar", "fallar")
        for fallo_en in range(1, 6)
    ],
)
def test_operaciones_de_ejecucion_revierten_cada_anexo(
    operacion, fallo_en,
):
    class RegistroConFallo(RegistroEventos):
        def __init__(self):
            super().__init__()
            self.llamadas = 0
            self.fallo_en = None

        def anexar(self, evento):
            self.llamadas += 1
            if self.llamadas == self.fallo_en:
                raise RuntimeError(f"fallo de anexo {self.fallo_en}")
            super().anexar(evento)

    mundo, registro_base, reservas = _preparar_estado(operacion)
    registro = RegistroConFallo()
    registro.restaurar(registro_base.instantanea())
    registro.llamadas = 0
    registro.fallo_en = fallo_en
    mundo_antes = copy.deepcopy(mundo)
    eventos_antes = registro.instantanea()
    reservas_antes = reservas.instantanea()
    funciones = {
        "iniciar": iniciar_ejecucion,
        "llegar": llegar_a_destino,
        "completar": completar_plan,
        "fallar": fallar_plan,
    }

    with pytest.raises(RuntimeError, match=f"fallo de anexo {fallo_en}"):
        tiempo = mundo.tiempo_actual + 1
        if operacion == "iniciar":
            tiempo = max(tiempo, mundo.planes["t1"].desde)
        funciones[operacion](
            mundo, registro, reservas, "t1", tiempo, "fallo inyectado",
        )

    assert mundo == mundo_antes
    assert registro.instantanea() == eventos_antes
    assert reservas.instantanea() == reservas_antes


@pytest.mark.parametrize("operacion", ["completar", "fallar"])
def test_cierre_revierte_todo_si_falla_liberar_reservas(operacion, monkeypatch):
    import zoo_ops.dominio.operaciones as operaciones

    mundo, eventos, reservas = _preparar_estado("completar")
    mundo_antes = copy.deepcopy(mundo)
    eventos_antes = eventos.instantanea()
    reservas_antes = reservas.instantanea()

    def fallar_liberacion(*_args):
        raise RuntimeError("fallo liberando reservas")

    monkeypatch.setattr(operaciones, "liberar_reservas_tarea", fallar_liberacion)
    funcion = completar_plan if operacion == "completar" else fallar_plan
    with pytest.raises(RuntimeError, match="fallo liberando reservas"):
        funcion(mundo, eventos, reservas, "t1", 7, "fallo")

    assert mundo == mundo_antes
    assert eventos.instantanea() == eventos_antes
    assert reservas.instantanea() == reservas_antes


@pytest.mark.parametrize(
    ("operacion", "estado_tarea", "estado_cuidador", "estado_vehiculo", "tiempo"),
    [
        ("iniciar", EstadoTarea.PENDIENTE, EstadoCuidador.DISPONIBLE,
         EstadoVehiculo.DISPONIBLE, 5),
        ("iniciar", EstadoTarea.ASIGNADA, EstadoCuidador.DISPONIBLE,
         EstadoVehiculo.RESERVADO, 5),
        ("iniciar", EstadoTarea.ASIGNADA, EstadoCuidador.ASIGNADO,
         EstadoVehiculo.DISPONIBLE, 5),
        ("iniciar", EstadoTarea.ASIGNADA, EstadoCuidador.ASIGNADO,
         EstadoVehiculo.RESERVADO, 4),
        ("iniciar", EstadoTarea.ASIGNADA, EstadoCuidador.ASIGNADO,
         EstadoVehiculo.RESERVADO, 100),
        ("llegar", EstadoTarea.PENDIENTE, EstadoCuidador.EN_CAMINO,
         EstadoVehiculo.EN_RUTA, 5),
        ("llegar", EstadoTarea.EN_CURSO, EstadoCuidador.ASIGNADO,
         EstadoVehiculo.EN_RUTA, 5),
        ("llegar", EstadoTarea.EN_CURSO, EstadoCuidador.EN_CAMINO,
         EstadoVehiculo.RESERVADO, 5),
        ("completar", EstadoTarea.ASIGNADA, EstadoCuidador.EJECUTANDO,
         EstadoVehiculo.EN_USO, 5),
        ("completar", EstadoTarea.EN_CURSO, EstadoCuidador.EN_CAMINO,
         EstadoVehiculo.EN_USO, 5),
        ("completar", EstadoTarea.EN_CURSO, EstadoCuidador.EJECUTANDO,
         EstadoVehiculo.EN_RUTA, 5),
        ("fallar", EstadoTarea.ASIGNADA, EstadoCuidador.EJECUTANDO,
         EstadoVehiculo.EN_USO, 5),
        ("fallar", EstadoTarea.EN_CURSO, EstadoCuidador.EN_CAMINO,
         EstadoVehiculo.EN_USO, 5),
        ("fallar", EstadoTarea.EN_CURSO, EstadoCuidador.EJECUTANDO,
         EstadoVehiculo.EN_RUTA, 5),
    ],
)
def test_precondiciones_del_ciclo_rechazan_sin_mutar_ni_consumir_ids(
    operacion, estado_tarea, estado_cuidador, estado_vehiculo, tiempo,
):
    mundo = _mundo_ciclo(
        estado_tarea=estado_tarea,
        estado_cuidador=estado_cuidador,
        estado_vehiculo=estado_vehiculo,
        plan_registrado=True,
    )
    plan = mundo.planes["t1"]
    eventos = RegistroEventos()
    reservas = RegistroReservas()
    for reserva in paquete_de_reservas(plan):
        reservas.agregar_reserva(reserva)
    mundo_antes = copy.deepcopy(mundo)
    eventos_antes = eventos.instantanea()
    reservas_antes = reservas.instantanea()
    funciones = {
        "iniciar": iniciar_ejecucion,
        "llegar": llegar_a_destino,
        "completar": completar_plan,
        "fallar": fallar_plan,
    }

    with pytest.raises(ErrorDominio):
        funciones[operacion](
            mundo, eventos, reservas, "t1", tiempo, "precondición inválida",
        )

    assert mundo == mundo_antes
    assert eventos.instantanea() == eventos_antes
    assert reservas.instantanea() == reservas_antes


@pytest.mark.parametrize(
    ("operacion", "paso"),
    [
        ("iniciar", "iniciar"),
        ("llegar", "llegar"),
        ("completar", "completar"),
        ("fallar", "fallar"),
    ],
)
def test_cada_operacion_rechaza_tiempo_que_retrocede(
    operacion, paso,
):
    mundo, eventos, reservas = _preparar_estado(paso)
    mundo_antes = copy.deepcopy(mundo)
    eventos_antes = eventos.instantanea()
    reservas_antes = reservas.instantanea()
    funciones = {
        "iniciar": iniciar_ejecucion,
        "llegar": llegar_a_destino,
        "completar": completar_plan,
        "fallar": fallar_plan,
    }

    with pytest.raises(ErrorDominio, match="retrocede"):
        funciones[operacion](
            mundo, eventos, reservas, "t1", mundo.tiempo_actual - 1,
            "reloj retrocede",
        )

    assert mundo == mundo_antes
    assert eventos.instantanea() == eventos_antes
    assert reservas.instantanea() == reservas_antes


def test_invariante_13_detecta_ubicaciones_distintas_del_destino(
):
    mundo = _mundo_ciclo(
        estado_tarea=EstadoTarea.EN_CURSO,
        estado_cuidador=EstadoCuidador.EJECUTANDO,
        estado_vehiculo=EstadoVehiculo.EN_USO,
        plan_registrado=True,
    )

    reservas = RegistroReservas()
    for reserva in paquete_de_reservas(mundo.planes["t1"]):
        reservas.agregar_reserva(reserva)
    violaciones, _ = verificar_invariantes(mundo, reservas)

    ubicaciones = [
        violacion for violacion in violaciones
        if violacion.invariante == "INV-13-ubicacion-destino"
    ]
    assert len(ubicaciones) == 4


def test_invariante_13_no_valida_ubicacion_durante_el_transito():
    mundo = _mundo_ciclo(
        estado_tarea=EstadoTarea.EN_CURSO,
        estado_cuidador=EstadoCuidador.EN_CAMINO,
        estado_vehiculo=EstadoVehiculo.EN_RUTA,
        plan_registrado=True,
    )
    reservas = RegistroReservas()
    for reserva in paquete_de_reservas(mundo.planes["t1"]):
        reservas.agregar_reserva(reserva)

    violaciones, _ = verificar_invariantes(mundo, reservas)

    assert not any(
        violacion.invariante == "INV-13-ubicacion-destino"
        for violacion in violaciones
    )


@given(acciones=st.lists(
    st.sampled_from(("asignar", "desasignar", "iniciar", "llegar", "completar", "fallar")),
    min_size=1,
    max_size=25,
))
@settings(max_examples=40, deadline=None)
def test_secuencias_aleatorias_del_ciclo_preservan_invariantes_y_reconstruccion(
    acciones,
):
    inicial = _mundo_ciclo()
    mundo = copy.deepcopy(inicial)
    eventos = RegistroEventos()
    reservas = RegistroReservas()

    for accion in acciones:
        tiempo = mundo.tiempo_actual + 1
        try:
            if accion == "asignar":
                plan = _plan(desde=tiempo, hasta=tiempo + 100)
                asignar_plan(mundo, eventos, reservas, plan, tiempo, accion)
            elif accion == "desasignar":
                desasignar_plan(mundo, eventos, reservas, "t1", tiempo, accion)
            elif accion == "iniciar":
                iniciar_ejecucion(mundo, eventos, reservas, "t1", tiempo, accion)
            elif accion == "llegar":
                llegar_a_destino(mundo, eventos, reservas, "t1", tiempo, accion)
            elif accion == "completar":
                completar_plan(mundo, eventos, reservas, "t1", tiempo, accion)
            else:
                fallar_plan(mundo, eventos, reservas, "t1", tiempo, accion)
        except ErrorDominio:
            pass

        _assert_sin_violaciones(mundo, reservas)
        reconstruido = reconstruir_estado(eventos.obtener_todos(), inicial)
        assert verificar_reconstruccion(mundo, reconstruido) == []
