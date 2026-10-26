"""Planes de ejecución y validación de requisitos de recursos."""

from collections import Counter
from dataclasses import dataclass, field
from typing import Iterable, List, Optional, Tuple

from zoo_ops.dominio.entidades import Cuidador, Mundo, Tarea, Vehiculo
from zoo_ops.dominio.enums import (
    EstadoCuidador, EstadoEquipo, EstadoTarea, EstadoVehiculo,
    MedioPermitido, TipoVehiculo,
)
from zoo_ops.dominio.errores import PlanInvalido


@dataclass(frozen=True)
class PlanEjecucion:
    """Recursos y ventana temporal asignados para ejecutar una tarea."""

    tarea_id: str
    cuidadores: Tuple[str, ...]
    desde: int
    hasta: int
    vehiculo_id: Optional[str] = None
    equipos: Tuple[str, ...] = field(default_factory=tuple)
    animales_transportados: Tuple[str, ...] = field(default_factory=tuple)
    ruta: Tuple[str, ...] = field(default_factory=tuple)

    def __post_init__(self) -> None:
        """Rechaza planes cuya estructura no permita una ejecución válida."""
        errores = []
        if not isinstance(self.tarea_id, str) or not self.tarea_id:
            errores.append("tarea_id debe ser un ID no vacío")
        if not isinstance(self.cuidadores, tuple) or not self.cuidadores:
            errores.append("cuidadores debe ser una tupla no vacía")
        elif any(not isinstance(item, str) or not item for item in self.cuidadores):
            errores.append("cada cuidador debe tener un ID no vacío")
        elif len(self.cuidadores) != len(set(self.cuidadores)):
            errores.append("cuidadores no puede contener duplicados")
        if self.vehiculo_id is not None and (
            not isinstance(self.vehiculo_id, str) or not self.vehiculo_id
        ):
            errores.append("vehiculo_id debe ser None o un ID no vacío")
        if not isinstance(self.equipos, tuple):
            errores.append("equipos debe ser una tupla")
        elif any(not isinstance(item, str) or not item for item in self.equipos):
            errores.append("cada equipo debe tener un ID no vacío")
        elif len(self.equipos) != len(set(self.equipos)):
            errores.append("equipos no puede contener duplicados")
        if not isinstance(self.animales_transportados, tuple):
            errores.append("animales_transportados debe ser una tupla")
        elif any(
            not isinstance(item, str) or not item
            for item in self.animales_transportados
        ):
            errores.append("cada animal transportado debe tener un ID no vacío")
        elif len(self.animales_transportados) != len(set(self.animales_transportados)):
            errores.append("animales_transportados no puede contener duplicados")
        if not isinstance(self.ruta, tuple):
            errores.append("ruta debe ser una tupla")
        elif any(not isinstance(item, str) or not item for item in self.ruta):
            errores.append("cada nodo de la ruta debe tener un ID no vacío")
        if (
            not isinstance(self.desde, int) or isinstance(self.desde, bool)
            or not isinstance(self.hasta, int) or isinstance(self.hasta, bool)
            or self.hasta <= self.desde
        ):
            errores.append("hasta debe ser mayor que desde y ambos deben ser enteros")
        if errores:
            raise PlanInvalido(errores)


def cubre_requisitos_cuidadores(
    tarea: Tarea,
    cuidadores: Iterable[Cuidador],
) -> List[str]:
    """Comprueba si el equipo cubre colectivamente habilidades y certificaciones."""
    equipo = tuple(cuidadores)
    errores = []
    for requisito in tarea.habilidades_requeridas:
        nivel_maximo = max(
            (cuidador.habilidades.get(requisito.habilidad, 0) for cuidador in equipo),
            default=0,
        )
        if nivel_maximo < requisito.nivel_minimo:
            errores.append(
                f"El equipo no cubre {requisito.habilidad.name}: "
                f"nivel {nivel_maximo} < {requisito.nivel_minimo} "
                "(nivel máximo del equipo)"
            )
    for certificacion in tarea.certificaciones_requeridas:
        if not any(
            certificacion in cuidador.certificaciones for cuidador in equipo
        ):
            errores.append(
                f"El equipo no cubre la certificación {certificacion.name}"
            )
    return errores


def validar_capacidad_vehiculo(
    vehiculo: Vehiculo,
    cuidadores: Tuple[str, ...],
    animales_transportados: Tuple[str, ...],
) -> List[str]:
    """Devuelve los excesos de capacidad de personas o animales."""
    errores = []
    if len(cuidadores) > vehiculo.capacidad_personas:
        errores.append(
            f"El equipo de cuidadores excede la capacidad de personas "
            f"del vehículo {vehiculo.id}"
        )
    if len(animales_transportados) > vehiculo.capacidad_animales:
        errores.append(
            f"Los animales exceden la capacidad de animales del vehículo "
            f"{vehiculo.id}"
        )
    return errores


