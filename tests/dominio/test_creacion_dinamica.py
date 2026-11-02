"""Pruebas de serialización y creación reconstruible de tareas e incidentes."""

import copy

import pytest

from zoo_ops.dominio.catalogos import ESPECIES_CATALOGO
from zoo_ops.dominio.entidades import (
    Animal, EfectoAnimal, HabilidadRequerida, Incidente, MomentoEfecto,
    Mundo, Tarea,
)
from zoo_ops.dominio.enums import (
    Certificacion, EstadoAnimal, EstadoIncidente, EstadoTarea, Habilidad,
    PrioridadTarea, TipoIncidente, TipoEquipo, TipoVehiculo,
)
from zoo_ops.dominio.errores import ErrorDominio
from zoo_ops.dominio.eventos import (
    RegistroEventos, TipoEvento, aplicar_evento, crear_evento,
    incidente_a_datos_extra, incidente_desde_datos_extra,
    reconstruir_estado, tarea_a_datos_extra, tarea_desde_datos_extra,
    verificar_reconstruccion,
)
from zoo_ops.dominio.operaciones import abrir_incidente


def _tarea(id="t1", **cambios):
    datos = {
        "id": id,
        "tipo": "traslado",
        "prioridad_base": PrioridadTarea.ALTA,
        "urgencia": 37,
        "nodo_destino": "n2",
        "duracion_estimada": 90,
        "habilidades_requeridas": (
            HabilidadRequerida(Habilidad.MANEJO_FELINOS, 3),
        ),
        "certificaciones_requeridas": frozenset({Certificacion.TRANQUILIZANTE}),
        "vehiculo_requerido": TipoVehiculo.CAMION_TRASLADO,
        "equipos_requeridos": (TipoEquipo.DARDOS_TRANQUILIZANTES,),
        "ventana_tiempo": (10, 100),
        "dependencias": frozenset(),
        "interrumpible": False,
        "estado": EstadoTarea.PENDIENTE,
        "incidente_origen": "i1",
        "efectos": (
            EfectoAnimal("a1", EstadoAnimal.EN_TRASLADO, MomentoEfecto.AL_INICIAR),
        ),
        "cuidadores_asignados": (),
        "personas_minimas": 3,
    }
    datos.update(cambios)
    return Tarea(**datos)

def _incidente(**cambios):
    datos = {
        "id": "i1",
        "tipo": TipoIncidente.ESCAPE_TERRESTRE,
        "severidad": 8,
        "ubicacion": "n1",
        "estado": EstadoIncidente.ABIERTO,
        "tareas_generadas": frozenset({"t1", "t2"}),
        "animal_relacionado": "a1",
    }
    datos.update(cambios)
    return Incidente(**datos)


def _datos_tarea():
    return tarea_a_datos_extra(_tarea())


def _datos_incidente():
    return incidente_a_datos_extra(_incidente())


def _mundo_inicial():
    return Mundo(animales={
        "a1": Animal(
            id="a1",
            especie=ESPECIES_CATALOGO["jaguar"],
            recinto_origen="r1",
            ubicacion="n1",
            estado=EstadoAnimal.ESCAPADO,
        ),
    })


def _registro_con_fallo_en(k):
    class RegistroConFallo(RegistroEventos):
        def __init__(self):
            super().__init__()
            self.llamadas = 0

        def anexar(self, evento):
            self.llamadas += 1
            if self.llamadas == k:
                raise RuntimeError(f"fallo inyectado {k}")
            super().anexar(evento)

    return RegistroConFallo()


def test_serializacion_de_tarea_es_de_ida_y_vuelta():
    assert tarea_desde_datos_extra(tarea_a_datos_extra(_tarea())) == _tarea()


def test_serializacion_de_incidente_es_de_ida_y_vuelta():
    assert incidente_desde_datos_extra(
        incidente_a_datos_extra(_incidente())
    ) == _incidente()


@pytest.mark.parametrize("campo", [
    "urgencia", "duracion_estimada", "personas_minimas", "interrumpible",
    "cuidadores_asignados", "prioridad_base", "estado",
    "habilidades_requeridas", "certificaciones_requeridas",
    "equipos_requeridos", "dependencias", "id", "tipo", "nodo_destino",
])
def test_deserializacion_de_tarea_rechaza_campo_obligatorio_ausente(campo):
    datos = _datos_tarea()
    del datos[campo]

    with pytest.raises(ErrorDominio):
        tarea_desde_datos_extra(datos)


@pytest.mark.parametrize(("campo", "valor"), [
    ("prioridad_base", "INEXISTENTE"),
    ("estado", "INEXISTENTE"),
    ("vehiculo_requerido", "INEXISTENTE"),
    ("habilidades_requeridas", ({"habilidad": "INEXISTENTE", "nivel_minimo": 1},)),
    ("certificaciones_requeridas", ("INEXISTENTE",)),
    ("equipos_requeridos", ("INEXISTENTE",)),
    ("urgencia", "37"),
    ("interrumpible", "false"),
    ("duracion_estimada", "90"),
    ("cuidadores_asignados", "c1"),
    ("ventana_tiempo", (1,)),
    ("dependencias", "t1"),
    ("efectos", ({"animal_id": "a1", "estado": "DESCONOCIDO", "momento": "AL_INICIAR"},)),
])
def test_deserializacion_de_tarea_rechaza_enums_y_tipos_invalidos(campo, valor):
    datos = _datos_tarea()
    datos[campo] = valor

    with pytest.raises(ErrorDominio):
        tarea_desde_datos_extra(datos)


