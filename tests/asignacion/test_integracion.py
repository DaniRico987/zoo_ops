"""Prueba de integración de estimación, asignación y ejecución."""

import ast
from pathlib import Path

from zoo_ops.asignacion import construir_plan, estimar_plan
from zoo_ops.dominio.entidades import Arista, Cuidador, Equipo, Mundo, Nodo, Tarea, Vehiculo
from zoo_ops.dominio.enums import (
    Certificacion, EstadoCuidador, EstadoEquipo, EstadoTarea, EstadoVehiculo,
    MedioPermitido, TipoEquipo, TipoNodo, TipoVehiculo,
)
from zoo_ops.dominio.eventos import RegistroEventos
from zoo_ops.dominio.invariantes import verificar_invariantes
from zoo_ops.dominio.operaciones import (
    asignar_plan, completar_plan, iniciar_ejecucion, llegar_a_destino,
)
from zoo_ops.dominio.plan import validar_plan
from zoo_ops.dominio.reservas import RegistroReservas


def _mundo_integracion():
    nodos = {
        "garaje": Nodo("garaje", TipoNodo.GARAJE, 0, 0),
        "cruce": Nodo("cruce", TipoNodo.CRUCE, 1, 0),
        "recogida": Nodo("recogida", TipoNodo.CRUCE, 0, 1),
        "destino": Nodo("destino", TipoNodo.RECINTO, 2, 0),
        "reserva": Nodo("reserva", TipoNodo.BODEGA, 3, 0),
    }
    medios_tierra = frozenset({MedioPermitido.JEEP})
    return Mundo(
        nodos=nodos,
        aristas={
            ("garaje", "cruce"): Arista(
                "garaje", "cruce", 10, medios_tierra,
            ),
            ("cruce", "destino"): Arista(
                "cruce", "destino", 10, medios_tierra,
            ),
            ("recogida", "garaje"): Arista(
                "recogida", "garaje", 5,
                frozenset({MedioPermitido.PIE}),
            ),
        },
        cuidadores={
            f"c{i}": Cuidador(
                f"c{i}", f"Cuidador {i}", ubicacion=("recogida",),
                certificaciones=frozenset({Certificacion.CAMION_TRASLADO}),
                estado=EstadoCuidador.DISPONIBLE,
            )
            for i in range(1, 4)
        },
        vehiculos={
            "v1": Vehiculo(
                "v1", TipoVehiculo.CAMION_TRASLADO, 10, 4, 2,
                Certificacion.CAMION_TRASLADO, "garaje",
                EstadoVehiculo.DISPONIBLE,
            ),
        },
        equipos={
            "dardos": Equipo(
                "dardos", TipoEquipo.DARDOS_TRANQUILIZANTES, "reserva",
                EstadoEquipo.DISPONIBLE,
            ),
        },
        tareas={
            "t1": Tarea(
                "t1", "traslado", nodo_destino="destino",
                duracion_estimada=30, personas_minimas=3,
                vehiculo_requerido=TipoVehiculo.CAMION_TRASLADO,
                equipos_requeridos=(TipoEquipo.DARDOS_TRANQUILIZANTES,),
            ),
        },
    )


def test_flujo_estimacion_asignacion_y_ejecucion_con_camion_y_dardos():
    mundo = _mundo_integracion()
    inicial = mundo.instantanea()
    eventos = RegistroEventos()
    reservas = RegistroReservas()
    tarea = mundo.tareas["t1"]
    cuidadores_ids = ("c1", "c2", "c3")

    estimacion = estimar_plan(mundo, tarea, cuidadores_ids, "v1", 0)
    assert estimacion is not None
    plan = construir_plan(
        estimacion, tarea, cuidadores_ids, "v1", ("dardos",),
    )
    assert validar_plan(mundo, plan) == []

    asignar_plan(mundo, eventos, reservas, plan, 0, "asignación")
    assert verificar_invariantes(mundo, reservas)[0] == []

    iniciar_ejecucion(mundo, eventos, reservas, "t1", 5, "salida")
    assert verificar_invariantes(mundo, reservas)[0] == []

    llegar_a_destino(mundo, eventos, reservas, "t1", 7, "llegada")
    assert verificar_invariantes(mundo, reservas)[0] == []

    completar_plan(mundo, eventos, reservas, "t1", 8, "completar")
    assert verificar_invariantes(mundo, reservas)[0] == []
    assert mundo.tareas["t1"].estado == EstadoTarea.COMPLETADA


def test_el_dominio_no_importa_el_paquete_de_asignacion():
    raiz = Path(__file__).resolve().parents[2]
    directorio_dominio = raiz / "zoo_ops" / "dominio"
    violaciones = []

    for ruta in sorted(directorio_dominio.rglob("*.py")):
        arbol = ast.parse(ruta.read_text(encoding="utf-8"), filename=str(ruta))
        for nodo in ast.walk(arbol):
            if isinstance(nodo, ast.Import):
                if any(
                    alias.name == "zoo_ops.asignacion"
                    or alias.name.startswith("zoo_ops.asignacion.")
                    for alias in nodo.names
                ):
                    violaciones.append((ruta, nodo.lineno))
            elif isinstance(nodo, ast.ImportFrom):
                importa_paquete = nodo.level == 0 and (
                    nodo.module == "zoo_ops.asignacion"
                    or (nodo.module or "").startswith("zoo_ops.asignacion.")
                )
                importa_desde_paquete_raiz = (
                    nodo.level == 0
                    and nodo.module == "zoo_ops"
                    and any(
                        alias.name == "asignacion"
                        or alias.name.startswith("asignacion.")
                        for alias in nodo.names
                    )
                )
                if importa_paquete or importa_desde_paquete_raiz:
                    violaciones.append((ruta, nodo.lineno))

    assert not violaciones
