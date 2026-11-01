"""Pruebas de propuestas pendientes y aplicación con confirmación."""

import copy

import pytest

from zoo_ops.asignacion.confirmacion import (
    aplicar_pendientes, generar_pendientes,
)
from zoo_ops.asignacion.planificacion import planificar
from zoo_ops.dominio.entidades import Tarea
from zoo_ops.dominio.enums import EstadoTarea, PrioridadTarea
from zoo_ops.dominio.errores import ErrorDominio
from zoo_ops.dominio.eventos import RegistroEventos
from zoo_ops.dominio.invariantes import verificar_invariantes
from zoo_ops.dominio.operaciones import (
    asignar_plan, completar_plan, iniciar_ejecucion, llegar_a_destino,
)
from zoo_ops.dominio.plan import PlanEjecucion
from zoo_ops.dominio.reservas import RegistroReservas
from tests.asignacion.test_planificacion import _mundo_simple, _tarea


def _pendientes(mundo, ahora=0, vigencia=120):
    resultado = planificar(mundo, RegistroReservas(), ahora)
    return generar_pendientes(
        resultado,
        ahora,
        vigencia_segundos=vigencia,
    )


def test_rutina_se_aplica_sin_confirmacion():
    mundo = _mundo_simple((_tarea("rutina"),), cuidadores=("c1",))
    reservas = RegistroReservas()
    eventos = RegistroEventos()
    pendientes = _pendientes(mundo)

    informe = aplicar_pendientes(
        mundo, eventos, reservas, pendientes, 0, "confirmar lote",
    )

    assert informe.resultados[0].estado == "aplicada"
    assert mundo.tareas["rutina"].estado == EstadoTarea.ASIGNADA
    assert informe.resultados[0].estimacion is not None


def test_emergencia_requiere_confirmacion_y_no_toca_registros_si_falta():
    mundo = _mundo_simple(
        (_tarea("emergencia", incidente_origen="inc1"),),
        cuidadores=("c1",),
    )
    eventos = RegistroEventos()
    reservas = RegistroReservas()
    pendientes = _pendientes(mundo)
    mundo_antes = copy.deepcopy(mundo)
    eventos_antes = eventos.instantanea()
    reservas_antes = reservas.instantanea()

    informe = aplicar_pendientes(
        mundo, eventos, reservas, pendientes, 0, "sin confirmación",
    )

    assert informe.resultados[0].estado == "pendiente_de_confirmacion"
    assert mundo == mundo_antes
    assert eventos.instantanea() == eventos_antes
    assert reservas.instantanea() == reservas_antes


def test_emergencia_confirmada_se_aplica_y_por_estado_filtra():
    mundo = _mundo_simple(
        (_tarea("emergencia", incidente_origen="inc1"),),
        cuidadores=("c1",),
    )
    eventos = RegistroEventos()
    reservas = RegistroReservas()
    pendientes = _pendientes(mundo)
    confirmaciones = {pendientes[0].id: None}

    informe = aplicar_pendientes(
        mundo,
        eventos,
        reservas,
        pendientes,
        0,
        "confirmación",
        confirmaciones,
    )

    assert informe.resultados[0].estado == "aplicada"
    assert informe.por_estado("aplicada") == informe.resultados


def test_indice_confirmado_aplica_una_alternativa_distinta():
    mundo = _mundo_simple((_tarea("rutina"),), cuidadores=("c1", "c2", "c3"))
    eventos = RegistroEventos()
    reservas = RegistroReservas()
    pendiente = _pendientes(mundo)[0]
    assert len(pendiente.alternativas) > 1
    alternativa = pendiente.alternativas[1]

    informe = aplicar_pendientes(
        mundo,
        eventos,
        reservas,
        (pendiente,),
        0,
        "elegir alternativa",
        {pendiente.id: 1},
    )

    assert informe.resultados[0].estado == "aplicada"
    assert mundo.tareas["rutina"].cuidadores_asignados == (
        alternativa.candidato.plan.cuidadores
    )


def test_propuesta_vencida_no_se_aplica():
    mundo = _mundo_simple((_tarea("rutina"),), cuidadores=("c1",))
    eventos = RegistroEventos()
    reservas = RegistroReservas()
    pendiente = _pendientes(mundo, vigencia=10)[0]
    mundo_antes = copy.deepcopy(mundo)

    informe = aplicar_pendientes(
        mundo, eventos, reservas, (pendiente,), 11, "expirada",
    )

    assert informe.resultados[0].estado == "vencida"
    assert mundo == mundo_antes
    assert not eventos.obtener_todos()
    assert reservas.instantanea() == {}


