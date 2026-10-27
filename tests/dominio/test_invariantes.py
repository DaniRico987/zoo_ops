"""
Pruebas unitarias para invariantes.py - verificación de invariantes del sistema.
"""

import copy

import pytest
from zoo_ops.dominio.invariantes import (
    verificar_invariantes, ViolacionInvariante, NoVerificada,
    _verificar_invariante_1_habilidades_cuidador,
    _verificar_invariante_2_solapamiento_reservas,
    _verificar_invariante_3_una_tarea_activa,
    _verificar_invariante_4_capacidad_vehiculo,
    _verificar_invariante_5_ruta_jeep,
    _verificar_invariante_9_planes_consistentes,
    _verificar_invariante_10_tarea_plan,
    _verificar_invariante_12_estados_plan,
    _verificar_invariante_6_animal_en_recinto_valido,
    _verificar_invariante_8_dependencias_tarea,
    verificar_invariante_eventos,
    formatear_violaciones, formatear_no_verificadas, assert_sin_violaciones
)
from zoo_ops.dominio.entidades import (
    Mundo, Nodo, Arista, Cuidador, Vehiculo, Animal, Recinto, Equipo, Tarea,
    HabilidadRequerida, IndicadoresSalud
)
from zoo_ops.dominio.enums import (
    TipoNodo, TipoRecinto, Medio, MedioPermitido, TipoVehiculo, TipoEquipo,
    Habilidad, Certificacion, EstadoCuidador, EstadoAnimal, EstadoVehiculo,
    EstadoTarea, EstadoIncidente, TipoIncidente, Peligrosidad
)
from zoo_ops.dominio.catalogos import ESPECIES_CATALOGO
from zoo_ops.dominio.reservas import RegistroReservas, Reserva, TipoRecurso, reservar_atomico
from zoo_ops.dominio.eventos import RegistroEventos, crear_evento, TipoEvento
from zoo_ops.dominio.estados import ejecutar_transicion
from zoo_ops.dominio.plan import PlanEjecucion


def _mundo_con_estado_plan(
    estado_tarea,
    estado_cuidador,
    estado_vehiculo,
):
    tarea = Tarea(
        id="t1",
        tipo="test",
        estado=estado_tarea,
        cuidadores_asignados=("c1",),
    )
    plan = PlanEjecucion(
        tarea_id="t1",
        cuidadores=("c1",),
        desde=10,
        hasta=20,
        vehiculo_id="v1",
    )
    return Mundo(
        tareas={"t1": tarea},
        cuidadores={
            "c1": Cuidador("c1", "Test", estado=estado_cuidador),
        },
        vehiculos={
            "v1": Vehiculo(
                "v1",
                TipoVehiculo.HELICOPTERO,
                5,
                2,
                1,
                Certificacion.HELICOPTERO,
                ubicacion="garaje",
                estado=estado_vehiculo,
            ),
        },
        planes={"t1": plan},
    )


@pytest.mark.parametrize(
    ("estado_tarea", "estado_cuidador", "estado_vehiculo"),
    [
        (
            EstadoTarea.ASIGNADA,
            EstadoCuidador.ASIGNADO,
            EstadoVehiculo.RESERVADO,
        ),
        (
            EstadoTarea.EN_CURSO,
            EstadoCuidador.EJECUTANDO,
            EstadoVehiculo.EN_RUTA,
        ),
        (
            EstadoTarea.PAUSADA,
            EstadoCuidador.PAUSADO,
            EstadoVehiculo.EN_USO,
        ),
    ],
)
def test_inv12_acepta_estados_coherentes_por_estado_de_tarea(
    estado_tarea,
    estado_cuidador,
    estado_vehiculo,
):
    mundo = _mundo_con_estado_plan(
        estado_tarea, estado_cuidador, estado_vehiculo,
    )

    assert _verificar_invariante_12_estados_plan(mundo) == []


@pytest.mark.parametrize(
    ("estado_tarea", "estado_cuidador", "estado_vehiculo", "tipo_invalido"),
    [
        (
            EstadoTarea.ASIGNADA,
            EstadoCuidador.DISPONIBLE,
            EstadoVehiculo.RESERVADO,
            "Cuidador",
        ),
        (
            EstadoTarea.ASIGNADA,
            EstadoCuidador.ASIGNADO,
            EstadoVehiculo.DISPONIBLE,
            "Vehiculo",
        ),
        (
            EstadoTarea.EN_CURSO,
            EstadoCuidador.FUERA_DE_TURNO,
            EstadoVehiculo.EN_RUTA,
            "Cuidador",
        ),
        (
            EstadoTarea.EN_CURSO,
            EstadoCuidador.EJECUTANDO,
            EstadoVehiculo.EN_MANTENIMIENTO,
            "Vehiculo",
        ),
        (
            EstadoTarea.PAUSADA,
            EstadoCuidador.DESCANSANDO,
            EstadoVehiculo.EN_USO,
            "Cuidador",
        ),
        (
            EstadoTarea.PAUSADA,
            EstadoCuidador.PAUSADO,
            EstadoVehiculo.DISPONIBLE,
            "Vehiculo",
        ),
    ],
)
def test_inv12_reporta_cada_estado_incoherente(
    estado_tarea,
    estado_cuidador,
    estado_vehiculo,
    tipo_invalido,
):
    mundo = _mundo_con_estado_plan(
        estado_tarea, estado_cuidador, estado_vehiculo,
    )

    violaciones = _verificar_invariante_12_estados_plan(mundo)

    assert len(violaciones) == 1
    assert violaciones[0].entidad_tipo == tipo_invalido


