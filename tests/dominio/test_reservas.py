"""
Pruebas unitarias para reservas.py - sistema de reservas atómicas.
"""

import pytest
from zoo_ops.dominio.reservas import (
    TipoRecurso, Reserva, RegistroReservas,
    reservar_atomico, liberar_reservas_tarea, verificar_disponibilidad_recurso,
    crear_reservas_para_tarea, validar_recursos_para_tarea, _orden_determinista_recursos,
    reservar_para_tarea
)
from zoo_ops.dominio.entidades import (
    Cuidador, Vehiculo, Equipo, Tarea, HabilidadRequerida, Mundo,
)
from zoo_ops.dominio.enums import (
    EstadoCuidador, EstadoEquipo, EstadoVehiculo, TipoVehiculo, TipoEquipo,
    Habilidad, Certificacion, PrioridadTarea
)
from zoo_ops.dominio.errores import (
    RecursosInvalidos, ReservaAtomicaFallida, ReservaInvalida,
)
from zoo_ops.dominio.catalogos import ESPECIES_CATALOGO


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


class TestCrearReservasParaTarea:
    """Pruebas de helpers para crear reservas desde tareas."""
    
    def test_crear_reservas_basicas(self):
        tarea = Tarea(id="t1", tipo="captura", duracion_estimada=3600)
        
        reservas = crear_reservas_para_tarea(
            tarea, cuidador_id="c1", vehiculo_id="v1", equipo_ids=["e1", "e2"],
            desde=1000, hasta=4600
        )
        
        assert len(reservas) == 4
        tipos = {r.recurso_tipo for r in reservas}
        assert TipoRecurso.CUIDADOR in tipos
        assert TipoRecurso.VEHICULO in tipos
        assert TipoRecurso.EQUIPO in tipos
        assert sum(1 for r in reservas if r.recurso_tipo == TipoRecurso.EQUIPO) == 2
    
    def test_crear_reservas_sin_recursos_opcionales(self):
        tarea = Tarea(id="t1", tipo="alimentacion")
        
        reservas = crear_reservas_para_tarea(tarea, desde=100, hasta=200)
        
        assert len(reservas) == 0
    
    def test_crear_reservas_intervalo_invalido(self):
        tarea = Tarea(id="t1", tipo="test")
        
        with pytest.raises(ReservaInvalida):
            crear_reservas_para_tarea(tarea, desde=200, hasta=100)