def test_reprogramacion_mueve_plan_al_tiempo_de_aplicacion():
    mundo = _mundo_simple((_tarea("rutina"),), cuidadores=("c1",))
    eventos = RegistroEventos()
    reservas = RegistroReservas()
    pendiente = _pendientes(mundo, vigencia=20)[0]
    mundo.tiempo_actual = 5

    informe = aplicar_pendientes(
        mundo, eventos, reservas, (pendiente,), 5, "reprogramar",
    )

    assert informe.resultados[0].estado == "aplicada"
    assert informe.resultados[0].estimacion.desde == 5
    assert mundo.planes["rutina"].desde == 5


def test_indices_invalidos_y_tiempo_retrocedido():
    mundo = _mundo_simple((_tarea("rutina"),), cuidadores=("c1",))
    pendiente = _pendientes(mundo)[0]
    eventos = RegistroEventos()
    reservas = RegistroReservas()

    informe = aplicar_pendientes(
        mundo,
        eventos,
        reservas,
        (pendiente,),
        0,
        "índice inválido",
        {pendiente.id: 99},
    )

    assert informe.resultados[0].estado == "rechazada"
    assert informe.resultados[0].errores
    with pytest.raises(ErrorDominio, match="retroceder"):
        aplicar_pendientes(
            mundo, eventos, reservas, (pendiente,), -1, "tiempo inválido",
        )


def test_confirmaciones_se_aplican_en_orden_determinista_en_copias():
    origen = _mundo_simple((
        _tarea("a", prioridad=PrioridadTarea.ALTA),
        _tarea("b", prioridad=PrioridadTarea.MEDIA),
    ))
    pendientes = _pendientes(origen)
    primera = copy.deepcopy(origen)
    segunda = copy.deepcopy(origen)

    informe_a = aplicar_pendientes(
        primera, RegistroEventos(), RegistroReservas(), pendientes, 0, "lote",
    )
    informe_b = aplicar_pendientes(
        segunda, RegistroEventos(), RegistroReservas(), pendientes, 0, "lote",
    )

    assert tuple(
        resultado.propuesta_id for resultado in informe_a.resultados
    ) == tuple(sorted(
        resultado.propuesta_id for resultado in informe_a.resultados
    ))
    assert informe_a == informe_b
    assert primera == segunda


def test_fallo_al_anexar_evento_es_atomico_y_se_continua(monkeypatch):
    mundo = _mundo_simple((
        _tarea("a", prioridad=PrioridadTarea.ALTA),
        _tarea("b", prioridad=PrioridadTarea.MEDIA),
    ))
    pendientes = _pendientes(mundo)
    eventos = RegistroEventos()
    reservas = RegistroReservas()
    anexar_original = eventos.anexar

    def anexar_con_fallo(evento):
        if evento.entidad_id == "a":
            raise ErrorDominio("fallo de anexión")
        return anexar_original(evento)

    monkeypatch.setattr(eventos, "anexar", anexar_con_fallo)

    informe = aplicar_pendientes(
        mundo,
        eventos,
        reservas,
        pendientes,
        0,
        "lote con fallo",
        {pendiente.id: None for pendiente in pendientes},
    )

    por_tarea = {resultado.tarea_id: resultado for resultado in informe.resultados}
    assert por_tarea["a"].estado == "rechazada"
    assert "fallo de anexión" in por_tarea["a"].errores
    assert por_tarea["b"].estado == "aplicada"
    assert mundo.tareas["a"].estado == EstadoTarea.PENDIENTE
    assert "a" not in mundo.planes
    assert not any(evento.entidad_id == "a" for evento in eventos)
    assert not any(
        reserva.tarea_id == "a"
        for reserva in reservas.todas_las_reservas()
    )
    assert eventos.obtener_todos()[0].id == 1
    assert mundo.tareas["b"].estado == EstadoTarea.ASIGNADA
    assert verificar_invariantes(mundo, reservas)[0] == []