def test_inv12_detecta_cuidador_disponible_despues_de_asignacion_directa():
    mundo = _mundo_con_estado_plan(
        EstadoTarea.PENDIENTE,
        EstadoCuidador.DISPONIBLE,
        EstadoVehiculo.DISPONIBLE,
    )
    mundo.eliminar_plan("t1")
    mundo.registrar_plan(PlanEjecucion(
        tarea_id="t1",
        cuidadores=("c1",),
        desde=10,
        hasta=20,
    ))
    ejecutar_transicion(
        mundo,
        RegistroEventos(),
        "Tarea",
        "t1",
        EstadoTarea.ASIGNADA,
        0,
        "asignación directa",
    )

    violaciones = _verificar_invariante_12_estados_plan(mundo)

    assert len(violaciones) == 1
    assert violaciones[0].entidad_tipo == "Cuidador"
    assert violaciones[0].entidad_id == "c1"


def test_registro_reservas_expone_copias_de_sus_reservas():
    registro = RegistroReservas()
    reserva = Reserva(TipoRecurso.CUIDADOR, "c1", "t1", 10, 20)
    registro.agregar_reserva(reserva)

    todas = registro.todas_las_reservas()
    por_recurso = registro.reservas_por_recurso()
    todas.clear()
    por_recurso[(TipoRecurso.CUIDADOR, "c1")].clear()
    por_recurso.clear()

    assert registro.todas_las_reservas() == [reserva]
    assert registro.reservas_por_recurso() == {
        (TipoRecurso.CUIDADOR, "c1"): [reserva],
    }


