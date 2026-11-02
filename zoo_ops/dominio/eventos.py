"""
Eventos y registro de eventos para el dominio de zoo-ops.
Eventos inmutables (frozen) y registro de solo anexar.

`aplicar_evento` es la ÚNICA lógica de aplicación de eventos sobre un Mundo.
`reconstruir_estado` delega en ella evento por evento; no reimplementa reglas.
"""

import copy
from dataclasses import dataclass, field, replace
from typing import Dict, List, Optional, Any
from enum import Enum, auto
from zoo_ops.dominio.enums import (
    Certificacion, EstadoCuidador, EstadoAnimal, EstadoVehiculo, EstadoTarea,
    EstadoIncidente, Habilidad, PrioridadTarea, TipoEquipo, TipoIncidente,
    TipoVehiculo,
)
from zoo_ops.dominio.entidades import (
    EfectoAnimal, HabilidadRequerida, Incidente, Lectura, MomentoEfecto,
    Mundo, Tarea,
)
from zoo_ops.dominio.errores import ErrorDominio, EventoDuplicado, EventoNoSoportado


# ============================================================================
# Tipos de evento
# ============================================================================

class TipoEvento(Enum):
    """Tipos de eventos en el sistema."""
    CAMBIO_ESTADO = auto()
    CREACION_ENTIDAD = auto()
    ELIMINACION_ENTIDAD = auto()
    RESERVA_CREADA = auto()
    RESERVA_LIBERADA = auto()
    TAREA_ASIGNADA = auto()
    TAREA_DESASIGNADA = auto()
    INCIDENTE_GENERADO = auto()
    LECTURA_SENSOR = auto()
    TICK_RELOJ = auto()
    PLAN_REGISTRADO = auto()
    PLAN_LIBERADO = auto()


# ============================================================================
# Evento inmutable
# ============================================================================

@dataclass(frozen=True)
class Evento:
    """Evento inmutable del sistema."""
    id: int  # incremental, único
    momento: int  # tiempo simulado en segundos
    tipo: TipoEvento
    entidad_tipo: str  # "Cuidador", "Animal", "Vehiculo", "Tarea", "Incidente", etc.
    entidad_id: str
    estado_antes: str
    estado_despues: str
    causa: str
    datos_extra: Dict[str, Any] = field(default_factory=dict)


def crear_evento(
    registro_eventos: "RegistroEventos",
    momento: int,
    tipo: TipoEvento,
    entidad_tipo: str,
    entidad_id: str,
    estado_antes: str,
    estado_despues: str,
    causa: str,
    datos_extra: Optional[Dict[str, Any]] = None
) -> Evento:
    """Crea un evento usando el contador local del registro indicado."""
    return Evento(
        id=registro_eventos.siguiente_id_evento(),
        momento=momento,
        tipo=tipo,
        entidad_tipo=entidad_tipo,
        entidad_id=entidad_id,
        estado_antes=estado_antes,
        estado_despues=estado_despues,
        causa=causa,
        datos_extra=datos_extra or {}
    )


def _enum_a_nombre(enum_value: Any) -> str:
    """Serializa un enum por nombre, o deja los valores básicos intactos."""
    return enum_value.name if hasattr(enum_value, "name") else enum_value


def efecto_animal_a_datos_extra(efecto: EfectoAnimal) -> Dict[str, Any]:
    """Serializa un efecto de animal en un formato estable para eventos."""
    return {
        "animal_id": efecto.animal_id,
        "estado": efecto.estado.name,
        "momento": efecto.momento.name,
        "recinto_destino": efecto.recinto_destino,
    }


