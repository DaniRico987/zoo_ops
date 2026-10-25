"""
Pruebas basadas en propiedades con Hypothesis.

El mundo "vivo" evoluciona SOLO mediante `ejecutar_transicion`; la reconstrucción
parte de una copia profunda del mundo INICIAL. No se usa `replace` para cambiar
estados ni se anexan eventos a mano después de una transición.
"""

import ast
import copy
import os

import pytest
from hypothesis import given, settings, strategies as st
from hypothesis.stateful import (
    RuleBasedStateMachine, initialize, invariant, precondition, rule,
)

from zoo_ops.dominio.catalogos import ESPECIES_CATALOGO
from zoo_ops.dominio.entidades import (
    Animal, Cuidador, Mundo, Recinto, Tarea, Vehiculo,
)
from zoo_ops.dominio.enums import (
    Certificacion, EstadoAnimal, EstadoCuidador, EstadoTarea, EstadoVehiculo,
    PrioridadTarea, TipoRecinto, TipoVehiculo,
)
from zoo_ops.dominio.errores import (
    DependenciaInexistente, ErrorDominio, EventoNoSoportado, ReservaAtomicaFallida,
    TransicionInvalida,
)
from zoo_ops.dominio.estados import (
    TRANSICIONES_ANIMAL, TRANSICIONES_CUIDADOR, TRANSICIONES_TAREA,
    TRANSICIONES_VEHICULO, ejecutar_transicion,
)
from zoo_ops.dominio.eventos import (
    Evento, RegistroEventos, TipoEvento, reconstruir_estado,
    verificar_reconstruccion,
)
from zoo_ops.dominio.invariantes import verificar_invariantes
from zoo_ops.dominio.reservas import (
    RegistroReservas, Reserva, TipoRecurso, reservar_atomico,
)


settings.register_profile("zoo_ops", max_examples=100, deadline=None)
settings.load_profile("zoo_ops")


# ============================================================================
# Estrategias
# ============================================================================

@st.composite
def cuidador_strategy(draw):
    return Cuidador(
        id="c1",
        nombre="Cuidador",
        estado=draw(st.sampled_from(list(EstadoCuidador))),
    )


@st.composite
def vehiculo_strategy(draw):
    return Vehiculo(
        id="v1",
        tipo=TipoVehiculo.JEEP,
        velocidad=10.0,
        capacidad_personas=4,
        capacidad_animales=2,
        certificacion_requerida=Certificacion.JEEP,
        ubicacion="garaje",
        estado=draw(st.sampled_from(list(EstadoVehiculo))),
    )


@st.composite
def tarea_strategy(draw):
    return Tarea(
        id="t1",
        tipo="test",
        prioridad_base=draw(st.sampled_from(list(PrioridadTarea))),
        urgencia=draw(st.integers(0, 100)),
        estado=draw(st.sampled_from(list(EstadoTarea))),
    )


@st.composite
def animal_strategy(draw):
    clave = draw(st.sampled_from(sorted(ESPECIES_CATALOGO)))
    return Animal(
        id="a1",
        especie=ESPECIES_CATALOGO[clave],
        recinto_origen="rec1",
        ubicacion="rec1",
        estado=draw(st.sampled_from(list(EstadoAnimal))),
    ), clave


def _elegir_destino(destinos, paso):
    """Elige un destino de forma determinista y variada."""
    opciones = sorted(destinos, key=lambda estado: estado.name)
    return opciones[paso % len(opciones)]


# ============================================================================
# Transiciones válidas
# ============================================================================