class TestInvariante1HabilidadesCuidador:
    """Pruebas de invariante 1: habilidades y certificaciones."""
    
    def setup_method(self):
        self.registro = RegistroReservas()
    
    def test_cuidador_con_habilidades_suficientes(self):
        cuidador = Cuidador(
            id="c1", nombre="Test",
            habilidades={Habilidad.MANEJO_FELINOS: 5},
            certificaciones=frozenset({Certificacion.TRANQUILIZANTE}),
            estado=EstadoCuidador.EJECUTANDO
        )
        
        tarea = Tarea(
            id="t1", tipo="captura",
            habilidades_requeridas=(HabilidadRequerida(Habilidad.MANEJO_FELINOS, 4),),
            certificaciones_requeridas=frozenset({Certificacion.TRANQUILIZANTE}),
            estado=EstadoTarea.EN_CURSO,
            cuidadores_asignados=("c1",)
        )
        
        mundo = Mundo(cuidadores={"c1": cuidador}, tareas={"t1": tarea})
        
        violaciones = _verificar_invariante_1_habilidades_cuidador(mundo)
        assert len(violaciones) == 0
    
    def test_cuidador_falta_habilidad(self):
        cuidador = Cuidador(
            id="c1", nombre="Test",
            habilidades={Habilidad.MANEJO_FELINOS: 3},  # nivel 3 < 4
            certificaciones=frozenset({Certificacion.TRANQUILIZANTE}),
            estado=EstadoCuidador.EJECUTANDO
        )
        
        tarea = Tarea(
            id="t1", tipo="captura",
            habilidades_requeridas=(HabilidadRequerida(Habilidad.MANEJO_FELINOS, 4),),
            estado=EstadoTarea.EN_CURSO,
            cuidadores_asignados=("c1",)
        )
        
        mundo = Mundo(cuidadores={"c1": cuidador}, tareas={"t1": tarea})
        
        violaciones = _verificar_invariante_1_habilidades_cuidador(mundo)
        assert len(violaciones) == 1
        assert "nivel 3 < 4" in violaciones[0].detalle
    
    def test_cuidador_falta_certificacion(self):
        cuidador = Cuidador(
            id="c1", nombre="Test",
            habilidades={Habilidad.MANEJO_FELINOS: 5},
            certificaciones=frozenset(),  # sin tranquilizante
            estado=EstadoCuidador.EJECUTANDO
        )
        
        tarea = Tarea(
            id="t1", tipo="captura",
            certificaciones_requeridas=frozenset({Certificacion.TRANQUILIZANTE}),
            estado=EstadoTarea.EN_CURSO,
            cuidadores_asignados=("c1",)
        )
        
        mundo = Mundo(cuidadores={"c1": cuidador}, tareas={"t1": tarea})
        
        violaciones = _verificar_invariante_1_habilidades_cuidador(mundo)
        assert len(violaciones) == 1
        assert "TRANQUILIZANTE" in violaciones[0].detalle

    def test_equipo_cubre_requisitos_repartidos_entre_cuidadores(self):
        cuidador_valido = Cuidador(
            id="c1", nombre="Válido",
            habilidades={Habilidad.MANEJO_FELINOS: 4},
            certificaciones=frozenset({Certificacion.TRANQUILIZANTE}),
            estado=EstadoCuidador.EJECUTANDO,
        )
        cuidador_aves = Cuidador(
            id="c2", nombre="Aves",
            habilidades={Habilidad.MANEJO_AVES: 3},
            estado=EstadoCuidador.EJECUTANDO,
        )
        tarea = Tarea(
            id="t1", tipo="captura",
            habilidades_requeridas=(
                HabilidadRequerida(Habilidad.MANEJO_FELINOS, 4),
                HabilidadRequerida(Habilidad.MANEJO_AVES, 3),
            ),
            certificaciones_requeridas=frozenset({Certificacion.TRANQUILIZANTE}),
            estado=EstadoTarea.EN_CURSO,
            cuidadores_asignados=("c1", "c2"),
        )
        mundo = Mundo(
            cuidadores={"c1": cuidador_valido, "c2": cuidador_aves},
            tareas={"t1": tarea},
        )

        violaciones = _verificar_invariante_1_habilidades_cuidador(mundo)

        assert violaciones == []

    def test_equipo_que_no_cubre_requisito_produce_violacion(self):
        cuidador = Cuidador(
            id="c1", nombre="Sin habilidad",
            estado=EstadoCuidador.EJECUTANDO,
        )
        tarea = Tarea(
            id="t1", tipo="captura",
            habilidades_requeridas=(
                HabilidadRequerida(Habilidad.MANEJO_FELINOS, 4),
            ),
            estado=EstadoTarea.EN_CURSO,
            cuidadores_asignados=("c1",),
        )

        violaciones = _verificar_invariante_1_habilidades_cuidador(
            Mundo(cuidadores={"c1": cuidador}, tareas={"t1": tarea})
        )

        assert len(violaciones) == 1
        assert violaciones[0].entidad_id == "t1"
        assert "MANEJO_FELINOS" in violaciones[0].detalle
    
    def test_solo_tareas_activas(self):
        """Solo verifica tareas en ASIGNADA, EN_CURSO, PAUSADA."""
        cuidador = Cuidador(
            id="c1", nombre="Test",
            habilidades={}, certificaciones=frozenset(),
            estado=EstadoCuidador.DISPONIBLE
        )
        
        # Tarea PENDIENTE no asignada - no debe verificar
        tarea_pendiente = Tarea(
            id="t1", tipo="captura",
            habilidades_requeridas=(HabilidadRequerida(Habilidad.MANEJO_FELINOS, 4),),
            estado=EstadoTarea.PENDIENTE,
            cuidadores_asignados=("c1",)
        )
        
        # Tarea ASIGNADA - sí debe verificar
        tarea_asignada = Tarea(
            id="t2", tipo="captura",
            habilidades_requeridas=(HabilidadRequerida(Habilidad.MANEJO_FELINOS, 4),),
            estado=EstadoTarea.ASIGNADA,
            cuidadores_asignados=("c1",)
        )
        
        mundo = Mundo(
            cuidadores={"c1": cuidador},
            tareas={"t1": tarea_pendiente, "t2": tarea_asignada}
        )
        
        violaciones = _verificar_invariante_1_habilidades_cuidador(mundo)
        # Solo debe fallar t2
        assert len(violaciones) == 1
        assert violaciones[0].entidad_id == "t2"