def test_cambio_de_mundo_rechaza_recurso_consumido_y_aplica_independiente():
    mundo = _mundo_simple((
        _tarea("a", prioridad=PrioridadTarea.ALTA),
        _tarea("b", prioridad=PrioridadTarea.MEDIA),
    ))
    propuestas = _pendientes(mundo)
    propuesta_a = next(
        pendiente for pendiente in propuestas if pendiente.tarea_id == "a"
    )
    cuidador_a = propuesta_a.alternativas[
        propuesta_a.indice_propuesto
    ].candidato.plan.cuidadores[0]
    mundo.tareas["externa"] = Tarea(
        "externa",
        "externa",
        nodo_destino="destino",
        duracion_estimada=20,
    )
    reservas = RegistroReservas()
    eventos = RegistroEventos()
    asignar_plan(
        mundo,
        eventos,
        reservas,
        PlanEjecucion(
            tarea_id="externa",
            cuidadores=(cuidador_a,),
            desde=0,
            hasta=20,
        ),
        0,
        "consumir recurso",
    )

    informe = aplicar_pendientes(
        mundo,
        eventos,
        reservas,
        propuestas,
        0,
        "aplicar propuestas",
        {pendiente.id: None for pendiente in propuestas},
    )

    por_tarea = {resultado.tarea_id: resultado for resultado in informe.resultados}
    assert por_tarea["a"].estado == "rechazada"
    assert por_tarea["b"].estado == "aplicada"
    assert verificar_invariantes(mundo, reservas)[0] == []


def test_plan_no_estimable_se_rechaza_con_motivo_y_continua():
    mundo = _mundo_simple((
        _tarea("a", prioridad=PrioridadTarea.ALTA),
        _tarea("b", prioridad=PrioridadTarea.MEDIA),
    ))
    pendientes = _pendientes(mundo)
    propuesta_a = next(
        pendiente for pendiente in pendientes if pendiente.tarea_id == "a"
    )
    cuidador_a = propuesta_a.alternativas[
        propuesta_a.indice_propuesto
    ].candidato.plan.cuidadores[0]
    del mundo.cuidadores[cuidador_a]
    eventos = RegistroEventos()
    reservas = RegistroReservas()

    informe = aplicar_pendientes(
        mundo,
        eventos,
        reservas,
        pendientes,
        0,
        "cuidador retirado",
        {pendiente.id: None for pendiente in pendientes},
    )

    por_tarea = {resultado.tarea_id: resultado for resultado in informe.resultados}
    assert por_tarea["a"].estado == "rechazada"
    assert por_tarea["a"].errores == ("no_estimable",)
    assert por_tarea["b"].estado == "aplicada"


def test_integracion_proponer_confirmar_ejecutar_planes():
    mundo = _mundo_simple((
        _tarea("emergencia", incidente_origen="inc1"),
        _tarea("rutina", prioridad=PrioridadTarea.MEDIA),
    ))
    eventos = RegistroEventos()
    reservas = RegistroReservas()
    plan_global = planificar(mundo, reservas, 0)
    pendientes = generar_pendientes(plan_global, 0)
    confirmaciones = {
        pendiente.id: None
        for pendiente in pendientes
        if pendiente.requiere_confirmacion
    }

    informe = aplicar_pendientes(
        mundo,
        eventos,
        reservas,
        pendientes,
        0,
        "confirmación integración",
        confirmaciones,
    )
    aplicadas = informe.por_estado("aplicada")
    assert len(aplicadas) == 2
    assert verificar_invariantes(mundo, reservas)[0] == []

    hitos = []
    for resultado in aplicadas:
        estimacion = resultado.estimacion
        hitos.extend((
            (estimacion.salida, 0, resultado.tarea_id, "iniciar"),
            (estimacion.llegada, 1, resultado.tarea_id, "llegar"),
            (estimacion.fin, 2, resultado.tarea_id, "completar"),
        ))
    for tiempo, _, tarea_id, operacion in sorted(hitos):
        if operacion == "iniciar":
            iniciar_ejecucion(
                mundo, eventos, reservas, tarea_id, tiempo, "salida",
            )
        elif operacion == "llegar":
            llegar_a_destino(
                mundo, eventos, reservas, tarea_id, tiempo, "llegada",
            )
        else:
            completar_plan(
                mundo, eventos, reservas, tarea_id, tiempo, "fin",
            )
        assert verificar_invariantes(mundo, reservas)[0] == []
