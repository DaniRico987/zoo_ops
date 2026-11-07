"""Integración de propuestas, ejecución y cierre de un escape de jaguar."""

import copy

import pytest

from zoo_ops.asignacion.confirmacion import (
    aplicar_pendientes,
    generar_pendientes,
)
from zoo_ops.asignacion.planificacion import planificar
from zoo_ops.dominio.catalogos import ESPECIES_CATALOGO
from zoo_ops.dominio.entidades import (
    Animal,
    Arista,
    Cuidador,
    EfectoAnimal,
    Equipo,
    HabilidadRequerida,
    Incidente,
    MomentoEfecto,
    Mundo,
    Nodo,
    Recinto,
    Tarea,
    Vehiculo,
)
from zoo_ops.dominio.enums import (
    Certificacion,
    EstadoAnimal,
    EstadoCuidador,
    EstadoEquipo,
    EstadoIncidente,
    EstadoTarea,
    EstadoVehiculo,
    Habilidad,
    MedioPermitido,
    PrioridadTarea,
    TipoEquipo,
    TipoIncidente,
    TipoNodo,
    TipoRecinto,
    TipoVehiculo,
)
from zoo_ops.dominio.errores import ErrorDominio
from zoo_ops.dominio.eventos import (
    RegistroEventos,
    reconstruir_estado,
    verificar_reconstruccion,
)
from zoo_ops.dominio.invariantes import verificar_invariantes
from zoo_ops.dominio.estados import ejecutar_transicion
from zoo_ops.dominio.operaciones import (
    abrir_incidente,
    completar_plan,
    fallar_plan,
    iniciar_ejecucion,
    llegar_a_destino,
)
from zoo_ops.dominio.reservas import RegistroReservas


def _mundo_escape():
    medios = frozenset({MedioPermitido.JEEP, MedioPermitido.PIE})
    nodos = {
        "garaje": Nodo("garaje", TipoNodo.GARAJE, 0, 0),
        "zona": Nodo("zona", TipoNodo.CRUCE, 1, 0),
        "recinto": Nodo("recinto", TipoNodo.RECINTO, 2, 0),
    }
    aristas = {
        (origen, destino): Arista(origen, destino, 10, medios)
        for origen in nodos
        for destino in nodos
        if origen != destino
    }
    cuidadores = {}
    for indice in range(1, 6):
        certificaciones = {Certificacion.CAMION_TRASLADO}
        if indice <= 2:
            certificaciones.add(Certificacion.TRANQUILIZANTE)
        cuidadores[f"c{indice}"] = Cuidador(
            id=f"c{indice}",
            nombre=f"Cuidador {indice}",
            habilidades={Habilidad.MANEJO_FELINOS: 4},
            certificaciones=frozenset(certificaciones),
            ubicacion=("garaje",),
            estado=EstadoCuidador.DISPONIBLE,
        )

    return Mundo(
        nodos=nodos,
        aristas=aristas,
        recintos={
            "recinto": Recinto(
                "recinto",
                TipoRecinto.ABIERTO,
                especies_admitidas=frozenset({"jaguar"}),
            ),
        },
        cuidadores=cuidadores,
        vehiculos={
            "camion": Vehiculo(
                "camion",
                TipoVehiculo.CAMION_TRASLADO,
                10,
                5,
                2,
                Certificacion.CAMION_TRASLADO,
                "zona",
                EstadoVehiculo.DISPONIBLE,
            ),
        },
        animales={
            "jaguar": Animal(
                "jaguar",
                ESPECIES_CATALOGO["jaguar"],
                "recinto",
                "zona",
                EstadoAnimal.ESCAPADO,
            ),
        },
        equipos={
            "dardos": Equipo(
                "dardos",
                TipoEquipo.DARDOS_TRANQUILIZANTES,
                "zona",
                EstadoEquipo.DISPONIBLE,
            ),
        },
    )