class TestInvariante2SolapamientoReservas:
    """Pruebas de invariante 2: solapamiento de reservas."""
    
    def setup_method(self):
        self.registro = RegistroReservas()
    
    def test_sin_solapamiento(self):
        r1 = Reserva(TipoRecurso.CUIDADOR, "c1", "t1", 100, 200)
        r2 = Reserva(TipoRecurso.CUIDADOR, "c1", "t2", 200, 300)  # borde: no solapa
        reservar_atomico(self.registro, [r1, r2])
        
        mundo = Mundo()
        violaciones = _verificar_invariante_2_solapamiento_reservas(mundo, self.registro)
        assert len(violaciones) == 0
    
    def test_con_solapamiento(self):
        r1 = Reserva(TipoRecurso.CUIDADOR, "c1", "t1", 100, 200)
        self.registro.agregar_reserva(r1)
        # agregar_reserva ahora valida solapamientos y lanza ReservaInvalida
        r2 = Reserva(TipoRecurso.CUIDADOR, "c1", "t2", 150, 250)  # solapa con r1
        with pytest.raises(Exception) as exc:
            self.registro.agregar_reserva(r2)
        assert "Solapamiento" in str(exc.value)
        
        # La invariante 2 detecta solapamientos en el registro
        # Como r2 no se agregó, no hay solapamiento en el registro
        mundo = Mundo()
        violaciones = _verificar_invariante_2_solapamiento_reservas(mundo, self.registro)
        assert len(violaciones) == 0
        
        # Restaurar un registro corrupto permite verificar que la invariante lo detecta.
        self.registro.restaurar({
            (TipoRecurso.CUIDADOR, "c1"): [r1, r2],
        })
        violaciones = _verificar_invariante_2_solapamiento_reservas(mundo, self.registro)
        assert len(violaciones) == 1
        assert "Solapamiento" in violaciones[0].detalle


class TestInvariante3UnaTareaActiva:
    """Pruebas de invariante 3: una tarea activa por cuidador."""
    
    def test_cuidador_sin_tareas_activas(self):
        cuidador = Cuidador(id="c1", nombre="Test", estado=EstadoCuidador.DISPONIBLE)
        mundo = Mundo(cuidadores={"c1": cuidador})
        
        violaciones = _verificar_invariante_3_una_tarea_activa(mundo)
        assert len(violaciones) == 0
    
    def test_cuidador_una_tarea_activa(self):
        cuidador = Cuidador(id="c1", nombre="Test", estado=EstadoCuidador.EJECUTANDO)
        tarea = Tarea(
            id="t1", tipo="test", estado=EstadoTarea.EN_CURSO,
            cuidadores_asignados=("c1",),
        )
        mundo = Mundo(cuidadores={"c1": cuidador}, tareas={"t1": tarea})
        
        violaciones = _verificar_invariante_3_una_tarea_activa(mundo)
        assert len(violaciones) == 0
    
    def test_cuidador_dos_tareas_activas(self):
        cuidador = Cuidador(id="c1", nombre="Test", estado=EstadoCuidador.EJECUTANDO)
        t1 = Tarea(
            id="t1", tipo="test", estado=EstadoTarea.EN_CURSO,
            cuidadores_asignados=("c0", "c1"),
        )
        t2 = Tarea(
            id="t2", tipo="test", estado=EstadoTarea.ASIGNADA,
            cuidadores_asignados=("c1",),
        )
        mundo = Mundo(cuidadores={"c1": cuidador}, tareas={"t1": t1, "t2": t2})
        
        violaciones = _verificar_invariante_3_una_tarea_activa(mundo)
        assert len(violaciones) == 1
        assert "2 tareas activas" in violaciones[0].detalle
        assert violaciones[0].entidad_id == "c1"


class TestInvariante4CapacidadVehiculoPlan:
    """INV-4 verifica capacidades a partir del plan de ejecución."""

    def test_plan_que_excede_capacidad_produce_violaciones(self):
        tarea = Tarea(
            id="t1", tipo="traslado", estado=EstadoTarea.ASIGNADA,
            cuidadores_asignados=("c1", "c2", "c3"),
        )
        plan = PlanEjecucion(
            tarea_id="t1",
            cuidadores=("c1", "c2", "c3"),
            vehiculo_id="v1",
            animales_transportados=("a1", "a2"),
            desde=10,
            hasta=20,
        )
        vehiculo = Vehiculo(
            id="v1", tipo=TipoVehiculo.CAMION_TRASLADO, velocidad=5,
            capacidad_personas=2, capacidad_animales=1,
            certificacion_requerida=Certificacion.CAMION_TRASLADO,
            ubicacion="garaje",
        )
        cuidadores = {
            cid: Cuidador(
                id=cid, nombre=cid, estado=EstadoCuidador.EJECUTANDO,
            )
            for cid in ("c1", "c2", "c3")
        }

        violaciones = _verificar_invariante_4_capacidad_vehiculo(
            Mundo(
                tareas={"t1": tarea}, planes={"t1": plan},
                vehiculos={"v1": vehiculo}, cuidadores=cuidadores,
            )
        )

        assert len(violaciones) == 2
        assert all(item.invariante == "INV-4-capacidad-vehiculo" for item in violaciones)

    def test_plan_dentro_de_capacidad_no_viola(self):
        tarea = Tarea(
            id="t1", tipo="traslado", estado=EstadoTarea.ASIGNADA,
            cuidadores_asignados=("c1", "c2"),
        )
        plan = PlanEjecucion(
            tarea_id="t1", cuidadores=("c1", "c2"), vehiculo_id="v1",
            animales_transportados=("a1",), desde=10, hasta=20,
        )
        vehiculo = Vehiculo(
            id="v1", tipo=TipoVehiculo.CAMION_TRASLADO, velocidad=5,
            capacidad_personas=2, capacidad_animales=1,
            certificacion_requerida=Certificacion.CAMION_TRASLADO,
            ubicacion="garaje",
        )

        assert _verificar_invariante_4_capacidad_vehiculo(
            Mundo(tareas={"t1": tarea}, planes={"t1": plan}, vehiculos={"v1": vehiculo})
        ) == []

    def test_plan_con_vehiculo_inexistente_produce_violacion(self):
        tarea = Tarea(
            id="t1", tipo="traslado", estado=EstadoTarea.ASIGNADA,
        )
        plan = PlanEjecucion(
            tarea_id="t1", cuidadores=("c1",), vehiculo_id="v-missing",
            desde=10, hasta=20,
        )

        violaciones = _verificar_invariante_4_capacidad_vehiculo(
            Mundo(tareas={"t1": tarea}, planes={"t1": plan})
        )

        assert len(violaciones) == 1
        assert violaciones[0].invariante == "INV-4-capacidad-vehiculo"


