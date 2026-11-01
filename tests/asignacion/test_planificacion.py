"""Pruebas de planificación global sin mutar el mundo recibido."""

import copy
from dataclasses import replace

import pytest

from zoo_ops.asignacion import planificacion
from zoo_ops.asignacion.candidatos import Candidato
from zoo_ops.asignacion.puntaje import Componentes, Perfil, Pesos, Puntuado
from zoo_ops.asignacion.propuesta import Propuesta
from zoo_ops.asignacion.tiempos import Estimacion
from zoo_ops.dominio.entidades import Arista, Cuidador, Mundo, Nodo, Tarea, Vehiculo
from zoo_ops.dominio.enums import (
    Certificacion, EstadoCuidador, EstadoTarea, EstadoVehiculo,
    MedioPermitido, PrioridadTarea, TipoNodo, TipoVehiculo,
)
from zoo_ops.dominio.errores import ErrorDominio
from zoo_ops.dominio.eventos import RegistroEventos
from zoo_ops.dominio.invariantes import verificar_invariantes
from zoo_ops.dominio.operaciones import (
    asignar_plan, completar_plan, iniciar_ejecucion, llegar_a_destino,
)
from zoo_ops.dominio.reservas import RegistroReservas, paquete_de_reservas
from zoo_ops.dominio.plan import PlanEjecucion


_PESOS = Pesos(0.0, 0.0, 0.0, 0.0, 1.0)
_COMPONENTES = Componentes(1.0, 1.0, 1.0, 1.0, 1.0)


def _mundo_simple(tareas, cuidadores=("c1", "c2")):
    return Mundo(
        nodos={
            "origen": Nodo("origen", TipoNodo.CRUCE, 0, 0),
            "destino": Nodo("destino", TipoNodo.RECINTO, 2, 0),
        },
        aristas={
            ("origen", "destino"): Arista(
                "origen",
                "destino",
                2,
                frozenset({MedioPermitido.PIE, MedioPermitido.JEEP}),
            ),
        },
        cuidadores={
            cuidador_id: Cuidador(
                cuidador_id,
                cuidador_id,
                certificaciones=frozenset({Certificacion.CAMION_TRASLADO}),
                ubicacion=("origen",),
                estado=EstadoCuidador.DISPONIBLE,
            )
            for cuidador_id in cuidadores
        },
        tareas={tarea.id: tarea for tarea in tareas},
    )


def _tarea(
    tarea_id,
    *,
    tipo="rutina",
    prioridad=PrioridadTarea.MEDIA,
    urgencia=0,
    dependencias=frozenset(),
    incidente_origen=None,
    vehiculo_requerido=None,
):
    return Tarea(
        tarea_id,
        tipo,
        prioridad_base=prioridad,
        urgencia=urgencia,
        nodo_destino="destino",
        duracion_estimada=5,
        dependencias=frozenset(dependencias),
        incidente_origen=incidente_origen,
        vehiculo_requerido=vehiculo_requerido,
    )


def _puntuado(tarea_id, cuidadores, puntaje, *, desde=0, hasta=10):
    candidato = Candidato(
        PlanEjecucion(
            tarea_id=tarea_id,
            cuidadores=tuple(cuidadores),
            desde=desde,
            hasta=hasta,
        ),
        Estimacion(
            ruta=(),
            espera_recogida=0,
            viaje=0,
            desde=desde,
            hasta=hasta,
        ),
    )
    return Puntuado(
        candidato,
        Perfil.RUTINA,
        _PESOS,
        _COMPONENTES,
        puntaje,
    )


def _inyectar_rankings(monkeypatch, rankings):
    def proponer(mundo, reservas, tarea_id, ahora, **opciones):
        return Propuesta(
            tarea_id=tarea_id,
            perfil=Perfil.RUTINA,
            ranking=rankings.get(tarea_id, ()),
            descartados=(),
        )

    monkeypatch.setattr(planificacion, "proponer_planes", proponer)


