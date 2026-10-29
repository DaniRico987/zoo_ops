"""Prueba de integración de propuestas con el ciclo de ejecución."""

import copy

import pytest

from zoo_ops.asignacion.puntaje import Perfil, Pesos
from zoo_ops.asignacion.propuesta import proponer_planes
from zoo_ops.dominio.errores import ErrorDominio
from zoo_ops.dominio.enums import EstadoTarea
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