def efecto_animal_desde_datos_extra(datos: Dict[str, Any]) -> EfectoAnimal:
    """Reconstruye un efecto de animal desde datos_extra."""
    if not isinstance(datos, dict):
        raise ErrorDominio("datos_extra del efecto de animal debe ser un diccionario")
    for campo in ("animal_id", "estado", "momento"):
        if campo not in datos:
            raise ErrorDominio(f"datos_extra del efecto carece de campo {campo!r}")
    estado = _enum_desde_nombre(EstadoAnimal, datos["estado"], "estado de efecto")
    momento = _enum_desde_nombre(MomentoEfecto, datos["momento"], "momento de efecto")
    if not isinstance(datos["animal_id"], str):
        raise ErrorDominio("animal_id del efecto debe ser texto")
    recinto_destino = datos.get("recinto_destino")
    if recinto_destino is not None and not isinstance(recinto_destino, str):
        raise ErrorDominio("recinto_destino del efecto debe ser texto o None")
    if estado == EstadoAnimal.EN_RECINTO and not recinto_destino:
        raise ErrorDominio(
            "Un efecto a EN_RECINTO requiere recinto_destino en datos_extra"
        )
    return EfectoAnimal(
        animal_id=datos["animal_id"],
        estado=estado,
        momento=momento,
        recinto_destino=recinto_destino,
    )


def _enum_desde_nombre(enum_tipo, valor, campo):
    """Convierte un nombre de enum y traduce datos inválidos a ErrorDominio."""
    if not isinstance(valor, str):
        raise ErrorDominio(f"{campo} debe ser el nombre de un enum")
    try:
        return enum_tipo[valor]
    except KeyError as exc:
        raise ErrorDominio(f"{campo} inválido: {valor!r}") from exc


def _secuencia_datos(valor, campo):
    """Valida las colecciones serializadas y las normaliza a tupla."""
    if not isinstance(valor, (list, tuple)):
        raise ErrorDominio(f"datos_extra[{campo!r}] debe ser una lista o tupla")
    return tuple(valor)


def _exigir_tipo(valor, tipo, campo):
    """Valida un campo escalar evitando coerciones implícitas."""
    if type(valor) is not tipo:
        raise ErrorDominio(f"datos_extra[{campo!r}] debe ser {tipo.__name__}")


def tarea_a_datos_extra(tarea: Tarea) -> Dict[str, Any]:
    """Serializa una tarea para almacenamiento o reconstrucción del mundo."""
    return {
        "id": tarea.id,
        "tipo": tarea.tipo,
        "prioridad_base": tarea.prioridad_base.name,
        "urgencia": tarea.urgencia,
        "nodo_destino": tarea.nodo_destino,
        "duracion_estimada": tarea.duracion_estimada,
        "habilidades_requeridas": [
            {
                "habilidad": requisito.habilidad.name,
                "nivel_minimo": requisito.nivel_minimo,
            }
            for requisito in tarea.habilidades_requeridas
        ],
        "certificaciones_requeridas": tuple(
            sorted((cert.name for cert in tarea.certificaciones_requeridas))
        ),
        "vehiculo_requerido": None if tarea.vehiculo_requerido is None else tarea.vehiculo_requerido.name,
        "equipos_requeridos": tuple(equipo.name for equipo in tarea.equipos_requeridos),
        "ventana_tiempo": tarea.ventana_tiempo,
        "dependencias": tuple(sorted(tarea.dependencias)),
        "interrumpible": tarea.interrumpible,
        "estado": tarea.estado.name,
        "incidente_origen": tarea.incidente_origen,
        "efectos": tuple(efecto_animal_a_datos_extra(efecto) for efecto in tarea.efectos),
        "cuidadores_asignados": tuple(tarea.cuidadores_asignados),
        "personas_minimas": tarea.personas_minimas,
    }


