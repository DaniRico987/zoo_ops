"""
Pruebas de las máquinas de estado.

Todas las transiciones se ejecutan por la única vía pública:
`ejecutar_transicion`. Los tests comprueban tanto el evento devuelto como el
estado real del mundo y del registro de eventos.
"""

import copy

import pytest

from zoo_ops.dominio.catalogos import ESPECIES_CATALOGO, Especie
from zoo_ops.dominio.entidades import (
    Animal, Cuidador, HabilidadRequerida, Incidente, Mundo, Recinto, Tarea,
    Vehiculo,
)
from zoo_ops.dominio.enums import (
    Certificacion, EstadoAnimal, EstadoCuidador, EstadoIncidente, EstadoTarea,
    EstadoVehiculo, Habilidad, Medio, Peligrosidad, TipoIncidente, TipoRecinto,
    TipoVehiculo,
)
from zoo_ops.dominio.errores import (
    DependenciaInexistente, ErrorDominio, EventoDuplicado, PlanInvalido,
    TiempoRetrocede, TransicionInvalida,
)
from zoo_ops.dominio.estados import (
    TRANSICIONES_ANIMAL, TRANSICIONES_CUIDADOR, TRANSICIONES_INCIDENTE,
    TRANSICIONES_TAREA, TRANSICIONES_VEHICULO,
    ejecutar_transicion, validar_transicion_animal_extra,
    validar_transicion_incidente_extra, validar_transicion_tarea_extra,
)
from zoo_ops.dominio.eventos import (
    RegistroEventos, TipoEvento,
)
from zoo_ops.dominio.plan import PlanEjecucion


# ============================================================================
# Helpers
# ============================================================================

def _cuidador(estado=EstadoCuidador.FUERA_DE_TURNO, id="c1"):
    return Cuidador(id=id, nombre="Cuidador", estado=estado)


def _animal(estado=EstadoAnimal.EN_RECINTO, especie="jaguar", ubicacion="rec1", id="a1"):
    return Animal(
        id=id,
        especie=ESPECIES_CATALOGO[especie],
        recinto_origen="rec1",
        ubicacion=ubicacion,
        estado=estado,
    )


def _recinto(id="rec1", especies=("jaguar",)):
    return Recinto(
        nodo_id=id,
        tipo=TipoRecinto.ABIERTO,
        especies_admitidas=frozenset(especies),
        capacidad=4,
    )


def _incidente(
    estado=EstadoIncidente.ABIERTO,
    tipo=TipoIncidente.ESCAPE_TERRESTRE,
    tareas_generadas=frozenset(),
    animal_relacionado=None,
):
    return Incidente(
        id="i1",
        tipo=tipo,
        severidad=5,
        ubicacion="rec1",
        estado=estado,
        tareas_generadas=tareas_generadas,
        animal_relacionado=animal_relacionado,
    )


def _vehiculo(estado=EstadoVehiculo.DISPONIBLE):
    return Vehiculo(
        id="v1",
        tipo=TipoVehiculo.JEEP,
        velocidad=10.0,
        capacidad_personas=4,
        capacidad_animales=2,
        certificacion_requerida=Certificacion.JEEP,
        ubicacion="garaje",
        estado=estado,
    )


# ============================================================================
# Tablas
# ============================================================================

class TestTablasDeTransiciones:
    def test_todas_las_tablas_son_frozenset(self):
        for tabla in (
            TRANSICIONES_CUIDADOR, TRANSICIONES_ANIMAL, TRANSICIONES_VEHICULO,
            TRANSICIONES_TAREA, TRANSICIONES_INCIDENTE,
        ):
            for estado, destinos in tabla.items():
                assert isinstance(destinos, frozenset), f"{estado} no es frozenset"

    def test_cuidador_tiene_las_transiciones_esperadas(self):
        assert TRANSICIONES_CUIDADOR[EstadoCuidador.FUERA_DE_TURNO] == frozenset(
            {EstadoCuidador.DISPONIBLE}
        )
        assert EstadoCuidador.EN_CAMINO not in TRANSICIONES_CUIDADOR[EstadoCuidador.DISPONIBLE]
        assert TRANSICIONES_TAREA[EstadoTarea.CANCELADA] == frozenset()
        assert TRANSICIONES_INCIDENTE[EstadoIncidente.CERRADO] == frozenset()


# ============================================================================
# Cuidador
# ============================================================================

