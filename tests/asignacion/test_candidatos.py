"""Pruebas de generación pura y determinista de candidatos."""

import copy

import pytest

from zoo_ops.asignacion.candidatos import generar_candidatos
from zoo_ops.dominio.entidades import (
    Animal, Arista, Cuidador, Equipo, HabilidadRequerida, Mundo, Nodo, Tarea,
    Vehiculo,
)
from zoo_ops.dominio.catalogos import ESPECIES_CATALOGO
from zoo_ops.dominio.enums import (
    Certificacion, EstadoCuidador, EstadoEquipo, EstadoTarea, EstadoVehiculo,
    Habilidad, MedioPermitido, TipoEquipo, TipoNodo, TipoVehiculo,
)
from zoo_ops.dominio.errores import ErrorDominio
from zoo_ops.dominio.eventos import RegistroEventos
from zoo_ops.dominio.invariantes import verificar_invariantes
from zoo_ops.dominio.operaciones import (
    asignar_plan, completar_plan, iniciar_ejecucion, llegar_a_destino,
)
from zoo_ops.dominio.reservas import (
    RegistroReservas, Reserva, TipoRecurso,
)


def _mundo(
    *,
    vehiculo_requerido=TipoVehiculo.CAMION_TRASLADO,
    estado_camion=EstadoVehiculo.DISPONIBLE,
    con_dardos=True,
    certificaciones_tranquilizante=True,
    tarea_estado=EstadoTarea.PENDIENTE,
    k=3,
):
    medios = frozenset({MedioPermitido.PIE, MedioPermitido.JEEP})
    nodos = {
        nodo_id: Nodo(nodo_id, tipo, x, y)
        for nodo_id, tipo, x, y in (
            ("garaje", TipoNodo.GARAJE, 0, 0),
            ("cruce", TipoNodo.CRUCE, 1, 0),
            ("destino", TipoNodo.RECINTO, 2, 0),
            ("patio", TipoNodo.CRUCE, 0, 1),
            ("bodega", TipoNodo.BODEGA, 1, 1),
        )
    }
    cuidadores = {}
    for indice in range(1, 6):
        certificaciones = {
            Certificacion.CAMION_TRASLADO,
            Certificacion.JEEP,
            Certificacion.HELICOPTERO,
        }
        if certificaciones_tranquilizante and indice <= 2:
            certificaciones.add(Certificacion.TRANQUILIZANTE)
        cuidadores[f"c{indice}"] = Cuidador(
            id=f"c{indice}",
            nombre=f"Cuidador {indice}",
            habilidades={Habilidad.MANEJO_FELINOS: 4},
            certificaciones=frozenset(certificaciones),
            velocidad_base=1,
            ubicacion=("patio",),
            estado=EstadoCuidador.DISPONIBLE,
        )
    vehiculos = {
        "camion": Vehiculo(
            "camion", TipoVehiculo.CAMION_TRASLADO, 10, 4, 2,
            Certificacion.CAMION_TRASLADO, "garaje", estado_camion,
        ),
        "jeep": Vehiculo(
            "jeep", TipoVehiculo.JEEP, 10, 2, 1,
            Certificacion.JEEP, "garaje", EstadoVehiculo.DISPONIBLE,
        ),
        "helicoptero": Vehiculo(
            "helicoptero", TipoVehiculo.HELICOPTERO, 10, 4, 2,
            Certificacion.HELICOPTERO, "garaje", EstadoVehiculo.DISPONIBLE,
        ),
    }
    equipos = {}
    if con_dardos:
        equipos["dardos"] = Equipo(
            "dardos", TipoEquipo.DARDOS_TRANQUILIZANTES, "bodega",
            EstadoEquipo.DISPONIBLE,
        )
    tarea = Tarea(
        "t1",
        "traslado de jaguar",
        nodo_destino="destino",
        duracion_estimada=20,
        habilidades_requeridas=(
            HabilidadRequerida(Habilidad.MANEJO_FELINOS, 4),
        ),
        certificaciones_requeridas=frozenset({Certificacion.TRANQUILIZANTE}),
        vehiculo_requerido=vehiculo_requerido,
        equipos_requeridos=(TipoEquipo.DARDOS_TRANQUILIZANTES,),
        estado=tarea_estado,
        personas_minimas=k,
    )
    return Mundo(
        nodos=nodos,
        aristas={
            ("patio", "garaje"): Arista(
                "patio", "garaje", 2, frozenset({MedioPermitido.PIE}),
            ),
            ("garaje", "cruce"): Arista("garaje", "cruce", 10, medios),
            ("cruce", "destino"): Arista("cruce", "destino", 10, medios),
        },
        cuidadores=cuidadores,
        vehiculos=vehiculos,
        equipos=equipos,
        tareas={"t1": tarea},
    )


