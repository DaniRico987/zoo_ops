"""
Pruebas unitarias para catalogos.py
"""

import pytest
from zoo_ops.dominio.catalogos import (
    ESPECIES_CATALOGO, HABILIDADES_CATALOGO, CERTIFICACIONES_CATALOGO,
    EQUIPOS_CATALOGO, Especie, DefinicionHabilidad, DefinicionCertificacion,
    DefinicionEquipo, obtener_especie, listar_especies
)
from zoo_ops.dominio.entidades import Sensor
from zoo_ops.dominio.enums import (
    Medio, Peligrosidad, TipoVehiculo, TipoRecinto, TipoEquipo,
    Habilidad, Certificacion, TipoSensor
)


class TestEspeciesCatalogo:
    """Pruebas del catálogo de especies."""
    
    def test_especies_existen(self):
        assert "jaguar" in ESPECIES_CATALOGO
        assert "mono_aullador" in ESPECIES_CATALOGO
        assert "tapir" in ESPECIES_CATALOGO
        assert "guacamaya_roja" in ESPECIES_CATALOGO
        assert "pirarucu" in ESPECIES_CATALOGO
        assert len(ESPECIES_CATALOGO) == 5
    
    def test_jaguar_propiedades(self):
        e = ESPECIES_CATALOGO["jaguar"]
        assert e.nombre == "Jaguar"
        assert e.medio == Medio.TERRESTRE
        assert e.peligrosidad == Peligrosidad.ALTA
        assert e.requiere_tranquilizante is True
        assert e.habilidad_requerida == Habilidad.MANEJO_FELINOS
        assert e.nivel_minimo_habilidad == 4
        assert e.tipo_vehiculo_traslado == TipoVehiculo.CAMION_TRASLADO
        assert e.minimo_personas_traslado == 3
        assert e.tipo_recinto_requerido == TipoRecinto.ABIERTO
    
    def test_mono_aullador_propiedades(self):
        e = ESPECIES_CATALOGO["mono_aullador"]
        assert e.nombre == "Mono aullador"
        assert e.medio == Medio.TERRESTRE
        assert e.peligrosidad == Peligrosidad.MEDIA
        assert e.requiere_tranquilizante is False
        assert e.habilidad_requerida == Habilidad.MANEJO_PRIMATES
        assert e.nivel_minimo_habilidad == 3
        assert e.tipo_vehiculo_traslado == TipoVehiculo.JEEP
        assert e.minimo_personas_traslado == 2
        assert e.tipo_recinto_requerido == TipoRecinto.ABIERTO
    
    def test_tapir_propiedades(self):
        e = ESPECIES_CATALOGO["tapir"]
        assert e.nombre == "Tapir"
        assert e.medio == Medio.TERRESTRE
        assert e.peligrosidad == Peligrosidad.BAJA
        assert e.requiere_tranquilizante is True
        assert e.habilidad_requerida == Habilidad.MANEJO_UNGULADOS
        assert e.nivel_minimo_habilidad == 3
        assert e.tipo_vehiculo_traslado == TipoVehiculo.CAMION_TRASLADO
        assert e.minimo_personas_traslado == 3
        assert e.tipo_recinto_requerido == TipoRecinto.ABIERTO
    
    def test_guacamaya_roja_propiedades(self):
        e = ESPECIES_CATALOGO["guacamaya_roja"]
        assert e.nombre == "Guacamaya roja"
        assert e.medio == Medio.AEREO
        assert e.peligrosidad == Peligrosidad.MEDIA
        assert e.requiere_tranquilizante is False
        assert e.habilidad_requerida == Habilidad.MANEJO_AVES
        assert e.nivel_minimo_habilidad == 3
        assert e.tipo_vehiculo_traslado == TipoVehiculo.JEEP
        assert e.minimo_personas_traslado == 2
        assert e.tipo_recinto_requerido == TipoRecinto.AVIARIO
    
    def test_pirarucu_propiedades(self):
        e = ESPECIES_CATALOGO["pirarucu"]
        assert e.nombre == "Pirarucu"
        assert e.medio == Medio.ACUATICO
        assert e.peligrosidad == Peligrosidad.BAJA
        assert e.requiere_tranquilizante is False
        assert e.habilidad_requerida == Habilidad.MANEJO_ACUATICO
        assert e.nivel_minimo_habilidad == 3
        assert e.tipo_vehiculo_traslado == TipoVehiculo.JEEP
        assert e.minimo_personas_traslado == 2
        assert e.tipo_recinto_requerido == TipoRecinto.ACUARIO
    
    def test_obtener_especie_existente(self):
        e = obtener_especie("jaguar")
        assert e.nombre == "Jaguar"
    
    def test_obtener_especie_inexistente(self):
        with pytest.raises(ValueError):
            obtener_especie("inexistente")
    
    def test_listar_especies(self):
        lista = listar_especies()
        assert len(lista) == 5
        assert all(isinstance(e, Especie) for e in lista)
    
    def test_especie_frozen(self):
        e = ESPECIES_CATALOGO["jaguar"]
        with pytest.raises(Exception):  # FrozenInstanceError o AttributeError
            e.nombre = "Otro"