class TestInvariante5RutaJeepPlan:
    """INV-5 verifica rutas terrestres usando el grafo del mundo."""

    def _mundo(self, bloqueada=False, medios=None):
        tarea = Tarea(
            id="t1", tipo="traslado", nodo_destino="destino",
            estado=EstadoTarea.ASIGNADA, cuidadores_asignados=("c1",),
        )
        plan = PlanEjecucion(
            tarea_id="t1", cuidadores=("c1",), vehiculo_id="v1",
            desde=10, hasta=20, ruta=("garaje", "destino"),
        )
        vehiculo = Vehiculo(
            id="v1", tipo=TipoVehiculo.JEEP, velocidad=5,
            capacidad_personas=2, capacidad_animales=1,
            certificacion_requerida=Certificacion.JEEP, ubicacion="garaje",
        )
        arista = Arista(
            "garaje", "destino", 10,
            frozenset(medios if medios is not None else {MedioPermitido.JEEP}),
            bloqueada,
        )
        return Mundo(
            tareas={"t1": tarea}, planes={"t1": plan},
            vehiculos={"v1": vehiculo},
            nodos={
                "garaje": Nodo("garaje", TipoNodo.GARAJE, 0, 0),
                "destino": Nodo("destino", TipoNodo.RECINTO, 1, 1),
            },
            aristas={("garaje", "destino"): arista},
        )

    def test_ruta_jeep_valida_no_viola(self):
        assert _verificar_invariante_5_ruta_jeep(self._mundo()) == []

    def test_ruta_camion_bloqueada_produce_violacion(self):
        tarea = Tarea(
            id="t1", tipo="traslado", nodo_destino="destino",
            estado=EstadoTarea.ASIGNADA, cuidadores_asignados=("c1",),
        )
        plan = PlanEjecucion(
            tarea_id="t1", cuidadores=("c1",), vehiculo_id="v1",
            desde=10, hasta=20, ruta=("garaje", "destino"),
        )
        vehiculo = Vehiculo(
            id="v1", tipo=TipoVehiculo.CAMION_TRASLADO, velocidad=5,
            capacidad_personas=2, capacidad_animales=1,
            certificacion_requerida=Certificacion.CAMION_TRASLADO,
            ubicacion="garaje",
        )
        mundo = Mundo(
            tareas={"t1": tarea}, planes={"t1": plan},
            vehiculos={"v1": vehiculo},
            nodos={
                "garaje": Nodo("garaje", TipoNodo.GARAJE, 0, 0),
                "destino": Nodo("destino", TipoNodo.RECINTO, 1, 1),
            },
            aristas={
                ("garaje", "destino"): Arista(
                    "garaje", "destino", 10,
                    frozenset({MedioPermitido.JEEP}),
                    bloqueada=True,
                ),
            },
        )

        violaciones = _verificar_invariante_5_ruta_jeep(mundo)

        assert len(violaciones) == 1
        assert violaciones[0].invariante == "INV-5-jeep-aristas-validas"

    @pytest.mark.parametrize("bloqueada, medios", [
        (True, {MedioPermitido.JEEP}),
        (False, {MedioPermitido.PIE}),
    ])
    def test_ruta_jeep_no_transitable_produce_violacion(self, bloqueada, medios):
        violaciones = _verificar_invariante_5_ruta_jeep(
            self._mundo(bloqueada=bloqueada, medios=medios)
        )

        assert len(violaciones) == 1
        assert violaciones[0].invariante == "INV-5-jeep-aristas-validas"

    def test_plan_con_vehiculo_inexistente_produce_violacion(self):
        tarea = Tarea(
            id="t1", tipo="traslado", estado=EstadoTarea.ASIGNADA,
        )
        plan = PlanEjecucion(
            tarea_id="t1", cuidadores=("c1",), vehiculo_id="v-missing",
            desde=10, hasta=20,
        )

        violaciones = _verificar_invariante_5_ruta_jeep(
            Mundo(tareas={"t1": tarea}, planes={"t1": plan})
        )

        assert len(violaciones) == 1
        assert violaciones[0].invariante == "INV-5-jeep-aristas-validas"


