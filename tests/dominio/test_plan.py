"""Pruebas del plan de ejecución y la cobertura de requisitos."""

import copy
from dataclasses import FrozenInstanceError

import pytest

from zoo_ops.dominio.entidades import (
    Arista, Cuidador, Equipo, HabilidadRequerida, Nodo, Tarea, Vehiculo, Mundo,
)
from zoo_ops.dominio.enums import (
    Certificacion, EstadoCuidador, EstadoEquipo, EstadoTarea, EstadoVehiculo,
    Habilidad, MedioPermitido, TipoEquipo, TipoNodo, TipoVehiculo,
)
from zoo_ops.dominio.errores import (
    ErrorDominio, EventoDuplicado, PlanInvalido, TiempoRetrocede,
)
from zoo_ops.dominio.estados import ejecutar_transicion
from zoo_ops.dominio.eventos import (
    Evento, RegistroEventos, TipoEvento, reconstruir_estado,
    verificar_reconstruccion,
)
from zoo_ops.dominio.plan import (
    PlanEjecucion, cubre_requisitos_cuidadores, exigir_plan_valido,
    validar_plan,
)
from zoo_ops.dominio.operaciones import (
    liberar_plan_con_evento, registrar_plan_con_evento,
)


def _cuidador(
    cuidador_id,
    habilidades=None,
    certificaciones=(),
    estado=EstadoCuidador.DISPONIBLE,
):
    return Cuidador(
        id=cuidador_id,
        nombre=cuidador_id,
        habilidades=habilidades or {},
        certificaciones=frozenset(certificaciones),
        estado=estado,
    )


def _vehiculo(
    tipo=TipoVehiculo.CAMION_TRASLADO,
    estado=EstadoVehiculo.DISPONIBLE,
    capacidad_personas=2,
    capacidad_animales=1,
    ubicacion="garaje",
    certificacion=Certificacion.CAMION_TRASLADO,
):
    return Vehiculo(
        id="v1",
        tipo=tipo,
        velocidad=5.0,
        capacidad_personas=capacidad_personas,
        capacidad_animales=capacidad_animales,
        certificacion_requerida=certificacion,
        ubicacion=ubicacion,
        estado=estado,
    )


def _tarea(**cambios):
    valores = {
        "id": "t1",
        "tipo": "traslado",
        "nodo_destino": "destino",
        "habilidades_requeridas": (
            HabilidadRequerida(Habilidad.MANEJO_FELINOS, 4),
            HabilidadRequerida(Habilidad.MANEJO_AVES, 3),
        ),
        "certificaciones_requeridas": frozenset({Certificacion.TRANQUILIZANTE}),
        "personas_minimas": 2,
        "vehiculo_requerido": TipoVehiculo.CAMION_TRASLADO,
        "equipos_requeridos": (TipoEquipo.DARDOS_TRANQUILIZANTES,),
    }
    valores.update(cambios)
    return Tarea(**valores)


def _mundo(tarea=None, **cambios):
    valores = {
        "tareas": {"t1": tarea or _tarea()},
        "cuidadores": {
            "c1": _cuidador(
                "c1",
                {Habilidad.MANEJO_FELINOS: 4},
                {Certificacion.TRANQUILIZANTE, Certificacion.CAMION_TRASLADO},
            ),
            "c2": _cuidador("c2", {Habilidad.MANEJO_AVES: 3}),
            "c3": _cuidador("c3", {Habilidad.MANEJO_AVES: 3}),
        },
        "vehiculos": {"v1": _vehiculo()},
        "equipos": {
            "e1": Equipo(
                id="e1",
                tipo=TipoEquipo.DARDOS_TRANQUILIZANTES,
                ubicacion="bodega",
            ),
        },
        "nodos": {
            "garaje": Nodo("garaje", TipoNodo.GARAJE, 0, 0),
            "destino": Nodo("destino", TipoNodo.RECINTO, 1, 1),
        },
        "aristas": {
            ("garaje", "destino"): Arista(
                "garaje", "destino", 10,
                frozenset({MedioPermitido.JEEP}),
            ),
        },
        "animales": {"a1": {"id": "a1"}},
        "tiempo_actual": 5,
    }
    valores.update(cambios)
    return Mundo(**valores)


def _plan(**cambios):
    valores = {
        "tarea_id": "t1",
        "cuidadores": ("c1", "c2"),
        "vehiculo_id": "v1",
        "equipos": ("e1",),
        "animales_transportados": ("a1",),
        "ruta": ("garaje", "destino"),
        "desde": 10,
        "hasta": 20,
    }
    valores.update(cambios)
    return PlanEjecucion(**valores)


