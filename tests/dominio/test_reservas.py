"""
Pruebas unitarias para reservas.py - sistema de reservas atómicas.
"""

import pytest
from zoo_ops.dominio.reservas import (
    TipoRecurso, Reserva, RegistroReservas,
    reservar_atomico, liberar_reservas_tarea, verificar_disponibilidad_recurso,
    paquete_de_reservas, reservar_plan, _orden_determinista_recursos,
)
from zoo_ops.dominio.entidades import (
    Arista, Cuidador, Vehiculo, Equipo, Tarea, HabilidadRequerida, Mundo, Nodo,
)
from zoo_ops.dominio.enums import (
    EstadoCuidador, EstadoEquipo, EstadoVehiculo, TipoVehiculo, TipoEquipo,
    Habilidad, Certificacion, MedioPermitido, TipoNodo,
)
from zoo_ops.dominio.errores import (
    PlanInvalido, ReservaAtomicaFallida, ReservaInvalida,
)
from zoo_ops.dominio.plan import PlanEjecucion, validar_plan


class TestReserva:
    """Pruebas de la clase Reserva."""
    
    def test_crear_reserva_valida(self):
        r = Reserva(
            recurso_tipo=TipoRecurso.CUIDADOR,
            recurso_id="c1",
            tarea_id="t1",
            desde=100,
            hasta=200
        )
        assert r.recurso_tipo == TipoRecurso.CUIDADOR
        assert r.recurso_id == "c1"
        assert r.tarea_id == "t1"
        assert r.desde == 100
        assert r.hasta == 200
    
    def test_reserva_desde_mayor_que_hasta_falla(self):
        with pytest.raises(ReservaInvalida):
            Reserva(TipoRecurso.CUIDADOR, "c1", "t1", 200, 100)
    
    def test_reserva_igual_desde_hasta_falla(self):
        with pytest.raises(ReservaInvalida):
            Reserva(TipoRecurso.CUIDADOR, "c1", "t1", 100, 100)
    
    def test_solapa_con_mismo_recurso(self):
        r1 = Reserva(TipoRecurso.CUIDADOR, "c1", "t1", 100, 200)
        r2 = Reserva(TipoRecurso.CUIDADOR, "c1", "t2", 150, 250)
        r3 = Reserva(TipoRecurso.CUIDADOR, "c1", "t3", 200, 300)  # borde: no solapa
        r4 = Reserva(TipoRecurso.VEHICULO, "v1", "t1", 100, 200)  # distinto recurso
        
        assert r1.solapa_con(r2) is True
        assert r1.solapa_con(r3) is False  # [100,200) y [200,300) no se solapan
        assert r1.solapa_con(r4) is False  # distinto tipo de recurso
    
    def test_solapa_con_inverso(self):
        r1 = Reserva(TipoRecurso.CUIDADOR, "c1", "t1", 100, 200)
        r2 = Reserva(TipoRecurso.CUIDADOR, "c1", "t2", 50, 150)
        
        assert r1.solapa_con(r2) is True
        assert r2.solapa_con(r1) is True