@given(data=st.data())
def test_transiciones_cuidador_validas_nunca_fallan(data):
    c = data.draw(cuidador_strategy())
    mundo = Mundo(cuidadores={"c1": c})
    registro = RegistroEventos()

    destinos = TRANSICIONES_CUIDADOR.get(c.estado, frozenset())
    if not destinos:
        return

    nuevo = data.draw(st.sampled_from(sorted(destinos, key=lambda e: e.name)))
    evento = ejecutar_transicion(
        mundo, registro, "Cuidador", "c1", nuevo, 10, "test",
    )

    assert evento.estado_antes == c.estado.name
    assert evento.estado_despues == nuevo.name
    assert mundo.cuidadores["c1"].estado == nuevo
    assert len(registro) == 1


@given(data=st.data())
def test_transiciones_vehiculo_validas_nunca_fallan(data):
    v = data.draw(vehiculo_strategy())
    mundo = Mundo(vehiculos={"v1": v})
    registro = RegistroEventos()

    destinos = TRANSICIONES_VEHICULO.get(v.estado, frozenset())
    if not destinos:
        return

    nuevo = data.draw(st.sampled_from(sorted(destinos, key=lambda e: e.name)))
    ejecutar_transicion(mundo, registro, "Vehiculo", "v1", nuevo, 10, "test")

    assert mundo.vehiculos["v1"].estado == nuevo


@given(data=st.data())
def test_transiciones_tarea_validas_nunca_fallan(data):
    t = data.draw(tarea_strategy())
    c1 = Cuidador(id="c1", nombre="C", estado=EstadoCuidador.DISPONIBLE)
    mundo = Mundo(cuidadores={"c1": c1}, tareas={"t1": t})
    registro = RegistroEventos()

    destinos = TRANSICIONES_TAREA.get(t.estado, frozenset())
    if not destinos:
        return

    nuevo = data.draw(st.sampled_from(sorted(destinos, key=lambda e: e.name)))
    parametros = {"cuidador_id": "c1"} if nuevo == EstadoTarea.ASIGNADA else {}

    ejecutar_transicion(
        mundo, registro, "Tarea", "t1", nuevo, 10, "test", **parametros,
    )

    assert mundo.tareas["t1"].estado == nuevo


@given(data=st.data())
def test_transiciones_animal_validas_nunca_fallan(data):
    animal, clave = data.draw(animal_strategy())
    recinto = Recinto(
        nodo_id="rec1",
        tipo=TipoRecinto.ABIERTO,
        especies_admitidas=frozenset({clave}),
        capacidad=5,
    )
    mundo = Mundo(animales={"a1": animal}, recintos={"rec1": recinto})
    registro = RegistroEventos()

    destinos = TRANSICIONES_ANIMAL.get(animal.estado, frozenset())
    if not destinos:
        return

    nuevo = data.draw(st.sampled_from(sorted(destinos, key=lambda e: e.name)))
    try:
        ejecutar_transicion(
            mundo, registro, "Animal", "a1", nuevo, 10, "test",
            recinto_destino="rec1",
        )
    except TransicionInvalida as exc:
        assert (
            "acuático" in str(exc).lower()
            or "tranquilizante" in str(exc).lower()
        )
        assert mundo.animales["a1"].estado == animal.estado
        return

    assert mundo.animales["a1"].estado == nuevo


@given(data=st.data())
def test_transiciones_invalidas_lanzan_excepcion(data):
    c = Cuidador(id="c1", nombre="C", estado=EstadoCuidador.DISPONIBLE)
    invalidos = [
        e for e in EstadoCuidador
        if e not in TRANSICIONES_CUIDADOR[EstadoCuidador.DISPONIBLE]
    ]
    nuevo = data.draw(st.sampled_from(invalidos))

    with pytest.raises(TransicionInvalida):
        ejecutar_transicion(
            Mundo(cuidadores={"c1": c}), RegistroEventos(),
            "Cuidador", "c1", nuevo, 0, "test",
        )


# ============================================================================
# Reservas atómicas
# ============================================================================