class TestPlanEjecucion:
    @pytest.mark.parametrize("cambios", [
        {"tarea_id": ""},
        {"cuidadores": ()},
        {"cuidadores": ("c1", "c1")},
        {"equipos": ("e1", "e1")},
        {"animales_transportados": ("a1", "a1")},
        {"cuidadores": ["c1"]},
        {"desde": 20, "hasta": 20},
        {"desde": 21, "hasta": 20},
        {"ruta": ("",)},
    ])
    def test_rechaza_estructura_invalida(self, cambios):
        with pytest.raises(PlanInvalido):
            _plan(**cambios)

    def test_es_inmutable(self):
        plan = _plan()

        with pytest.raises(FrozenInstanceError):
            plan.desde = 30

    def test_valida_estructura_de_plan_basica(self):
        assert _plan().tarea_id == "t1"

    @pytest.mark.parametrize("faltante", ["desde", "hasta"])
    def test_desde_y_hasta_son_obligatorios(self, faltante):
        valores = {"tarea_id": "t1", "cuidadores": ("c1",), "desde": 0, "hasta": 1}
        del valores[faltante]

        with pytest.raises(TypeError):
            PlanEjecucion(**valores)


class TestCoberturaRequisitosCuidadores:
    def test_requisitos_pueden_cubrirse_entre_varios_cuidadores(self):
        tarea = _tarea()
        cuidadores = [_mundo().cuidadores[key] for key in ("c1", "c2")]

        assert cubre_requisitos_cuidadores(tarea, cuidadores) == []

    def test_informa_habilidad_y_certificacion_no_cubiertas(self):
        tarea = _tarea()
        cuidador = _cuidador("c1")

        errores = cubre_requisitos_cuidadores(tarea, [cuidador])

        assert any("MANEJO_FELINOS" in error for error in errores)
        assert any("MANEJO_AVES" in error for error in errores)
        assert any("TRANQUILIZANTE" in error for error in errores)