class TestCuidador:
    def test_asignado_puede_volver_a_disponible_antes_de_salir(self):
        mundo = Mundo(cuidadores={
            "c1": _cuidador(EstadoCuidador.ASIGNADO),
        })
        registro = RegistroEventos()

        evento = ejecutar_transicion(
            mundo, registro, "Cuidador", "c1",
            EstadoCuidador.DISPONIBLE, 10, "cancelar asignación",
        )

        assert evento.estado_antes == "ASIGNADO"
        assert mundo.cuidadores["c1"].estado == EstadoCuidador.DISPONIBLE

    def test_transicion_valida_muta_mundo_y_anexa_evento(self):
        mundo = Mundo(cuidadores={"c1": _cuidador()})
        registro = RegistroEventos()

        evento = ejecutar_transicion(
            mundo, registro, "Cuidador", "c1",
            EstadoCuidador.DISPONIBLE, 100, "inicio de turno",
        )

        assert evento.estado_antes == "FUERA_DE_TURNO"
        assert evento.estado_despues == "DISPONIBLE"
        assert mundo.cuidadores["c1"].estado == EstadoCuidador.DISPONIBLE
        assert mundo.tiempo_actual == 100
        assert len(registro) == 1
        assert registro[0] is evento

    def test_no_se_puede_pasar_un_estado_actual_obsoleto(self):
        # El llamador no recibe ni pasa estado_actual: tras la primera transición
        # el mundo ya está en DISPONIBLE y repetirla desde fuera de turno falla.
        mundo = Mundo(cuidadores={"c1": _cuidador()})
        registro = RegistroEventos()

        ejecutar_transicion(
            mundo, registro, "Cuidador", "c1",
            EstadoCuidador.DISPONIBLE, 100, "inicio de turno",
        )

        with pytest.raises(TransicionInvalida, match="no permitida"):
            ejecutar_transicion(
                mundo, registro, "Cuidador", "c1",
                EstadoCuidador.DISPONIBLE, 110, "repetición con dato obsoleto",
            )

        assert mundo.cuidadores["c1"].estado == EstadoCuidador.DISPONIBLE
        assert len(registro) == 1

    def test_transicion_invalida_no_muta_nada(self):
        mundo = Mundo(cuidadores={"c1": _cuidador(EstadoCuidador.DISPONIBLE)})
        registro = RegistroEventos()
        antes = copy.deepcopy(mundo)

        with pytest.raises(TransicionInvalida, match="no permitida"):
            ejecutar_transicion(
                mundo, registro, "Cuidador", "c1",
                EstadoCuidador.EN_CAMINO, 100, "intento inválido",
            )

        assert mundo == antes
        assert len(registro) == 0

    def test_entidad_inexistente_lanza_error_de_dominio(self):
        mundo = Mundo()
        registro = RegistroEventos()

        with pytest.raises(ErrorDominio, match="no existe"):
            ejecutar_transicion(
                mundo, registro, "Cuidador", "c_inexistente",
                EstadoCuidador.DISPONIBLE, 100, "x",
            )

        assert len(registro) == 0

    def test_tipo_de_entidad_desconocido_lanza_error_de_dominio(self):
        with pytest.raises(ErrorDominio, match="desconocido"):
            ejecutar_transicion(
                Mundo(), RegistroEventos(), "Planta", "p1",
                EstadoCuidador.DISPONIBLE, 100, "x",
            )

    def test_fallo_de_validar_anexo_no_muta_el_mundo_ni_el_registro(self):
        class RegistroConIdFijo(RegistroEventos):
            def siguiente_id_evento(self):
                return 1

        mundo = Mundo(cuidadores={"c1": _cuidador()})
        registro = RegistroConIdFijo()
        previo = ejecutar_transicion(
            mundo, registro, "Cuidador", "c1",
            EstadoCuidador.DISPONIBLE, 100, "primera transición",
        )
        antes = copy.deepcopy(mundo)
        registro_antes = copy.deepcopy(registro)

        with pytest.raises(EventoDuplicado):
            ejecutar_transicion(
                mundo, registro, "Cuidador", "c1",
                EstadoCuidador.ASIGNADO, 110, "id duplicado",
            )

        assert mundo == antes
        assert registro.obtener_todos() == registro_antes.obtener_todos() == [previo]
        assert registro._ultimo_id_evento == registro_antes._ultimo_id_evento

    def test_fallo_de_anexar_revierte_mundo_reloj_y_registro(self):
        class RegistroConAnexoFallido(RegistroEventos):
            def siguiente_id_evento(self):
                return 1

            def validar_anexo(self, evento):
                return super().validar_anexo(evento)

            def anexar(self, evento):
                raise RuntimeError("fallo al anexar")

        mundo = Mundo(cuidadores={"c1": _cuidador()}, tiempo_actual=5)
        registro = RegistroConAnexoFallido()
        antes = copy.deepcopy(mundo)
        registro_antes = copy.deepcopy(registro)

        with pytest.raises(RuntimeError, match="fallo al anexar"):
            ejecutar_transicion(
                mundo, registro, "Cuidador", "c1",
                EstadoCuidador.DISPONIBLE, 100, "anexo fallido",
            )

        assert mundo == antes
        assert mundo.tiempo_actual == antes.tiempo_actual
        assert registro.obtener_todos() == registro_antes.obtener_todos()
        assert registro._ultimo_id_evento == registro_antes._ultimo_id_evento

    def test_transicion_con_tiempo_menor_no_muta_mundo_ni_registro(self):
        mundo = Mundo(
            cuidadores={"c1": _cuidador()},
            tiempo_actual=20,
        )
        registro = RegistroEventos()
        antes = copy.deepcopy(mundo)

        with pytest.raises(TiempoRetrocede):
            ejecutar_transicion(
                mundo, registro, "Cuidador", "c1",
                EstadoCuidador.DISPONIBLE, 19, "reloj retrocede",
            )

        assert mundo == antes
        assert len(registro) == 0

    def test_transiciones_en_el_mismo_instante_se_aceptan(self):
        mundo = Mundo(cuidadores={"c1": _cuidador()})
        registro = RegistroEventos()

        primero = ejecutar_transicion(
            mundo, registro, "Cuidador", "c1",
            EstadoCuidador.DISPONIBLE, 20, "inicio",
        )
        segundo = ejecutar_transicion(
            mundo, registro, "Cuidador", "c1",
            EstadoCuidador.ASIGNADO, 20, "asignacion",
        )

        assert primero.momento == segundo.momento == 20
        assert primero.id < segundo.id
        assert mundo.tiempo_actual == 20

    def test_estado_que_no_pertenece_al_enum_lanza_error_de_dominio(self):
        mundo = Mundo(cuidadores={"c1": _cuidador()})

        with pytest.raises(ErrorDominio, match="no pertenece"):
            ejecutar_transicion(
                mundo, RegistroEventos(), "Cuidador", "c1",
                "DISPONIBLE", 100, "x",
            )