class TestRegistroReservas:
    """Pruebas del registro de reservas."""
    
    def setup_method(self):
        self.registro = RegistroReservas()
    
    def test_verificar_disponibilidad_vacio(self):
        assert self.registro.verificar_disponibilidad(TipoRecurso.CUIDADOR, "c1", 100, 200) is True

    def test_verificar_disponibilidad_sin_reservas_no_muta_el_registro(self):
        antes = self.registro.reservas_por_recurso()

        assert self.registro.verificar_disponibilidad(
            TipoRecurso.CUIDADOR, "c1", 100, 200,
        ) is True

        assert self.registro.reservas_por_recurso() == antes
    
    def test_agregar_y_verificar(self):
        r = Reserva(TipoRecurso.CUIDADOR, "c1", "t1", 100, 200)
        self.registro.agregar_reserva(r)
        
        assert self.registro.verificar_disponibilidad(TipoRecurso.CUIDADOR, "c1", 100, 200) is False
        assert self.registro.verificar_disponibilidad(TipoRecurso.CUIDADOR, "c1", 50, 150) is False
        assert self.registro.verificar_disponibilidad(TipoRecurso.CUIDADOR, "c1", 200, 300) is True
        assert self.registro.verificar_disponibilidad(TipoRecurso.CUIDADOR, "c2", 100, 200) is True
    
    def test_agregar_reserva_solapada_lanza_error(self):
        r1 = Reserva(TipoRecurso.CUIDADOR, "c1", "t1", 100, 200)
        self.registro.agregar_reserva(r1)
        r2 = Reserva(TipoRecurso.CUIDADOR, "c1", "t2", 150, 250)  # solapa
        
        with pytest.raises(Exception) as exc:
            self.registro.agregar_reserva(r2)
        assert "Solapamiento" in str(exc.value)
    
    def test_liberar_reservas_tarea(self):
        r1 = Reserva(TipoRecurso.CUIDADOR, "c1", "t1", 100, 200)
        r2 = Reserva(TipoRecurso.VEHICULO, "v1", "t1", 100, 200)
        r3 = Reserva(TipoRecurso.CUIDADOR, "c1", "t2", 300, 400)
        
        self.registro.agregar_reserva(r1)
        self.registro.agregar_reserva(r2)
        self.registro.agregar_reserva(r3)
        
        liberadas = self.registro.liberar_reservas_de_tarea("t1")
        
        assert len(liberadas) == 2
        assert self.registro.verificar_disponibilidad(TipoRecurso.CUIDADOR, "c1", 100, 200) is True
        assert self.registro.verificar_disponibilidad(TipoRecurso.VEHICULO, "v1", 100, 200) is True
        # t2 sigue reservada
        assert self.registro.verificar_disponibilidad(TipoRecurso.CUIDADOR, "c1", 300, 400) is False
    
    def test_obtener_reservas_tarea(self):
        r1 = Reserva(TipoRecurso.CUIDADOR, "c1", "t1", 100, 200)
        r2 = Reserva(TipoRecurso.VEHICULO, "v1", "t1", 100, 200)
        self.registro.agregar_reserva(r1)
        self.registro.agregar_reserva(r2)
        
        reservas = self.registro.obtener_reservas_de_tarea("t1")
        assert len(reservas) == 2


class TestReservarAtomico:
    """Pruebas de reserva atómica (todo o nada)."""
    
    def setup_method(self):
        self.registro = RegistroReservas()
    
    def test_reservar_atomico_exito(self):
        reservas = [
            Reserva(TipoRecurso.CUIDADOR, "c1", "t1", 100, 200),
            Reserva(TipoRecurso.VEHICULO, "v1", "t1", 100, 200),
        ]
        
        resultado = reservar_atomico(self.registro, reservas)
        
        assert len(resultado) == 2
        assert self.registro.verificar_disponibilidad(TipoRecurso.CUIDADOR, "c1", 100, 200) is False
        assert self.registro.verificar_disponibilidad(TipoRecurso.VEHICULO, "v1", 100, 200) is False
    
    def test_reservar_atomico_cuidador_vehiculo_equipo_mismo_intervalo(self):
        """Paquete con cuidador, vehículo y equipo distintos en el MISMO intervalo se reserva bien."""
        reservas = [
            Reserva(TipoRecurso.CUIDADOR, "c1", "t1", 100, 200),
            Reserva(TipoRecurso.VEHICULO, "v1", "t1", 100, 200),
            Reserva(TipoRecurso.EQUIPO, "e1", "t1", 100, 200),
        ]
        
        resultado = reservar_atomico(self.registro, reservas)
        
        assert len(resultado) == 3
        assert self.registro.verificar_disponibilidad(TipoRecurso.CUIDADOR, "c1", 100, 200) is False
        assert self.registro.verificar_disponibilidad(TipoRecurso.VEHICULO, "v1", 100, 200) is False
        assert self.registro.verificar_disponibilidad(TipoRecurso.EQUIPO, "e1", 100, 200) is False
    
    def test_reservar_atomico_falla_solapamiento_intra_paquete(self):
        """Dos reservas solapadas del mismo recurso en un paquete se rechazan sin crear ninguna."""
        r1 = Reserva(TipoRecurso.CUIDADOR, "c1", "t1", 100, 200)
        r2 = Reserva(TipoRecurso.CUIDADOR, "c1", "t2", 150, 250)  # solapa con r1
        
        with pytest.raises(ReservaAtomicaFallida) as exc:
            reservar_atomico(self.registro, [r1, r2])
        
        assert "intra-paquete" in str(exc.value)
        # Verificar rollback: ninguna reserva creada
        assert self.registro.verificar_disponibilidad(TipoRecurso.CUIDADOR, "c1", 100, 200) is True
        assert self.registro.verificar_disponibilidad(TipoRecurso.CUIDADOR, "c1", 150, 250) is True
    
    def test_reservar_atomico_intervalo_vacio_invertido(self):
        """Intervalo vacío o invertido se rechaza."""
        with pytest.raises(ReservaInvalida):
            Reserva(TipoRecurso.CUIDADOR, "c1", "t1", 100, 100)
        with pytest.raises(ReservaInvalida):
            Reserva(TipoRecurso.CUIDADOR, "c1", "t1", 200, 100)