def tarea_desde_datos_extra(datos: Dict[str, Any]) -> Tarea:
    """Reconstruye una tarea validando tipos y campos serializados."""
    if not isinstance(datos, dict):
        raise ErrorDominio("datos_extra de la tarea debe ser un diccionario")
    obligatorios = (
        "id", "tipo", "prioridad_base", "urgencia", "nodo_destino",
        "duracion_estimada", "habilidades_requeridas",
        "certificaciones_requeridas", "equipos_requeridos", "dependencias",
        "interrumpible", "estado", "cuidadores_asignados", "personas_minimas",
    )
    faltantes = [campo for campo in obligatorios if campo not in datos]
    if faltantes:
        raise ErrorDominio(f"datos_extra de la tarea carece de campos: {', '.join(faltantes)}")

    for campo in ("id", "tipo", "nodo_destino"):
        if not isinstance(datos[campo], str):
            raise ErrorDominio(f"datos_extra[{campo!r}] debe ser texto")
    for campo in ("urgencia", "duracion_estimada", "personas_minimas"):
        _exigir_tipo(datos[campo], int, campo)
    _exigir_tipo(datos["interrumpible"], bool, "interrumpible")

    try:
        prioridad = _enum_desde_nombre(
            PrioridadTarea, datos["prioridad_base"], "prioridad_base",
        )
        estado = _enum_desde_nombre(EstadoTarea, datos["estado"], "estado")
        vehiculo = datos.get("vehiculo_requerido")
        vehiculo = (
            None if vehiculo is None else
            _enum_desde_nombre(TipoVehiculo, vehiculo, "vehiculo_requerido")
        )
        habilidades = []
        for item in _secuencia_datos(
            datos["habilidades_requeridas"], "habilidades_requeridas",
        ):
            if not isinstance(item, dict) or not {
                "habilidad", "nivel_minimo",
            }.issubset(item):
                raise ErrorDominio(
                    "Cada habilidad requerida debe incluir habilidad y nivel_minimo"
                )
            _exigir_tipo(item["nivel_minimo"], int, "nivel_minimo")
            habilidades.append(HabilidadRequerida(
                habilidad=_enum_desde_nombre(
                    Habilidad, item["habilidad"], "habilidad requerida",
                ),
                nivel_minimo=item["nivel_minimo"],
            ))

        certificaciones = tuple(
            _enum_desde_nombre(Certificacion, nombre, "certificacion requerida")
            for nombre in _secuencia_datos(
                datos["certificaciones_requeridas"], "certificaciones_requeridas",
            )
        )
        equipos = tuple(
            _enum_desde_nombre(TipoEquipo, nombre, "equipo requerido")
            for nombre in _secuencia_datos(
                datos["equipos_requeridos"], "equipos_requeridos",
            )
        )
        dependencias = _secuencia_datos(datos["dependencias"], "dependencias")
        cuidadores = _secuencia_datos(
            datos["cuidadores_asignados"], "cuidadores_asignados",
        )
        for campo, valores in (
            ("dependencias", dependencias),
            ("cuidadores_asignados", cuidadores),
        ):
            if any(not isinstance(valor, str) for valor in valores):
                raise ErrorDominio(f"Cada elemento de {campo} debe ser texto")

        efectos = tuple(
            efecto_animal_desde_datos_extra(efecto)
            for efecto in _secuencia_datos(datos.get("efectos", ()), "efectos")
        )
        ventana = datos.get("ventana_tiempo")
        if ventana is not None:
            ventana = _secuencia_datos(ventana, "ventana_tiempo")
            if len(ventana) != 2 or any(type(valor) is not int for valor in ventana):
                raise ErrorDominio(
                    "ventana_tiempo debe contener exactamente dos enteros"
                )
            ventana = tuple(ventana)
        incidente_origen = datos.get("incidente_origen")
        if incidente_origen is not None and not isinstance(incidente_origen, str):
            raise ErrorDominio("incidente_origen debe ser texto o None")

        return Tarea(
            id=datos["id"],
            tipo=datos["tipo"],
            prioridad_base=prioridad,
            urgencia=datos["urgencia"],
            nodo_destino=datos["nodo_destino"],
            duracion_estimada=datos["duracion_estimada"],
            habilidades_requeridas=tuple(habilidades),
            certificaciones_requeridas=frozenset(certificaciones),
            vehiculo_requerido=vehiculo,
            equipos_requeridos=equipos,
            ventana_tiempo=ventana,
            dependencias=frozenset(dependencias),
            interrumpible=datos["interrumpible"],
            estado=estado,
            incidente_origen=incidente_origen,
            efectos=efectos,
            cuidadores_asignados=cuidadores,
            personas_minimas=datos["personas_minimas"],
        )
    except (KeyError, TypeError, ValueError, AttributeError) as exc:
        raise ErrorDominio(f"datos_extra no permiten reconstruir la tarea: {exc}") from exc