def test_deserializacion_de_tarea_normaliza_ventana_a_tupla():
    datos = _datos_tarea()
    datos["ventana_tiempo"] = [5, 20]

    assert tarea_desde_datos_extra(datos).ventana_tiempo == (5, 20)


def test_deserializacion_de_tarea_admite_omitir_campos_opcionales():
    datos = _datos_tarea()
    for campo in (
        "ventana_tiempo", "vehiculo_requerido", "incidente_origen", "efectos",
    ):
        del datos[campo]

    tarea = tarea_desde_datos_extra(datos)

    assert tarea.ventana_tiempo is None
    assert tarea.vehiculo_requerido is None
    assert tarea.incidente_origen is None
    assert tarea.efectos == ()


@pytest.mark.parametrize("campo", [
    "id", "tipo", "severidad", "ubicacion", "estado", "tareas_generadas",
])
def test_deserializacion_de_incidente_rechaza_campo_obligatorio_ausente(campo):
    datos = _datos_incidente()
    del datos[campo]

    with pytest.raises(ErrorDominio):
        incidente_desde_datos_extra(datos)


@pytest.mark.parametrize(("campo", "valor"), [
    ("tipo", "INEXISTENTE"),
    ("estado", "INEXISTENTE"),
    ("severidad", "8"),
    ("ubicacion", 4),
    ("tareas_generadas", "t1"),
    ("animal_relacionado", 4),
])
def test_deserializacion_de_incidente_rechaza_enums_y_tipos_invalidos(campo, valor):
    datos = _datos_incidente()
    datos[campo] = valor

    with pytest.raises(ErrorDominio):
        incidente_desde_datos_extra(datos)


def test_deserializacion_de_incidente_admite_omitir_animal_relacionado():
    datos = _datos_incidente()
    del datos["animal_relacionado"]

    assert incidente_desde_datos_extra(datos).animal_relacionado is None


def test_creacion_de_entidad_aplica_solo_estados_iniciales():
    mundo = Mundo()
    evento = crear_evento(
        RegistroEventos(), 10, TipoEvento.CREACION_ENTIDAD, "Tarea", "t1",
        "", "PENDIENTE", "test", datos_extra=tarea_a_datos_extra(_tarea()),
    )

    aplicar_evento(mundo, evento)

    assert mundo.tareas["t1"] == _tarea()


@pytest.mark.parametrize(("entidad_tipo", "entidad_id", "estado", "datos"), [
    ("Tarea", "t1", "ASIGNADA", None),
    ("Incidente", "i1", "CERRADO", None),
])
def test_creacion_rechaza_estado_no_inicial(entidad_tipo, entidad_id, estado, datos):
    if entidad_tipo == "Tarea":
        datos = tarea_a_datos_extra(_tarea())
    else:
        datos = incidente_a_datos_extra(_incidente())
    evento = crear_evento(
        RegistroEventos(), 10, TipoEvento.CREACION_ENTIDAD, entidad_tipo,
        entidad_id, "", estado, "test", datos_extra=datos,
    )

    with pytest.raises(ErrorDominio):
        aplicar_evento(Mundo(), evento)


def test_creacion_rechaza_tarea_inicial_con_cuidadores_asignados():
    datos = tarea_a_datos_extra(_tarea(cuidadores_asignados=("c1",)))
    evento = crear_evento(
        RegistroEventos(), 10, TipoEvento.CREACION_ENTIDAD, "Tarea", "t1",
        "", "PENDIENTE", "test", datos_extra=datos,
    )

    with pytest.raises(ErrorDominio):
        aplicar_evento(Mundo(), evento)


@pytest.mark.parametrize(
    ("entidad_tipo", "entidad_id", "datos"),
    [
        ("Tarea", "t1", lambda: tarea_a_datos_extra(
            _tarea(estado=EstadoTarea.ASIGNADA),
        )),
        ("Incidente", "i1", lambda: incidente_a_datos_extra(
            _incidente(estado=EstadoIncidente.CERRADO),
        )),
    ],
)
def test_creacion_rechaza_estado_no_inicial_en_entidad(
    entidad_tipo, entidad_id, datos,
):
    estado = "PENDIENTE" if entidad_tipo == "Tarea" else "ABIERTO"
    evento = crear_evento(
        RegistroEventos(), 10, TipoEvento.CREACION_ENTIDAD, entidad_tipo,
        entidad_id, "", estado, "test", datos_extra=datos(),
    )

    with pytest.raises(ErrorDominio):
        aplicar_evento(Mundo(), evento)