def validar_ruta_terrestre(
    mundo: Mundo,
    tarea: Tarea,
    plan: PlanEjecucion,
) -> List[str]:
    """Valida la ruta de cualquier vehículo terrestre, excepto helicópteros."""
    errores = []
    vehiculo = mundo.vehiculos.get(plan.vehiculo_id) if plan.vehiculo_id else None
    if vehiculo is None or vehiculo.tipo == TipoVehiculo.HELICOPTERO:
        return errores
    if not plan.ruta:
        return ["La ruta terrestre no puede estar vacía"]
    if plan.ruta[0] != vehiculo.ubicacion:
        errores.append(
            f"La ruta terrestre debe empezar en {vehiculo.ubicacion}"
        )
    if plan.ruta[-1] != tarea.nodo_destino:
        errores.append(
            f"La ruta terrestre debe terminar en {tarea.nodo_destino}"
        )
    for nodo_id in plan.ruta:
        if nodo_id not in mundo.nodos:
            errores.append(f"El nodo {nodo_id} de la ruta no existe")
    for origen, destino in zip(plan.ruta, plan.ruta[1:]):
        arista = mundo.aristas.get((origen, destino))
        if arista is None or arista.origen != origen or arista.destino != destino:
            errores.append(f"No existe la arista {origen} -> {destino}")
        elif arista.bloqueada or MedioPermitido.JEEP not in arista.medios_permitidos:
            errores.append(
                f"La arista {origen} -> {destino} no es transitable por la red vial"
            )
    return errores


def validar_plan(mundo: Mundo, plan: PlanEjecucion) -> List[str]:
    """Valida un plan completo sin modificar el mundo ni sus entidades."""
    if not isinstance(mundo, Mundo):
        raise TypeError("mundo debe ser una instancia de Mundo")
    if not isinstance(plan, PlanEjecucion):
        raise TypeError("plan debe ser una instancia de PlanEjecucion")

    tarea = mundo.tareas.get(plan.tarea_id)
    if tarea is None:
        return [f"la tarea {plan.tarea_id} no existe en el mundo"]

    errores = []
    if tarea.estado != EstadoTarea.PENDIENTE:
        errores.append(
            f"La tarea {tarea.id} no está PENDIENTE "
            f"(estado: {tarea.estado.name})"
        )

    cuidadores = []
    for cuidador_id in plan.cuidadores:
        cuidador = mundo.cuidadores.get(cuidador_id)
        if cuidador is None:
            errores.append(f"Cuidador {cuidador_id} no existe")
            continue
        cuidadores.append(cuidador)
        if cuidador.estado != EstadoCuidador.DISPONIBLE:
            errores.append(
                f"Cuidador {cuidador_id} no está DISPONIBLE "
                f"(estado: {cuidador.estado.name})"
            )
    if len(plan.cuidadores) < tarea.personas_minimas:
        errores.append(
            f"La tarea requiere al menos {tarea.personas_minimas} cuidadores"
        )
    errores.extend(cubre_requisitos_cuidadores(tarea, cuidadores))

    vehiculo = None
    if tarea.vehiculo_requerido is not None and plan.vehiculo_id is None:
        errores.append(
            f"La tarea requiere vehículo de tipo {tarea.vehiculo_requerido.name}"
        )
    if plan.vehiculo_id is not None:
        vehiculo = mundo.vehiculos.get(plan.vehiculo_id)
        if vehiculo is None:
            errores.append(f"Vehículo {plan.vehiculo_id} no existe")
        else:
            if vehiculo.estado != EstadoVehiculo.DISPONIBLE:
                errores.append(
                    f"Vehículo {plan.vehiculo_id} no está DISPONIBLE "
                    f"(estado: {vehiculo.estado.name})"
                )
            if (
                tarea.vehiculo_requerido is not None
                and vehiculo.tipo != tarea.vehiculo_requerido
            ):
                errores.append(
                    f"El vehículo {plan.vehiculo_id} no es del tipo requerido "
                    f"{tarea.vehiculo_requerido.name}"
                )
            if not any(
                vehiculo.certificacion_requerida in cuidador.certificaciones
                for cuidador in cuidadores
            ):
                errores.append(
                    f"Al menos un cuidador debe tener certificación "
                    f"{vehiculo.certificacion_requerida.name} para el vehículo "
                    f"{plan.vehiculo_id}"
                )
            errores.extend(
                validar_capacidad_vehiculo(
                    vehiculo, plan.cuidadores, plan.animales_transportados,
                )
            )
            if vehiculo.tipo != TipoVehiculo.HELICOPTERO:
                errores.extend(validar_ruta_terrestre(mundo, tarea, plan))

    tipos_equipo_presentes = Counter()
    for equipo_id in plan.equipos:
        equipo = mundo.equipos.get(equipo_id)
        if equipo is None:
            errores.append(f"Equipo {equipo_id} no existe")
            continue
        tipos_equipo_presentes[equipo.tipo] += 1
        if equipo.estado != EstadoEquipo.DISPONIBLE:
            errores.append(
                f"Equipo {equipo_id} no está DISPONIBLE "
                f"(estado: {equipo.estado.name})"
            )
    cantidades_requeridas = Counter(tarea.equipos_requeridos)
    for tipo_requerido, cantidad in cantidades_requeridas.items():
        if tipos_equipo_presentes[tipo_requerido] < cantidad:
            errores.append(
                f"El plan requiere {cantidad} equipos de tipo "
                f"{tipo_requerido.name}, pero incluye "
                f"{tipos_equipo_presentes[tipo_requerido]}"
            )

    for animal_id in plan.animales_transportados:
        if animal_id not in mundo.animales:
            errores.append(f"Animal {animal_id} no existe")
    if plan.animales_transportados and plan.vehiculo_id is None:
        errores.append("Los animales transportados requieren un vehículo")

    if plan.desde < mundo.tiempo_actual:
        errores.append(
            f"El inicio del plan ({plan.desde}) es anterior al tiempo actual "
            f"({mundo.tiempo_actual})"
        )
    return errores


def exigir_plan_valido(mundo: Mundo, plan: PlanEjecucion) -> None:
    """Exige que el plan cumpla todos los requisitos de tarea y mundo."""
    errores = validar_plan(mundo, plan)
    if errores:
        raise PlanInvalido(errores)