class TestRegistroReservasEliminarReserva:
    """Pruebas del método eliminar_reserva."""
    
    def setup_method(self):
        self.registro = RegistroReservas()
    
    def test_eliminar_reserva_existente(self):
        r = Reserva(TipoRecurso.CUIDADOR, "c1", "t1", 100, 200)
        self.registro.agregar_reserva(r)
        
        resultado = self.registro.eliminar_reserva(r)
        
        assert resultado is True
        assert self.registro.verificar_disponibilidad(TipoRecurso.CUIDADOR, "c1", 100, 200) is True
    
    def test_eliminar_reserva_inexistente(self):
        r = Reserva(TipoRecurso.CUIDADOR, "c1", "t1", 100, 200)
        # No agregar al registro
        
        resultado = self.registro.eliminar_reserva(r)
        
        assert resultado is False


class TestRollbackForzado:
    """Pruebas de reversión ante fallo forzado durante inserción."""
    
    def setup_method(self):
        self.registro = RegistroReservas()
    
    def test_rollback_ante_fallo_insercion(self):
        """Un fallo forzado durante la inserción deja el registro como estaba."""
        
        class RegistroConFallo(RegistroReservas):
            def __init__(self):
                super().__init__()
                self.contador_inserciones = 0
            
            def agregar_reserva(self, reserva: Reserva) -> None:
                self.contador_inserciones += 1
                if self.contador_inserciones == 2:
                    raise RuntimeError("Fallo forzado en segunda inserción")
                super().agregar_reserva(reserva)
        
        registro = RegistroConFallo()
        
        r1 = Reserva(TipoRecurso.CUIDADOR, "c1", "t1", 100, 200)
        r2 = Reserva(TipoRecurso.VEHICULO, "v1", "t1", 100, 200)
        
        with pytest.raises(RuntimeError, match="Fallo forzado"):
            reservar_atomico(registro, [r1, r2])
        
        # Verificar rollback: ninguna reserva creada
        assert registro.verificar_disponibilidad(TipoRecurso.CUIDADOR, "c1", 100, 200) is True
        assert registro.verificar_disponibilidad(TipoRecurso.VEHICULO, "v1", 100, 200) is True
    
    def test_reservar_atomico_falla_solapamiento_con_existentes(self):
        # Primera reserva OK
        r1 = Reserva(TipoRecurso.CUIDADOR, "c1", "t1", 100, 200)
        reservar_atomico(self.registro, [r1])
        
        # Segunda reserva falla por solapamiento con existente
        r2 = Reserva(TipoRecurso.CUIDADOR, "c1", "t2", 150, 250)
        r3 = Reserva(TipoRecurso.VEHICULO, "v1", "t2", 100, 200)
        
        with pytest.raises(ReservaAtomicaFallida) as exc:
            reservar_atomico(self.registro, [r2, r3])
        
        # Verificar que NO se creó ninguna reserva nueva (todo o nada)
        # La reserva original t1 (100-200) solapa con 150-250, así que NO debe estar disponible
        assert self.registro.verificar_disponibilidad(TipoRecurso.CUIDADOR, "c1", 150, 250) is False
        # El vehículo v1 no tenía reserva original, y la atómica falló, así que debe estar disponible
        assert self.registro.verificar_disponibilidad(TipoRecurso.VEHICULO, "v1", 100, 200) is True
        # La reserva original sigue ahí
        assert self.registro.verificar_disponibilidad(TipoRecurso.CUIDADOR, "c1", 100, 200) is False
    
    def test_reservar_atomico_falla_solapamiento_intra_paquete(self):
        # Dos reservas del mismo recurso en el mismo paquete que se solapan
        r1 = Reserva(TipoRecurso.CUIDADOR, "c1", "t1", 100, 200)
        r2 = Reserva(TipoRecurso.CUIDADOR, "c1", "t2", 150, 250)  # solapa con r1
        
        with pytest.raises(ReservaAtomicaFallida) as exc:
            reservar_atomico(self.registro, [r1, r2])
        
        assert "intra-paquete" in str(exc.value)
        # Ninguna reserva debe haberse creado
        assert self.registro.verificar_disponibilidad(TipoRecurso.CUIDADOR, "c1", 100, 200) is True
        assert self.registro.verificar_disponibilidad(TipoRecurso.CUIDADOR, "c1", 150, 250) is True
    
    def test_reservar_atomico_lista_vacia(self):
        resultado = reservar_atomico(self.registro, [])
        assert resultado == []
    
    def test_orden_determinista(self):
        """Verifica que el orden determinista evita deadlocks."""
        reservas = [
            Reserva(TipoRecurso.VEHICULO, "v2", "t1", 100, 200),
            Reserva(TipoRecurso.CUIDADOR, "c1", "t1", 100, 200),
            Reserva(TipoRecurso.EQUIPO, "e1", "t1", 100, 200),
            Reserva(TipoRecurso.CUIDADOR, "c0", "t1", 100, 200),
        ]
        
        ordenadas = _orden_determinista_recursos(reservas)
        
        # Orden por valor del enum: CUIDADOR (1) < VEHICULO (2) < EQUIPO (3)
        # Dentro de mismo tipo: por recurso_id, luego por desde
        assert ordenadas[0].recurso_tipo == TipoRecurso.CUIDADOR
        assert ordenadas[0].recurso_id == "c0"
        assert ordenadas[1].recurso_tipo == TipoRecurso.CUIDADOR
        assert ordenadas[1].recurso_id == "c1"
        assert ordenadas[2].recurso_tipo == TipoRecurso.VEHICULO
        assert ordenadas[3].recurso_tipo == TipoRecurso.EQUIPO
    
    def test_excluir_tarea_en_verificacion(self):
        r1 = Reserva(TipoRecurso.CUIDADOR, "c1", "t1", 100, 200)
        self.registro.agregar_reserva(r1)
        
        # Sin excluir: no disponible
        assert self.registro.verificar_disponibilidad(TipoRecurso.CUIDADOR, "c1", 100, 200) is False
        
        # Excluyendo t1: disponible (para reprogramar la misma tarea)
        assert self.registro.verificar_disponibilidad(
            TipoRecurso.CUIDADOR, "c1", 100, 200, excluir_tarea="t1"
        ) is True


