"""Prueba de integración de propuestas con el ciclo de ejecución."""

import copy
from dataclasses import replace

import pytest

from zoo_ops.asignacion.puntaje import Perfil, Pesos
from zoo_ops.asignacion.propuesta import proponer_planes
from zoo_ops.dominio.errores import ErrorDominio
from zoo_ops.dominio.enums import EstadoTarea, TipoVehiculo
from zoo_ops.dominio.eventos import RegistroEventos
from zoo_ops.dominio.invariantes import verificar_invariantes
from zoo_ops.dominio.operaciones import (
    asignar_plan, completar_plan, iniciar_ejecucion, llegar_a_destino,
)
from zoo_ops.dominio.reservas import RegistroReservas
from tests.asignacion.test_candidatos import _mundo


def test_propuesta_ranking_se_puede_ejecutar_en_sus_tiempos_estimados():
    mundo = _mundo()
    reservas = RegistroReservas()
    eventos = RegistroEventos()
    propuesta = proponer_planes(mundo, reservas, "t1", 0)

    assert propuesta.ranking
    puntuado = propuesta.ranking[0]
    asignar_plan(
        mundo, eventos, reservas, puntuado.candidato.plan, 0,
        "confirmación de propuesta",
    )
    assert verificar_invariantes(mundo, reservas)[0] == []

    iniciar_ejecucion(
        mundo, eventos, reservas, "t1",
        puntuado.candidato.estimacion.salida, "salida",
    )
    assert verificar_invariantes(mundo, reservas)[0] == []

    llegar_a_destino(
        mundo, eventos, reservas, "t1",
        puntuado.candidato.estimacion.llegada, "llegada",
    )
    assert verificar_invariantes(mundo, reservas)[0] == []

    completar_plan(
        mundo, eventos, reservas, "t1",
        puntuado.candidato.estimacion.fin, "fin",
    )
    assert verificar_invariantes(mundo, reservas)[0] == []
    assert mundo.tareas["t1"].estado == EstadoTarea.COMPLETADA


def test_propuesta_es_pura_y_admite_perfil_y_pesos_explicitos():
    mundo = _mundo()
    reservas = RegistroReservas()
    mundo_antes = copy.deepcopy(mundo)
    reservas_antes = reservas.instantanea()
    pesos = Pesos(1.0, 0.0, 0.0, 0.0, 0.0)

    propuesta = proponer_planes(
        mundo,
        reservas,
        "t1",
        0,
        perfil=Perfil.RUTINA,
        pesos=pesos,
    )

    assert propuesta.perfil == Perfil.RUTINA
    assert all(item.perfil == Perfil.RUTINA and item.pesos == pesos
               for item in propuesta.ranking)
    assert mundo == mundo_antes
    assert reservas.instantanea() == reservas_antes


def test_propuesta_rechaza_tarea_que_no_existe():
    with pytest.raises(ErrorDominio, match="no existe"):
        proponer_planes(
            _mundo(), RegistroReservas(), "ausente", 0,
        )


def _mundo_sin_tipo_vehiculo(*, incidente_origen=None, tipo="rutina"):
    mundo = _mundo()
    mundo.tareas["t1"] = replace(
        mundo.tareas["t1"],
        tipo=tipo,
        incidente_origen=incidente_origen,
        vehiculo_requerido=None,
        certificaciones_requeridas=frozenset(),
        equipos_requeridos=(),
    )
    return mundo


def test_propuesta_de_rutina_excluye_helicopteros_y_emergencia_los_incluye():
    reservas = RegistroReservas()
    rutina = proponer_planes(
        _mundo_sin_tipo_vehiculo(), reservas, "t1", 0,
    )
    emergencia = proponer_planes(
        _mundo_sin_tipo_vehiculo(incidente_origen="inc1"),
        reservas,
        "t1",
        0,
    )

    assert rutina.perfil == Perfil.RUTINA
    assert all(
        item.candidato.plan.vehiculo_id != "helicoptero"
        for item in rutina.ranking
    )
    assert emergencia.perfil == Perfil.EMERGENCIA
    assert any(
        item.candidato.plan.vehiculo_id == "helicoptero"
        for item in emergencia.ranking
    )


def test_propuesta_conserva_helicoptero_requerido_en_perfil_rutina():
    mundo = _mundo()
    mundo.tareas["t1"] = replace(
        mundo.tareas["t1"],
        tipo="rutina",
        vehiculo_requerido=TipoVehiculo.HELICOPTERO,
    )

    propuesta = proponer_planes(mundo, RegistroReservas(), "t1", 0)

    assert propuesta.perfil == Perfil.RUTINA
    assert propuesta.ranking
    assert all(
        item.candidato.plan.vehiculo_id == "helicoptero"
        for item in propuesta.ranking
    )


def test_propuesta_usa_perfiles_por_tipo_y_escala_explicita():
    mundo = _mundo()
    mundo.tareas["t1"] = replace(mundo.tareas["t1"], tipo="rescate")

    propuesta = proponer_planes(
        mundo,
        RegistroReservas(),
        "t1",
        0,
        perfiles_por_tipo={"rescate": Perfil.MANTENIMIENTO},
        escala_tiempo_segundos=120,
    )

    assert propuesta.perfil == Perfil.MANTENIMIENTO
    assert all(
        item.componentes.tiempo >= 0
        for item in propuesta.ranking
    )


def test_propuesta_permite_sobrescribir_politica_de_helicoptero():
    propuesta = proponer_planes(
        _mundo_sin_tipo_vehiculo(),
        RegistroReservas(),
        "t1",
        0,
        tipos_vehiculo_excluidos=(),
    )

    assert any(
        item.candidato.plan.vehiculo_id == "helicoptero"
        for item in propuesta.ranking
    )