def test_reservas_atomicas_todo_o_nada():
    registro = RegistroReservas()
    for reserva in [
        Reserva(TipoRecurso.CUIDADOR, "c1", "t0", 100, 200),
        Reserva(TipoRecurso.VEHICULO, "v1", "t0", 100, 200),
    ]:
        registro.agregar_reserva(reserva)

    with pytest.raises(ReservaAtomicaFallida):
        reservar_atomico(registro, [
            Reserva(TipoRecurso.CUIDADOR, "c1", "t1", 150, 250),
            Reserva(TipoRecurso.EQUIPO, "e1", "t1", 100, 200),
        ])

    assert registro.verificar_disponibilidad(TipoRecurso.CUIDADOR, "c1", 150, 250) is False
    assert registro.verificar_disponibilidad(TipoRecurso.EQUIPO, "e1", 100, 200) is True
    assert registro.verificar_disponibilidad(TipoRecurso.VEHICULO, "v1", 100, 200) is False


def test_orden_determinista_siempre_igual():
    from zoo_ops.dominio.reservas import _orden_determinista_recursos

    reservas = [
        Reserva(TipoRecurso.VEHICULO, "v2", "t1", 100, 200),
        Reserva(TipoRecurso.CUIDADOR, "c1", "t1", 100, 200),
        Reserva(TipoRecurso.EQUIPO, "e1", "t1", 100, 200),
        Reserva(TipoRecurso.CUIDADOR, "c0", "t1", 100, 200),
    ]

    ids1 = [(r.recurso_tipo, r.recurso_id, r.desde) for r in _orden_determinista_recursos(reservas)]
    ids2 = [(r.recurso_tipo, r.recurso_id, r.desde) for r in _orden_determinista_recursos(list(reversed(reservas)))]
    ids3 = [(r.recurso_tipo, r.recurso_id, r.desde) for r in _orden_determinista_recursos(reservas[:])]

    assert ids1 == ids2 == ids3


# ============================================================================
# Máquina de estados: reconstrucción honesta
# ============================================================================

