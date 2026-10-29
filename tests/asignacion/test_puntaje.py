"""Pruebas de perfiles, componentes y ranking de candidatos."""

import math

import pytest

from zoo_ops.asignacion.candidatos import Candidato
from zoo_ops.asignacion.puntaje import (
    NIVEL_MAXIMO_HABILIDAD, PERFILES, Componentes, Perfil, Pesos, explicar,
    perfil_de_tarea, puntuar_candidatos,
)
from zoo_ops.asignacion.tiempos import Estimacion
from zoo_ops.dominio.entidades import Cuidador, HabilidadRequerida, Mundo, Tarea
from zoo_ops.dominio.enums import (
    Certificacion, EstadoCuidador, EstadoTarea, Habilidad,
)
from zoo_ops.dominio.errores import ErrorDominio
from zoo_ops.dominio.plan import PlanEjecucion


def _tarea(
    *,
    tipo="rescate",
    incidente_origen=None,
    habilidades=(),
):
    return Tarea(
        "t1",
        tipo,
        nodo_destino="destino",
        habilidades_requeridas=tuple(habilidades),
        incidente_origen=incidente_origen,
    )


def _candidato(cuidadores, *, llegada, desde=0, hasta=None):
    hasta = llegada + 10 if hasta is None else hasta
    estimacion = Estimacion(
        ruta=(),
        espera_recogida=0,
        viaje=llegada - desde,
        desde=desde,
        hasta=hasta,
    )
    return Candidato(
        PlanEjecucion(
            tarea_id="t1",
            cuidadores=tuple(cuidadores),
            desde=desde,
            hasta=hasta,
        ),
        estimacion,
    )


def _mundo_puntaje(tarea=None):
    mundo = Mundo(
        nodos={},
        tareas={"t1": tarea or _tarea()},
        cuidadores={
            "c1": Cuidador(
                "c1",
                "Uno",
                habilidades={Habilidad.MANEJO_FELINOS: 4},
                certificaciones=frozenset({Certificacion.TRANQUILIZANTE}),
                ubicacion=("destino",),
                estado=EstadoCuidador.DISPONIBLE,
                fatiga=20,
            ),
            "c2": Cuidador(
                "c2",
                "Dos",
                habilidades={Habilidad.MANEJO_FELINOS: 2},
                ubicacion=("origen",),
                estado=EstadoCuidador.DISPONIBLE,
                fatiga=60,
            ),
            "c3": Cuidador(
                "c3",
                "Tres",
                ubicacion=("origen",),
                estado=EstadoCuidador.DISPONIBLE,
                fatiga=0,
            ),
        },
    )
    return mundo


def _candidatos_para_tiempo():
    return (
        _candidato(("c1", "c2"), llegada=10),
        _candidato(("c1", "c3"), llegada=20),
    )


def test_pesos_de_perfiles_suman_uno_y_pesos_invalidos_se_rechazan():
    with pytest.raises(TypeError):
        PERFILES[Perfil.RUTINA] = Pesos(0.0, 0.0, 0.0, 0.0, 1.0)
    for pesos in PERFILES.values():
        assert math.isclose(
            pesos.tiempo + pesos.habilidad + pesos.carga
            + pesos.fatiga + pesos.continuidad,
            1.0,
            abs_tol=1e-9,
        )

    with pytest.raises(ErrorDominio, match="sumar 1"):
        Pesos(0.5, 0.2, 0.2, 0.2, 0.1)
    with pytest.raises(ErrorDominio, match="negativos"):
        Pesos(-0.1, 0.3, 0.3, 0.3, 0.2)