def incidente_a_datos_extra(incidente: Incidente) -> Dict[str, Any]:
    """Serializa un incidente con enums por nombre y tareas ordenadas."""
    return {
        "id": incidente.id,
        "tipo": incidente.tipo.name,
        "severidad": incidente.severidad,
        "ubicacion": incidente.ubicacion,
        "estado": incidente.estado.name,
        "tareas_generadas": tuple(sorted(incidente.tareas_generadas)),
        "animal_relacionado": incidente.animal_relacionado,
    }


def incidente_desde_datos_extra(datos: Dict[str, Any]) -> Incidente:
    """Reconstruye un incidente y valida todos sus datos."""
    if not isinstance(datos, dict):
        raise ErrorDominio("datos_extra del incidente debe ser un diccionario")
    obligatorios = ("id", "tipo", "severidad", "ubicacion", "estado", "tareas_generadas")
    faltantes = [campo for campo in obligatorios if campo not in datos]
    if faltantes:
        raise ErrorDominio(
            "datos_extra del incidente carece de campos: " + ", ".join(faltantes)
        )
    for campo in ("id", "ubicacion"):
        if not isinstance(datos[campo], str):
            raise ErrorDominio(f"datos_extra[{campo!r}] debe ser texto")
    _exigir_tipo(datos["severidad"], int, "severidad")
    tareas = _secuencia_datos(datos["tareas_generadas"], "tareas_generadas")
    if any(not isinstance(tarea_id, str) for tarea_id in tareas):
        raise ErrorDominio("Cada id de tareas_generadas debe ser texto")
    animal_id = datos.get("animal_relacionado")
    if animal_id is not None and not isinstance(animal_id, str):
        raise ErrorDominio("animal_relacionado debe ser texto o None")
    try:
        return Incidente(
            id=datos["id"],
            tipo=_enum_desde_nombre(TipoIncidente, datos["tipo"], "tipo"),
            severidad=datos["severidad"],
            ubicacion=datos["ubicacion"],
            estado=_enum_desde_nombre(EstadoIncidente, datos["estado"], "estado"),
            tareas_generadas=frozenset(tareas),
            animal_relacionado=animal_id,
        )
    except (KeyError, TypeError, ValueError, AttributeError) as exc:
        raise ErrorDominio(
            f"datos_extra no permiten reconstruir el incidente: {exc}"
        ) from exc


def plan_a_datos_extra(plan: "PlanEjecucion") -> Dict[str, Any]:
    """Serializa todos los campos de un plan en datos aptos para un evento."""
    return {
        "tarea_id": plan.tarea_id,
        "cuidadores": tuple(plan.cuidadores),
        "desde": plan.desde,
        "hasta": plan.hasta,
        "vehiculo_id": plan.vehiculo_id,
        "equipos": tuple(plan.equipos),
        "animales_transportados": tuple(plan.animales_transportados),
        "ruta": tuple(plan.ruta),
    }


def plan_desde_datos_extra(datos: Dict[str, Any]) -> "PlanEjecucion":
    """Reconstruye un plan y normaliza a tuplas sus campos de colección."""
    from zoo_ops.dominio.plan import PlanEjecucion

    if not isinstance(datos, dict):
        raise ErrorDominio("datos_extra del plan debe ser un diccionario")
    campos = (
        "tarea_id", "cuidadores", "desde", "hasta", "vehiculo_id",
        "equipos", "animales_transportados", "ruta",
    )
    faltantes = [campo for campo in campos if campo not in datos]
    if faltantes:
        raise ErrorDominio(
            f"datos_extra del plan carece de campos: {', '.join(faltantes)}"
        )
    for campo in (
        "cuidadores", "equipos", "animales_transportados", "ruta",
    ):
        valor = datos[campo]
        if not isinstance(valor, (list, tuple)):
            raise ErrorDominio(
                f"datos_extra[{campo!r}] debe ser una lista o una tupla"
            )

    try:
        return PlanEjecucion(
            tarea_id=datos["tarea_id"],
            cuidadores=tuple(datos["cuidadores"]),
            desde=datos["desde"],
            hasta=datos["hasta"],
            vehiculo_id=datos["vehiculo_id"],
            equipos=tuple(datos["equipos"]),
            animales_transportados=tuple(datos["animales_transportados"]),
            ruta=tuple(datos["ruta"]),
        )
    except (KeyError, TypeError, ValueError) as exc:
        raise ErrorDominio(f"datos_extra no permiten reconstruir el plan: {exc}") from exc