def test_generar_candidatos_cubre_habilidad_y_certificaciones():
    mundo = _mundo()

    resultado = generar_candidatos(mundo, RegistroReservas(), "t1", 0)

    assert resultado.candidatos
    for candidato in resultado.candidatos:
        assert len(candidato.plan.cuidadores) == 3
        assert any(
            Certificacion.TRANQUILIZANTE
            in mundo.cuidadores[cuid].certificaciones
            for cuid in candidato.plan.cuidadores
        )
        assert candidato.plan.vehiculo_id == "camion"
        assert candidato.plan.equipos == ("dardos",)


def test_sin_vehiculo_requerido_disponible_se_descarta():
    mundo = _mundo(estado_camion=EstadoVehiculo.RESERVADO)

    resultado = generar_candidatos(mundo, RegistroReservas(), "t1", 0)

    assert not resultado.candidatos
    assert any(descartado.motivo == "sin_vehiculo" for descartado in resultado.descartados)


def test_sin_suficientes_cuidadores_alcanzables_se_descarta():
    mundo = _mundo()
    mundo.cuidadores.clear()

    resultado = generar_candidatos(mundo, RegistroReservas(), "t1", 0)

    assert not resultado.candidatos
    assert any(
        descartado.motivo == "pocos_cuidadores"
        for descartado in resultado.descartados
    )


def test_sin_equipo_requerido_se_descarta():
    mundo = _mundo(con_dardos=False)

    resultado = generar_candidatos(mundo, RegistroReservas(), "t1", 0)

    assert not resultado.candidatos
    assert any(descartado.motivo == "sin_equipo" for descartado in resultado.descartados)


def test_equipo_sin_certificacion_cuenta_como_sin_cobertura():
    mundo = _mundo(certificaciones_tranquilizante=False)

    resultado = generar_candidatos(mundo, RegistroReservas(), "t1", 0)

    assert not resultado.candidatos
    sin_cobertura = [
        descartado for descartado in resultado.descartados
        if descartado.motivo == "sin_cobertura"
    ]
    assert len(sin_cobertura) == 1


def test_reserva_ocupada_descarta_plan():
    mundo = _mundo()
    reservas = RegistroReservas()
    reservas.agregar_reserva(
        Reserva(TipoRecurso.VEHICULO, "camion", "otra", 0, 1000),
    )
    reservas_antes = reservas.instantanea()

    resultado = generar_candidatos(mundo, reservas, "t1", 0)

    assert not resultado.candidatos
    assert reservas.instantanea() == reservas_antes
    assert any(
        descartado.motivo == "reserva_ocupada"
        for descartado in resultado.descartados
    )


def test_cuidadores_con_tarea_activa_no_son_elegibles():
    mundo = _mundo()
    tarea_activa = Tarea(
        "activa", "otra tarea", nodo_destino="destino",
        estado=EstadoTarea.ASIGNADA, cuidadores_asignados=("c1",),
    )
    mundo.tareas["activa"] = tarea_activa

    resultado = generar_candidatos(mundo, RegistroReservas(), "t1", 0)

    assert resultado.candidatos
    assert all(
        "c1" not in candidato.plan.cuidadores
        for candidato in resultado.candidatos
    )


def test_cuidador_ubicado_fuera_del_grafo_no_es_elegible():
    mundo = _mundo()
    mundo.cuidadores["c6"] = Cuidador(
        "c6",
        "Cuidador fuera del grafo",
        habilidades={Habilidad.MANEJO_FELINOS: 4},
        certificaciones=frozenset({
            Certificacion.CAMION_TRASLADO,
            Certificacion.TRANQUILIZANTE,
        }),
        ubicacion=("nodo-ausente",),
        estado=EstadoCuidador.DISPONIBLE,
    )

    resultado = generar_candidatos(mundo, RegistroReservas(), "t1", 0)

    assert resultado.candidatos
    assert all("c6" not in candidato.plan.cuidadores for candidato in resultado.candidatos)


def test_tarea_sin_tipo_requerido_considera_helicoptero():
    mundo = _mundo(vehiculo_requerido=None)

    resultado = generar_candidatos(mundo, RegistroReservas(), "t1", 0)

    assert any(
        candidato.plan.vehiculo_id == "helicoptero"
        for candidato in resultado.candidatos
    )