def test_peso_prioridad_crece_con_el_enum():
    tareas = [
        _tarea("baja", prioridad=PrioridadTarea.BAJA),
        _tarea("media", prioridad=PrioridadTarea.MEDIA),
        _tarea("alta", prioridad=PrioridadTarea.ALTA),
        _tarea("critica", prioridad=PrioridadTarea.CRITICA),
    ]

    pesos = [planificacion.peso_prioridad(tarea) for tarea in tareas]

    assert pesos == sorted(pesos)
    assert len(set(pesos)) == len(pesos)


def test_tareas_listas_filtra_dependencias_y_ordena_por_perfil_prioridad_y_id():
    mundo = _mundo_simple((
        _tarea("routine-b", prioridad=PrioridadTarea.ALTA),
        _tarea("routine-a", prioridad=PrioridadTarea.ALTA),
        _tarea(
            "routine-urgent",
            prioridad=PrioridadTarea.ALTA,
            urgencia=2,
        ),
        _tarea("routine-low", prioridad=PrioridadTarea.BAJA),
        _tarea("emergency", incidente_origen="inc1"),
        _tarea("maintenance", tipo="mantenimiento"),
        _tarea("blocked", dependencias=frozenset({"pending"})),
        _tarea("missing", dependencias=frozenset({"absent"})),
        replace(
            _tarea("pending", prioridad=PrioridadTarea.BAJA),
            estado=EstadoTarea.BLOQUEADA,
        ),
        replace(
            _tarea("completed-dependency"),
            estado=EstadoTarea.COMPLETADA,
        ),
        _tarea(
            "after-completed",
            prioridad=PrioridadTarea.BAJA,
            dependencias=frozenset({"completed-dependency"}),
        ),
        _tarea("planned"),
    ))
    mundo.planes["planned"] = PlanEjecucion(
        "planned", ("c1",), 0, 10,
    )

    listas = planificacion.tareas_listas(mundo)

    assert tuple(tarea.id for tarea in listas) == (
        "emergency",
        "routine-urgent",
        "routine-a",
        "routine-b",
        "after-completed",
        "routine-low",
        "maintenance",
    )


def test_tareas_listas_acepta_perfiles_por_tipo():
    mundo = _mundo_simple((
        _tarea("rutina"),
        _tarea("mantenimiento", tipo="mantenimiento"),
    ))

    listas = planificacion.tareas_listas(
        mundo,
        perfiles_por_tipo={"rutina": Perfil.EMERGENCIA},
    )

    assert tuple(tarea.id for tarea in listas) == (
        "rutina",
        "mantenimiento",
    )


def test_planificar_expone_alternativas_truncadas_por_tarea():
    mundo = _mundo_simple((_tarea("t1"),))

    resultado = planificacion.planificar(
        mundo, RegistroReservas(), 0, max_candidatos_por_tarea=2,
    )

    assert tuple(resultado.alternativas_por_tarea) == ("t1",)
    assert len(resultado.alternativas_por_tarea["t1"]) == 2
    with pytest.raises(TypeError):
        resultado.alternativas_por_tarea["t2"] = ()


def test_tareas_pendientes_con_dependencias_incumplidas_se_reportan():
    mundo = _mundo_simple((
        _tarea("prereq", prioridad=PrioridadTarea.BAJA),
        _tarea(
            "waits",
            dependencias=frozenset({"prereq", "missing"}),
        ),
    ))

    resultado = planificacion.planificar(mundo, RegistroReservas(), 0)

    espera = next(
        item for item in resultado.no_asignadas
        if item.tarea_id == "waits"
    )
    assert espera.motivo == "dependencias_pendientes"
    assert espera.detalle == ("missing", "prereq")