class ReconstruccionHonestaMachine(RuleBasedStateMachine):
    """
    El mundo vivo evoluciona SOLO con `ejecutar_transicion`.
    La reconstrucción parte de una copia profunda del mundo inicial.
    """

    def __init__(self):
        super().__init__()
        self.mundo_vivo = Mundo()
        self.registro = RegistroEventos()
        self.registro_reservas = RegistroReservas()
        self.tiempo = 0
        self.paso = 0
        self._mundo_inicial = Mundo()

    @initialize()
    def setup(self):
        self.mundo_vivo = Mundo(
            cuidadores={"c1": Cuidador(
                id="c1", nombre="C", estado=EstadoCuidador.FUERA_DE_TURNO,
            )},
            animales={"a1": Animal(
                id="a1",
                especie=ESPECIES_CATALOGO["mono_aullador"],
                recinto_origen="rec1",
                ubicacion="rec1",
                estado=EstadoAnimal.EN_RECINTO,
            )},
            recintos={"rec1": Recinto(
                nodo_id="rec1",
                tipo=TipoRecinto.ABIERTO,
                especies_admitidas=frozenset({"mono_aullador"}),
                capacidad=2,
            )},
            vehiculos={"v1": Vehiculo(
                id="v1",
                tipo=TipoVehiculo.JEEP,
                velocidad=10.0,
                capacidad_personas=4,
                capacidad_animales=2,
                certificacion_requerida=Certificacion.JEEP,
                ubicacion="garaje",
                estado=EstadoVehiculo.DISPONIBLE,
            )},
            tareas={
                "t0": Tarea(id="t0", tipo="test", estado=EstadoTarea.COMPLETADA),
                "t1": Tarea(
                    id="t1", tipo="test", dependencias=frozenset({"t0"}),
                ),
            },
        )
        self.registro = RegistroEventos()
        self.registro_reservas = RegistroReservas()
        self.registro_reservas.agregar_reserva(
            Reserva(TipoRecurso.CUIDADOR, "c1", "t1", 0, 10000)
        )
        self.tiempo = 0
        self.paso = 0
        self._mundo_inicial = copy.deepcopy(self.mundo_vivo)

    def _avanzar_tiempo(self):
        self.tiempo += 10
        self.paso += 1

    @precondition(lambda self: bool(self.mundo_vivo.cuidadores))
    @rule()
    def transicion_cuidador(self):
        cuidador = self.mundo_vivo.cuidadores["c1"]
        destinos = TRANSICIONES_CUIDADOR.get(cuidador.estado, frozenset())
        if not destinos:
            return
        self._avanzar_tiempo()
        ejecutar_transicion(
            self.mundo_vivo, self.registro, "Cuidador", "c1",
            _elegir_destino(destinos, self.paso), self.tiempo, "auto",
        )

    @precondition(lambda self: bool(self.mundo_vivo.animales))
    @rule()
    def transicion_animal(self):
        animal = self.mundo_vivo.animales["a1"]
        destinos = TRANSICIONES_ANIMAL.get(animal.estado, frozenset())
        if not destinos:
            return
        self._avanzar_tiempo()
        ejecutar_transicion(
            self.mundo_vivo, self.registro, "Animal", "a1",
            _elegir_destino(destinos, self.paso), self.tiempo, "auto",
            recinto_destino="rec1",
        )

    @precondition(lambda self: bool(self.mundo_vivo.vehiculos))
    @rule()
    def transicion_vehiculo(self):
        vehiculo = self.mundo_vivo.vehiculos["v1"]
        destinos = TRANSICIONES_VEHICULO.get(vehiculo.estado, frozenset())
        if not destinos:
            return
        self._avanzar_tiempo()
        ejecutar_transicion(
            self.mundo_vivo, self.registro, "Vehiculo", "v1",
            _elegir_destino(destinos, self.paso), self.tiempo, "auto",
        )

    @precondition(lambda self: "t1" in self.mundo_vivo.tareas)
    @rule()
    def transicion_tarea_con_asignacion(self):
        tarea = self.mundo_vivo.tareas["t1"]
        destinos = TRANSICIONES_TAREA.get(tarea.estado, frozenset())
        if not destinos:
            return
        self._avanzar_tiempo()
        nuevo = _elegir_destino(destinos, self.paso)
        if nuevo == EstadoTarea.ASIGNADA:
            cuidador = self.mundo_vivo.cuidadores.get("c1")
            if cuidador is None or cuidador.estado != EstadoCuidador.DISPONIBLE:
                destinos = destinos - {EstadoTarea.ASIGNADA}
                if not destinos:
                    return
                nuevo = _elegir_destino(destinos, self.paso)
        parametros = (
            {"cuidador_id": "c1"} if nuevo == EstadoTarea.ASIGNADA else {}
        )
        ejecutar_transicion(
            self.mundo_vivo, self.registro, "Tarea", "t1",
            nuevo, self.tiempo, "auto", **parametros,
        )

    @invariant()
    def reconstruccion_coincide(self):
        reconstruido = reconstruir_estado(
            self.registro.obtener_todos(), self._mundo_inicial,
        )
        diferencias = verificar_reconstruccion(self.mundo_vivo, reconstruido)
        assert not diferencias, f"Reconstrucción difiere: {diferencias}"

    @invariant()
    def invariantes_se_mantienen(self):
        violaciones, _ = verificar_invariantes(
            self.mundo_vivo,
            self.registro_reservas,
            registro_eventos=self.registro,
            estado_inicial=self._mundo_inicial,
        )
        assert not violaciones, [v.invariante for v in violaciones]


TestReconstruccionHonesta = ReconstruccionHonestaMachine.TestCase
TestReconstruccionHonesta.settings = settings(
    max_examples=40, stateful_step_count=15, deadline=None,
)