# ============================================================================
# Vehículo
# ============================================================================

class TestVehiculo:
    def test_transicion_valida(self):
        mundo = Mundo(vehiculos={"v1": _vehiculo()})

        evento = ejecutar_transicion(
            mundo, RegistroEventos(), "Vehiculo", "v1",
            EstadoVehiculo.RESERVADO, 50, "reservar",
        )

        assert evento.estado_despues == "RESERVADO"
        assert mundo.vehiculos["v1"].estado == EstadoVehiculo.RESERVADO

    def test_transicion_no_permitida_por_tabla(self):
        mundo = Mundo(vehiculos={"v1": _vehiculo(EstadoVehiculo.EN_RUTA)})

        with pytest.raises(TransicionInvalida):
            ejecutar_transicion(
                mundo, RegistroEventos(), "Vehiculo", "v1",
                EstadoVehiculo.EN_MANTENIMIENTO, 50, "mantenimiento",
            )


# ============================================================================
# Animal
# ============================================================================

class TestAnimal:
    def test_animal_acuatico_no_puede_escapar(self):
        mundo = Mundo(animales={"a1": _animal(especie="pirarucu")})

        with pytest.raises(TransicionInvalida, match="acuático"):
            ejecutar_transicion(
                mundo, RegistroEventos(), "Animal", "a1",
                EstadoAnimal.ESCAPADO, 10, "escape",
            )

        assert mundo.animales["a1"].estado == EstadoAnimal.EN_RECINTO

    def test_animal_terrestre_puede_escapar(self):
        mundo = Mundo(animales={"a1": _animal()})

        ejecutar_transicion(
            mundo, RegistroEventos(), "Animal", "a1",
            EstadoAnimal.ESCAPADO, 10, "escape",
        )

        assert mundo.animales["a1"].estado == EstadoAnimal.ESCAPADO

    def test_requiere_tranquilizante_no_puede_trasladarse_directo(self):
        mundo = Mundo(animales={"a1": _animal(EstadoAnimal.LOCALIZADO)})

        with pytest.raises(TransicionInvalida, match="tranquilizante"):
            ejecutar_transicion(
                mundo, RegistroEventos(), "Animal", "a1",
                EstadoAnimal.EN_TRASLADO, 10, "traslado directo",
            )

    def test_requiere_tranquilizante_pasa_por_tranquilizado(self):
        mundo = Mundo(animales={"a1": _animal(EstadoAnimal.LOCALIZADO)})
        registro = RegistroEventos()

        ejecutar_transicion(
            mundo, registro, "Animal", "a1",
            EstadoAnimal.TRANQUILIZADO, 10, "tranquilizar",
        )
        ejecutar_transicion(
            mundo, registro, "Animal", "a1",
            EstadoAnimal.EN_TRASLADO, 20, "trasladar",
        )

        assert mundo.animales["a1"].estado == EstadoAnimal.EN_TRASLADO
        assert len(registro) == 2

    def test_en_recinto_sin_parametro_recinto_destino_falla(self):
        mundo = Mundo(animales={"a1": _animal(EstadoAnimal.EN_TRASLADO)})

        with pytest.raises(ErrorDominio, match="recinto_destino"):
            ejecutar_transicion(
                mundo, RegistroEventos(), "Animal", "a1",
                EstadoAnimal.EN_RECINTO, 10, "volver",
            )

    def test_en_recinto_con_recinto_inexistente_falla(self):
        mundo = Mundo(animales={"a1": _animal(EstadoAnimal.EN_TRASLADO)})

        with pytest.raises(TransicionInvalida, match="no existe"):
            ejecutar_transicion(
                mundo, RegistroEventos(), "Animal", "a1",
                EstadoAnimal.EN_RECINTO, 10, "volver",
                recinto_destino="rec_inexistente",
            )

    def test_inv6_recinto_que_no_admite_la_especie(self):
        mundo = Mundo(
            animales={"a1": _animal(EstadoAnimal.EN_TRASLADO)},
            recintos={"rec1": _recinto(especies=("guacamaya_roja",))},
        )

        with pytest.raises(TransicionInvalida, match="no admite"):
            ejecutar_transicion(
                mundo, RegistroEventos(), "Animal", "a1",
                EstadoAnimal.EN_RECINTO, 10, "volver",
                recinto_destino="rec1",
            )

        assert mundo.animales["a1"].estado == EstadoAnimal.EN_TRASLADO

    def test_inv6_especie_fuera_del_catalogo(self):
        especie_fantasma = Especie(
            nombre="Especie fantasma",
            medio=Medio.TERRESTRE,
            peligrosidad=Peligrosidad.BAJA,
            requiere_tranquilizante=False,
            habilidad_requerida=Habilidad.MANEJO_PRIMATES,
            nivel_minimo_habilidad=1,
            tipo_vehiculo_traslado=TipoVehiculo.JEEP,
            minimo_personas_traslado=1,
            tipo_recinto_requerido=TipoRecinto.ABIERTO,
        )
        animal = Animal(
            id="a1",
            especie=especie_fantasma,
            recinto_origen="rec1",
            ubicacion="campo",
            estado=EstadoAnimal.EN_TRASLADO,
        )
        mundo = Mundo(
            animales={"a1": animal},
            recintos={"rec1": _recinto(especies=("jaguar",))},
        )

        with pytest.raises(TransicionInvalida, match="catálogo"):
            ejecutar_transicion(
                mundo, RegistroEventos(), "Animal", "a1",
                EstadoAnimal.EN_RECINTO, 10, "volver",
                recinto_destino="rec1",
            )

    def test_inv6_recinto_valido_actualiza_ubicacion(self):
        mundo = Mundo(
            animales={"a1": _animal(EstadoAnimal.EN_TRASLADO, ubicacion="campo")},
            recintos={"rec1": _recinto(especies=("jaguar",))},
        )

        evento = ejecutar_transicion(
            mundo, RegistroEventos(), "Animal", "a1",
            EstadoAnimal.EN_RECINTO, 10, "volver",
            recinto_destino="rec1",
        )

        assert mundo.animales["a1"].estado == EstadoAnimal.EN_RECINTO
        assert mundo.animales["a1"].ubicacion == "rec1"
        assert evento.datos_extra["ubicacion"] == "rec1"

    def test_inv6_desde_en_observacion_tambien_valida(self):
        mundo = Mundo(
            animales={"a1": _animal(EstadoAnimal.EN_OBSERVACION, ubicacion="campo")},
            recintos={"rec1": _recinto(especies=("jaguar",))},
        )

        evento = ejecutar_transicion(
            mundo, RegistroEventos(), "Animal", "a1",
            EstadoAnimal.EN_RECINTO, 10, "volver",
            recinto_destino="rec1",
        )

        assert mundo.animales["a1"].estado == EstadoAnimal.EN_RECINTO
        assert mundo.animales["a1"].ubicacion == "rec1"
        assert evento.datos_extra["ubicacion"] == "rec1"

    def test_validador_animal_directo(self):
        animal = _animal(EstadoAnimal.ESCAPADO)
        mundo = Mundo(recintos={"rec1": _recinto()})

        assert validar_transicion_animal_extra(
            animal, EstadoAnimal.ESCAPADO, EstadoAnimal.EN_RECINTO, mundo, "rec1"
        ) is None
        assert "requiere" in validar_transicion_animal_extra(
            animal, EstadoAnimal.ESCAPADO, EstadoAnimal.EN_RECINTO, mundo, None
        )


