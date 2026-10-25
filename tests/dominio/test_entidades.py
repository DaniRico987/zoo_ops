"""
Pruebas unitarias para entidades.py
"""

import pytest
from dataclasses import FrozenInstanceError
from zoo_ops.dominio.entidades import (
    Nodo, Arista, Recinto, Cuidador, Vehiculo, IndicadoresSalud, Animal,
    Equipo, Tarea, HabilidadRequerida, Incidente, Sensor, Lectura, Mundo,
    esta_en_nodo, esta_en_arista, obtener_nodo_actual, obtener_arista_actual
)
from zoo_ops.dominio.enums import (
    TipoNodo, TipoRecinto, Medio, MedioPermitido, TipoVehiculo, TipoEquipo,
    Habilidad, Certificacion, EstadoCuidador, EstadoAnimal, EstadoVehiculo,
    EstadoEquipo, EstadoTarea, EstadoIncidente, TipoIncidente, TipoSensor,
    PrioridadTarea
)
from zoo_ops.dominio.catalogos import ESPECIES_CATALOGO
from zoo_ops.dominio.errores import ErrorDominio


class TestNodo:
    """Pruebas de Nodo."""
    
    def test_crear_nodo(self):
        n = Nodo(id="n1", tipo=TipoNodo.RECINTO, x=10.0, y=20.0, z=0.0)
        assert n.id == "n1"
        assert n.tipo == TipoNodo.RECINTO
        assert n.x == 10.0
        assert n.y == 20.0
        assert n.z == 0.0
    
    def test_nodo_z_default(self):
        n = Nodo(id="n1", tipo=TipoNodo.CRUCE, x=0.0, y=0.0)
        assert n.z == 0.0
    
    def test_nodo_frozen(self):
        n = Nodo(id="n1", tipo=TipoNodo.RECINTO, x=0.0, y=0.0)
        with pytest.raises(FrozenInstanceError):
            n.x = 1.0


class TestArista:
    """Pruebas de Arista."""
    
    def test_crear_arista(self):
        a = Arista(
            origen="n1", destino="n2", distancia=100.0,
            medios_permitidos=frozenset({MedioPermitido.PIE, MedioPermitido.JEEP}),
            bloqueada=False
        )
        assert a.origen == "n1"
        assert a.destino == "n2"
        assert a.distancia == 100.0
        assert MedioPermitido.JEEP in a.medios_permitidos
        assert a.bloqueada is False
    
    def test_arista_bloqueada_default(self):
        a = Arista(origen="n1", destino="n2", distancia=50.0)
        assert a.bloqueada is False
        assert a.medios_permitidos == frozenset()


class TestRecinto:
    """Pruebas de Recinto."""
    
    def test_crear_recinto(self):
        r = Recinto(
            nodo_id="n1", tipo=TipoRecinto.ABIERTO,
            especies_admitidas=frozenset({"jaguar", "tapir"}),
            capacidad=5
        )
        assert r.nodo_id == "n1"
        assert r.tipo == TipoRecinto.ABIERTO
        assert "jaguar" in r.especies_admitidas
        assert r.capacidad == 5
        assert r.estado == "operativo"


class TestCuidador:
    """Pruebas de Cuidador."""
    
    def test_crear_cuidador(self):
        c = Cuidador(
            id="c1", nombre="Juan",
            habilidades={Habilidad.MANEJO_FELINOS: 4, Habilidad.CONDUCCION: 3},
            certificaciones=frozenset({Certificacion.TRANQUILIZANTE, Certificacion.JEEP}),
            velocidad_base=1.5,
            ubicacion=("n1",),
            estado=EstadoCuidador.DISPONIBLE,
            fatiga=10,
            turno=(0, 28800)
        )
        assert c.id == "c1"
        assert c.nombre == "Juan"
        assert c.habilidades[Habilidad.MANEJO_FELINOS] == 4
        assert Certificacion.TRANQUILIZANTE in c.certificaciones
        assert c.velocidad_base == 1.5
        assert c.ubicacion == ("n1",)
        assert c.estado == EstadoCuidador.DISPONIBLE
        assert c.fatiga == 10
        assert c.turno == (0, 28800)
    
    def test_cuidador_en_arista(self):
        c = Cuidador(
            id="c1", nombre="Juan",
            ubicacion=("n1", "n2", 0.5)
        )
        assert c.ubicacion == ("n1", "n2", 0.5)


class TestVehiculo:
    """Pruebas de Vehiculo."""
    
    def test_crear_vehiculo(self):
        v = Vehiculo(
            id="v1", tipo=TipoVehiculo.JEEP, velocidad=10.0,
            capacidad_personas=4, capacidad_animales=2,
            certificacion_requerida=Certificacion.JEEP,
            ubicacion="garaje1", estado=EstadoVehiculo.DISPONIBLE
        )
        assert v.id == "v1"
        assert v.tipo == TipoVehiculo.JEEP
        assert v.velocidad == 10.0
        assert v.capacidad_personas == 4
        assert v.capacidad_animales == 2
        assert v.certificacion_requerida == Certificacion.JEEP
        assert v.ubicacion == "garaje1"
        assert v.estado == EstadoVehiculo.DISPONIBLE


class TestAnimal:
    """Pruebas de Animal."""
    
    def test_crear_animal(self):
        especie = ESPECIES_CATALOGO["jaguar"]
        a = Animal(
            id="a1", especie=especie, recinto_origen="rec1",
            ubicacion="rec1", estado=EstadoAnimal.EN_RECINTO,
            salud=IndicadoresSalud(peso=80.0, consumo_alimento=100.0, actividad=70.0)
        )
        assert a.id == "a1"
        assert a.especie == especie
        assert a.recinto_origen == "rec1"
        assert a.ubicacion == "rec1"
        assert a.estado == EstadoAnimal.EN_RECINTO
        assert a.salud.peso == 80.0