class TestValidarPlan:
    def test_plan_completo_valido_y_sin_mutaciones(self):
        mundo = _mundo()
        antes = copy.deepcopy(mundo)

        assert validar_plan(mundo, _plan()) == []
        assert mundo == antes

    def test_plan_duplicado_se_rechaza(self):
        mundo = _mundo()
        mundo.registrar_plan(_plan())

        errores = validar_plan(mundo, _plan())

        assert any("ya tiene un plan registrado" in error for error in errores)

    def test_plan_que_referencia_tarea_inexistente_se_rechaza(self):
        mundo = _mundo()

        assert any(
            "la tarea otra no existe en el mundo" in error
            for error in validar_plan(mundo, _plan(tarea_id="otra"))
        )

    def test_plan_de_otra_tarea_se_valida_con_su_tarea_del_mundo(self):
        mundo = _mundo()
        mundo.tareas["t2"] = Tarea(id="t2", tipo="alimentacion")

        assert validar_plan(
            mundo,
            _plan(
                tarea_id="t2", vehiculo_id=None, equipos=(),
                animales_transportados=(), ruta=(),
            ),
        ) == []

    def test_todos_los_cuidadores_deben_existir(self):
        errores = validar_plan(
            _mundo(), _plan(cuidadores=("c1", "inexistente")),
        )

        assert any("Cuidador inexistente no existe" in error for error in errores)

    def test_todos_los_cuidadores_deben_estar_disponibles(self):
        mundo = _mundo(cuidadores={
            **_mundo().cuidadores,
            "c2": _cuidador("c2", {Habilidad.MANEJO_AVES: 3}, estado=EstadoCuidador.EJECUTANDO),
        })

        assert any(
            "Cuidador c2 no está DISPONIBLE" in error
            for error in validar_plan(mundo, _plan())
        )

    def test_cantidad_cuidadores_debe_cumplir_minimo(self):
        assert any(
            "requiere al menos 2" in error
            for error in validar_plan(_mundo(), _plan(cuidadores=("c1",)))
        )

    def test_cobertura_de_requisitos_es_del_equipo(self):
        assert validar_plan(_mundo(), _plan()) == []

    def test_cobertura_de_habilidad_incompleta_se_rechaza(self):
        mundo = _mundo(cuidadores={"c1": _cuidador("c1")})

        assert any(
            "MANEJO_FELINOS" in error
            for error in validar_plan(mundo, _plan(cuidadores=("c1",)))
        )

    def test_cobertura_de_certificacion_incompleta_se_rechaza(self):
        mundo = _mundo(cuidadores={
            "c1": _cuidador(
                "c1", {Habilidad.MANEJO_FELINOS: 4},
            ),
            "c2": _cuidador("c2", {Habilidad.MANEJO_AVES: 3}),
        })

        assert any(
            "TRANQUILIZANTE" in error
            for error in validar_plan(mundo, _plan())
        )

    def test_tarea_debe_existir_en_el_mundo(self):
        mundo = _mundo(tareas={})

        assert validar_plan(mundo, _plan()) == [
            "la tarea t1 no existe en el mundo",
        ]

    def test_tarea_debe_estar_pendiente(self):
        mundo = _mundo(tarea=_tarea(estado=EstadoTarea.ASIGNADA))

        assert any(
            "no está PENDIENTE" in error
            for error in validar_plan(mundo, _plan())
        )

    def test_vehiculo_requerido_debe_estar_en_plan(self):
        assert any(
            "requiere vehículo" in error
            for error in validar_plan(_mundo(), _plan(vehiculo_id=None))
        )

    def test_vehiculo_debe_existir(self):
        assert any(
            "Vehículo faltante no existe" in error
            for error in validar_plan(_mundo(), _plan(vehiculo_id="faltante"))
        )

    def test_vehiculo_debe_estar_disponible(self):
        mundo = _mundo(vehiculos={"v1": _vehiculo(estado=EstadoVehiculo.EN_USO)})

        assert any(
            "Vehículo v1 no está DISPONIBLE" in error
            for error in validar_plan(mundo, _plan())
        )

    def test_vehiculo_debe_ser_del_tipo_requerido(self):
        mundo = _mundo(vehiculos={"v1": _vehiculo(tipo=TipoVehiculo.JEEP)})

        assert any(
            "tipo requerido" in error
            for error in validar_plan(mundo, _plan())
        )

    def test_algun_cuidador_debe_tener_certificacion_del_vehiculo(self):
        mundo = _mundo(cuidadores={
            "c1": _cuidador(
                "c1", {Habilidad.MANEJO_FELINOS: 4},
                {Certificacion.TRANQUILIZANTE},
            ),
            "c2": _cuidador("c2", {Habilidad.MANEJO_AVES: 3}),
        })

        assert any(
            "CAMION_TRASLADO" in error
            for error in validar_plan(mundo, _plan())
        )

    def test_equipo_debe_existir_y_estar_disponible(self):
        mundo = _mundo(equipos={
            "e1": Equipo(
                "e1", TipoEquipo.DARDOS_TRANQUILIZANTES, "bodega",
                EstadoEquipo.EN_USO,
            ),
        })

        assert any(
            "Equipo e1 no está DISPONIBLE" in error
            for error in validar_plan(mundo, _plan())
        )
        assert any(
            "Equipo faltante no existe" in error
            for error in validar_plan(_mundo(), _plan(equipos=("faltante",)))
        )

    def test_equipo_del_plan_debe_cubrir_tipos_requeridos(self):
        mundo = _mundo(equipos={
            "e1": Equipo("e1", TipoEquipo.RED_CAPTURA, "bodega"),
        })

        assert any(
            "DARDOS_TRANQUILIZANTES" in error
            for error in validar_plan(mundo, _plan())
        )

    def test_requisito_repetido_de_equipo_exige_suficiente_cantidad(self):
        tarea = _tarea(
            equipos_requeridos=(
                TipoEquipo.JAULA_PORTATIL,
                TipoEquipo.JAULA_PORTATIL,
            ),
        )
        mundo = _mundo(
            tarea=tarea,
            equipos={
                "e1": Equipo("e1", TipoEquipo.JAULA_PORTATIL, "bodega"),
            },
        )

        assert any(
            "2" in error and "JAULA_PORTATIL" in error
            for error in validar_plan(mundo, _plan(equipos=("e1",)))
        )

    def test_cantidad_suficiente_de_tipo_de_equipo_repetido_es_valida(self):
        tarea = _tarea(
            equipos_requeridos=(
                TipoEquipo.JAULA_PORTATIL,
                TipoEquipo.JAULA_PORTATIL,
            ),
        )
        mundo = _mundo(
            tarea=tarea,
            equipos={
                "e1": Equipo("e1", TipoEquipo.JAULA_PORTATIL, "bodega"),
                "e2": Equipo("e2", TipoEquipo.JAULA_PORTATIL, "bodega"),
            },
        )

        assert validar_plan(mundo, _plan(equipos=("e1", "e2"))) == []

    def test_cantidad_cuidadores_no_supera_capacidad(self):
        assert any(
            "capacidad de personas" in error
            for error in validar_plan(
                _mundo(), _plan(cuidadores=("c1", "c2", "c3")),
            )
        )

    def test_cantidad_animales_no_supera_capacidad(self):
        assert any(
            "capacidad de animales" in error
            for error in validar_plan(
                _mundo(animales={"a1": object(), "a2": object()}),
                _plan(animales_transportados=("a1", "a2")),
            )
        )

    def test_animales_transportados_deben_existir(self):
        mundo = _mundo(animales={})

        assert any(
            "Animal ausente no existe" in error
            for error in validar_plan(
                mundo, _plan(animales_transportados=("ausente",)),
            )
        )

    def test_animales_transportados_requieren_vehiculo(self):
        assert any(
            "requieren un vehículo" in error
            for error in validar_plan(
                _mundo(),
                _plan(vehiculo_id=None, animales_transportados=("a1",)),
            )
        )

    def test_inicio_no_antecede_tiempo_actual(self):
        assert any(
            "anterior al tiempo actual" in error
            for error in validar_plan(_mundo(), _plan(desde=4, hasta=20))
        )

    @pytest.mark.parametrize("cambios, esperado", [
        ({"ruta": ()}, "no puede estar vacía"),
        ({"ruta": ("otro", "destino")}, "empezar"),
        ({"ruta": ("garaje", "otro")}, "termina"),
        ({"ruta": ("garaje", "destino")}, "arista"),
    ])
    def test_ruta_jeep_debe_ser_valida(self, cambios, esperado):
        mundo = _mundo(vehiculos={
            "v1": _vehiculo(
                tipo=TipoVehiculo.JEEP,
                certificacion=Certificacion.JEEP,
                capacidad_personas=2,
            ),
        }, aristas={})

        assert any(
            esperado in error.lower()
            for error in validar_plan(
                _mundo(
                    vehiculos=mundo.vehiculos,
                    aristas=mundo.aristas,
                    tarea=_tarea(vehiculo_requerido=TipoVehiculo.JEEP),
                ),
                _plan(**cambios),
            )
        )

    def test_ruta_jeep_rechaza_arista_bloqueada_o_sin_medio(self):
        for arista in (
            Arista("garaje", "destino", 1, frozenset({MedioPermitido.JEEP}), True),
            Arista("garaje", "destino", 1, frozenset({MedioPermitido.PIE})),
        ):
            mundo = _mundo(
                vehiculos={
                    "v1": _vehiculo(
                        tipo=TipoVehiculo.JEEP,
                        certificacion=Certificacion.JEEP,
                    ),
                },
                aristas={("garaje", "destino"): arista},
            )

            errores = validar_plan(
                _mundo(
                    vehiculos=mundo.vehiculos,
                    aristas=mundo.aristas,
                    tarea=_tarea(vehiculo_requerido=TipoVehiculo.JEEP),
                ),
                _plan(ruta=("garaje", "destino")),
            )

            assert any("no es transitable" in error for error in errores)

    def test_ruta_no_se_exige_a_helicoptero(self):
        mundo = _mundo(vehiculos={
            "v1": _vehiculo(
                tipo=TipoVehiculo.HELICOPTERO,
                certificacion=Certificacion.HELICOPTERO,
            ),
        })
        tarea = _tarea(vehiculo_requerido=TipoVehiculo.HELICOPTERO)
        mundo.tareas["t1"] = tarea
        plan = _plan(cuidadores=(
            "c1",
            "c2",
        ))
        mundo.cuidadores["c1"] = _cuidador(
            "c1",
            {Habilidad.MANEJO_FELINOS: 4},
            {Certificacion.TRANQUILIZANTE, Certificacion.HELICOPTERO},
        )

        assert validar_plan(mundo, plan) == []

    def test_ruta_jeep_valida_se_acepta(self):
        mundo = _mundo(
            cuidadores={
                **_mundo().cuidadores,
                "c1": _cuidador(
                    "c1",
                    {Habilidad.MANEJO_FELINOS: 4},
                    {
                        Certificacion.TRANQUILIZANTE,
                        Certificacion.JEEP,
                    },
                ),
            },
            vehiculos={
                "v1": _vehiculo(
                    tipo=TipoVehiculo.JEEP,
                    certificacion=Certificacion.JEEP,
                ),
            },
            aristas={
                ("garaje", "destino"): Arista(
                    "garaje", "destino", 10,
                    frozenset({MedioPermitido.JEEP}),
                ),
            },
        )
        tarea = _tarea(vehiculo_requerido=TipoVehiculo.JEEP)
        mundo.tareas["t1"] = tarea

        assert validar_plan(
            mundo, _plan(ruta=("garaje", "destino")),
        ) == []

    def test_ruta_camion_valida_se_acepta(self):
        mundo = _mundo(
            tarea=_tarea(vehiculo_requerido=TipoVehiculo.CAMION_TRASLADO),
            aristas={
                ("garaje", "destino"): Arista(
                    "garaje", "destino", 10,
                    frozenset({MedioPermitido.JEEP}),
                ),
            },
        )

        assert validar_plan(
            mundo, _plan(ruta=("garaje", "destino")),
        ) == []

    def test_ruta_camion_vacia_se_rechaza(self):
        mundo = _mundo()

        assert any(
            "ruta terrestre no puede estar vacía" in error.lower()
            for error in validar_plan(mundo, _plan(ruta=()))
        )

    def test_ruta_camion_con_arista_bloqueada_se_rechaza(self):
        mundo = _mundo(aristas={
            ("garaje", "destino"): Arista(
                "garaje", "destino", 10,
                frozenset({MedioPermitido.JEEP}),
                bloqueada=True,
            ),
        })

        assert any(
            "no es transitable" in error
            for error in validar_plan(
                mundo, _plan(ruta=("garaje", "destino")),
            )
        )

    def test_ruta_terrestre_rechaza_nodo_inexistente(self):
        tarea = _tarea(nodo_destino="destino-ausente")
        mundo = _mundo(
            tarea=tarea,
            nodos={
                "garaje": Nodo("garaje", TipoNodo.GARAJE, 0, 0),
            },
            aristas={},
        )

        assert any(
            "destino-ausente" in error.lower() and "no existe" in error.lower()
            for error in validar_plan(
                mundo, _plan(ruta=("garaje", "destino-ausente")),
            )
        )

    def test_exigir_plan_valido_regresa_si_el_plan_es_correcto(self):
        exigir_plan_valido(_mundo(), _plan())

    def test_exigir_plan_valido_lanza_error_si_la_tarea_no_existe(self):
        with pytest.raises(PlanInvalido) as error:
            exigir_plan_valido(_mundo(), _plan(tarea_id="otra"))

        assert any(
            "la tarea otra no existe en el mundo" in item
            for item in error.value.errores
        )


