"""Pruebas de asignación compuesta y reversión total."""

import copy

import pytest
from hypothesis import given, settings, strategies as st

from zoo_ops.dominio.catalogos import ESPECIES_CATALOGO
from zoo_ops.dominio.entidades import (
    Animal, Arista, Cuidador, Equipo, HabilidadRequerida, Mundo, Nodo,
    Recinto, Tarea, Vehiculo,
)
from zoo_ops.dominio.enums import (
    Certificacion, EstadoCuidador, EstadoEquipo, EstadoTarea, EstadoVehiculo,
    Habilidad, MedioPermitido, TipoEquipo, TipoNodo, TipoRecinto, TipoVehiculo,
)
from zoo_ops.dominio.errores import ErrorDominio, ReservaAtomicaFallida
from zoo_ops.dominio.eventos import (
    Evento, RegistroEventos, TipoEvento, reconstruir_estado,
    verificar_reconstruccion,
)
from zoo_ops.dominio.invariantes import verificar_invariantes
from zoo_ops.dominio.operaciones import (
    asignar_plan, desasignar_plan, liberar_plan_con_evento,
    registrar_plan_con_evento,
)
from zoo_ops.dominio.plan import PlanEjecucion
from zoo_ops.dominio.reservas import RegistroReservas, Reserva, TipoRecurso