def _plan_reserva(
    tarea_id="t1",
    cuidadores=("c1",),
    vehiculo_id=None,
    equipos=(),
    desde=100,
    hasta=200,
    ruta=(),
):
    return PlanEjecucion(
        tarea_id=tarea_id,
        cuidadores=cuidadores,
        vehiculo_id=vehiculo_id,
        equipos=equipos,
        desde=desde,
        hasta=hasta,
        ruta=ruta,
    )


def _mundo_con_tarea(tarea, **cambios):
    valores = {"tareas": {tarea.id: tarea}}
    valores.update(cambios)
    return Mundo(**valores)


class TestPaqueteDeReservas:
    """Pruebas de construcción del paquete desde un plan."""

    def test_crear_reservas_basicas(self):
        plan = _plan_reserva(
            vehiculo_id="v1", equipos=("e1", "e2"), desde=1000, hasta=4600,
        )

        reservas = paquete_de_reservas(plan)

        assert len(reservas) == 4
        tipos = {reserva.recurso_tipo for reserva in reservas}
        assert TipoRecurso.CUIDADOR in tipos
        assert TipoRecurso.VEHICULO in tipos
        assert TipoRecurso.EQUIPO in tipos
        assert sum(
            1 for reserva in reservas
            if reserva.recurso_tipo == TipoRecurso.EQUIPO
        ) == 2

    def test_un_plan_sin_recursos_opcionales_reserva_su_cuidador(self):
        reservas = paquete_de_reservas(_plan_reserva())

        assert len(reservas) == 1
        assert reservas[0].recurso_tipo == TipoRecurso.CUIDADOR

    def test_plan_rechaza_intervalo_invalido(self):
        with pytest.raises(PlanInvalido):
            _plan_reserva(desde=200, hasta=100)


