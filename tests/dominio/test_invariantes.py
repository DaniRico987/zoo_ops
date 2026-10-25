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
    _verificar_invariante_6_animal_en_recinto_valido,
    _verificar_invariante_8_dependencias_tarea,
    verificar_invariante_eventos,
    _no_verificada_invariante_4,
    _no_verificada_invariante_5,
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
            cuidador_asignado="c1"
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
            cuidador_asignado="c1"
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
            cuidador_asignado="c1"
        )
        
        mundo = Mundo(cuidadores={"c1": cuidador}, tareas={"t1": tarea})
        
        violaciones = _verificar_invariante_1_habilidades_cuidador(mundo)
        assert len(violaciones) == 1
        assert "TRANQUILIZANTE" in violaciones[0].detalle
    
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
            cuidador_asignado="c1"
        )
        
        # Tarea ASIGNADA - sí debe verificar
        tarea_asignada = Tarea(
            id="t2", tipo="captura",
            habilidades_requeridas=(HabilidadRequerida(Habilidad.MANEJO_FELINOS, 4),),
            estado=EstadoTarea.ASIGNADA,
            cuidador_asignado="c1"
        )
        
        mundo = Mundo(
            cuidadores={"c1": cuidador},
            tareas={"t1": tarea_pendiente, "t2": tarea_asignada}
        )
        
        violaciones = _verificar_invariante_1_habilidades_cuidador(mundo)
        # Solo debe fallar t2
        assert len(violaciones) == 1
        assert violaciones[0].entidad_id == "c1"


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
        
        # Para probar la detección de solapamiento en la invariante,
        # necesitamos agregar r2 sin validación (simular estado corrupto)
        # Usamos el registro interno directamente
        self.registro._reservas_por_recurso[(TipoRecurso.CUIDADOR, "c1")].append(r2)
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
        tarea = Tarea(id="t1", tipo="test", estado=EstadoTarea.EN_CURSO, cuidador_asignado="c1")
        mundo = Mundo(cuidadores={"c1": cuidador}, tareas={"t1": tarea})
        
        violaciones = _verificar_invariante_3_una_tarea_activa(mundo)
        assert len(violaciones) == 0
    
    def test_cuidador_dos_tareas_activas(self):
        cuidador = Cuidador(id="c1", nombre="Test", estado=EstadoCuidador.EJECUTANDO)
        t1 = Tarea(id="t1", tipo="test", estado=EstadoTarea.EN_CURSO, cuidador_asignado="c1")
        t2 = Tarea(id="t2", tipo="test", estado=EstadoTarea.ASIGNADA, cuidador_asignado="c1")
        mundo = Mundo(cuidadores={"c1": cuidador}, tareas={"t1": t1, "t2": t2})
        
        violaciones = _verificar_invariante_3_una_tarea_activa(mundo)
        assert len(violaciones) == 1
        assert "2 tareas activas" in violaciones[0].detalle


class TestInvariante4NoVerificada:
    """Pruebas de que INV-4 aparece en no_verificadas."""
    
    def test_invariante_4_en_no_verificadas(self):
        registro = RegistroReservas()
        mundo = Mundo()
        violaciones, no_verificadas = verificar_invariantes(mundo, registro)
        
        inv4 = [nv for nv in no_verificadas if nv.invariante == "INV-4-capacidad-vehiculo"]
        assert len(inv4) == 1
        assert "motor de asignación" in inv4[0].motivo


class TestInvariante5NoVerificada:
    """Pruebas de que INV-5 aparece en no_verificadas."""
    
    def test_invariante_5_en_no_verificadas(self):
        registro = RegistroReservas()
        mundo = Mundo()
        violaciones, no_verificadas = verificar_invariantes(mundo, registro)
        
        inv5 = [nv for nv in no_verificadas if nv.invariante == "INV-5-jeep-aristas-validas"]
        assert len(inv5) == 1
        assert "motor de asignación" in inv5[0].motivo


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
        # INV-4 e INV-5 deben estar en no_verificadas
        assert len(no_verificadas) == 2
        inv_ids = {nv.invariante for nv in no_verificadas}
        assert "INV-4-capacidad-vehiculo" in inv_ids
        assert "INV-5-jeep-aristas-validas" in inv_ids
    
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
            estado=EstadoTarea.EN_CURSO, cuidador_asignado="c1"
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