def test_inv9_reporta_referencias_rotas_en_planes():
    plan = PlanEjecucion(
        tarea_id="missing-task",
        cuidadores=("missing-caregiver",),
        vehiculo_id="missing-vehicle",
        equipos=("missing-equipment",),
        desde=10,
        hasta=20,
    )
    mundo = Mundo(planes={"missing-task": plan})

    violaciones, _ = verificar_invariantes(mundo, RegistroReservas())

    assert len(violaciones) == 4
    assert all(
        item.invariante == "INV-9-planes-consistentes"
        for item in violaciones
    )
    assert {item.detalle for item in violaciones} == {
        "La tarea missing-task no existe",
        "El cuidador missing-caregiver no existe",
        "El vehículo missing-vehicle no existe",
        "El equipo missing-equipment no existe",
    }


def test_inv9_no_viola_un_plan_con_referencias_existentes():
    tarea = Tarea(id="t1", tipo="test")
    plan = PlanEjecucion(
        tarea_id="t1", cuidadores=("c1",), vehiculo_id="v1",
        equipos=("e1",), desde=10, hasta=20,
    )
    mundo = Mundo(
        tareas={"t1": tarea},
        cuidadores={"c1": Cuidador("c1", "Test")},
        vehiculos={
            "v1": Vehiculo(
                id="v1", tipo=TipoVehiculo.CAMION_TRASLADO, velocidad=5,
                capacidad_personas=2, capacidad_animales=1,
                certificacion_requerida=Certificacion.CAMION_TRASLADO,
                ubicacion="garaje",
            ),
        },
        equipos={"e1": Equipo("e1", TipoEquipo.RED_CAPTURA, "bodega")},
        planes={"t1": plan},
    )

    assert _verificar_invariante_9_planes_consistentes(mundo) == []


def test_tarea_activa_sin_plan_viola_inv10_sin_omitir_inv4_inv5():
    tarea = Tarea(
        id="t1", tipo="test", estado=EstadoTarea.ASIGNADA,
        cuidadores_asignados=("c1",),
    )
    mundo = Mundo(
        tareas={"t1": tarea},
        cuidadores={"c1": Cuidador("c1", "Test", estado=EstadoCuidador.EJECUTANDO)},
    )

    violaciones, no_verificadas = verificar_invariantes(
        mundo, RegistroReservas(),
    )

    assert any(
        item.invariante == "INV-10-tarea-plan" and item.entidad_id == "t1"
        for item in violaciones
    )
    assert not any(
        item.invariante in {
            "INV-4-capacidad-vehiculo", "INV-5-jeep-aristas-validas",
        }
        for item in no_verificadas
    )


def test_inv10_tarea_activa_con_plan_y_cuidadores_coincidentes():
    tarea = Tarea(
        id="t1", tipo="test", estado=EstadoTarea.ASIGNADA,
        cuidadores_asignados=("c1",),
    )
    plan = PlanEjecucion(
        tarea_id="t1", cuidadores=("c1",), desde=10, hasta=20,
    )
    mundo = Mundo(
        tareas={"t1": tarea},
        cuidadores={"c1": Cuidador("c1", "Test")},
        planes={"t1": plan},
    )

    assert _verificar_invariante_10_tarea_plan(mundo) == []


def test_inv10_detecta_cuidadores_distintos_entre_tarea_y_plan():
    tarea = Tarea(
        id="t1", tipo="test", estado=EstadoTarea.ASIGNADA,
        cuidadores_asignados=("c1",),
    )
    plan = PlanEjecucion(
        tarea_id="t1", cuidadores=("c2",), desde=10, hasta=20,
    )
    mundo = Mundo(tareas={"t1": tarea}, planes={"t1": plan})

    violaciones = _verificar_invariante_10_tarea_plan(mundo)

    assert len(violaciones) == 1
    assert violaciones[0].invariante == "INV-10-tarea-plan"