class TestEquipo:
    """Pruebas de Equipo."""
    
    def test_crear_equipo(self):
        e = Equipo(
            id="e1", tipo=TipoEquipo.DARDOS_TRANQUILIZANTES,
            ubicacion="bodega1", estado=EstadoEquipo.DISPONIBLE
        )
        assert e.id == "e1"
        assert e.tipo == TipoEquipo.DARDOS_TRANQUILIZANTES
        assert e.ubicacion == "bodega1"
        assert e.estado == EstadoEquipo.DISPONIBLE


class TestTarea:
    """Pruebas de Tarea."""
    
    def test_crear_tarea_simple(self):
        t = Tarea(
            id="t1", tipo="captura", prioridad_base=PrioridadTarea.ALTA,
            urgencia=50, nodo_destino="n1", duracion_estimada=3600
        )
        assert t.id == "t1"
        assert t.tipo == "captura"
        assert t.prioridad_base == PrioridadTarea.ALTA
        assert t.urgencia == 50
        assert t.nodo_destino == "n1"
        assert t.duracion_estimada == 3600
        assert t.estado == EstadoTarea.PENDIENTE
        assert t.interrumpible is True
        assert t.personas_minimas == 1

    def test_personas_minimas_menor_que_uno_lanza_error_de_dominio(self):
        with pytest.raises(ErrorDominio, match="personas_minimas"):
            Tarea(id="t1", tipo="captura", personas_minimas=0)
    
    def test_crear_tarea_con_habilidades(self):
        t = Tarea(
            id="t1", tipo="traslado",
            habilidades_requeridas=(
                HabilidadRequerida(Habilidad.MANEJO_FELINOS, 4),
                HabilidadRequerida(Habilidad.CONDUCCION, 3),
            ),
            certificaciones_requeridas=frozenset({Certificacion.TRANQUILIZANTE, Certificacion.JEEP}),
            recursos_requeridos=("e1", "v1"),
            ventana_tiempo=(1000, 5000),
            dependencias=frozenset({"t0"}),
            interrumpible=False
        )
        assert len(t.habilidades_requeridas) == 2
        assert t.habilidades_requeridas[0].habilidad == Habilidad.MANEJO_FELINOS
        assert t.habilidades_requeridas[0].nivel_minimo == 4
        assert Certificacion.TRANQUILIZANTE in t.certificaciones_requeridas
        assert "e1" in t.recursos_requeridos
        assert t.ventana_tiempo == (1000, 5000)
        assert "t0" in t.dependencias
        assert t.interrumpible is False


class TestIncidente:
    """Pruebas de Incidente."""
    
    def test_crear_incidente(self):
        i = Incidente(
            id="i1", tipo=TipoIncidente.ESCAPE_TERRESTRE, severidad=8,
            ubicacion="rec1", estado=EstadoIncidente.ABIERTO,
            tareas_generadas=frozenset({"t1", "t2"}),
            animal_relacionado="a1"
        )
        assert i.id == "i1"
        assert i.tipo == TipoIncidente.ESCAPE_TERRESTRE
        assert i.severidad == 8
        assert i.ubicacion == "rec1"
        assert i.estado == EstadoIncidente.ABIERTO
        assert "t1" in i.tareas_generadas
        assert i.animal_relacionado == "a1"


class TestSensorLectura:
    """Pruebas de Sensor y Lectura."""
    
    def test_crear_sensor(self):
        s = Sensor(id="s1", tipo=TipoSensor.TEMPERATURA, recinto_id="rec1", ubicacion="sumergido")
        assert s.id == "s1"
        assert s.tipo == TipoSensor.TEMPERATURA
        assert s.recinto_id == "rec1"
        assert s.ubicacion == "sumergido"
    
    def test_crear_lectura(self):
        l = Lectura(sensor_id="s1", valor=25.5, momento=1000)
        assert l.sensor_id == "s1"
        assert l.valor == 25.5
        assert l.momento == 1000


class TestMundo:
    """Pruebas de Mundo (estado global)."""
    
    def test_mundo_vacio(self):
        m = Mundo()
        assert m.tiempo_actual == 0
        assert len(m.nodos) == 0
        assert len(m.cuidadores) == 0
        assert len(m.tareas) == 0
    
    def test_mundo_con_entidades(self):
        n = Nodo(id="n1", tipo=TipoNodo.RECINTO, x=0, y=0)
        c = Cuidador(id="c1", nombre="Test")
        m = Mundo(nodos={"n1": n}, cuidadores={"c1": c}, tiempo_actual=100)
        assert m.nodos["n1"] == n
        assert m.cuidadores["c1"] == c
        assert m.tiempo_actual == 100


class TestUtilidadesUbicacion:
    """Pruebas de funciones de utilidad para ubicación."""
    
    def test_esta_en_nodo(self):
        assert esta_en_nodo(("n1",)) is True
        assert esta_en_nodo(("n1", "n2", 0.5)) is False
        assert esta_en_nodo(()) is False
    
    def test_esta_en_arista(self):
        assert esta_en_arista(("n1", "n2", 0.5)) is True
        assert esta_en_arista(("n1",)) is False
        assert esta_en_arista(("n1", "n2")) is False
    
    def test_obtener_nodo_actual(self):
        assert obtener_nodo_actual(("n1",)) == "n1"
        assert obtener_nodo_actual(("n1", "n2", 0.5)) is None
    
    def test_obtener_arista_actual(self):
        assert obtener_arista_actual(("n1", "n2", 0.5)) == ("n1", "n2", 0.5)
        assert obtener_arista_actual(("n1",)) is None