@pytest.mark.parametrize(
    ("tarea", "perfiles_por_tipo", "esperado"),
    [
        (_tarea(tipo="rescate", incidente_origen="i1"), None, Perfil.EMERGENCIA),
        (_tarea(tipo="mantenimiento"), None, Perfil.MANTENIMIENTO),
        (_tarea(tipo="cuidado"), None, Perfil.RUTINA),
        (
            _tarea(tipo="alimentacion", incidente_origen="i1"),
            {"alimentacion": Perfil.MANTENIMIENTO},
            Perfil.MANTENIMIENTO,
        ),
    ],
)
def test_perfil_de_tarea_usa_mapa_y_deducciones(tarea, perfiles_por_tipo, esperado):
    assert perfil_de_tarea(tarea, perfiles_por_tipo) == esperado


def test_tiempo_es_uno_para_candidato_unico_y_normaliza_dos_candidatos():
    mundo = _mundo_puntaje()
    tarea = mundo.tareas["t1"]
    unico = puntuar_candidatos(
        mundo, "t1", (_candidato(("c1",), llegada=10),), perfil=Perfil.RUTINA,
    )
    dos = puntuar_candidatos(
        mundo, "t1", _candidatos_para_tiempo(), perfil=Perfil.RUTINA,
    )

    assert unico[0].componentes.tiempo == 1.0
    assert [item.componentes.tiempo for item in dos] == [1.0, 0.0]
    assert tarea.estado == EstadoTarea.PENDIENTE


def test_componentes_habilidad_carga_fatiga_y_continuidad_calculados_a_mano():
    tarea = _tarea(
        incidente_origen="inc1",
        habilidades=(HabilidadRequerida(Habilidad.MANEJO_FELINOS, 3),),
    )
    mundo = _mundo_puntaje(tarea)
    mundo.tareas["cierre1"] = Tarea(
        "cierre1", "otra", estado=EstadoTarea.COMPLETADA,
        cuidadores_asignados=("c1",),
    )
    mundo.tareas["cierre2"] = Tarea(
        "cierre2", "otra", estado=EstadoTarea.FALLIDA,
        cuidadores_asignados=("c1",),
    )
    mundo.tareas["cierre3"] = Tarea(
        "cierre3", "otra", estado=EstadoTarea.COMPLETADA,
        cuidadores_asignados=("c2",),
    )

    puntaje = puntuar_candidatos(
        mundo,
        "t1",
        (_candidato(("c1", "c2"), llegada=10),),
        perfil=Perfil.EMERGENCIA,
    )[0]

    assert NIVEL_MAXIMO_HABILIDAD == 5
    assert puntaje.componentes.habilidad == 0.8
    assert puntaje.componentes.carga == 0.25
    assert puntaje.componentes.fatiga == 0.6
    assert puntaje.componentes.continuidad == 0.5


def test_habilidad_de_rutina_y_sin_requisitos():
    tarea = _tarea(
        habilidades=(HabilidadRequerida(Habilidad.MANEJO_FELINOS, 3),),
    )
    mundo = _mundo_puntaje(tarea)
    puntaje = puntuar_candidatos(
        mundo, "t1", (_candidato(("c1", "c2"), llegada=10),),
        perfil=Perfil.RUTINA,
    )[0]
    mundo_sin_requisitos = _mundo_puntaje(_tarea())
    sin_requisitos = puntuar_candidatos(
        mundo_sin_requisitos, "t1", (_candidato(("c1",), llegada=10),),
        perfil=Perfil.RUTINA,
    )[0]

    assert puntaje.componentes.habilidad == 0.75
    assert sin_requisitos.componentes.habilidad == 1.0


def test_emergencia_prefiere_equipo_rapido_aunque_tenga_mas_fatiga():
    mundo = _mundo_puntaje()
    mundo.cuidadores["c1"] = Cuidador(
        "c1", "Cansado", ubicacion=("origen",), fatiga=100,
    )
    mundo.cuidadores["c2"] = Cuidador(
        "c2", "Descansado", ubicacion=("origen",), fatiga=0,
    )
    candidatos = (
        _candidato(("c1",), llegada=10),
        _candidato(("c2",), llegada=20),
    )

    ranking = puntuar_candidatos(
        mundo, "t1", candidatos, perfil=Perfil.EMERGENCIA,
    )

    assert ranking[0].candidato == candidatos[0]
    assert ranking[0].componentes.fatiga == 0