# ============================================================================
# Secuencias de transiciones (mundo vivo mutado solo por ejecutar_transicion)
# ============================================================================

@given(
    momentos=st.lists(st.integers(min_value=0, max_value=100), max_size=20),
    data=st.data(),
)
@settings(max_examples=50)
def test_reconstruccion_coincide_para_transiciones_con_tiempo_no_decreciente(
    momentos, data,
):
    inicial = Mundo(cuidadores={"c1": Cuidador(
        id="c1", nombre="C", estado=EstadoCuidador.FUERA_DE_TURNO,
    )})
    mundo = copy.deepcopy(inicial)
    registro = RegistroEventos()

    for momento in sorted(momentos):
        actual = mundo.cuidadores["c1"].estado
        destinos = TRANSICIONES_CUIDADOR.get(actual, frozenset())
        if not destinos:
            break
        nuevo = data.draw(st.sampled_from(sorted(destinos, key=lambda e: e.name)))
        ejecutar_transicion(
            mundo, registro, "Cuidador", "c1", nuevo, momento, "secuencia",
        )

    reconstruido = reconstruir_estado(registro.obtener_todos(), copy.deepcopy(inicial))
    assert not verificar_reconstruccion(mundo, reconstruido)


@given(data=st.data())
@settings(max_examples=50)
def test_secuencia_transiciones_cuidador(data):
    inicial = Mundo(cuidadores={"c1": Cuidador(
        id="c1", nombre="C", estado=EstadoCuidador.FUERA_DE_TURNO,
    )})
    mundo = copy.deepcopy(inicial)
    registro = RegistroEventos()
    tiempo = 0

    for _ in range(data.draw(st.integers(1, 5))):
        actual = mundo.cuidadores["c1"].estado
        destinos = TRANSICIONES_CUIDADOR.get(actual, frozenset())
        if not destinos:
            break
        nuevo = data.draw(st.sampled_from(sorted(destinos, key=lambda e: e.name)))
        tiempo += 10
        ejecutar_transicion(
            mundo, registro, "Cuidador", "c1", nuevo, tiempo, "secuencia",
        )

    violaciones, _ = verificar_invariantes(mundo, RegistroReservas())
    assert not violaciones

    reconstruido = reconstruir_estado(registro.obtener_todos(), inicial)
    assert not verificar_reconstruccion(mundo, reconstruido)


@given(data=st.data())
@settings(max_examples=50)
def test_secuencia_transiciones_animal(data):
    inicial = Mundo(
        animales={"a1": Animal(
            id="a1",
            especie=ESPECIES_CATALOGO["mono_aullador"],
            recinto_origen="rec1",
            ubicacion="rec1",
            estado=EstadoAnimal.EN_RECINTO,
        )},
        recintos={"rec1": Recinto(
            nodo_id="rec1",
            tipo=TipoRecinto.ABIERTO,
            especies_admitidas=frozenset({"mono_aullador"}),
            capacidad=2,
        )},
    )
    mundo = copy.deepcopy(inicial)
    registro = RegistroEventos()
    tiempo = 0

    for _ in range(data.draw(st.integers(1, 5))):
        actual = mundo.animales["a1"].estado
        destinos = TRANSICIONES_ANIMAL.get(actual, frozenset())
        if not destinos:
            break
        nuevo = data.draw(st.sampled_from(sorted(destinos, key=lambda e: e.name)))
        tiempo += 10
        ejecutar_transicion(
            mundo, registro, "Animal", "a1", nuevo, tiempo, "secuencia",
            recinto_destino="rec1",
        )

    violaciones, _ = verificar_invariantes(mundo, RegistroReservas())
    assert not violaciones

    reconstruido = reconstruir_estado(registro.obtener_todos(), inicial)
    assert not verificar_reconstruccion(mundo, reconstruido)