def test_animales_transportados_no_generan_opcion_sin_vehiculo():
    mundo = _mundo(vehiculo_requerido=None)
    mundo.animales["jaguar"] = Animal(
        "jaguar", ESPECIES_CATALOGO["jaguar"], "recinto", "recinto",
    )

    resultado = generar_candidatos(
        mundo, RegistroReservas(), "t1", 0,
        animales_transportados=("jaguar",),
    )

    assert resultado.candidatos
    assert all(candidato.plan.vehiculo_id is not None for candidato in resultado.candidatos)


def test_sin_vehiculos_permitidos_y_sin_tipo_requerido_considera_solo_sin_vehiculo():
    mundo = _mundo(vehiculo_requerido=None)

    resultado = generar_candidatos(
        mundo, RegistroReservas(), "t1", 0, permitir_vehiculos=False,
    )

    assert resultado.candidatos
    assert all(candidato.plan.vehiculo_id is None for candidato in resultado.candidatos)


def test_capacidad_insuficiente_se_registra_como_descartado():
    mundo = _mundo(vehiculo_requerido=None, k=3)

    resultado = generar_candidatos(mundo, RegistroReservas(), "t1", 0)

    assert any(
        descartado.motivo == "capacidad"
        and "jeep" in " ".join(descartado.detalle)
        for descartado in resultado.descartados
    )


def test_ruta_de_candidato_terrestre_comienza_en_ubicacion_del_camion():
    mundo = _mundo()

    resultado = generar_candidatos(mundo, RegistroReservas(), "t1", 0)

    assert resultado.candidatos
    assert all(
        candidato.plan.ruta[0] == mundo.vehiculos["camion"].ubicacion
        for candidato in resultado.candidatos
    )


def test_recorte_voraz_produce_candidato_valido():
    mundo = _mundo()

    resultado = generar_candidatos(
        mundo, RegistroReservas(), "t1", 0, max_combinaciones=1,
    )

    assert resultado.candidatos
    assert resultado.candidatos[0].plan.cuidadores == ("c1", "c2", "c3")


def test_recorte_voraz_sin_cobertura_se_descarta_una_vez():
    mundo = _mundo(certificaciones_tranquilizante=False)

    resultado = generar_candidatos(
        mundo, RegistroReservas(), "t1", 0, max_combinaciones=1,
    )

    assert not resultado.candidatos
    sin_cobertura = [
        descartado for descartado in resultado.descartados
        if descartado.motivo == "sin_cobertura"
    ]
    assert len(sin_cobertura) == 1


def test_resultado_es_determinista_y_no_muta_mundo_ni_reservas():
    mundo = _mundo(vehiculo_requerido=None)
    reservas = RegistroReservas()
    mundo_antes = copy.deepcopy(mundo)
    reservas_antes = reservas.instantanea()

    primero = generar_candidatos(mundo, reservas, "t1", 0)
    segundo = generar_candidatos(mundo, reservas, "t1", 0)

    assert primero == segundo
    claves_orden = [
        (
            candidato.estimacion.hasta,
            candidato.plan.cuidadores,
            candidato.plan.vehiculo_id or "",
        )
        for candidato in primero.candidatos
    ]
    assert claves_orden == sorted(claves_orden)
    assert mundo == mundo_antes
    assert reservas.instantanea() == reservas_antes


def test_tarea_no_pendiente_se_rechaza():
    mundo = _mundo(tarea_estado=EstadoTarea.ASIGNADA)

    with pytest.raises(ErrorDominio, match="PENDIENTE"):
        generar_candidatos(mundo, RegistroReservas(), "t1", 0)


def test_tarea_inexistente_se_rechaza():
    with pytest.raises(ErrorDominio, match="no existe"):
        generar_candidatos(_mundo(), RegistroReservas(), "no-existe", 0)


def test_candidato_primero_completa_el_ciclo_en_los_tiempos_estimados():
    mundo = _mundo()
    eventos = RegistroEventos()
    reservas = RegistroReservas()
    resultado = generar_candidatos(mundo, reservas, "t1", 0)
    assert resultado.candidatos
    candidato = resultado.candidatos[0]

    asignar_plan(
        mundo, eventos, reservas, candidato.plan, 0, "asignación",
    )
    assert verificar_invariantes(mundo, reservas)[0] == []

    iniciar_ejecucion(
        mundo, eventos, reservas, "t1", candidato.estimacion.salida, "salida",
    )
    assert verificar_invariantes(mundo, reservas)[0] == []

    llegar_a_destino(
        mundo, eventos, reservas, "t1", candidato.estimacion.llegada, "llegada",
    )
    assert verificar_invariantes(mundo, reservas)[0] == []

    completar_plan(
        mundo, eventos, reservas, "t1", candidato.estimacion.fin, "completar",
    )
    assert verificar_invariantes(mundo, reservas)[0] == []