# ============================================================================
# Tarea
# ============================================================================

class TestTarea:
    def _mundo(self, tarea, cuidadores=None):
        return Mundo(
            tareas={tarea.id: tarea},
            cuidadores=cuidadores or {},
        )

    def _registrar_plan(self, mundo, tarea_id, cuidadores):
        mundo.registrar_plan(PlanEjecucion(
            tarea_id=tarea_id,
            cuidadores=tuple(cuidadores),
            desde=0,
            hasta=100,
        ))

    def test_asignada_sin_plan_falla(self):
        tarea = Tarea(id="t2", tipo="test")
        mundo = self._mundo(tarea)

        with pytest.raises(TransicionInvalida, match="plan registrado"):
            ejecutar_transicion(
                mundo, RegistroEventos(), "Tarea", "t2",
                EstadoTarea.ASIGNADA, 10, "asignar",
            )

    def test_asignada_rechaza_cuidadores_ids_recibidos_por_argumento(self):
        tarea = Tarea(id="t2", tipo="test")
        mundo = self._mundo(tarea, {
            "c1": _cuidador(EstadoCuidador.DISPONIBLE),
        })
        self._registrar_plan(mundo, "t2", ("c1",))
        registro = RegistroEventos()
        antes = copy.deepcopy(mundo)

        with pytest.raises(ErrorDominio, match="ya no recibe cuidadores_ids"):
            ejecutar_transicion(
                mundo, registro, "Tarea", "t2",
                EstadoTarea.ASIGNADA, 10, "asignar",
                cuidadores_ids=("c1",),
            )

        assert mundo == antes
        assert len(registro) == 0

    def test_plan_sin_cuidadores_falla_sin_cambios(self):
        tarea = Tarea(id="t2", tipo="test")
        mundo = self._mundo(tarea, {
            "c1": _cuidador(EstadoCuidador.DISPONIBLE),
        })
        registro = RegistroEventos()
        antes = copy.deepcopy(mundo)

        with pytest.raises(PlanInvalido, match="tupla no vacía"):
            PlanEjecucion(tarea_id="t2", cuidadores=(), desde=0, hasta=100)

        assert mundo == antes
        assert len(registro) == 0

    def test_plan_con_cuidadores_duplicados_falla(self):
        tarea = Tarea(id="t2", tipo="test")
        mundo = self._mundo(tarea, {
            "c1": _cuidador(EstadoCuidador.DISPONIBLE),
        })

        with pytest.raises(PlanInvalido, match="duplicados"):
            PlanEjecucion(
                tarea_id="t2", cuidadores=("c1", "c1"), desde=0, hasta=100,
            )
        assert "t2" not in mundo.planes

    def test_asignada_con_cuidador_inexistente_falla(self):
        tarea = Tarea(id="t2", tipo="test")
        mundo = self._mundo(tarea)
        self._registrar_plan(mundo, "t2", ("c_inexistente",))

        with pytest.raises(TransicionInvalida, match="no existe"):
            ejecutar_transicion(
                mundo, RegistroEventos(), "Tarea", "t2",
                EstadoTarea.ASIGNADA, 10, "asignar",
            )

    @pytest.mark.parametrize("estado", [
        EstadoCuidador.FUERA_DE_TURNO,
        EstadoCuidador.DESCANSANDO,
        EstadoCuidador.EJECUTANDO,
    ])
    def test_asignada_rechaza_cuidador_no_disponible(self, estado):
        c1 = _cuidador(estado)
        t2 = Tarea(id="t2", tipo="test")
        mundo = Mundo(cuidadores={"c1": c1}, tareas={"t2": t2})
        self._registrar_plan(mundo, "t2", ("c1",))

        with pytest.raises(TransicionInvalida, match="DISPONIBLE"):
            ejecutar_transicion(
                mundo, RegistroEventos(), "Tarea", "t2",
                EstadoTarea.ASIGNADA, 10, "asignar",
            )

        assert mundo.tareas["t2"].estado == EstadoTarea.PENDIENTE
        assert mundo.tareas["t2"].cuidadores_asignados == ()

    def test_asignada_con_tarea_inexistente_falla(self):
        mundo = Mundo(cuidadores={"c1": _cuidador(EstadoCuidador.DISPONIBLE)})
        registro = RegistroEventos()

        with pytest.raises(ErrorDominio, match="no existe"):
            ejecutar_transicion(
                mundo, registro, "Tarea", "t_no_existe",
                EstadoTarea.ASIGNADA, 10, "asignar",
            )

        assert len(registro) == 0

    def test_inv3_cuidador_con_otra_tarea_activa_falla(self):
        c1 = _cuidador(EstadoCuidador.DISPONIBLE)
        t1 = Tarea(
            id="t1", tipo="test", estado=EstadoTarea.EN_CURSO,
            cuidadores_asignados=("c1",),
        )
        t2 = Tarea(id="t2", tipo="test")
        mundo = Mundo(cuidadores={"c1": c1}, tareas={"t1": t1, "t2": t2})
        self._registrar_plan(mundo, "t2", ("c1",))

        with pytest.raises(TransicionInvalida, match="INV-3"):
            ejecutar_transicion(
                mundo, RegistroEventos(), "Tarea", "t2",
                EstadoTarea.ASIGNADA, 10, "asignar",
            )

    def test_asignada_permite_dos_cuidadores_validos(self):
        cuidadores = {
            "c1": _cuidador(EstadoCuidador.DISPONIBLE, id="c1"),
            "c2": _cuidador(EstadoCuidador.DISPONIBLE, id="c2"),
        }
        t2 = Tarea(id="t2", tipo="test", personas_minimas=2)
        mundo = Mundo(cuidadores=cuidadores, tareas={"t2": t2})
        self._registrar_plan(mundo, "t2", ("c1", "c2"))
        registro = RegistroEventos()

        evento = ejecutar_transicion(
            mundo, registro, "Tarea", "t2",
            EstadoTarea.ASIGNADA, 10, "asignar",
        )

        assert evento.datos_extra["cuidadores_ids"] == ("c1", "c2")
        assert mundo.tareas["t2"].estado == EstadoTarea.ASIGNADA
        assert mundo.tareas["t2"].cuidadores_asignados == ("c1", "c2")

    def test_asignada_con_un_cuidador_menos_que_el_minimo_falla(self):
        tarea = Tarea(id="t2", tipo="test", personas_minimas=2)
        mundo = self._mundo(tarea, {
            "c1": _cuidador(EstadoCuidador.DISPONIBLE),
        })
        self._registrar_plan(mundo, "t2", ("c1",))

        with pytest.raises(TransicionInvalida, match="al menos 2 personas"):
            ejecutar_transicion(
                mundo, RegistroEventos(), "Tarea", "t2",
                EstadoTarea.ASIGNADA, 10, "asignar",
            )

    def test_asignada_con_un_cuidador_ocupado_rechaza_todo_sin_cambios(self):
        c1 = _cuidador(EstadoCuidador.DISPONIBLE, id="c1")
        c2 = _cuidador(EstadoCuidador.DISPONIBLE, id="c2")
        tarea_activa = Tarea(
            id="t1", tipo="test", estado=EstadoTarea.EN_CURSO,
            cuidadores_asignados=("c2",),
        )
        tarea_pendiente = Tarea(id="t2", tipo="test", personas_minimas=2)
        mundo = Mundo(
            cuidadores={"c1": c1, "c2": c2},
            tareas={"t1": tarea_activa, "t2": tarea_pendiente},
        )
        registro = RegistroEventos()
        self._registrar_plan(mundo, "t2", ("c1", "c2"))
        antes = copy.deepcopy(mundo)

        with pytest.raises(TransicionInvalida, match="INV-3"):
            ejecutar_transicion(
                mundo, registro, "Tarea", "t2",
                EstadoTarea.ASIGNADA, 10, "asignar",
            )

        assert mundo == antes
        assert len(registro) == 0

    def test_asignada_acepta_cobertura_repartida_entre_cuidadores(self):
        tarea = Tarea(
            id="t2",
            tipo="captura",
            personas_minimas=2,
            habilidades_requeridas=(
                HabilidadRequerida(Habilidad.MANEJO_FELINOS, 4),
                HabilidadRequerida(Habilidad.MANEJO_AVES, 3),
            ),
            certificaciones_requeridas=frozenset({Certificacion.TRANQUILIZANTE}),
        )
        cuidadores = {
            "c1": Cuidador(
                "c1", "Felinos",
                habilidades={Habilidad.MANEJO_FELINOS: 4},
                certificaciones=frozenset({Certificacion.TRANQUILIZANTE}),
                estado=EstadoCuidador.DISPONIBLE,
            ),
            "c2": Cuidador(
                "c2", "Aves",
                habilidades={Habilidad.MANEJO_AVES: 3},
                estado=EstadoCuidador.DISPONIBLE,
            ),
        }
        mundo = Mundo(cuidadores=cuidadores, tareas={"t2": tarea})
        self._registrar_plan(mundo, "t2", ("c1", "c2"))

        ejecutar_transicion(
            mundo, RegistroEventos(), "Tarea", "t2",
            EstadoTarea.ASIGNADA, 10, "asignar equipo",
        )

        assert mundo.tareas["t2"].cuidadores_asignados == ("c1", "c2")

    def test_asignada_rechaza_equipo_sin_cobertura_y_no_muta(self):
        tarea = Tarea(
            id="t2",
            tipo="captura",
            personas_minimas=2,
            habilidades_requeridas=(
                HabilidadRequerida(Habilidad.MANEJO_FELINOS, 4),
                HabilidadRequerida(Habilidad.MANEJO_AVES, 3),
            ),
            certificaciones_requeridas=frozenset({Certificacion.TRANQUILIZANTE}),
        )
        cuidadores = {
            "c1": Cuidador(
                "c1", "Felinos",
                habilidades={Habilidad.MANEJO_FELINOS: 4},
                estado=EstadoCuidador.DISPONIBLE,
            ),
            "c2": Cuidador(
                "c2", "Sin requisitos",
                estado=EstadoCuidador.DISPONIBLE,
            ),
        }
        mundo = Mundo(cuidadores=cuidadores, tareas={"t2": tarea})
        registro = RegistroEventos()
        self._registrar_plan(mundo, "t2", ("c1", "c2"))
        antes = copy.deepcopy(mundo)

        with pytest.raises(TransicionInvalida, match="no cubre"):
            ejecutar_transicion(
                mundo, registro, "Tarea", "t2",
                EstadoTarea.ASIGNADA, 10, "asignar equipo incompleto",
            )

        assert mundo == antes
        assert len(registro) == 0

    def test_vuelta_a_pendiente_limpia_cuidador(self):
        c1 = _cuidador(EstadoCuidador.ASIGNADO)
        t2 = Tarea(
            id="t2", tipo="test", estado=EstadoTarea.ASIGNADA,
            cuidadores_asignados=("c1",),
        )
        mundo = Mundo(cuidadores={"c1": c1}, tareas={"t2": t2})

        evento = ejecutar_transicion(
            mundo, RegistroEventos(), "Tarea", "t2",
            EstadoTarea.PENDIENTE, 20, "desasignar",
        )

        assert evento.datos_extra["cuidadores_ids"] == ()
        assert mundo.tareas["t2"].cuidadores_asignados == ()

    def test_en_curso_con_dependencia_completada(self):
        t1 = Tarea(id="t1", tipo="test", estado=EstadoTarea.COMPLETADA)
        t2 = Tarea(
            id="t2", tipo="test", estado=EstadoTarea.ASIGNADA,
            cuidadores_asignados=("c1",), dependencias=frozenset({"t1"}),
        )
        mundo = Mundo(tareas={"t1": t1, "t2": t2})

        ejecutar_transicion(
            mundo, RegistroEventos(), "Tarea", "t2",
            EstadoTarea.EN_CURSO, 30, "iniciar",
        )

        assert mundo.tareas["t2"].estado == EstadoTarea.EN_CURSO

    def test_en_curso_con_dependencia_pendiente_falla(self):
        t1 = Tarea(id="t1", tipo="test", estado=EstadoTarea.PENDIENTE)
        t2 = Tarea(
            id="t2", tipo="test", estado=EstadoTarea.ASIGNADA,
            cuidadores_asignados=("c1",), dependencias=frozenset({"t1"}),
        )
        mundo = Mundo(tareas={"t1": t1, "t2": t2})

        with pytest.raises(TransicionInvalida, match="pendientes"):
            ejecutar_transicion(
                mundo, RegistroEventos(), "Tarea", "t2",
                EstadoTarea.EN_CURSO, 30, "iniciar",
            )

        assert mundo.tareas["t2"].estado == EstadoTarea.ASIGNADA

    def test_dependencia_inexistente_lanza_error(self):
        t2 = Tarea(
            id="t2", tipo="test", estado=EstadoTarea.ASIGNADA,
            cuidadores_asignados=("c1",), dependencias=frozenset({"t_no_existe"}),
        )
        mundo = Mundo(tareas={"t2": t2})

        with pytest.raises(DependenciaInexistente):
            ejecutar_transicion(
                mundo, RegistroEventos(), "Tarea", "t2",
                EstadoTarea.EN_CURSO, 30, "iniciar",
            )

    def test_validador_tarea_directo(self):
        c1 = _cuidador(EstadoCuidador.DISPONIBLE)
        t2 = Tarea(id="t2", tipo="test")
        mundo = Mundo(cuidadores={"c1": c1}, tareas={"t2": t2})
        self._registrar_plan(mundo, "t2", ("c1",))

        assert validar_transicion_tarea_extra(
            "t2", EstadoTarea.PENDIENTE, EstadoTarea.ASIGNADA, mundo
        ) is None
        assert "requiere" in validar_transicion_tarea_extra(
            "t2", EstadoTarea.PENDIENTE, EstadoTarea.ASIGNADA,
            Mundo(tareas={"t2": t2}),
        )