def test_planificar_registra_conflicto_inesperado_y_continua(monkeypatch):
    mundo = _mundo_simple((
        _tarea("a", prioridad=PrioridadTarea.ALTA),
        _tarea("b", prioridad=PrioridadTarea.MEDIA),
    ))
    asignar_original = planificacion.asignar_plan

    def asignar_con_fallo(mundo_local, eventos, reservas, plan, tiempo, causa):
        if plan.tarea_id == "a":
            raise ErrorDominio("fallo inyectado")
        return asignar_original(
            mundo_local, eventos, reservas, plan, tiempo, causa,
        )

    monkeypatch.setattr(planificacion, "asignar_plan", asignar_con_fallo)

    resultado = planificacion.planificar(mundo, RegistroReservas(), 0)

    assert tuple(item.tarea_id for item in resultado.asignaciones) == ("b",)
    assert any(
        item.tarea_id == "a"
        and item.motivo == "conflicto_inesperado"
        and item.detalle == ("fallo inyectado",)
        for item in resultado.no_asignadas
    )


def test_planes_conflictivos_solo_si_solapan_intervalos_del_mismo_recurso():
    plan_a = PlanEjecucion("a", ("c1",), 0, 5)
    plan_b = PlanEjecucion("b", ("c1",), 5, 10)
    plan_solapado = PlanEjecucion("c", ("c1",), 4, 8)

    reservas_a = tuple(paquete_de_reservas(plan_a))
    reservas_b = tuple(paquete_de_reservas(plan_b))
    reservas_solapadas = tuple(paquete_de_reservas(plan_solapado))

    assert not planificacion._planes_conflictivos(reservas_a, reservas_b)
    assert planificacion._planes_conflictivos(
        reservas_a, reservas_solapadas,
    )


def test_planificar_rechaza_tiempo_anterior_y_animales_transportados():
    mundo = _mundo_simple((_tarea("t1"),))
    mundo.tiempo_actual = 5

    with pytest.raises(ErrorDominio, match="retroceder"):
        planificacion.planificar(mundo, RegistroReservas(), 4)
    with pytest.raises(ErrorDominio, match="animales_transportados"):
        planificacion.planificar(
            mundo, RegistroReservas(), 5, animales_transportados=(),
        )


def test_exacto_encuentra_dos_asignaciones_y_el_voraz_solo_una(monkeypatch):
    mundo = _mundo_simple((
        _tarea("a", prioridad=PrioridadTarea.ALTA),
        _tarea("b", prioridad=PrioridadTarea.BAJA),
    ))
    rankings = {
        "a": (
            _puntuado("a", ("c1",), 0.9),
            _puntuado("a", ("c2",), 0.8),
        ),
        "b": (_puntuado("b", ("c1",), 1.0),),
    }
    _inyectar_rankings(monkeypatch, rankings)

    exacto = planificacion.planificar(
        mundo, RegistroReservas(), 0, max_nodos=100,
    )
    voraz = planificacion.planificar(
        mundo, RegistroReservas(), 0, max_nodos=1,
    )

    assert len(exacto.asignaciones) == 2
    assert exacto.estrategia_por_nivel[Perfil.RUTINA] == "exacta"
    assert {item.tarea_id: item.puntuado.candidato.plan.cuidadores
            for item in exacto.asignaciones} == {
        "a": ("c2",), "b": ("c1",),
    }
    assert len(voraz.asignaciones) == 1
    assert voraz.estrategia_por_nivel[Perfil.RUTINA] == "voraz"
    assert voraz.asignaciones[0].tarea_id == "a"


def test_tareas_que_compiten_por_recursos_incluyen_motivo_de_compromiso():
    tarea_alta = _tarea(
        "alta", prioridad=PrioridadTarea.ALTA,
        vehiculo_requerido=TipoVehiculo.CAMION_TRASLADO,
    )
    tarea_baja = _tarea(
        "baja", prioridad=PrioridadTarea.BAJA,
        vehiculo_requerido=TipoVehiculo.CAMION_TRASLADO,
    )
    mundo = _mundo_simple((tarea_alta, tarea_baja), cuidadores=("c1",))
    mundo.vehiculos["v1"] = Vehiculo(
        "v1",
        TipoVehiculo.CAMION_TRASLADO,
        2,
        2,
        2,
        Certificacion.CAMION_TRASLADO,
        "origen",
        EstadoVehiculo.DISPONIBLE,
    )

    resultado = planificacion.planificar(mundo, RegistroReservas(), 0)

    assert tuple(item.tarea_id for item in resultado.asignaciones) == ("alta",)
    assert tuple(item.tarea_id for item in resultado.no_asignadas) == ("baja",)
    assert resultado.no_asignadas[0].motivo == "recursos_comprometidos"


