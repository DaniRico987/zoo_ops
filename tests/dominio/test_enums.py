"""
Pruebas unitarias para enums.py
"""

import pytest
from zoo_ops.dominio.enums import (
    TipoNodo, TipoRecinto, Medio, Peligrosidad, TipoVehiculo, TipoEquipo,
    Habilidad, Certificacion, EstadoCuidador, EstadoAnimal, EstadoVehiculo,
    EstadoTarea, EstadoIncidente, TipoIncidente, TipoSensor, MedioPermitido,
    PrioridadTarea
)


class TestEnumsValores:
    """Verifica que los enums tengan los valores esperados."""
    
    def test_tipo_nodo(self):
        assert TipoNodo.RECINTO
        assert TipoNodo.CRUCE
        assert TipoNodo.HELIPUERTO
        assert TipoNodo.CLINICA
        assert TipoNodo.GARAJE
        assert TipoNodo.BODEGA
    
    def test_tipo_recinto(self):
        assert TipoRecinto.ABIERTO
        assert TipoRecinto.AVIARIO
        assert TipoRecinto.ACUARIO
    
    def test_medio(self):
        assert Medio.TERRESTRE
        assert Medio.AEREO
        assert Medio.ACUATICO
    
    def test_peligrosidad(self):
        assert Peligrosidad.BAJA
        assert Peligrosidad.MEDIA
        assert Peligrosidad.ALTA
    
    def test_tipo_vehiculo(self):
        assert TipoVehiculo.JEEP
        assert TipoVehiculo.HELICOPTERO
        assert TipoVehiculo.CAMION_TRASLADO
    
    def test_tipo_equipo(self):
        assert TipoEquipo.DARDOS_TRANQUILIZANTES
        assert TipoEquipo.RED_CAPTURA
        assert TipoEquipo.RED_AVES
        assert TipoEquipo.JAULA_PORTATIL
        assert TipoEquipo.CONTENEDOR_OXIGENADO
    
    def test_habilidad(self):
        assert Habilidad.REPARACION
        assert Habilidad.MANEJO_FELINOS
        assert Habilidad.MANEJO_PRIMATES
        assert Habilidad.MANEJO_UNGULADOS
        assert Habilidad.MANEJO_AVES
        assert Habilidad.MANEJO_ACUATICO
        assert Habilidad.MANTENIMIENTO_SISTEMAS
        assert Habilidad.PRIMEROS_AUXILIOS
        assert Habilidad.VETERINARIA_BASICA
        assert Habilidad.CONDUCCION
    
    def test_certificacion(self):
        assert Certificacion.JEEP
        assert Certificacion.HELICOPTERO
        assert Certificacion.TRANQUILIZANTE
        assert Certificacion.CAMION_TRASLADO
    
    def test_estado_cuidador(self):
        assert EstadoCuidador.FUERA_DE_TURNO
        assert EstadoCuidador.DISPONIBLE
        assert EstadoCuidador.ASIGNADO
        assert EstadoCuidador.EN_CAMINO
        assert EstadoCuidador.EJECUTANDO
        assert EstadoCuidador.PAUSADO
        assert EstadoCuidador.DESCANSANDO
    
    def test_estado_animal(self):
        assert EstadoAnimal.EN_RECINTO
        assert EstadoAnimal.ESCAPADO
        assert EstadoAnimal.LOCALIZADO
        assert EstadoAnimal.TRANQUILIZADO
        assert EstadoAnimal.EN_TRASLADO
        assert EstadoAnimal.EN_CLINICA
        assert EstadoAnimal.EN_OBSERVACION
    
    def test_estado_vehiculo(self):
        assert EstadoVehiculo.DISPONIBLE
        assert EstadoVehiculo.RESERVADO
        assert EstadoVehiculo.EN_RUTA
        assert EstadoVehiculo.EN_USO
        assert EstadoVehiculo.EN_MANTENIMIENTO
    
    def test_estado_tarea(self):
        assert EstadoTarea.PENDIENTE
        assert EstadoTarea.BLOQUEADA
        assert EstadoTarea.ASIGNADA
        assert EstadoTarea.EN_CURSO
        assert EstadoTarea.PAUSADA
        assert EstadoTarea.COMPLETADA
        assert EstadoTarea.FALLIDA
        assert EstadoTarea.CANCELADA
    
    def test_estado_incidente(self):
        assert EstadoIncidente.ABIERTO
        assert EstadoIncidente.EN_RESPUESTA
        assert EstadoIncidente.CONTENIDO
        assert EstadoIncidente.CERRADO
    
    def test_tipo_incidente(self):
        assert TipoIncidente.ESCAPE_TERRESTRE
        assert TipoIncidente.ESCAPE_AEREO
        assert TipoIncidente.FALLA_SOPORTE_VITAL
    
    def test_tipo_sensor(self):
        assert TipoSensor.TEMPERATURA
        assert TipoSensor.OXIGENO_DISUELTO
        assert TipoSensor.PH
    
    def test_medio_permitido(self):
        assert MedioPermitido.PIE
        assert MedioPermitido.JEEP
    
    def test_prioridad_tarea_valores(self):
        assert PrioridadTarea.BAJA.value == 1
        assert PrioridadTarea.MEDIA.value == 2
        assert PrioridadTarea.ALTA.value == 3
        assert PrioridadTarea.CRITICA.value == 4


class TestEnumsComparacion:
    """Verifica comparaciones y comportamiento de enums."""
    
    def test_enum_equality(self):
        assert EstadoCuidador.DISPONIBLE == EstadoCuidador.DISPONIBLE
        assert EstadoCuidador.DISPONIBLE != EstadoCuidador.ASIGNADO
    
    def test_enum_in_set(self):
        estados = {EstadoCuidador.DISPONIBLE, EstadoCuidador.ASIGNADO}
        assert EstadoCuidador.DISPONIBLE in estados
        assert EstadoCuidador.FUERA_DE_TURNO not in estados
    
    def test_enum_iteration(self):
        # Verificar que se puede iterar
        estados = list(EstadoCuidador)
        assert len(estados) == 7
    
    def test_prioridad_orden(self):
        assert PrioridadTarea.BAJA < PrioridadTarea.MEDIA
        assert PrioridadTarea.MEDIA < PrioridadTarea.ALTA
        assert PrioridadTarea.ALTA < PrioridadTarea.CRITICA