class TestInvariante6AnimalEnRecintoValido:
    """Pruebas de invariante 6: animal en recinto que admite su especie."""
    
    def test_animal_en_recinto_admitido(self):
        especie = ESPECIES_CATALOGO["jaguar"]
        recinto = Recinto(
            nodo_id="rec1", tipo=TipoRecinto.ABIERTO,
            especies_admitidas=frozenset({"jaguar"}), capacidad=2
        )
        
        animal = Animal(
            id="a1", especie=especie, recinto_origen="rec1",
            ubicacion="rec1", estado=EstadoAnimal.EN_RECINTO
        )
        
        mundo = Mundo(recintos={"rec1": recinto}, animales={"a1": animal})
        
        violaciones = _verificar_invariante_6_animal_en_recinto_valido(mundo)
        assert len(violaciones) == 0
    
    def test_animal_en_recinto_no_admitido(self):
        especie = ESPECIES_CATALOGO["jaguar"]
        recinto = Recinto(
            nodo_id="rec1", tipo=TipoRecinto.AVIARIO,  # aviario no admite jaguar
            especies_admitidas=frozenset({"guacamaya_roja"}), capacidad=2
        )
        
        animal = Animal(
            id="a1", especie=especie, recinto_origen="rec1",
            ubicacion="rec1", estado=EstadoAnimal.EN_RECINTO
        )
        
        mundo = Mundo(recintos={"rec1": recinto}, animales={"a1": animal})
        
        violaciones = _verificar_invariante_6_animal_en_recinto_valido(mundo)
        assert len(violaciones) == 1
        assert "no admite" in violaciones[0].detalle
    
    def test_especie_no_en_catalogo(self):
        """Especie no en catálogo produce violación."""
        # Crear una especie que no está en ESPECIES_CATALOGO
        from zoo_ops.dominio.catalogos import Especie
        from zoo_ops.dominio.enums import Medio, Peligrosidad, TipoVehiculo, TipoRecinto
        
        especie_desconocida = Especie(
            nombre="EspecieDesconocida",
            medio=Medio.TERRESTRE,
            peligrosidad=Peligrosidad.MEDIA,
            requiere_tranquilizante=False,
            habilidad_requerida=Habilidad.MANEJO_FELINOS,
            nivel_minimo_habilidad=3,
            tipo_vehiculo_traslado=TipoVehiculo.JEEP,
            minimo_personas_traslado=2,
            tipo_recinto_requerido=TipoRecinto.ABIERTO,
        )
        
        recinto = Recinto(
            nodo_id="rec1", tipo=TipoRecinto.ABIERTO,
            especies_admitidas=frozenset({"jaguar"}), capacidad=2
        )
        
        animal = Animal(
            id="a1", especie=especie_desconocida, recinto_origen="rec1",
            ubicacion="rec1", estado=EstadoAnimal.EN_RECINTO
        )
        
        mundo = Mundo(recintos={"rec1": recinto}, animales={"a1": animal})
        
        violaciones = _verificar_invariante_6_animal_en_recinto_valido(mundo)
        assert len(violaciones) == 1
        assert "no está en el catálogo" in violaciones[0].detalle


class TestInvariante8DependenciasTarea:
    """Pruebas de invariante 8: dependencias de tareas."""
    
    def test_tarea_sin_dependencias(self):
        tarea = Tarea(id="t1", tipo="test", estado=EstadoTarea.EN_CURSO)
        mundo = Mundo(tareas={"t1": tarea})
        
        violaciones = _verificar_invariante_8_dependencias_tarea(mundo)
        assert len(violaciones) == 0
    
    def test_tarea_dependencia_completada(self):
        t1 = Tarea(id="t1", tipo="test", estado=EstadoTarea.COMPLETADA)
        t2 = Tarea(id="t2", tipo="test", estado=EstadoTarea.EN_CURSO, dependencias=frozenset({"t1"}))
        mundo = Mundo(tareas={"t1": t1, "t2": t2})
        
        violaciones = _verificar_invariante_8_dependencias_tarea(mundo)
        assert len(violaciones) == 0
    
    def test_tarea_dependencia_pendiente(self):
        t1 = Tarea(id="t1", tipo="test", estado=EstadoTarea.PENDIENTE)
        t2 = Tarea(id="t2", tipo="test", estado=EstadoTarea.EN_CURSO, dependencias=frozenset({"t1"}))
        mundo = Mundo(tareas={"t1": t1, "t2": t2})
        
        violaciones = _verificar_invariante_8_dependencias_tarea(mundo)
        assert len(violaciones) == 1
        assert "no completada" in violaciones[0].detalle
    
    def test_tarea_completada_con_dependencia_pendiente(self):
        """COMPLETADA también viola si dependencias pendientes."""
        t1 = Tarea(id="t1", tipo="test", estado=EstadoTarea.PENDIENTE)
        t2 = Tarea(id="t2", tipo="test", estado=EstadoTarea.COMPLETADA, dependencias=frozenset({"t1"}))
        mundo = Mundo(tareas={"t1": t1, "t2": t2})
        
        violaciones = _verificar_invariante_8_dependencias_tarea(mundo)
        assert len(violaciones) == 1
    
    def test_dependencia_inexistente(self):
        """Dependencia que no existe en el mundo es violación."""
        t2 = Tarea(id="t2", tipo="test", estado=EstadoTarea.EN_CURSO, dependencias=frozenset({"t1_inexistente"}))
        mundo = Mundo(tareas={"t2": t2})
        
        violaciones = _verificar_invariante_8_dependencias_tarea(mundo)
        assert len(violaciones) == 1
        assert "no existe" in violaciones[0].detalle