# ============================================================================
# Registro de eventos (append-only)
# ============================================================================

class RegistroEventos:
    """
    Registro de eventos de solo anexar.
    No permite modificar ni borrar eventos.
    """

    def __init__(self):
        self._eventos: List[Evento] = []
        self._ultimo_id_evento = 0

    def instantanea(self) -> tuple:
        """Devuelve una copia profunda de los eventos y del contador de IDs."""
        return copy.deepcopy((self._eventos, self._ultimo_id_evento))

    def restaurar(self, instantanea: tuple) -> None:
        """Restaura los eventos y el contador sin reemplazar el registro."""
        if (
            not isinstance(instantanea, tuple)
            or len(instantanea) != 2
            or not isinstance(instantanea[0], list)
            or not isinstance(instantanea[1], int)
        ):
            raise TypeError("instantanea no es válida para RegistroEventos")
        eventos, ultimo_id = copy.deepcopy(instantanea)
        self._eventos = eventos
        self._ultimo_id_evento = ultimo_id

    def siguiente_id_evento(self) -> int:
        """Genera un ID incremental, aislado de los demás registros."""
        self._ultimo_id_evento += 1
        return self._ultimo_id_evento

    def validar_anexo(self, evento: Evento) -> None:
        """
        Valida que el evento pueda anexarse sin modificar el registro.

        Raises:
            EventoDuplicado: Si ya existe un evento con el mismo ID.
        """
        if any(existente.id == evento.id for existente in self._eventos):
            raise EventoDuplicado(evento.id)

    def anexar(self, evento: Evento) -> None:
        """Añade un evento al registro, rechazando IDs duplicados."""
        self.validar_anexo(evento)
        self._ultimo_id_evento = max(self._ultimo_id_evento, evento.id)
        self._eventos.append(evento)

    def obtener_todos(self) -> List[Evento]:
        """Retorna una copia de la lista de eventos."""
        return list(self._eventos)

    def obtener_por_entidad(self, entidad_tipo: str, entidad_id: str) -> List[Evento]:
        """Filtra eventos por entidad."""
        return [e for e in self._eventos
                if e.entidad_tipo == entidad_tipo and e.entidad_id == entidad_id]

    def obtener_por_tipo(self, tipo: TipoEvento) -> List[Evento]:
        """Filtra eventos por tipo."""
        return [e for e in self._eventos if e.tipo == tipo]

    def obtener_desde_momento(self, momento: int) -> List[Evento]:
        """Eventos desde un momento (inclusive)."""
        return [e for e in self._eventos if e.momento >= momento]

    def __len__(self) -> int:
        return len(self._eventos)

    def __iter__(self):
        return iter(self._eventos)

    def __getitem__(self, idx) -> Evento:
        return self._eventos[idx]


# ============================================================================
# Aplicación de eventos (única lógica de aplicación)
# ============================================================================

# Tipo de entidad -> (colección del Mundo, enum de estado)
_ENTIDADES_CAMBIO_ESTADO = {
    "Cuidador": ("cuidadores", EstadoCuidador),
    "Animal": ("animales", EstadoAnimal),
    "Vehiculo": ("vehiculos", EstadoVehiculo),
    "Tarea": ("tareas", EstadoTarea),
    "Incidente": ("incidentes", EstadoIncidente),
}

# Campos de entidad que un evento CAMBIO_ESTADO puede modificar además de `estado`.
_CAMPOS_EXTRA_CAMBIO_ESTADO = {
    "ubicacion": "ubicacion",
    "cuidadores_ids": "cuidadores_asignados",
}