@given(data=st.data())
@settings(max_examples=50)
def test_secuencia_tarea_con_reserva_y_asignacion(data):
    inicial = Mundo(
        cuidadores={"c1": Cuidador(
            id="c1", nombre="C", estado=EstadoCuidador.DISPONIBLE,
        )},
        tareas={
            "t0": Tarea(id="t0", tipo="test", estado=EstadoTarea.COMPLETADA),
            "t1": Tarea(
                id="t1", tipo="test", dependencias=frozenset({"t0"}),
            ),
        },
    )
    mundo = copy.deepcopy(inicial)
    registro = RegistroEventos()
    reservas = RegistroReservas()
    reservas.agregar_reserva(
        Reserva(TipoRecurso.CUIDADOR, "c1", "t1", 0, 10000)
    )
    tiempo = 0

    for _ in range(data.draw(st.integers(1, 5))):
        actual = mundo.tareas["t1"].estado
        destinos = TRANSICIONES_TAREA.get(actual, frozenset())
        if not destinos:
            break
        nuevo = data.draw(st.sampled_from(sorted(destinos, key=lambda e: e.name)))
        tiempo += 10
        parametros = (
            {"cuidador_id": "c1"} if nuevo == EstadoTarea.ASIGNADA else {}
        )
        ejecutar_transicion(
            mundo, registro, "Tarea", "t1", nuevo, tiempo, "secuencia",
            **parametros,
        )

    violaciones, _ = verificar_invariantes(
        mundo, reservas, registro_eventos=registro, estado_inicial=inicial,
    )
    assert not violaciones

    reconstruido = reconstruir_estado(registro.obtener_todos(), inicial)
    assert not verificar_reconstruccion(mundo, reconstruido)


# ============================================================================
# Invariantes preventivas y casos límite
# ============================================================================

def test_inv3_cuidador_con_tarea_activa():
    c1 = Cuidador(id="c1", nombre="C", estado=EstadoCuidador.DISPONIBLE)
    t1 = Tarea(id="t1", tipo="test", estado=EstadoTarea.EN_CURSO, cuidador_asignado="c1")
    t2 = Tarea(id="t2", tipo="test")
    mundo = Mundo(cuidadores={"c1": c1}, tareas={"t1": t1, "t2": t2})

    with pytest.raises(TransicionInvalida, match="INV-3"):
        ejecutar_transicion(
            mundo, RegistroEventos(), "Tarea", "t2",
            EstadoTarea.ASIGNADA, 10, "asignar", cuidador_id="c1",
        )

    assert mundo.tareas["t2"].estado == EstadoTarea.PENDIENTE


def test_inv6_recinto_no_admitido():
    animal = Animal(
        id="a1", especie=ESPECIES_CATALOGO["jaguar"],
        recinto_origen="rec1", ubicacion="campo", estado=EstadoAnimal.EN_TRASLADO,
    )
    recinto = Recinto(
        nodo_id="rec1", tipo=TipoRecinto.AVIARIO,
        especies_admitidas=frozenset({"guacamaya_roja"}), capacidad=2,
    )
    mundo = Mundo(animales={"a1": animal}, recintos={"rec1": recinto})

    with pytest.raises(TransicionInvalida, match="no admite"):
        ejecutar_transicion(
            mundo, RegistroEventos(), "Animal", "a1",
            EstadoAnimal.EN_RECINTO, 10, "volver", recinto_destino="rec1",
        )


def test_dependencias_calculadas_por_dominio():
    t1 = Tarea(id="t1", tipo="test", estado=EstadoTarea.COMPLETADA)
    t2 = Tarea(
        id="t2", tipo="test", estado=EstadoTarea.ASIGNADA,
        cuidador_asignado="c1", dependencias=frozenset({"t1"}),
    )
    mundo = Mundo(tareas={"t1": t1, "t2": t2})

    evento = ejecutar_transicion(
        mundo, RegistroEventos(), "Tarea", "t2",
        EstadoTarea.EN_CURSO, 100, "iniciar",
    )

    assert evento.estado_despues == "EN_CURSO"