class TestValidarPlanDesdeReservas:
    """Pruebas migradas de validación de recursos al plan de ejecución."""

    def test_validar_cuidador_habilidades(self):
        cuidador = Cuidador(
            id="c1", nombre="Test",
            habilidades={Habilidad.MANEJO_FELINOS: 3},  # nivel 3, requiere 4
            certificaciones=frozenset({Certificacion.TRANQUILIZANTE}),
            estado=EstadoCuidador.DISPONIBLE
        )
        
        tarea = Tarea(
            id="t1", tipo="captura",
            habilidades_requeridas=(HabilidadRequerida(Habilidad.MANEJO_FELINOS, 4),),
            certificaciones_requeridas=frozenset({Certificacion.TRANQUILIZANTE})
        )
        
        mundo = _mundo_con_tarea(tarea, cuidadores={"c1": cuidador})
        errores = validar_plan(mundo, _plan_reserva())
        
        assert len(errores) == 1
        assert "nivel 3 < 4" in errores[0]
    
    def test_validar_cuidador_certificacion_faltante(self):
        cuidador = Cuidador(
            id="c1", nombre="Test",
            habilidades={Habilidad.MANEJO_FELINOS: 5},
            certificaciones=frozenset(),  # sin certificaciones
            estado=EstadoCuidador.DISPONIBLE
        )
        
        tarea = Tarea(
            id="t1", tipo="captura",
            certificaciones_requeridas=frozenset({Certificacion.TRANQUILIZANTE})
        )
        
        mundo = _mundo_con_tarea(tarea, cuidadores={"c1": cuidador})
        errores = validar_plan(mundo, _plan_reserva())
        
        assert any("TRANQUILIZANTE" in e for e in errores)
    
    def test_validar_cuidador_estado_no_disponible(self):
        cuidador = Cuidador(
            id="c1", nombre="Test",
            habilidades={Habilidad.MANEJO_FELINOS: 5},
            certificaciones=frozenset({Certificacion.TRANQUILIZANTE}),
            estado=EstadoCuidador.EN_CAMINO  # no disponible
        )
        
        tarea = Tarea(id="t1", tipo="captura")
        
        mundo = _mundo_con_tarea(tarea, cuidadores={"c1": cuidador})
        errores = validar_plan(mundo, _plan_reserva())
        assert any("no está disponible" in e.lower() for e in errores)

    def test_validar_cuidador_en_estado_asignado_no_esta_disponible(self):
        cuidador = Cuidador(
            id="c1", nombre="Test", estado=EstadoCuidador.ASIGNADO,
        )
        tarea = Tarea(id="t1", tipo="captura")
        mundo = _mundo_con_tarea(tarea, cuidadores={"c1": cuidador})

        errores = validar_plan(
            mundo, _plan_reserva(),
        )

        assert any("no está disponible" in error.lower() for error in errores)

    def test_validar_recursos_rechaza_diccionarios_en_lugar_de_mundo(self):
        with pytest.raises(TypeError, match="Mundo"):
            validar_plan(
                {"cuidadores": {}, "vehiculos": {}, "equipos": {}, "tareas": {}},
                _plan_reserva(),
            )
    
    def test_validar_vehiculo_certificacion_cuidador(self):
        cuidador = Cuidador(
            id="c1", nombre="Test",
            certificaciones=frozenset({Certificacion.JEEP}),  # solo jeep
            estado=EstadoCuidador.DISPONIBLE
        )
        
        vehiculo = Vehiculo(
            id="v1", tipo=TipoVehiculo.CAMION_TRASLADO,  # requiere camion_traslado
            velocidad=5.0, capacidad_personas=3, capacidad_animales=2,
            certificacion_requerida=Certificacion.CAMION_TRASLADO,
            ubicacion="garaje", estado=EstadoVehiculo.DISPONIBLE
        )
        
        tarea = Tarea(id="t1", tipo="traslado")
        
        mundo = _mundo_con_tarea(
            tarea, cuidadores={"c1": cuidador}, vehiculos={"v1": vehiculo},
        )
        errores = validar_plan(mundo, _plan_reserva(vehiculo_id="v1"))
        
        assert any("CAMION_TRASLADO" in e for e in errores)
    
    def test_validar_equipo_no_disponible(self):
        equipo = Equipo(
            id="e1", tipo=TipoEquipo.DARDOS_TRANQUILIZANTES,
            ubicacion="bodega", estado=EstadoEquipo.EN_USO  # no disponible
        )
        
        tarea = Tarea(
            id="t1", tipo="captura",
            equipos_requeridos=(TipoEquipo.DARDOS_TRANQUILIZANTES,),
        )
        
        mundo = _mundo_con_tarea(
            tarea,
            equipos={"e1": equipo},
            cuidadores={
                "c1": Cuidador(
                    id="c1", nombre="Test", estado=EstadoCuidador.DISPONIBLE,
                ),
            },
        )
        errores = validar_plan(mundo, _plan_reserva(equipos=("e1",)))
        
        assert any("no está disponible" in e.lower() for e in errores)