class TestValidarRecursosParaTarea:
    """Pruebas de validación de recursos para una tarea."""
    
    def setup_method(self):
        self.registro = RegistroReservas()
    
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
        
        mundo = Mundo(cuidadores={"c1": cuidador})
        errores = validar_recursos_para_tarea(tarea, mundo, cuidador_id="c1")
        
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
        
        mundo = Mundo(cuidadores={"c1": cuidador})
        errores = validar_recursos_para_tarea(tarea, mundo, cuidador_id="c1")
        
        assert any("TRANQUILIZANTE" in e for e in errores)
    
    def test_validar_cuidador_estado_no_disponible(self):
        cuidador = Cuidador(
            id="c1", nombre="Test",
            habilidades={Habilidad.MANEJO_FELINOS: 5},
            certificaciones=frozenset({Certificacion.TRANQUILIZANTE}),
            estado=EstadoCuidador.EN_CAMINO  # no disponible
        )
        
        tarea = Tarea(id="t1", tipo="captura")
        
        mundo = Mundo(cuidadores={"c1": cuidador})
        errores = validar_recursos_para_tarea(tarea, mundo, cuidador_id="c1")
        assert any("no está disponible" in e for e in errores)

    def test_validar_cuidador_en_estado_asignado_no_esta_disponible(self):
        cuidador = Cuidador(
            id="c1", nombre="Test", estado=EstadoCuidador.ASIGNADO,
        )
        mundo = Mundo(cuidadores={"c1": cuidador})

        errores = validar_recursos_para_tarea(
            Tarea(id="t1", tipo="captura"), mundo, cuidador_id="c1",
        )

        assert any("no está disponible" in error for error in errores)

    def test_validar_recursos_rechaza_diccionarios_en_lugar_de_mundo(self):
        with pytest.raises(TypeError, match="Mundo"):
            validar_recursos_para_tarea(
                Tarea(id="t1", tipo="captura"),
                {"cuidadores": {}, "vehiculos": {}, "equipos": {}},
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
        
        mundo = Mundo(cuidadores={"c1": cuidador}, vehiculos={"v1": vehiculo})
        errores = validar_recursos_para_tarea(
            tarea, mundo, cuidador_id="c1", vehiculo_id="v1"
        )
        
        assert any("CAMION_TRASLADO" in e for e in errores)
    
    def test_validar_equipo_no_disponible(self):
        equipo = Equipo(
            id="e1", tipo=TipoEquipo.DARDOS_TRANQUILIZANTES,
            ubicacion="bodega", estado=EstadoEquipo.EN_USO  # no disponible
        )
        
        tarea = Tarea(id="t1", tipo="captura", recursos_requeridos=("e1",))
        
        mundo = Mundo(equipos={"e1": equipo})
        errores = validar_recursos_para_tarea(tarea, mundo, equipo_ids=["e1"])
        
        assert any("no está disponible" in e for e in errores)


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


class TestReservarParaTarea:
    """Pruebas de reservar_para_tarea (válida recursos y reserva atómicamente)."""
    
    def setup_method(self):
        self.registro = RegistroReservas()
    
    def test_reservar_para_tarea_exito(self):
        cuidador = Cuidador(
            id="c1", nombre="Test",
            habilidades={Habilidad.MANEJO_FELINOS: 5},
            certificaciones=frozenset({Certificacion.TRANQUILIZANTE, Certificacion.CAMION_TRASLADO}),
            estado=EstadoCuidador.DISPONIBLE
        )
        
        vehiculo = Vehiculo(
            id="v1", tipo=TipoVehiculo.CAMION_TRASLADO,
            velocidad=5.0, capacidad_personas=3, capacidad_animales=2,
            certificacion_requerida=Certificacion.CAMION_TRASLADO,
            ubicacion="garaje", estado=EstadoVehiculo.DISPONIBLE
        )
        
        tarea = Tarea(
            id="t1", tipo="traslado",
            habilidades_requeridas=(HabilidadRequerida(Habilidad.MANEJO_FELINOS, 4),),
            certificaciones_requeridas=frozenset({Certificacion.TRANQUILIZANTE}),
            recursos_requeridos=("v1", "e1")
        )
        
        equipo = Equipo(
            id="e1", tipo=TipoEquipo.DARDOS_TRANQUILIZANTES,
            ubicacion="bodega", estado=EstadoEquipo.DISPONIBLE
        )
        mundo = Mundo(
            cuidadores={"c1": cuidador},
            vehiculos={"v1": vehiculo},
            equipos={"e1": equipo},
        )
        
        paquete = crear_reservas_para_tarea(
            tarea, cuidador_id="c1", vehiculo_id="v1", equipo_ids=["e1"],
            desde=100, hasta=200
        )
        reservas = reservar_para_tarea(
            mundo, self.registro, tarea, paquete
        )
        
        assert len(reservas) == 3
        assert {r.recurso_tipo for r in reservas} == {
            TipoRecurso.CUIDADOR, TipoRecurso.VEHICULO, TipoRecurso.EQUIPO,
        }
        assert self.registro.verificar_disponibilidad(TipoRecurso.CUIDADOR, "c1", 100, 200) is False
        assert self.registro.verificar_disponibilidad(TipoRecurso.VEHICULO, "v1", 100, 200) is False
        assert self.registro.verificar_disponibilidad(TipoRecurso.EQUIPO, "e1", 100, 200) is False
    
    def test_reservar_para_tarea_rechaza_solapamiento_intra_paquete(self):
        tarea = Tarea(id="t1", tipo="test")
        paquete = [
            Reserva(TipoRecurso.EQUIPO, "e1", "t1", 100, 200),
            Reserva(TipoRecurso.EQUIPO, "e1", "t1", 150, 250),
        ]
        
        equipo = Equipo(
            id="e1", tipo=TipoEquipo.DARDOS_TRANQUILIZANTES,
            ubicacion="bodega", estado=EstadoEquipo.DISPONIBLE
        )
        mundo = Mundo(equipos={"e1": equipo})
        with pytest.raises(ReservaAtomicaFallida, match="intra-paquete"):
            reservar_para_tarea(mundo, self.registro, tarea, paquete)
        
        assert self.registro.verificar_disponibilidad(TipoRecurso.EQUIPO, "e1", 100, 200) is True
        assert self.registro.verificar_disponibilidad(TipoRecurso.EQUIPO, "e1", 150, 250) is True
    
    def test_reservar_para_tarea_falla_validacion(self):
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
        
        mundo = Mundo(cuidadores={"c1": cuidador})
        paquete = crear_reservas_para_tarea(
            tarea, cuidador_id="c1", desde=100, hasta=200
        )
        with pytest.raises(RecursosInvalidos) as exc:
            reservar_para_tarea(mundo, self.registro, tarea, paquete)
        
        assert "nivel 3 < 4" in str(exc.value)
        # No debe haber reservas creadas
        assert self.registro.verificar_disponibilidad(TipoRecurso.CUIDADOR, "c1", 100, 200) is True
    
    def test_reservar_para_tarea_rechaza_paquete_vacio_con_recursos(self):
        tarea = Tarea(
            id="t1", tipo="test", recursos_requeridos=("v1",),
        )

        with pytest.raises(RecursosInvalidos, match="vacío"):
            reservar_para_tarea(Mundo(), self.registro, tarea, [])

        assert self.registro.obtener_reservas_de_tarea("t1") == []

    def test_reservar_para_tarea_rechaza_paquete_vacio_con_certificaciones(self):
        tarea = Tarea(
            id="t1", tipo="test",
            certificaciones_requeridas=frozenset({Certificacion.TRANQUILIZANTE}),
        )

        with pytest.raises(RecursosInvalidos, match="vacío"):
            reservar_para_tarea(Mundo(), self.registro, tarea, [])

        assert self.registro.obtener_reservas_de_tarea("t1") == []

    def test_reservar_para_tarea_paquete_vacio_sin_requisitos_es_noop(self):
        tarea = Tarea(id="t1", tipo="alimentacion")

        resultado = reservar_para_tarea(Mundo(), self.registro, tarea, [])

        assert resultado == []
        assert self.registro.obtener_reservas_de_tarea("t1") == []

    def test_reservar_para_tarea_rechaza_paquete_de_otra_tarea(self):
        tarea = Tarea(id="t1", tipo="test")
        paquete = [Reserva(TipoRecurso.CUIDADOR, "c1", "t2", 100, 200)]
        
        with pytest.raises(RecursosInvalidos, match="no pertenece"):
            reservar_para_tarea(Mundo(), self.registro, tarea, paquete)
        
        assert self.registro.verificar_disponibilidad(TipoRecurso.CUIDADOR, "c1", 100, 200) is True
    
    def test_reservar_para_tarea_rechaza_varios_cuidadores(self):
        tarea = Tarea(id="t1", tipo="test")
        paquete = [
            Reserva(TipoRecurso.CUIDADOR, "c1", "t1", 100, 200),
            Reserva(TipoRecurso.CUIDADOR, "c2", "t1", 100, 200),
        ]
        
        with pytest.raises(RecursosInvalidos, match="un solo cuidador"):
            reservar_para_tarea(Mundo(), self.registro, tarea, paquete)