def _evento_no_soportado(evento: Evento, tipo: TipoEvento) -> EventoNoSoportado:
    """Construye el error uniforme para un evento que no puede aplicarse."""
    return EventoNoSoportado(
        tipo_evento=tipo.name,
        entidad_tipo=evento.entidad_tipo,
        entidad_id=evento.entidad_id,
    )


def aplicar_evento(mundo: Mundo, evento: Evento) -> Mundo:
    """
    Aplica un evento al mundo mutándolo mediante sus métodos.

    Args:
        mundo: Mundo a modificar (se muta in-place)
        evento: Evento a aplicar

    Returns:
        El mismo mundo mutado

    Raises:
        EventoNoSoportado: Si el tipo de evento no tiene aplicador
        ErrorDominio: Si el evento CAMBIO_ESTADO es inconsistente con el mundo
    """
    aplicadores = {
        TipoEvento.CAMBIO_ESTADO: _aplicar_cambio_estado,
        TipoEvento.CREACION_ENTIDAD: _aplicar_creacion,
        TipoEvento.ELIMINACION_ENTIDAD: _aplicar_eliminacion,
        TipoEvento.RESERVA_CREADA: _aplicar_reserva,
        TipoEvento.RESERVA_LIBERADA: _aplicar_reserva,
        TipoEvento.TAREA_ASIGNADA: _aplicar_tarea_asignada,
        TipoEvento.TAREA_DESASIGNADA: _aplicar_tarea_desasignada,
        TipoEvento.INCIDENTE_GENERADO: _aplicar_incidente_generado,
        TipoEvento.LECTURA_SENSOR: _aplicar_lectura,
        TipoEvento.TICK_RELOJ: _aplicar_tick_reloj,
        TipoEvento.PLAN_REGISTRADO: _aplicar_plan_registrado,
        TipoEvento.PLAN_LIBERADO: _aplicar_plan_liberado,
    }
    aplicador = aplicadores.get(evento.tipo)
    if aplicador is None:
        raise _evento_no_soportado(evento, evento.tipo)
    return aplicador(mundo, evento)


def _aplicar_cambio_estado(mundo: Mundo, evento: Evento) -> Mundo:
    """Aplica un evento CAMBIO_ESTADO al mundo (muta el mundo)."""
    config = _ENTIDADES_CAMBIO_ESTADO.get(evento.entidad_tipo)
    if config is None:
        raise _evento_no_soportado(evento, TipoEvento.CAMBIO_ESTADO)

    attr_name, enum_tipo = config
    entidad = getattr(mundo, attr_name).get(evento.entidad_id)
    if entidad is None:
        raise _evento_no_soportado(evento, TipoEvento.CAMBIO_ESTADO)

    try:
        nuevo_estado = enum_tipo[evento.estado_despues]
    except KeyError as exc:
        raise ErrorDominio(
            f"Estado {evento.estado_despues!r} no pertenece a {enum_tipo.__name__} "
            f"({evento.entidad_tipo}:{evento.entidad_id})"
        ) from exc

    kwargs = {"estado": nuevo_estado}
    for campo_evento, campo_entidad in _CAMPOS_EXTRA_CAMBIO_ESTADO.items():
        if campo_evento in evento.datos_extra:
            if not hasattr(entidad, campo_entidad):
                raise ErrorDominio(
                    f"El campo {campo_entidad!r} no existe en {type(entidad).__name__} "
                    f"({evento.entidad_tipo}:{evento.entidad_id})"
                )
            valor = evento.datos_extra[campo_evento]
            if campo_evento == "cuidadores_ids":
                valor = tuple(valor)
            kwargs[campo_entidad] = valor

    mundo.sustituir_entidad(attr_name, evento.entidad_id, replace(entidad, **kwargs))
    return mundo