def test_rutina_prefiere_equipo_menos_cargado_y_descansado_aunque_tarde():
    mundo = _mundo_puntaje()
    mundo.cuidadores["c1"] = Cuidador(
        "c1", "Cansado y cargado", ubicacion=("origen",), fatiga=100,
    )
    mundo.cuidadores["c2"] = Cuidador(
        "c2", "Descansado", ubicacion=("origen",), fatiga=0,
    )
    mundo.tareas["carga"] = Tarea(
        "carga", "anterior", estado=EstadoTarea.COMPLETADA,
        cuidadores_asignados=("c1",) * 5,
    )
    candidatos = (
        _candidato(("c1",), llegada=10),
        _candidato(("c2",), llegada=20),
    )

    ranking = puntuar_candidatos(
        mundo, "t1", candidatos, perfil=Perfil.RUTINA,
    )

    assert ranking[0].candidato == candidatos[1]


def test_pesos_explicitos_sustituyen_perfil_y_desempate_es_determinista():
    mundo = _mundo_puntaje()
    mundo.cuidadores["c1"] = Cuidador("c1", "A", ubicacion=("origen",))
    mundo.cuidadores["c2"] = Cuidador("c2", "B", ubicacion=("origen",))
    candidatos = (
        _candidato(("c2",), llegada=10, hasta=15),
        _candidato(("c1",), llegada=10, hasta=15),
    )
    pesos = Pesos(0.0, 0.0, 0.0, 0.0, 1.0)

    primero = puntuar_candidatos(
        mundo, "t1", candidatos, perfil=Perfil.EMERGENCIA, pesos=pesos,
    )
    segundo = puntuar_candidatos(
        mundo, "t1", candidatos, perfil=Perfil.RUTINA, pesos=pesos,
    )

    assert tuple(item.candidato.plan.cuidadores for item in primero) == tuple(
        item.candidato.plan.cuidadores for item in segundo
    ) == (
        ("c1",), ("c2",),
    )
    assert all(
        item.pesos == pesos and item.puntaje == 0.0
        for item in primero + segundo
    )


def test_explicar_muestra_contribuciones_que_suman_el_puntaje():
    mundo = _mundo_puntaje()
    puntaje = puntuar_candidatos(
        mundo, "t1", _candidatos_para_tiempo(), perfil=Perfil.RUTINA,
    )[0]
    explicacion = explicar(puntaje)
    lineas_componentes = [
        linea for linea in explicacion.splitlines()
        if linea.split(":", 1)[0] in {
            "tiempo", "habilidad", "carga", "fatiga", "continuidad",
        }
    ]
    contribuciones = [float(linea.rsplit("=", 1)[1]) for linea in lineas_componentes]

    assert len(contribuciones) == 5
    assert abs(sum(contribuciones) - puntaje.puntaje) <= 1e-9


def test_puntuar_es_puro_ordenado_y_tarea_debe_ser_pendiente():
    mundo = _mundo_puntaje()
    mundo_antes = mundo.instantanea()
    candidatos = _candidatos_para_tiempo()
    ranking = puntuar_candidatos(mundo, "t1", candidatos)

    assert len(ranking) == len(candidatos)
    assert mundo == mundo_antes
    assert puntuar_candidatos(mundo, "t1", ()) == ()

    mundo.tareas["t1"] = Tarea("t1", "ocupada", estado=EstadoTarea.ASIGNADA)
    with pytest.raises(ErrorDominio, match="PENDIENTE"):
        puntuar_candidatos(mundo, "t1", candidatos)


def test_componentes_sin_habilidades_requeridas_valen_uno():
    mundo = _mundo_puntaje(_tarea())
    puntuado = puntuar_candidatos(
        mundo, "t1", (_candidato(("c1",), llegada=5),),
    )[0]

    assert puntuado.componentes.habilidad == 1.0