def test_emergencia_compromete_recursos_antes_de_rutina():
    emergencia = _tarea(
        "emergencia",
        prioridad=PrioridadTarea.MEDIA,
        incidente_origen="inc1",
        vehiculo_requerido=TipoVehiculo.CAMION_TRASLADO,
    )
    rutina = _tarea(
        "rutina",
        prioridad=PrioridadTarea.CRITICA,
        vehiculo_requerido=TipoVehiculo.CAMION_TRASLADO,
    )
    mundo = _mundo_simple((emergencia, rutina), cuidadores=("c1",))
    mundo.vehiculos["v1"] = Vehiculo(
        "v1",
        TipoVehiculo.CAMION_TRASLADO,
        2,
        2,
        2,
        Certificacion.CAMION_TRASLADO,
        "origen",
        EstadoVehiculo.DISPONIBLE,
    )

    resultado = planificacion.planificar(mundo, RegistroReservas(), 0)

    assert tuple(item.tarea_id for item in resultado.asignaciones) == (
        "emergencia",
    )
    assert tuple(
        (item.tarea_id, item.motivo) for item in resultado.no_asignadas
    ) == (("rutina", "sin_candidatos"),)
    assert resultado.estrategia_por_nivel[Perfil.EMERGENCIA] == "exacta"
    assert resultado.estrategia_por_nivel[Perfil.RUTINA] == "exacta"


def test_tarea_sin_candidatos_se_incluye_con_motivo():
    mundo = _mundo_simple((_tarea("t1"),), cuidadores=())

    resultado = planificacion.planificar(mundo, RegistroReservas(), 0)

    assert not resultado.asignaciones
    assert resultado.no_asignadas[0].motivo == "sin_candidatos"


def test_planificar_es_determinista_y_no_muta_entradas():
    mundo = _mundo_simple((_tarea("t1"),))
    reservas = RegistroReservas()
    mundo_antes = copy.deepcopy(mundo)
    reservas_antes = copy.deepcopy(reservas.instantanea())

    primero = planificacion.planificar(mundo, reservas, 0)
    segundo = planificacion.planificar(mundo, reservas, 0)

    assert primero == segundo
    assert mundo == mundo_antes
    assert reservas.instantanea() == reservas_antes


def test_asignaciones_planificadas_se_pueden_aplicar_y_ejecutar():
    mundo = _mundo_simple((
        _tarea("t1", prioridad=PrioridadTarea.ALTA),
        _tarea("t2", prioridad=PrioridadTarea.MEDIA),
    ))
    reservas = RegistroReservas()
    eventos = RegistroEventos()
    resultado = planificacion.planificar(mundo, reservas, 0)

    assert len(resultado.asignaciones) == 2
    for asignacion in resultado.asignaciones:
        asignar_plan(
            mundo,
            eventos,
            reservas,
            asignacion.puntuado.candidato.plan,
            0,
            "prueba de planificación",
        )
        assert verificar_invariantes(mundo, reservas)[0] == []

    hitos = []
    for asignacion in resultado.asignaciones:
        estimacion = asignacion.puntuado.candidato.estimacion
        hitos.extend((
            (estimacion.salida, "iniciar", asignacion.tarea_id),
            (estimacion.llegada, "llegar", asignacion.tarea_id),
            (estimacion.fin, "completar", asignacion.tarea_id),
        ))
    for tiempo, operacion, tarea_id in sorted(hitos):
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