class TestHabilidadesCatalogo:
    """Pruebas del catálogo de habilidades."""
    
    def test_todas_habilidades_presentes(self):
        assert len(HABILIDADES_CATALOGO) == 10
        for h in Habilidad:
            assert h in HABILIDADES_CATALOGO
    
    def test_manejo_felinos_requiere_certificacion(self):
        d = HABILIDADES_CATALOGO[Habilidad.MANEJO_FELINOS]
        assert d.requiere_certificacion == Certificacion.TRANQUILIZANTE
    
    def test_manejo_ungulados_requiere_certificacion(self):
        d = HABILIDADES_CATALOGO[Habilidad.MANEJO_UNGULADOS]
        assert d.requiere_certificacion == Certificacion.TRANQUILIZANTE
    
    def test_conduccion_requiere_certificacion(self):
        d = HABILIDADES_CATALOGO[Habilidad.CONDUCCION]
        assert d.requiere_certificacion == Certificacion.JEEP
    
    def test_otras_no_requieren_certificacion(self):
        for h in [Habilidad.REPARACION, Habilidad.MANEJO_PRIMATES, 
                  Habilidad.MANEJO_AVES, Habilidad.MANEJO_ACUATICO,
                  Habilidad.MANTENIMIENTO_SISTEMAS, Habilidad.PRIMEROS_AUXILIOS,
                  Habilidad.VETERINARIA_BASICA]:
            d = HABILIDADES_CATALOGO[h]
            assert d.requiere_certificacion is None


class TestCertificacionesCatalogo:
    """Pruebas del catálogo de certificaciones."""
    
    def test_todas_certificaciones_presentes(self):
        assert len(CERTIFICACIONES_CATALOGO) == 4
        for c in Certificacion:
            assert c in CERTIFICACIONES_CATALOGO
    
    def test_vehiculos_asociados(self):
        assert TipoVehiculo.JEEP in CERTIFICACIONES_CATALOGO[Certificacion.JEEP].vehiculos_asociados
        assert TipoVehiculo.HELICOPTERO in CERTIFICACIONES_CATALOGO[Certificacion.HELICOPTERO].vehiculos_asociados
        assert TipoVehiculo.CAMION_TRASLADO in CERTIFICACIONES_CATALOGO[Certificacion.CAMION_TRASLADO].vehiculos_asociados
        assert CERTIFICACIONES_CATALOGO[Certificacion.TRANQUILIZANTE].vehiculos_asociados == []


class TestEquiposCatalogo:
    """Pruebas del catálogo de equipos."""
    
    def test_todos_equipos_presentes(self):
        assert len(EQUIPOS_CATALOGO) == 5
        for e in TipoEquipo:
            assert e in EQUIPOS_CATALOGO
    
    def test_especies_compatibles(self):
        assert "jaguar" in EQUIPOS_CATALOGO[TipoEquipo.DARDOS_TRANQUILIZANTES].especies_compatibles
        assert "tapir" in EQUIPOS_CATALOGO[TipoEquipo.DARDOS_TRANQUILIZANTES].especies_compatibles
        assert "mono_aullador" in EQUIPOS_CATALOGO[TipoEquipo.RED_CAPTURA].especies_compatibles
        assert "guacamaya_roja" in EQUIPOS_CATALOGO[TipoEquipo.RED_AVES].especies_compatibles
        assert "mono_aullador" in EQUIPOS_CATALOGO[TipoEquipo.JAULA_PORTATIL].especies_compatibles
        assert "guacamaya_roja" in EQUIPOS_CATALOGO[TipoEquipo.JAULA_PORTATIL].especies_compatibles
        assert "pirarucu" in EQUIPOS_CATALOGO[TipoEquipo.CONTENEDOR_OXIGENADO].especies_compatibles


class TestSensor:
    """Pruebas de la estructura Sensor."""
    
    def test_crear_sensor(self):
        s = Sensor(id="s1", tipo=TipoSensor.TEMPERATURA, recinto_id="r1", ubicacion="esquina")
        assert s.id == "s1"
        assert s.tipo == TipoSensor.TEMPERATURA
        assert s.recinto_id == "r1"
        assert s.ubicacion == "esquina"
    
    def test_sensor_frozen(self):
        s = Sensor(id="s1", tipo=TipoSensor.TEMPERATURA, recinto_id="r1")
        with pytest.raises(Exception):
            s.id = "s2"