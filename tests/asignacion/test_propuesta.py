"""Prueba de integración de propuestas con el ciclo de ejecución."""

import copy
from dataclasses import replace

import pytest

from zoo_ops.asignacion.puntaje import Perfil, Pesos
from zoo_ops.asignacion.propuesta import proponer_planes
from zoo_ops.dominio.catalogos import ESPECIES_CATALOGO
from zoo_ops.dominio.entidades import Animal, EfectoAnimal, MomentoEfecto
from zoo_ops.dominio.errores import ErrorDominio
from zoo_ops.dominio.enums import (
    EstadoAnimal, EstadoTarea, EstadoVehiculo, TipoVehiculo,
)
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


def _mundo_con_efecto_de_traslado():
    mundo = _mundo()
    mundo.animales["a1"] = Animal(
        "a1", ESPECIES_CATALOGO["jaguar"], "recinto", "destino",
        estado=EstadoAnimal.TRANQUILIZADO,
    )
    mundo.tareas["t1"] = replace(
        mundo.tareas["t1"],
        efectos=(EfectoAnimal(
            "a1", EstadoAnimal.EN_TRASLADO, MomentoEfecto.AL_INICIAR,
        ),),
    )
    return mundo


def test_efecto_de_traslado_deriva_animal_y_exige_vehiculo():
    mundo = _mundo_con_efecto_de_traslado()

    propuesta = proponer_planes(mundo, RegistroReservas(), "t1", 0)

    assert propuesta.ranking
    assert all(
        puntuado.candidato.plan.vehiculo_id is not None
        and puntuado.candidato.plan.animales_transportados == ("a1",)
        for puntuado in propuesta.ranking
    )


def test_efecto_de_traslado_sin_vehiculo_requerido_disponible():
    mundo = _mundo_con_efecto_de_traslado()
    mundo.vehiculos["camion"] = replace(
        mundo.vehiculos["camion"], estado=EstadoVehiculo.RESERVADO,
    )

    propuesta = proponer_planes(mundo, RegistroReservas(), "t1", 0)

    assert not propuesta.ranking
    assert any(
        descartado.motivo == "sin_vehiculo"
        for descartado in propuesta.descartados
    )


def test_tarea_sin_efectos_de_traslado_no_incluye_animales():
    propuesta = proponer_planes(
        _mundo_sin_tipo_vehiculo(), RegistroReservas(), "t1", 0,
    )

    assert propuesta.ranking
    assert all(
        puntuado.candidato.plan.animales_transportados == ()
        for puntuado in propuesta.ranking
    )


def test_animales_explicitos_y_derivados_se_unen_sin_duplicados_y_ordenados():
    mundo = _mundo_con_efecto_de_traslado()
    mundo.animales["a2"] = Animal(
        "a2", ESPECIES_CATALOGO["jaguar"], "recinto", "destino",
        estado=EstadoAnimal.TRANQUILIZADO,
    )

    propuesta = proponer_planes(
        mundo, RegistroReservas(), "t1", 0,
        animales_transportados=("a2", "a1"),
    )

    assert propuesta.ranking
    assert all(
        puntuado.candidato.plan.animales_transportados == ("a1", "a2")
        for puntuado in propuesta.ranking
    )


def test_capacidad_insuficiente_para_animales_descarta_con_motivo_capacidad():
    mundo = _mundo_con_efecto_de_traslado()
    mundo.vehiculos["camion"] = replace(
        mundo.vehiculos["camion"], capacidad_animales=0,
    )

    propuesta = proponer_planes(mundo, RegistroReservas(), "t1", 0)

    assert not propuesta.ranking
    assert any(
        descartado.motivo == "capacidad"
        and "animales" in " ".join(descartado.detalle)
        for descartado in propuesta.descartados
    )