def test_creacion_rechaza_id_duplicado():
    evento = crear_evento(
        RegistroEventos(), 10, TipoEvento.CREACION_ENTIDAD, "Tarea", "t1",
        "", "PENDIENTE", "test", datos_extra=tarea_a_datos_extra(_tarea()),
    )

    with pytest.raises(ErrorDominio):
        aplicar_evento(Mundo(tareas={"t1": _tarea()}), evento)


def test_creacion_de_otros_tipos_sigue_siendo_noop():
    evento = crear_evento(
        RegistroEventos(), 10, TipoEvento.CREACION_ENTIDAD, "Sensor", "s1",
        "", "", "test",
    )

    assert aplicar_evento(Mundo(), evento).tareas == {}


def test_abrir_incidente_crea_entidades_y_reconstruye_el_mundo():
    inicial = _mundo_inicial()
    mundo = copy.deepcopy(inicial)
    eventos = RegistroEventos()
    incidente = _incidente(tareas_generadas=frozenset())
    tareas = (
        _tarea("t2", dependencias=frozenset({"t1"})),
        _tarea("t1", efectos=()),
    )

    creados = abrir_incidente(mundo, eventos, incidente, tareas, 12, "escape")

    assert [evento.entidad_id for evento in creados] == ["i1", "t1", "t2"]
    assert mundo.incidentes["i1"].tareas_generadas == frozenset({"t1", "t2"})
    assert all(t.estado == EstadoTarea.PENDIENTE for t in mundo.tareas.values())
    assert all(t.incidente_origen == "i1" for t in mundo.tareas.values())
    assert verificar_reconstruccion(
        mundo, reconstruir_estado(eventos.obtener_todos(), inicial)
    ) == []


@pytest.mark.parametrize("caso", [
    "reloj", "incidente_existente", "tarea_existente", "ids_repetidos",
    "incidente_estado", "tarea_estado", "tarea_asignada", "dependencia_ausente",
    "origen_mismatch", "ciclo", "ciclo_con_tarea_existente", "animal_ausente",
])
def test_abrir_incidente_rechaza_validaciones_sin_mutar_ni_consumir_ids(caso):
    mundo = _mundo_inicial()
    eventos = RegistroEventos()
    incidente = _incidente(tareas_generadas=frozenset())
    tareas = (_tarea("t1", efectos=()), _tarea("t2", efectos=()))
    tiempo = 12
    if caso == "reloj":
        mundo.tiempo_actual = 20
    elif caso == "incidente_existente":
        mundo.incidentes["i1"] = incidente
    elif caso == "tarea_existente":
        mundo.tareas["t1"] = _tarea("t1", efectos=())
    elif caso == "ids_repetidos":
        tareas = (_tarea("t1"), _tarea("t1"))
    elif caso == "incidente_estado":
        incidente = _incidente(
            tareas_generadas=frozenset(), estado=EstadoIncidente.CERRADO,
        )
    elif caso == "tarea_estado":
        tareas = (_tarea("t1", estado=EstadoTarea.BLOQUEADA),)
    elif caso == "tarea_asignada":
        tareas = (_tarea("t1", cuidadores_asignados=("c1",)),)
    elif caso == "origen_mismatch":
        tareas = (_tarea("t1", incidente_origen="otro"),)
    elif caso == "dependencia_ausente":
        tareas = (_tarea("t1", dependencias=frozenset({"missing"})),)
    elif caso == "ciclo":
        tareas = (
            _tarea("t1", dependencias=frozenset({"t2"})),
            _tarea("t2", dependencias=frozenset({"t1"})),
        )
    elif caso == "ciclo_con_tarea_existente":
        mundo.tareas["t0"] = _tarea("t0", dependencias=frozenset({"t1"}))
        tareas = (_tarea("t1", dependencias=frozenset({"t0"})),)
    elif caso == "animal_ausente":
        incidente = _incidente(
            tareas_generadas=frozenset(), animal_relacionado="missing",
        )

    mundo_antes = mundo.instantanea()
    eventos_antes = eventos.instantanea()
    with pytest.raises(ErrorDominio):
        abrir_incidente(mundo, eventos, incidente, tareas, tiempo, "test")

    assert mundo == mundo_antes
    assert eventos.instantanea() == eventos_antes


@pytest.mark.parametrize("fallo_en", (1, 2, 3))
def test_abrir_incidente_revierte_si_falla_cualquier_anexo(fallo_en):
    mundo = _mundo_inicial()
    eventos = _registro_con_fallo_en(fallo_en)
    incidente = _incidente(tareas_generadas=frozenset())
    tareas = (_tarea("t1", efectos=()), _tarea("t2", efectos=()))
    mundo_antes = mundo.instantanea()
    eventos_antes = eventos.instantanea()

    with pytest.raises(RuntimeError, match=f"fallo inyectado {fallo_en}"):
        abrir_incidente(mundo, eventos, incidente, tareas, 12, "test")

    assert mundo == mundo_antes
    assert eventos.instantanea() == eventos_antes