def _aplicar_creacion(mundo: Mundo, evento: Evento) -> Mundo:
    """Crea tareas e incidentes iniciales; otros tipos siguen siendo no-op."""
    configuracion = {
        "Tarea": ("tareas", tarea_desde_datos_extra, "PENDIENTE"),
        "Incidente": ("incidentes", incidente_desde_datos_extra, "ABIERTO"),
    }.get(evento.entidad_tipo)
    if configuracion is None:
        return mundo

    coleccion, deserializar, estado_inicial = configuracion
    if evento.estado_despues != estado_inicial:
        raise ErrorDominio(
            f"CREACION_ENTIDAD de {evento.entidad_tipo} debe iniciar en "
            f"{estado_inicial}"
        )
    if evento.entidad_id in getattr(mundo, coleccion):
        raise ErrorDominio(
            f"Ya existe {evento.entidad_tipo}:{evento.entidad_id} en el mundo"
        )
    entidad = deserializar(evento.datos_extra)
    if entidad.id != evento.entidad_id:
        raise ErrorDominio(
            f"El id serializado {entidad.id} no coincide con "
            f"el id del evento {evento.entidad_id}"
        )
    if evento.entidad_tipo == "Tarea":
        if entidad.estado.name != estado_inicial:
            raise ErrorDominio("Una tarea creada debe estar PENDIENTE")
        if entidad.cuidadores_asignados:
            raise ErrorDominio("Una tarea creada no puede tener cuidadores asignados")
    elif entidad.estado.name != estado_inicial:
        raise ErrorDominio("Un incidente creado debe estar ABIERTO")

    mundo.agregar_entidad(coleccion, evento.entidad_id, entidad)
    return mundo


def _aplicar_reserva(mundo: Mundo, evento: Evento) -> Mundo:
    """Aplica RESERVA_CREADA / RESERVA_LIBERADA (no-op: viven en RegistroReservas)."""
    return mundo


def _aplicar_eliminacion(mundo: Mundo, evento: Evento) -> Mundo:
    """Aplica ELIMINACION_ENTIDAD (no-op explícito documentado)."""
    return mundo


def _aplicar_tarea_asignada(mundo: Mundo, evento: Evento) -> Mundo:
    """Aplica TAREA_ASIGNADA (no-op explícito documentado)."""
    return mundo


def _aplicar_tarea_desasignada(mundo: Mundo, evento: Evento) -> Mundo:
    """Aplica TAREA_DESASIGNADA (no-op explícito documentado)."""
    return mundo


def _aplicar_incidente_generado(mundo: Mundo, evento: Evento) -> Mundo:
    """Aplica INCIDENTE_GENERADO (no-op explícito documentado)."""
    return mundo


def _aplicar_tick_reloj(mundo: Mundo, evento: Evento) -> Mundo:
    """Aplica TICK_RELOJ (no-op: el reloj se actualiza al momento del evento)."""
    return mundo


def _aplicar_plan_registrado(mundo: Mundo, evento: Evento) -> Mundo:
    """Reconstruye y registra el plan contenido en el evento."""
    if evento.entidad_tipo != "PlanEjecucion":
        raise _evento_no_soportado(evento, TipoEvento.PLAN_REGISTRADO)
    plan = plan_desde_datos_extra(evento.datos_extra)
    if plan.tarea_id != evento.entidad_id:
        raise ErrorDominio(
            f"El plan de la tarea {plan.tarea_id} no coincide con "
            f"la entidad del evento {evento.entidad_id}"
        )
    if plan.tarea_id in mundo.planes:
        raise ErrorDominio(f"Ya existe un plan para la tarea {plan.tarea_id}")
    mundo.registrar_plan(plan)
    return mundo


def _aplicar_plan_liberado(mundo: Mundo, evento: Evento) -> Mundo:
    """Elimina el plan indicado por el evento."""
    if evento.entidad_tipo != "PlanEjecucion":
        raise _evento_no_soportado(evento, TipoEvento.PLAN_LIBERADO)
    if evento.entidad_id not in mundo.planes:
        raise ErrorDominio(f"No existe un plan para la tarea {evento.entidad_id}")
    mundo.eliminar_plan(evento.entidad_id)
    return mundo