# ============================================================================
# Incidente
# ============================================================================

class TestIncidente:
    def test_transicion_abierto_a_en_respuesta(self):
        mundo = Mundo(incidentes={"i1": _incidente()})

        ejecutar_transicion(
            mundo, RegistroEventos(), "Incidente", "i1",
            EstadoIncidente.EN_RESPUESTA, 10, "responder",
        )

        assert mundo.incidentes["i1"].estado == EstadoIncidente.EN_RESPUESTA

    def test_cerrar_con_tareas_pendientes_falla(self):
        incidente = _incidente(
            EstadoIncidente.CONTENIDO,
            tareas_generadas=frozenset({"t1"}),
            animal_relacionado="a1",
        )
        mundo = Mundo(
            incidentes={"i1": incidente},
            tareas={"t1": Tarea(id="t1", tipo="test")},
            animales={"a1": _animal(EstadoAnimal.EN_RECINTO)},
        )

        with pytest.raises(TransicionInvalida, match="tareas"):
            ejecutar_transicion(
                mundo, RegistroEventos(), "Incidente", "i1",
                EstadoIncidente.CERRADO, 10, "cerrar",
            )

        assert mundo.incidentes["i1"].estado == EstadoIncidente.CONTENIDO

    def test_cerrar_considera_tareas_vinculadas_por_incidente_origen(self):
        incidente = _incidente(
            EstadoIncidente.CONTENIDO,
            animal_relacionado="a1",
        )
        mundo = Mundo(
            incidentes={"i1": incidente},
            tareas={
                "t1": Tarea(
                    id="t1", tipo="test", incidente_origen="i1",
                ),
            },
            animales={"a1": _animal(EstadoAnimal.EN_RECINTO)},
        )

        with pytest.raises(TransicionInvalida, match="tareas"):
            ejecutar_transicion(
                mundo, RegistroEventos(), "Incidente", "i1",
                EstadoIncidente.CERRADO, 10, "cerrar",
            )

        assert mundo.incidentes["i1"].estado == EstadoIncidente.CONTENIDO

    def test_cerrar_con_animal_fuera_de_recinto_falla(self):
        incidente = _incidente(
            EstadoIncidente.CONTENIDO,
            tareas_generadas=frozenset({"t1"}),
            animal_relacionado="a1",
        )
        mundo = Mundo(
            incidentes={"i1": incidente},
            tareas={"t1": Tarea(
                id="t1", tipo="test", estado=EstadoTarea.COMPLETADA,
            )},
            animales={"a1": _animal(EstadoAnimal.ESCAPADO)},
        )

        with pytest.raises(TransicionInvalida, match="recinto"):
            ejecutar_transicion(
                mundo, RegistroEventos(), "Incidente", "i1",
                EstadoIncidente.CERRADO, 10, "cerrar",
            )

    def test_cerrar_con_condiciones_cumplidas(self):
        incidente = _incidente(
            EstadoIncidente.CONTENIDO,
            tareas_generadas=frozenset({"t1", "t2"}),
            animal_relacionado="a1",
        )
        mundo = Mundo(
            incidentes={"i1": incidente},
            tareas={
                "t1": Tarea(
                    id="t1", tipo="test", estado=EstadoTarea.COMPLETADA,
                ),
                "t2": Tarea(
                    id="t2", tipo="test", estado=EstadoTarea.CANCELADA,
                ),
            },
            animales={"a1": _animal(EstadoAnimal.EN_RECINTO)},
        )

        ejecutar_transicion(
            mundo, RegistroEventos(), "Incidente", "i1",
            EstadoIncidente.CERRADO, 10, "cerrar",
        )

        assert mundo.incidentes["i1"].estado == EstadoIncidente.CERRADO

    def test_no_se_puede_forzar_el_cierre_con_banderas(self):
        incidente = _incidente(
            EstadoIncidente.CONTENIDO,
            tareas_generadas=frozenset({"t1"}),
            animal_relacionado="a1",
        )
        mundo = Mundo(
            incidentes={"i1": incidente},
            tareas={"t1": Tarea(id="t1", tipo="test")},
            animales={"a1": _animal(EstadoAnimal.ESCAPADO)},
        )

        with pytest.raises(TransicionInvalida, match="tareas"):
            ejecutar_transicion(
                mundo, RegistroEventos(), "Incidente", "i1",
                EstadoIncidente.CERRADO, 10, "cerrar",
                tareas_completadas_o_canceladas=True,
                animal_en_recinto=True,
            )

        assert mundo.incidentes["i1"].estado == EstadoIncidente.CONTENIDO

    def test_bandera_de_animal_no_fuerza_el_cierre(self):
        incidente = _incidente(
            EstadoIncidente.CONTENIDO,
            tareas_generadas=frozenset({"t1"}),
            animal_relacionado="a1",
        )
        mundo = Mundo(
            incidentes={"i1": incidente},
            tareas={"t1": Tarea(
                id="t1", tipo="test", estado=EstadoTarea.COMPLETADA,
            )},
            animales={"a1": _animal(EstadoAnimal.ESCAPADO)},
        )

        with pytest.raises(TransicionInvalida, match="recinto"):
            ejecutar_transicion(
                mundo, RegistroEventos(), "Incidente", "i1",
                EstadoIncidente.CERRADO, 10, "cerrar",
                animal_en_recinto=True,
            )

    def test_cierre_con_tarea_inexistente_lanza_error(self):
        incidente = _incidente(
            EstadoIncidente.CONTENIDO,
            tareas_generadas=frozenset({"t_no_existe"}),
            animal_relacionado="a1",
        )
        mundo = Mundo(
            incidentes={"i1": incidente},
            animales={"a1": _animal(EstadoAnimal.EN_RECINTO)},
        )

        with pytest.raises(ErrorDominio, match="no existe"):
            ejecutar_transicion(
                mundo, RegistroEventos(), "Incidente", "i1",
                EstadoIncidente.CERRADO, 10, "cerrar",
            )

    def test_cierre_con_animal_inexistente_lanza_error(self):
        incidente = _incidente(
            EstadoIncidente.CONTENIDO,
            animal_relacionado="a_no_existe",
        )
        mundo = Mundo(incidentes={"i1": incidente})

        with pytest.raises(ErrorDominio, match="no existe"):
            ejecutar_transicion(
                mundo, RegistroEventos(), "Incidente", "i1",
                EstadoIncidente.CERRADO, 10, "cerrar",
            )

    def test_cierre_de_escape_sin_animal_lanza_error(self):
        incidente = _incidente(EstadoIncidente.CONTENIDO)

        with pytest.raises(ErrorDominio, match="animal_relacionado"):
            ejecutar_transicion(
                Mundo(incidentes={"i1": incidente}),
                RegistroEventos(), "Incidente", "i1",
                EstadoIncidente.CERRADO, 10, "cerrar",
            )

    def test_cierre_de_incidente_no_escape_no_exige_animal(self):
        incidente = _incidente(
            EstadoIncidente.CONTENIDO,
            tipo=TipoIncidente.FALLA_SOPORTE_VITAL,
            tareas_generadas=frozenset({"t1"}),
        )
        mundo = Mundo(
            incidentes={"i1": incidente},
            tareas={"t1": Tarea(
                id="t1", tipo="test", estado=EstadoTarea.COMPLETADA,
            )},
        )

        ejecutar_transicion(
            mundo, RegistroEventos(), "Incidente", "i1",
            EstadoIncidente.CERRADO, 10, "cerrar",
        )

        assert mundo.incidentes["i1"].estado == EstadoIncidente.CERRADO

    def test_validador_incidente_directo(self):
        incidente = _incidente(
            EstadoIncidente.CONTENIDO,
            tareas_generadas=frozenset({"t1"}),
            animal_relacionado="a1",
        )
        mundo_ok = Mundo(
            incidentes={"i1": incidente},
            tareas={"t1": Tarea(
                id="t1", tipo="test", estado=EstadoTarea.COMPLETADA,
            )},
            animales={"a1": _animal(EstadoAnimal.EN_RECINTO)},
        )
        mundo_pendiente = Mundo(
            incidentes={"i1": incidente},
            tareas={"t1": Tarea(id="t1", tipo="test")},
            animales={"a1": _animal(EstadoAnimal.EN_RECINTO)},
        )
        mundo_fuera = Mundo(
            incidentes={"i1": incidente},
            tareas={"t1": Tarea(
                id="t1", tipo="test", estado=EstadoTarea.COMPLETADA,
            )},
            animales={"a1": _animal(EstadoAnimal.ESCAPADO)},
        )

        assert validar_transicion_incidente_extra(
            incidente, EstadoIncidente.CONTENIDO,
            EstadoIncidente.CERRADO, mundo_ok,
        ) is None
        assert "tareas" in validar_transicion_incidente_extra(
            incidente, EstadoIncidente.CONTENIDO,
            EstadoIncidente.CERRADO, mundo_pendiente,
        )
        assert "recinto" in validar_transicion_incidente_extra(
            incidente, EstadoIncidente.CONTENIDO,
            EstadoIncidente.CERRADO, mundo_fuera,
        )