class TestLiberarReservasTarea:
    """Pruebas de liberación de reservas."""
    
    def setup_method(self):
        self.registro = RegistroReservas()
    
    def test_liberar_reservas_tarea(self):
        r1 = Reserva(TipoRecurso.CUIDADOR, "c1", "t1", 100, 200)
        r2 = Reserva(TipoRecurso.VEHICULO, "v1", "t1", 100, 200)
        reservar_atomico(self.registro, [r1, r2])
        
        liberadas = liberar_reservas_tarea(self.registro, "t1")
        
        assert len(liberadas) == 2
        assert self.registro.verificar_disponibilidad(TipoRecurso.CUIDADOR, "c1", 100, 200) is True
        assert self.registro.verificar_disponibilidad(TipoRecurso.VEHICULO, "v1", 100, 200) is True


class TestEliminarReserva:
    """Pruebas del método eliminar_reserva."""
    
    def setup_method(self):
        self.registro = RegistroReservas()
    
    def test_eliminar_reserva_existente(self):
        r = Reserva(TipoRecurso.CUIDADOR, "c1", "t1", 100, 200)
        self.registro.agregar_reserva(r)
        
        resultado = self.registro.eliminar_reserva(r)
        
        assert resultado is True
        assert self.registro.verificar_disponibilidad(TipoRecurso.CUIDADOR, "c1", 100, 200) is True
    
    def test_eliminar_reserva_inexistente(self):
        r = Reserva(TipoRecurso.CUIDADOR, "c1", "t1", 100, 200)
        # No agregar al registro
        
        resultado = self.registro.eliminar_reserva(r)
        
        assert resultado is False