class TestVerificarInvariantesCompleto:
    """Pruebas de la función principal verificar_invariantes."""
    
    def setup_method(self):
        self.registro = RegistroReservas()
    
    def test_mundo_valido_sin_violaciones(self):
        cuidador = Cuidador(
            id="c1", nombre="Test",
            habilidades={Habilidad.MANEJO_FELINOS: 5},
            certificaciones=frozenset({Certificacion.TRANQUILIZANTE}),
            estado=EstadoCuidador.DISPONIBLE
        )
        
        especie = ESPECIES_CATALOGO["jaguar"]
        recinto = Recinto(
            nodo_id="rec1", tipo=TipoRecinto.ABIERTO,
            especies_admitidas=frozenset({"jaguar"}), capacidad=2
        )
        
        animal = Animal(
            id="a1", especie=especie, recinto_origen="rec1",
            ubicacion="rec1", estado=EstadoAnimal.EN_RECINTO
        )
        
        mundo = Mundo(
            cuidadores={"c1": cuidador},
            recintos={"rec1": recinto},
            animales={"a1": animal}
        )
        
        violaciones, no_verificadas = verificar_invariantes(mundo, self.registro)
        assert len(violaciones) == 0
        assert no_verificadas == []
    
    def test_formatear_violaciones(self):
        v = ViolacionInvariante("INV-1", "Cuidador", "c1", "falta habilidad")
        resultado = formatear_violaciones([v])
        assert "INV-1" in resultado
        assert "Cuidador/c1" in resultado
        assert "falta habilidad" in resultado
    
    def test_formatear_vacio(self):
        assert formatear_violaciones([]) == "Sin violaciones"
    
    def test_formatear_no_verificadas(self):
        nv = NoVerificada("INV-4", "requiere motor de asignación")
        resultado = formatear_no_verificadas([nv])
        assert "INV-4" in resultado
        assert "motor de asignación" in resultado
    
    def test_formatear_no_verificadas_vacio(self):
        assert formatear_no_verificadas([]) == "Todas las invariantes verificadas"
    
    def test_assert_sin_violaciones_pasa(self):
        mundo = Mundo()
        assert_sin_violaciones(mundo, self.registro)  # no debe lanzar
    
    def test_assert_sin_violaciones_falla(self):
        cuidador = Cuidador(
            id="c1", nombre="Test",
            habilidades={}, certificaciones=frozenset(),
            estado=EstadoCuidador.EJECUTANDO
        )
        tarea = Tarea(
            id="t1", tipo="test",
            habilidades_requeridas=(HabilidadRequerida(Habilidad.MANEJO_FELINOS, 4),),
            estado=EstadoTarea.EN_CURSO, cuidadores_asignados=("c1",)
        )
        mundo = Mundo(cuidadores={"c1": cuidador}, tareas={"t1": tarea})
        
        with pytest.raises(AssertionError):
            assert_sin_violaciones(mundo, self.registro)


class TestInvariante7Eventos:
    """INV-7: el mundo vivo debe coincidir con el reconstruido desde el inicial."""

    def setup_method(self):
        self.registro = RegistroReservas()

    def test_eventos_reproducen_el_mundo(self):
        inicial = Mundo(cuidadores={"c1": Cuidador(id="c1", nombre="C")})
        mundo = copy.deepcopy(inicial)
        registro = RegistroEventos()

        ejecutar_transicion(
            mundo, registro, "Cuidador", "c1",
            EstadoCuidador.DISPONIBLE, 100, "inicio de turno",
        )

        assert verificar_invariante_eventos(inicial, mundo, registro) == []

    def test_cambio_fuera_de_eventos_se_detecta(self):
        inicial = Mundo(cuidadores={"c1": Cuidador(id="c1", nombre="C")})
        mundo = copy.deepcopy(inicial)
        registro = RegistroEventos()

        # Mutación directa del contenedor: no genera evento, por tanto INV-7 debe verla.
        mundo.cuidadores["c1"] = Cuidador(
            id="c1", nombre="C", estado=EstadoCuidador.ASIGNADO,
        )

        violaciones = verificar_invariante_eventos(inicial, mundo, registro)

        assert len(violaciones) == 1
        assert violaciones[0].invariante == "INV-7-eventos-coinciden"

    def test_sin_estado_inicial_inv7_queda_no_verificada(self):
        _, no_verificadas = verificar_invariantes(
            Mundo(), self.registro, RegistroEventos(),
        )

        ids = {nv.invariante for nv in no_verificadas}
        assert "INV-7-eventos-coinciden" in ids


# Importar Reserva para test de invariante 2
from zoo_ops.dominio.reservas import Reserva, TipoRecurso