def _incidente_y_tareas():
    incidente = Incidente(
        "escape",
        TipoIncidente.ESCAPE_TERRESTRE,
        9,
        "zona",
        animal_relacionado="jaguar",
    )
    tareas = (
        Tarea(
            "t1",
            "localizar",
            prioridad_base=PrioridadTarea.CRITICA,
            nodo_destino="zona",
            habilidades_requeridas=(
                HabilidadRequerida(Habilidad.MANEJO_FELINOS, 4),
            ),
            efectos=(EfectoAnimal(
                "jaguar",
                EstadoAnimal.LOCALIZADO,
                MomentoEfecto.AL_COMPLETAR,
            ),),
        ),
        Tarea(
            "t2",
            "tranquilizar",
            prioridad_base=PrioridadTarea.CRITICA,
            nodo_destino="zona",
            certificaciones_requeridas=frozenset({
                Certificacion.TRANQUILIZANTE,
            }),
            equipos_requeridos=(TipoEquipo.DARDOS_TRANQUILIZANTES,),
            dependencias=frozenset({"t1"}),
            efectos=(EfectoAnimal(
                "jaguar",
                EstadoAnimal.TRANQUILIZADO,
                MomentoEfecto.AL_COMPLETAR,
            ),),
        ),
        Tarea(
            "t3",
            "trasladar",
            prioridad_base=PrioridadTarea.CRITICA,
            nodo_destino="recinto",
            vehiculo_requerido=TipoVehiculo.CAMION_TRASLADO,
            dependencias=frozenset({"t2"}),
            personas_minimas=3,
            efectos=(
                EfectoAnimal(
                    "jaguar",
                    EstadoAnimal.EN_TRASLADO,
                    MomentoEfecto.AL_INICIAR,
                ),
                EfectoAnimal(
                    "jaguar",
                    EstadoAnimal.EN_RECINTO,
                    MomentoEfecto.AL_COMPLETAR,
                    recinto_destino="recinto",
                ),
            ),
        ),
    )
    return incidente, tareas


def _comprobar_invariantes(mundo, reservas, eventos, inicial):
    violaciones, _ = verificar_invariantes(
        mundo,
        reservas,
        registro_eventos=eventos,
        estado_inicial=inicial,
    )
    assert violaciones == []


def _procesar_tarea(mundo, reservas, eventos, inicial, tarea_id, fallar=False):
    resultado = planificar(mundo, reservas, mundo.tiempo_actual)
    assert any(asignacion.tarea_id == tarea_id
               for asignacion in resultado.asignaciones)
    pendientes = generar_pendientes(resultado, mundo.tiempo_actual)
    assert pendientes
    assert all(propuesta.requiere_confirmacion for propuesta in pendientes)
    confirmaciones = {
        propuesta.id: None
        for propuesta in pendientes
        if propuesta.requiere_confirmacion
    }
    informe = aplicar_pendientes(
        mundo,
        eventos,
        reservas,
        pendientes,
        mundo.tiempo_actual,
        "confirmación de emergencia",
        confirmaciones,
    )
    aplicadas = informe.por_estado("aplicada")
    assert len(aplicadas) == 1
    estimacion = aplicadas[0].estimacion
    assert estimacion is not None
    if tarea_id == "t3":
        assert mundo.planes[tarea_id].animales_transportados == ("jaguar",)
    _comprobar_invariantes(mundo, reservas, eventos, inicial)

    iniciar_ejecucion(
        mundo, eventos, reservas, tarea_id, estimacion.salida, "iniciar",
    )
    _comprobar_invariantes(mundo, reservas, eventos, inicial)
    llegar_a_destino(
        mundo, eventos, reservas, tarea_id, estimacion.llegada, "llegada",
    )
    _comprobar_invariantes(mundo, reservas, eventos, inicial)
    if fallar:
        fallar_plan(
            mundo, eventos, reservas, tarea_id, estimacion.fin, "fallo",
        )
    else:
        completar_plan(
            mundo, eventos, reservas, tarea_id, estimacion.fin, "completar",
        )
    _comprobar_invariantes(mundo, reservas, eventos, inicial)