class TestReservarPlan:
    """Pruebas de validación y reserva atómica desde un plan."""

    def setup_method(self):
        self.registro = RegistroReservas()

    def test_reservar_plan_con_tres_cuidadores_camion_y_dardos(self):
        cuidadores = {
            "c1": Cuidador(
                id="c1", nombre="Test",
                habilidades={Habilidad.MANEJO_FELINOS: 5},
                certificaciones=frozenset({
                    Certificacion.TRANQUILIZANTE, Certificacion.CAMION_TRASLADO,
                }),
                estado=EstadoCuidador.DISPONIBLE,
            ),
            "c2": Cuidador(id="c2", nombre="Test", estado=EstadoCuidador.DISPONIBLE),
            "c3": Cuidador(id="c3", nombre="Test", estado=EstadoCuidador.DISPONIBLE),
        }
        vehiculo = Vehiculo(
            id="v1", tipo=TipoVehiculo.CAMION_TRASLADO,
            velocidad=5.0, capacidad_personas=3, capacidad_animales=2,
            certificacion_requerida=Certificacion.CAMION_TRASLADO,
            ubicacion="garaje", estado=EstadoVehiculo.DISPONIBLE
        )
        tarea = Tarea(
            id="t1", tipo="traslado", nodo_destino="destino",
            habilidades_requeridas=(HabilidadRequerida(Habilidad.MANEJO_FELINOS, 4),),
            certificaciones_requeridas=frozenset({Certificacion.TRANQUILIZANTE}),
            personas_minimas=3,
            vehiculo_requerido=TipoVehiculo.CAMION_TRASLADO,
            equipos_requeridos=(TipoEquipo.DARDOS_TRANQUILIZANTES,),
        )
        equipo = Equipo(
            id="e1", tipo=TipoEquipo.DARDOS_TRANQUILIZANTES,
            ubicacion="bodega", estado=EstadoEquipo.DISPONIBLE
        )
        mundo = _mundo_con_tarea(
            tarea,
            cuidadores=cuidadores,
            vehiculos={"v1": vehiculo},
            equipos={"e1": equipo},
            nodos={
                "garaje": Nodo("garaje", TipoNodo.GARAJE, 0, 0),
                "destino": Nodo("destino", TipoNodo.RECINTO, 1, 1),
            },
            aristas={
                ("garaje", "destino"): Arista(
                    "garaje", "destino", 10,
                    frozenset({MedioPermitido.JEEP}),
                ),
            },
        )
        plan = _plan_reserva(
            cuidadores=("c1", "c2", "c3"),
            vehiculo_id="v1",
            equipos=("e1",),
            ruta=("garaje", "destino"),
        )
        reservas = reservar_plan(mundo, self.registro, plan)

        assert len(reservas) == 5
        assert {reserva.recurso_tipo for reserva in reservas} == {
            TipoRecurso.CUIDADOR, TipoRecurso.VEHICULO, TipoRecurso.EQUIPO,
        }
        assert sum(r.recurso_tipo == TipoRecurso.CUIDADOR for r in reservas) == 3
        for cuidador_id in cuidadores:
            assert self.registro.verificar_disponibilidad(
                TipoRecurso.CUIDADOR, cuidador_id, 100, 200
            ) is False
        assert self.registro.verificar_disponibilidad(
            TipoRecurso.VEHICULO, "v1", 100, 200
        ) is False
        assert self.registro.verificar_disponibilidad(
            TipoRecurso.EQUIPO, "e1", 100, 200
        ) is False

    def test_reservar_plan_rechaza_solapamiento_sin_reservar_parcialmente(self):
        tarea = Tarea(id="t1", tipo="test")
        mundo = _mundo_con_tarea(
            tarea,
            cuidadores={
                "c1": Cuidador(
                    id="c1", nombre="Test", estado=EstadoCuidador.DISPONIBLE,
                ),
            },
            equipos={
                "e1": Equipo(
                    id="e1", tipo=TipoEquipo.DARDOS_TRANQUILIZANTES,
                    ubicacion="bodega",
                ),
            },
        )
        existente = Reserva(TipoRecurso.EQUIPO, "e1", "otra", 100, 200)
        self.registro.agregar_reserva(existente)

        with pytest.raises(ReservaAtomicaFallida):
            reservar_plan(
                mundo, self.registro,
                _plan_reserva(equipos=("e1",)),
            )

        assert self.registro.obtener_reservas_de_tarea("t1") == []
        assert self.registro.obtener_reservas_de_tarea("otra") == [existente]
        assert self.registro.verificar_disponibilidad(
            TipoRecurso.CUIDADOR, "c1", 100, 200
        ) is True

    def test_reservar_plan_falla_validacion_sin_reservar(self):
        cuidador = Cuidador(
            id="c1", nombre="Test",
            habilidades={Habilidad.MANEJO_FELINOS: 3},  # nivel insuficiente
            certificaciones=frozenset({Certificacion.TRANQUILIZANTE}),
            estado=EstadoCuidador.DISPONIBLE
        )
        tarea = Tarea(
            id="t1", tipo="traslado",
            habilidades_requeridas=(HabilidadRequerida(Habilidad.MANEJO_FELINOS, 4),),
            certificaciones_requeridas=frozenset({Certificacion.TRANQUILIZANTE})
        )
        mundo = _mundo_con_tarea(tarea, cuidadores={"c1": cuidador})
        with pytest.raises(PlanInvalido) as exc:
            reservar_plan(mundo, self.registro, _plan_reserva())

        assert "nivel 3 < 4" in str(exc.value)
        assert self.registro.verificar_disponibilidad(TipoRecurso.CUIDADOR, "c1", 100, 200) is True

    def test_reservar_plan_falla_si_falta_vehiculo_requerido(self):
        tarea = Tarea(
            id="t1", tipo="test", vehiculo_requerido=TipoVehiculo.JEEP,
        )

        with pytest.raises(PlanInvalido, match="requiere vehículo"):
            reservar_plan(
                _mundo_con_tarea(tarea, cuidadores={
                    "c1": Cuidador(
                        id="c1", nombre="Test",
                        estado=EstadoCuidador.DISPONIBLE,
                    ),
                }),
                self.registro, _plan_reserva(),
            )

        assert self.registro.obtener_reservas_de_tarea("t1") == []

    def test_reservar_plan_falla_si_el_equipo_no_cubre_certificacion(self):
        tarea = Tarea(
            id="t1", tipo="test",
            certificaciones_requeridas=frozenset({Certificacion.TRANQUILIZANTE}),
        )
        mundo = _mundo_con_tarea(tarea, cuidadores={
            "c1": Cuidador(
                id="c1", nombre="Test", estado=EstadoCuidador.DISPONIBLE,
            ),
        })

        with pytest.raises(PlanInvalido, match="TRANQUILIZANTE"):
            reservar_plan(mundo, self.registro, _plan_reserva())

        assert self.registro.obtener_reservas_de_tarea("t1") == []

    def test_reservar_plan_siempre_reserva_al_menos_un_cuidador(self):
        tarea = Tarea(id="t1", tipo="alimentacion")
        mundo = _mundo_con_tarea(tarea, cuidadores={
            "c1": Cuidador(
                id="c1", nombre="Test", estado=EstadoCuidador.DISPONIBLE,
            ),
        })

        resultado = reservar_plan(mundo, self.registro, _plan_reserva())

        assert len(resultado) == 1
        assert resultado[0].recurso_tipo == TipoRecurso.CUIDADOR
        assert self.registro.obtener_reservas_de_tarea("t1") == resultado

    def test_reservar_plan_rechaza_plan_de_otra_tarea(self):
        tarea = Tarea(id="t1", tipo="test")
        mundo = _mundo_con_tarea(tarea, cuidadores={
            "c1": Cuidador(
                id="c1", nombre="Test", estado=EstadoCuidador.DISPONIBLE,
            ),
        })

        with pytest.raises(PlanInvalido, match="no existe en el mundo"):
            reservar_plan(
                mundo, self.registro,
                _plan_reserva(tarea_id="t2"),
            )

        assert self.registro.verificar_disponibilidad(TipoRecurso.CUIDADOR, "c1", 100, 200) is True

    def test_reservar_plan_admite_varios_cuidadores(self):
        tarea = Tarea(id="t1", tipo="test")
        mundo = _mundo_con_tarea(tarea, cuidadores={
            cuidador_id: Cuidador(
                id=cuidador_id, nombre=cuidador_id,
                estado=EstadoCuidador.DISPONIBLE,
            )
            for cuidador_id in ("c1", "c2")
        })

        resultado = reservar_plan(
            mundo, self.registro,
            _plan_reserva(cuidadores=("c1", "c2")),
        )

        assert len(resultado) == 2
        for cuidador_id in ("c1", "c2"):
            assert self.registro.verificar_disponibilidad(
                TipoRecurso.CUIDADOR, cuidador_id, 100, 200
            ) is False

    def test_plan_con_cuidadores_duplicados_no_reserva(self):
        with pytest.raises(PlanInvalido, match="duplicados"):
            _plan_reserva(cuidadores=("c1", "c1"))

        assert self.registro.obtener_reservas_de_tarea("t1") == []