class TestEventosDePlan:
    def _registro_con_id_uno(self):
        registro = RegistroEventos()
        registro.anexar(Evento(
            id=1, momento=0, tipo=TipoEvento.TICK_RELOJ,
            entidad_tipo="Reloj", entidad_id="reloj",
            estado_antes="", estado_despues="", causa="manual",
        ))
        registro.siguiente_id_evento = lambda: 1
        return registro

    def test_registrar_plan_con_evento_actualiza_mundo_reloj_y_registro(self):
        mundo = _mundo()
        plan = _plan()
        registro = RegistroEventos()

        evento = registrar_plan_con_evento(
            mundo, registro, plan, tiempo=10, causa="despacho",
        )

        assert evento.tipo == TipoEvento.PLAN_REGISTRADO
        assert mundo.planes == {"t1": plan}
        assert mundo.tiempo_actual == 10
        assert list(registro) == [evento]

    def test_id_duplicado_no_muta_al_registrar_plan(self):
        mundo = _mundo()
        registro = self._registro_con_id_uno()
        plan = _plan()
        mundo_antes = copy.deepcopy(mundo)
        eventos_antes = registro.obtener_todos()

        with pytest.raises(EventoDuplicado):
            registrar_plan_con_evento(
                mundo, registro, plan, tiempo=10, causa="duplicado",
            )

        assert mundo == mundo_antes
        assert registro.obtener_todos() == eventos_antes

    def test_liberar_plan_con_evento_actualiza_mundo_reloj_y_registro(self):
        mundo = _mundo()
        plan = _plan()
        mundo.registrar_plan(plan)
        registro = RegistroEventos()

        evento = liberar_plan_con_evento(
            mundo, registro, "t1", tiempo=10, causa="cancelar despacho",
        )

        assert evento.tipo == TipoEvento.PLAN_LIBERADO
        assert mundo.planes == {}
        assert mundo.tiempo_actual == 10
        assert list(registro) == [evento]

    def test_no_puede_liberar_plan_de_tarea_activa(self):
        plan = _plan()
        tarea = Tarea(
            id="t1", tipo="traslado", estado=EstadoTarea.ASIGNADA,
            cuidadores_asignados=plan.cuidadores,
        )
        mundo = _mundo(tarea)
        mundo.registrar_plan(plan)
        registro = RegistroEventos()
        antes = copy.deepcopy(mundo)

        with pytest.raises(ErrorDominio, match="tarea activa"):
            liberar_plan_con_evento(
                mundo, registro, "t1", tiempo=10, causa="liberar",
            )

        assert mundo == antes
        assert len(registro) == 0

    def test_id_duplicado_no_muta_al_liberar_plan(self):
        mundo = _mundo()
        mundo.registrar_plan(_plan())
        registro = self._registro_con_id_uno()
        mundo_antes = copy.deepcopy(mundo)
        eventos_antes = registro.obtener_todos()

        with pytest.raises(EventoDuplicado):
            liberar_plan_con_evento(
                mundo, registro, "t1", tiempo=10, causa="duplicado",
            )

        assert mundo == mundo_antes
        assert registro.obtener_todos() == eventos_antes

    def test_registro_y_asignacion_reconstruyen_el_mundo_vivo(self):
        inicial = _mundo()
        mundo = copy.deepcopy(inicial)
        plan = _plan()
        registro = RegistroEventos()

        registrar_plan_con_evento(
            mundo, registro, plan, tiempo=10, causa="registrar",
        )
        ejecutar_transicion(
            mundo, registro, "Tarea", "t1",
            EstadoTarea.ASIGNADA, 20, "asignar",
        )
        ejecutar_transicion(
            mundo, registro, "Tarea", "t1",
            EstadoTarea.EN_CURSO, 30, "iniciar",
        )
        ejecutar_transicion(
            mundo, registro, "Tarea", "t1",
            EstadoTarea.COMPLETADA, 40, "completar",
        )
        liberar_plan_con_evento(
            mundo, registro, "t1", tiempo=50, causa="liberar",
        )

        reconstruido = reconstruir_estado(registro.obtener_todos(), inicial)
        assert verificar_reconstruccion(mundo, reconstruido) == []

    def test_fallo_al_anexar_restaura_mundo_y_reloj(self):
        class RegistroQueFallaAlAnexar(RegistroEventos):
            def anexar(self, evento):
                raise RuntimeError("fallo de anexo")

        mundo = _mundo()
        registro = RegistroQueFallaAlAnexar()
        antes = copy.deepcopy(mundo)
        plan = _plan()

        with pytest.raises(RuntimeError, match="fallo de anexo"):
            registrar_plan_con_evento(
                mundo, registro, plan, tiempo=10, causa="registrar",
            )

        assert mundo == antes
        assert mundo.tiempo_actual == antes.tiempo_actual
        assert len(registro) == 0

    def test_fallo_al_anexar_liberacion_restaurar_mundo_y_reloj(self):
        class RegistroQueFallaAlAnexar(RegistroEventos):
            def anexar(self, evento):
                raise RuntimeError("fallo de anexo")

        mundo = _mundo()
        mundo.registrar_plan(_plan())
        registro = RegistroQueFallaAlAnexar()
        antes = copy.deepcopy(mundo)

        with pytest.raises(RuntimeError, match="fallo de anexo"):
            liberar_plan_con_evento(
                mundo, registro, "t1", tiempo=10, causa="liberar",
            )

        assert mundo == antes
        assert mundo.tiempo_actual == antes.tiempo_actual
        assert len(registro) == 0

    def test_rechaza_tiempo_retrocedido_y_plan_invalido_sin_mutaciones(self):
        mundo = _mundo()
        mundo.tiempo_actual = 12
        registro = RegistroEventos()
        antes = copy.deepcopy(mundo)
        plan = _plan(desde=12, hasta=22)

        with pytest.raises(TiempoRetrocede):
            registrar_plan_con_evento(
                mundo, registro, plan, tiempo=11, causa="retroceso",
            )
        with pytest.raises(PlanInvalido):
            registrar_plan_con_evento(
                mundo, registro, _plan(tarea_id="ausente"),
                tiempo=12, causa="sin tarea",
            )

        assert mundo == antes
        assert len(registro) == 0