def _aplicar_lectura(mundo: Mundo, evento: Evento) -> Mundo:
    """
    Aplica LECTURA_SENSOR añadiendo una Lectura al mundo.

    El valor debe venir en `datos_extra["valor"]`; el sensor es `evento.entidad_id`
    y el momento es `evento.momento`.
    """
    if evento.entidad_tipo != "Sensor":
        raise _evento_no_soportado(evento, TipoEvento.LECTURA_SENSOR)
    if "valor" not in evento.datos_extra:
        raise ErrorDominio(
            f"LECTURA_SENSOR de {evento.entidad_id} requiere datos_extra['valor']"
        )
    mundo.lecturas.append(Lectura(
        sensor_id=evento.entidad_id,
        valor=float(evento.datos_extra["valor"]),
        momento=evento.momento,
    ))
    return mundo


# ============================================================================
# Reconstrucción de estado
# ============================================================================

# Eventos cuyo efecto no es reproducible solo con `estado_inicial` + los eventos:
# dependen de datos externos al Mundo (reservas, incidentes, reloj) o destruyen
# información. `reconstruir_estado` los rechaza de forma explícita.
EVENTOS_NO_RECONSTRUIBLES = frozenset({
    TipoEvento.ELIMINACION_ENTIDAD,
    TipoEvento.TAREA_ASIGNADA,
    TipoEvento.TAREA_DESASIGNADA,
    TipoEvento.INCIDENTE_GENERADO,
    TipoEvento.TICK_RELOJ,
})


def reconstruir_estado(eventos: List[Evento], estado_inicial: Mundo) -> Mundo:
    """
    Reproduce el estado del mundo aplicando eventos secuencialmente.

    Parte de una copia profunda de `estado_inicial` (no lo muta) y aplica cada
    evento con `aplicar_evento`. Los eventos de `EVENTOS_NO_RECONSTRUIBLES`
    lanzan `EventoNoSoportado`; no hay caminos silenciosos.

    Args:
        eventos: Lista de eventos (se ordenan por momento y luego por ID)
        estado_inicial: Estado de partida

    Returns:
        Mundo reconstruido

    Raises:
        EventoNoSoportado: Si un evento no es reproducible
        ErrorDominio: Si un CAMBIO_ESTADO es inconsistente con el mundo reconstruido
    """
    mundo = copy.deepcopy(estado_inicial)

    for evento in sorted(eventos, key=lambda e: (e.momento, e.id)):
        if evento.tipo in EVENTOS_NO_RECONSTRUIBLES:
            raise _evento_no_soportado(evento, evento.tipo)
        aplicar_evento(mundo, evento)
        mundo.tiempo_actual = evento.momento

    return mundo


def verificar_reconstruccion(mundo_vivo: Mundo, mundo_reconstruido: Mundo) -> List[str]:
    """
    Compara un mundo vivo con uno reconstruido y retorna lista de diferencias.
    Lista vacía = coinciden perfectamente.
    """
    diferencias = []

    # Comparar cada colección de entidades
    for attr in ["nodos", "aristas", "recintos", "cuidadores", "vehiculos",
                 "animales", "equipos", "tareas", "incidentes", "planes",
                 "sensores"]:
        vivo = getattr(mundo_vivo, attr)
        recon = getattr(mundo_reconstruido, attr)

        # Verificar claves
        claves_vivo = set(vivo.keys())
        claves_recon = set(recon.keys())

        if claves_vivo != claves_recon:
            faltantes = claves_vivo - claves_recon
            extras = claves_recon - claves_vivo
            if faltantes:
                diferencias.append(f"{attr}: faltan {faltantes}")
            if extras:
                diferencias.append(f"{attr}: sobran {extras}")

        # Verificar entidades comunes
        for clave in claves_vivo & claves_recon:
            if vivo[clave] != recon[clave]:
                diferencias.append(f"{attr}[{clave}]: difieren")

    # Comparar lecturas (lista)
    if mundo_vivo.lecturas != mundo_reconstruido.lecturas:
        diferencias.append("lecturas: listas difieren")

    # Comparar tiempo
    if mundo_vivo.tiempo_actual != mundo_reconstruido.tiempo_actual:
        diferencias.append(f"tiempo_actual: {mundo_vivo.tiempo_actual} != {mundo_reconstruido.tiempo_actual}")

    return diferencias