def test_flujo_completo_de_escape_reconstruye_y_cierra_el_incidente():
    mundo = _mundo_escape()
    inicial = copy.deepcopy(mundo)
    eventos = RegistroEventos()
    reservas = RegistroReservas()
    incidente, tareas = _incidente_y_tareas()

    abrir_incidente(mundo, eventos, incidente, list(tareas), 0, "escape")
    _comprobar_invariantes(mundo, reservas, eventos, inicial)
    ejecutar_transicion(
        mundo,
        eventos,
        "Incidente",
        "escape",
        EstadoIncidente.EN_RESPUESTA,
        0,
        "respuesta iniciada",
    )
    _comprobar_invariantes(mundo, reservas, eventos, inicial)

    for tarea_id in ("t1", "t2", "t3"):
        _procesar_tarea(
            mundo, reservas, eventos, inicial, tarea_id,
        )

    jaguar = mundo.animales["jaguar"]
    assert jaguar.estado == EstadoAnimal.EN_RECINTO
    assert jaguar.ubicacion == "recinto"
    assert all(
        mundo.tareas[tarea_id].estado == EstadoTarea.COMPLETADA
        for tarea_id in ("t1", "t2", "t3")
    )
    assert all(
        cuidador.estado == EstadoCuidador.DISPONIBLE
        for cuidador in mundo.cuidadores.values()
    )
    assert mundo.vehiculos["camion"].estado == EstadoVehiculo.DISPONIBLE
    assert mundo.equipos["dardos"].estado == EstadoEquipo.DISPONIBLE
    assert reservas.reservas_por_recurso() == {}

    ejecutar_transicion(
        mundo,
        eventos,
        "Incidente",
        "escape",
        EstadoIncidente.CONTENIDO,
        mundo.tiempo_actual,
        "animal contenido",
    )
    _comprobar_invariantes(mundo, reservas, eventos, inicial)
    ejecutar_transicion(
        mundo,
        eventos,
        "Incidente",
        "escape",
        EstadoIncidente.CERRADO,
        mundo.tiempo_actual,
        "incidente resuelto",
    )
    _comprobar_invariantes(mundo, reservas, eventos, inicial)

    reconstruido = reconstruir_estado(eventos.obtener_todos(), inicial)
    assert verificar_reconstruccion(mundo, reconstruido) == []


def test_emergencia_sin_confirmacion_no_modifica_mundo_ni_registros():
    mundo = _mundo_escape()
    inicial = copy.deepcopy(mundo)
    eventos = RegistroEventos()
    reservas = RegistroReservas()
    incidente, tareas = _incidente_y_tareas()
    abrir_incidente(mundo, eventos, incidente, list(tareas), 0, "escape")
    resultado = planificar(mundo, reservas, mundo.tiempo_actual)
    pendientes = generar_pendientes(resultado, mundo.tiempo_actual)
    assert pendientes
    assert all(propuesta.requiere_confirmacion for propuesta in pendientes)
    mundo_antes = copy.deepcopy(mundo)
    eventos_antes = eventos.instantanea()
    reservas_antes = reservas.instantanea()

    informe = aplicar_pendientes(
        mundo,
        eventos,
        reservas,
        pendientes,
        mundo.tiempo_actual,
        "sin confirmación",
    )

    assert informe.por_estado("pendiente_de_confirmacion")
    assert mundo == mundo_antes
    assert eventos.instantanea() == eventos_antes
    assert reservas.instantanea() == reservas_antes
    _comprobar_invariantes(mundo, reservas, eventos, inicial)


def test_fallar_tranquilizacion_deja_jaguar_localizado_y_no_cierra_incidente():
    mundo = _mundo_escape()
    inicial = copy.deepcopy(mundo)
    eventos = RegistroEventos()
    reservas = RegistroReservas()
    incidente, tareas = _incidente_y_tareas()
    abrir_incidente(mundo, eventos, incidente, list(tareas), 0, "escape")
    _comprobar_invariantes(mundo, reservas, eventos, inicial)
    ejecutar_transicion(
        mundo,
        eventos,
        "Incidente",
        "escape",
        EstadoIncidente.EN_RESPUESTA,
        0,
        "respuesta iniciada",
    )
    _comprobar_invariantes(mundo, reservas, eventos, inicial)
    _procesar_tarea(mundo, reservas, eventos, inicial, "t1")

    _procesar_tarea(
        mundo, reservas, eventos, inicial, "t2", fallar=True,
    )

    assert mundo.animales["jaguar"].estado == EstadoAnimal.LOCALIZADO
    assert mundo.tareas["t2"].estado == EstadoTarea.FALLIDA
    ejecutar_transicion(
        mundo,
        eventos,
        "Incidente",
        "escape",
        EstadoIncidente.CONTENIDO,
        mundo.tiempo_actual,
        "respuesta contenida",
    )
    _comprobar_invariantes(mundo, reservas, eventos, inicial)
    with pytest.raises(ErrorDominio):
        ejecutar_transicion(
            mundo,
            eventos,
            "Incidente",
            "escape",
            EstadoIncidente.CERRADO,
            mundo.tiempo_actual,
            "intento de cierre",
        )

    assert mundo.incidentes["escape"].estado == EstadoIncidente.CONTENIDO
    assert mundo.animales["jaguar"].estado == EstadoAnimal.LOCALIZADO
    _comprobar_invariantes(mundo, reservas, eventos, inicial)