def _mundo_pequeno():
    cuidadores = {
        "c1": Cuidador(
            "c1", "Uno",
            habilidades={Habilidad.MANEJO_FELINOS: 4},
            certificaciones=frozenset({
                Certificacion.TRANQUILIZANTE,
                Certificacion.CAMION_TRASLADO,
            }),
            estado=EstadoCuidador.DISPONIBLE,
        ),
        "c2": Cuidador(
            "c2", "Dos",
            habilidades={Habilidad.MANEJO_AVES: 3},
            certificaciones=frozenset({Certificacion.TRANQUILIZANTE}),
            estado=EstadoCuidador.DISPONIBLE,
        ),
        "c3": Cuidador(
            "c3", "Tres", estado=EstadoCuidador.DISPONIBLE,
        ),
    }
    tarea = Tarea(
        id="t1",
        tipo="traslado",
        nodo_destino="destino",
        habilidades_requeridas=(
            HabilidadRequerida(Habilidad.MANEJO_FELINOS, 4),
            HabilidadRequerida(Habilidad.MANEJO_AVES, 3),
        ),
        certificaciones_requeridas=frozenset({
            Certificacion.TRANQUILIZANTE,
        }),
        personas_minimas=3,
        vehiculo_requerido=TipoVehiculo.CAMION_TRASLADO,
        equipos_requeridos=(TipoEquipo.DARDOS_TRANQUILIZANTES,),
    )
    vehiculo = Vehiculo(
        "v1", TipoVehiculo.CAMION_TRASLADO, 10.0, 4, 2,
        Certificacion.CAMION_TRASLADO, ubicacion="garaje",
    )
    equipo = Equipo(
        "e1", TipoEquipo.DARDOS_TRANQUILIZANTES, ubicacion="bodega",
        estado=EstadoEquipo.DISPONIBLE,
    )
    especie_id, animal = next(iter(ESPECIES_CATALOGO.items()))

    return Mundo(
        cuidadores=cuidadores,
        vehiculos={"v1": vehiculo},
        equipos={"e1": equipo},
        animales={"a1": Animal(
            "a1", animal, "recinto", "recinto",
        )},
        recintos={"recinto": Recinto(
            "recinto", TipoRecinto.ABIERTO,
            especies_admitidas=frozenset({especie_id}),
        )},
        tareas={"t1": tarea},
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


def _plan(**cambios):
    valores = {
        "tarea_id": "t1",
        "cuidadores": ("c1", "c2", "c3"),
        "desde": 10,
        "hasta": 30,
        "vehiculo_id": "v1",
        "equipos": ("e1",),
        "animales_transportados": ("a1",),
        "ruta": ("garaje", "destino"),
    }
    valores.update(cambios)
    return PlanEjecucion(**valores)


def _fallar_anexo_en(k):
    class RegistroConFalloEnK(RegistroEventos):
        def __init__(self):
            super().__init__()
            self.llamadas = 0
            self.fallo_en = k

        def anexar(self, evento):
            self.llamadas += 1
            if self.fallo_en == self.llamadas:
                raise RuntimeError(f"fallo inyectado {self.fallo_en}")
            super().anexar(evento)

    return RegistroConFalloEnK()


def test_asignar_plan_compuesto_y_reconstruccion():
    inicial = _mundo_pequeno()
    mundo = copy.deepcopy(inicial)
    eventos = RegistroEventos()
    reservas = RegistroReservas()

    resultado = asignar_plan(
        mundo, eventos, reservas, _plan(), tiempo=5, causa="despacho",
    )

    assert len(resultado) == 6
    assert mundo.tareas["t1"].estado == EstadoTarea.ASIGNADA
    assert all(
        mundo.cuidadores[cuidador_id].estado == EstadoCuidador.ASIGNADO
        for cuidador_id in ("c1", "c2", "c3")
    )
    assert mundo.vehiculos["v1"].estado == EstadoVehiculo.RESERVADO
    assert mundo.planes == {"t1": _plan()}
    assert mundo.equipos["e1"].estado == EstadoEquipo.DISPONIBLE
    assert len(reservas.obtener_reservas_de_tarea("t1")) == 5
    assert verificar_invariantes(
        mundo, reservas, registro_eventos=eventos, estado_inicial=inicial,
    )[0] == []
    reconstruido = reconstruir_estado(eventos.obtener_todos(), inicial)
    assert verificar_reconstruccion(mundo, reconstruido) == []


@pytest.mark.parametrize("fallo_en", range(1, 7))
def test_asignar_plan_revierte_todos_los_pasos(fallo_en):
    mundo = _mundo_pequeno()
    eventos = _fallar_anexo_en(fallo_en)
    reservas = RegistroReservas()
    mundo_antes = mundo.instantanea()
    eventos_antes = eventos.instantanea()
    reservas_antes = reservas.instantanea()

    with pytest.raises(RuntimeError, match=f"fallo inyectado {fallo_en}"):
        asignar_plan(
            mundo, eventos, reservas, _plan(), tiempo=5, causa="fallar",
        )

    assert mundo == mundo_antes
    assert eventos.instantanea() == eventos_antes
    assert reservas.instantanea() == reservas_antes


def test_fallo_durante_insercion_de_reservas_revierte_todo():
    class RegistroReservasConFallo(RegistroReservas):
        def __init__(self):
            super().__init__()
            self.inserciones = 0

        def agregar_reserva(self, reserva):
            self.inserciones += 1
            if self.inserciones == 2:
                raise RuntimeError("fallo insertando reserva")
            super().agregar_reserva(reserva)

    mundo = _mundo_pequeno()
    eventos = RegistroEventos()
    reservas = RegistroReservasConFallo()
    mundo_antes = mundo.instantanea()
    eventos_antes = eventos.instantanea()
    reservas_antes = reservas.instantanea()

    with pytest.raises(RuntimeError, match="fallo insertando reserva"):
        asignar_plan(mundo, eventos, reservas, _plan(), 5, "fallar reserva")

    assert mundo == mundo_antes
    assert eventos.instantanea() == eventos_antes
    assert reservas.instantanea() == reservas_antes


@pytest.mark.parametrize(
    "caso",
    ["plan_invalido", "reloj", "plan_duplicado", "solapamiento"],
)
def test_fallos_previos_no_mutan_ni_consumen_ids(caso):
    mundo = _mundo_pequeno()
    eventos = RegistroEventos()
    reservas = RegistroReservas()
    plan = _plan()
    tiempo = 5
    if caso == "plan_invalido":
        plan = _plan(cuidadores=("ausente",))
    elif caso == "reloj":
        mundo.tiempo_actual = 6
    elif caso == "plan_duplicado":
        mundo.registrar_plan(plan)
    else:
        reservas.agregar_reserva(Reserva(
            TipoRecurso.CUIDADOR, "c2", "otra", 10, 30,
        ))

    mundo_antes = copy.deepcopy(mundo)
    eventos_antes = eventos.instantanea()
    reservas_antes = reservas.instantanea()
    error = ReservaAtomicaFallida if caso == "solapamiento" else ErrorDominio

    with pytest.raises(error):
        asignar_plan(mundo, eventos, reservas, plan, tiempo, "fallar")

    assert mundo == mundo_antes
    assert eventos.instantanea() == eventos_antes
    assert reservas.instantanea() == reservas_antes


def test_desasignar_plan_restaura_recursos_y_plan_con_historial():
    mundo = _mundo_pequeno()
    eventos = RegistroEventos()
    reservas = RegistroReservas()
    asignar_plan(mundo, eventos, reservas, _plan(), 5, "asignar")
    reservas_antes = RegistroReservas().instantanea()
    cantidad_eventos = len(eventos)

    resultado = desasignar_plan(
        mundo, eventos, reservas, "t1", tiempo=6, causa="cancelar",
    )

    assert len(resultado) == 6
    assert mundo.tareas["t1"].estado == EstadoTarea.PENDIENTE
    assert mundo.tareas["t1"].cuidadores_asignados == ()
    assert all(
        mundo.cuidadores[cuidador_id].estado == EstadoCuidador.DISPONIBLE
        for cuidador_id in ("c1", "c2", "c3")
    )
    assert mundo.vehiculos["v1"].estado == EstadoVehiculo.DISPONIBLE
    assert mundo.planes == {}
    assert reservas.instantanea() == reservas_antes
    assert len(eventos) == cantidad_eventos + 6


def test_desasignar_rechaza_tarea_no_asignada_sin_cambios():
    mundo = _mundo_pequeno()
    eventos = RegistroEventos()
    reservas = RegistroReservas()
    antes = (copy.deepcopy(mundo), eventos.instantanea(), reservas.instantanea())

    with pytest.raises(ErrorDominio, match="ASIGNADA"):
        desasignar_plan(mundo, eventos, reservas, "t1", 5, "rechazar")

    assert mundo == antes[0]
    assert eventos.instantanea() == antes[1]
    assert reservas.instantanea() == antes[2]


@pytest.mark.parametrize("fallo_en", range(1, 7))
def test_desasignar_plan_revierte_todo_si_falla_anexar(fallo_en):
    mundo = _mundo_pequeno()
    eventos = _fallar_anexo_en(None)
    reservas = RegistroReservas()
    asignar_plan(mundo, eventos, reservas, _plan(), 5, "asignar")
    eventos.llamadas = 0
    eventos_antes = eventos.instantanea()
    mundo_antes = copy.deepcopy(mundo)
    reservas_antes = reservas.instantanea()
    eventos.fallo_en = fallo_en

    with pytest.raises(RuntimeError, match=f"fallo inyectado {fallo_en}"):
        desasignar_plan(mundo, eventos, reservas, "t1", 6, "fallar")

    assert mundo == mundo_antes
    assert eventos.instantanea() == eventos_antes
    assert reservas.instantanea() == reservas_antes


def test_desasignar_plan_revierte_todo_si_falla_liberar_reservas(monkeypatch):
    import zoo_ops.dominio.operaciones as operaciones

    mundo = _mundo_pequeno()
    eventos = RegistroEventos()
    reservas = RegistroReservas()
    asignar_plan(mundo, eventos, reservas, _plan(), 5, "asignar")
    mundo_antes = copy.deepcopy(mundo)
    eventos_antes = eventos.instantanea()
    reservas_antes = reservas.instantanea()

    def fallar_liberacion(*_args):
        raise RuntimeError("fallo liberando reservas")

    monkeypatch.setattr(operaciones, "liberar_reservas_tarea", fallar_liberacion)
    with pytest.raises(RuntimeError, match="fallo liberando reservas"):
        desasignar_plan(mundo, eventos, reservas, "t1", 6, "fallar")

    assert mundo == mundo_antes
    assert eventos.instantanea() == eventos_antes
    assert reservas.instantanea() == reservas_antes


def test_registrar_plan_con_evento_no_borra_plan_preexistente_si_falla_anexar(
    monkeypatch,
):
    import zoo_ops.dominio.operaciones as operaciones

    mundo = _mundo_pequeno()
    plan = _plan()
    mundo.registrar_plan(plan)
    mundo_antes = copy.deepcopy(mundo)

    class RegistroConFallo(RegistroEventos):
        def anexar(self, evento):
            raise RuntimeError("fallo anexando plan")

    monkeypatch.setattr(operaciones, "exigir_plan_valido", lambda *_args: None)
    monkeypatch.setattr(operaciones, "aplicar_evento", lambda *_args: None)
    registro = RegistroConFallo()
    with pytest.raises(RuntimeError, match="fallo anexando plan"):
        registrar_plan_con_evento(mundo, registro, plan, 5, "fallar")

    assert mundo == mundo_antes
    assert registro.instantanea() == ([], 1)


def test_error_al_aplicar_registro_de_plan_preserva_plan_preexistente(monkeypatch):
    import zoo_ops.dominio.operaciones as operaciones

    mundo = _mundo_pequeno()
    plan = _plan()
    mundo.registrar_plan(plan)
    mundo_antes = copy.deepcopy(mundo)
    registro = RegistroEventos()

    monkeypatch.setattr(operaciones, "exigir_plan_valido", lambda *_args: None)
    with pytest.raises(ErrorDominio):
        registrar_plan_con_evento(mundo, registro, plan, 5, "duplicado")

    assert mundo == mundo_antes
    assert registro.obtener_todos() == []


def test_liberar_plan_con_evento_restablece_plan_si_falla_anexar():
    mundo = _mundo_pequeno()
    plan = _plan()
    mundo.registrar_plan(plan)
    mundo_antes = copy.deepcopy(mundo)

    class RegistroConFallo(RegistroEventos):
        def anexar(self, evento):
            raise RuntimeError("fallo liberando plan")

    registro = RegistroConFallo()
    with pytest.raises(RuntimeError, match="fallo liberando plan"):
        liberar_plan_con_evento(mundo, registro, "t1", 5, "fallar")

    assert mundo == mundo_antes
    assert registro.instantanea() == ([], 1)


def test_error_al_aplicar_liberacion_de_plan_no_se_enmascara(monkeypatch):
    import zoo_ops.dominio.operaciones as operaciones

    mundo = _mundo_pequeno()
    mundo.registrar_plan(_plan())
    mundo_antes = copy.deepcopy(mundo)
    registro = RegistroEventos()
    registro_antes = registro.instantanea()

    def fallar_aplicacion(*_args):
        raise RuntimeError("fallo original aplicando evento")

    monkeypatch.setattr(operaciones, "aplicar_evento", fallar_aplicacion)
    with pytest.raises(RuntimeError, match="fallo original aplicando evento"):
        liberar_plan_con_evento(mundo, registro, "t1", 5, "fallar")

    assert mundo == mundo_antes
    assert registro.obtener_todos() == registro_antes[0]
    assert registro.instantanea()[1] == registro_antes[1] + 1


@given(acciones=st.lists(st.booleans(), min_size=1, max_size=20))
@settings(max_examples=40, deadline=None)
def test_secuencia_asignar_desasignar_preserva_invariantes_y_reconstruccion(
    acciones,
):
    inicial = _mundo_pequeno()
    mundo = copy.deepcopy(inicial)
    eventos = RegistroEventos()
    reservas = RegistroReservas()
    asignado = False

    for indice, asignar in enumerate(acciones, start=1):
        if asignar and not asignado:
            plan = _plan(desde=indice, hasta=indice + 20)
            asignar_plan(
                mundo, eventos, reservas, plan,
                tiempo=indice, causa="propiedad asignar",
            )
            asignado = True
        elif not asignar and asignado:
            desasignar_plan(
                mundo, eventos, reservas, "t1",
                tiempo=indice, causa="propiedad desasignar",
            )
            asignado = False
        violaciones, _ = verificar_invariantes(mundo, reservas)
        assert violaciones == []
        assert verificar_reconstruccion(
            mundo,
            reconstruir_estado(eventos.obtener_todos(), inicial),
        ) == []


def test_asignar_directamente_sin_plan_falla_sin_mutar():
    from zoo_ops.dominio.estados import ejecutar_transicion
    from zoo_ops.dominio.errores import TransicionInvalida

    mundo = _mundo_pequeno()
    eventos = RegistroEventos()
    antes = copy.deepcopy(mundo)
    eventos_antes = eventos.instantanea()

    with pytest.raises(TransicionInvalida, match="plan"):
        ejecutar_transicion(
            mundo, eventos, "Tarea", "t1", EstadoTarea.ASIGNADA, 5,
            "sin plan",
        )

    assert mundo == antes
    assert eventos.instantanea() == eventos_antes


def test_instantaneas_restauran_estado_en_los_mismos_objetos():
    mundo = _mundo_pequeno()
    eventos = RegistroEventos()
    reservas = RegistroReservas()
    eventos.anexar(Evento(
        id=5, momento=1, tipo=TipoEvento.TICK_RELOJ,
        entidad_tipo="Reloj", entidad_id="reloj",
        estado_antes="", estado_despues="", causa="inicial",
    ))
    reservas.agregar_reserva(Reserva(
        TipoRecurso.CUIDADOR, "c1", "t0", 0, 1,
    ))
    mundo_antes = copy.deepcopy(mundo)
    eventos_antes = eventos.instantanea()
    reservas_antes = reservas.instantanea()
    referencias = (id(mundo), id(eventos), id(reservas))

    mundo.tiempo_actual = 99
    mundo.tareas.clear()
    eventos.siguiente_id_evento()
    eventos.anexar(Evento(
        id=6, momento=2, tipo=TipoEvento.TICK_RELOJ,
        entidad_tipo="Reloj", entidad_id="reloj",
        estado_antes="", estado_despues="", causa="extra",
    ))
    reservas.limpiar()

    mundo.restaurar(mundo_antes)
    eventos.restaurar(eventos_antes)
    reservas.restaurar(reservas_antes)

    assert (id(mundo), id(eventos), id(reservas)) == referencias
    assert mundo == mundo_antes
    assert eventos.instantanea() == eventos_antes
    assert eventos.siguiente_id_evento() == 6
    assert reservas.instantanea() == reservas_antes


def test_invariante_11_detecta_reservas_faltantes_sobrantes_y_tarea_ausente():
    from zoo_ops.dominio.estados import ejecutar_transicion
    from zoo_ops.dominio.operaciones import registrar_plan_con_evento

    mundo = _mundo_pequeno()
    plan = _plan()
    eventos = RegistroEventos()
    reservas = RegistroReservas()
    registrar_plan_con_evento(mundo, eventos, plan, 5, "plan")
    ejecutar_transicion(
        mundo, eventos, "Tarea", "t1", EstadoTarea.ASIGNADA, 5, "asignar",
    )
    paquete = [
        Reserva(TipoRecurso.CUIDADOR, "c1", "t1", 10, 30),
        Reserva(TipoRecurso.CUIDADOR, "extra", "t1", 10, 30),
        Reserva(TipoRecurso.EQUIPO, "e1", "missing-task", 10, 30),
    ]
    for reserva in paquete:
        reservas.agregar_reserva(reserva)

    violaciones, _ = verificar_invariantes(mundo, reservas)
    violaciones = [
        item for item in violaciones
        if item.invariante == "INV-11-reservas-plan"
    ]

    assert len(violaciones) == 6
    assert all(item.invariante == "INV-11-reservas-plan" for item in violaciones)


def test_invariante_11_no_violacion_con_paquete_exactamente_igual():
    mundo = _mundo_pequeno()
    eventos = RegistroEventos()
    reservas = RegistroReservas()
    asignar_plan(mundo, eventos, reservas, _plan(), 5, "asignar")

    violaciones, _ = verificar_invariantes(mundo, reservas)
    assert not any(
        item.invariante == "INV-11-reservas-plan"
        for item in violaciones
    )