def test_dependencia_inexistente_lanza_error():
    t2 = Tarea(
        id="t2", tipo="test", estado=EstadoTarea.ASIGNADA,
        cuidador_asignado="c1", dependencias=frozenset({"t_no_existe"}),
    )
    mundo = Mundo(tareas={"t2": t2})

    with pytest.raises(DependenciaInexistente):
        ejecutar_transicion(
            mundo, RegistroEventos(), "Tarea", "t2",
            EstadoTarea.EN_CURSO, 100, "iniciar",
        )


def test_evento_no_reconstruible():
    evento = Evento(
        id=1, momento=100, tipo=TipoEvento.TAREA_ASIGNADA,
        entidad_tipo="Tarea", entidad_id="t1",
        estado_antes="", estado_despues="", causa="test",
    )

    with pytest.raises(EventoNoSoportado, match="TAREA_ASIGNADA"):
        reconstruir_estado([evento], Mundo())


def test_invariantes_4_5_en_no_verificadas():
    violaciones, no_verificadas = verificar_invariantes(Mundo(), RegistroReservas())

    assert violaciones == []
    ids = {nv.invariante for nv in no_verificadas}
    assert "INV-4-capacidad-vehiculo" in ids
    assert "INV-5-jeep-aristas-validas" in ids


def test_estado_no_enum_en_ejecutar_transicion():
    mundo = Mundo(cuidadores={"c1": Cuidador(id="c1", nombre="C")})

    with pytest.raises(ErrorDominio, match="no pertenece"):
        ejecutar_transicion(
            mundo, RegistroEventos(), "Cuidador", "c1",
            "DISPONIBLE", 0, "test",
        )


# ============================================================================
# Test estático: no mutar estado/cuidador_asignado con replace(...)
# ============================================================================

# Campos que solo `eventos.py` puede escribir con dataclasses.replace.
_CAMPOS_PROTEGIDOS_REPLACE = {"estado", "cuidador_asignado"}


class _ReplaceEstadoVisitor(ast.NodeVisitor):
    """Busca llamadas a replace(..., estado=.../cuidador_asignado=...)."""

    def __init__(self, filepath):
        self.filepath = filepath
        self.violaciones = []

    def visit_Call(self, node):
        es_replace = (
            isinstance(node.func, ast.Name) and node.func.id == "replace"
        ) or (
            isinstance(node.func, ast.Attribute) and node.func.attr == "replace"
        )
        if es_replace:
            for kw in node.keywords:
                if kw.arg in _CAMPOS_PROTEGIDOS_REPLACE:
                    self.violaciones.append((self.filepath, node.lineno, kw.arg))
        self.generic_visit(node)


def test_ast_no_se_cambian_campos_de_estado_con_replace():
    raiz = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
    directorios = [
        os.path.join(raiz, "zoo_ops", "dominio"),
        os.path.join(raiz, "tests", "dominio"),
    ]
    permitidos = {"eventos.py"}
    violaciones = []

    for directorio in directorios:
        for nombre in sorted(os.listdir(directorio)):
            if not nombre.endswith(".py") or nombre in permitidos:
                continue
            ruta = os.path.join(directorio, nombre)
            with open(ruta, "r", encoding="utf-8") as archivo:
                fuente = archivo.read()
            try:
                arbol = ast.parse(fuente, filename=ruta)
            except SyntaxError as exc:
                pytest.fail(f"No se pudo analizar {ruta}: {exc}")
            visitor = _ReplaceEstadoVisitor(ruta)
            visitor.visit(arbol)
            violaciones.extend(visitor.violaciones)

    assert not violaciones, (
        "Se encontró replace(...) con campos protegidos "
        f"{sorted(_CAMPOS_PROTEGIDOS_REPLACE)} fuera de eventos.py: {violaciones}"
    )
