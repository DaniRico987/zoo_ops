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
    EstadoCuidador, EstadoAnimal, EstadoVehiculo, EstadoTarea, EstadoIncidente
)
from zoo_ops.dominio.entidades import Lectura, Mundo
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


# Contador global para IDs de eventos (se usa en el registro)
_contador_eventos: int = 0


def _siguiente_id_evento() -> int:
    """Genera el siguiente ID de evento."""
    global _contador_eventos
    _contador_eventos += 1
    return _contador_eventos


def reiniciar_contador_eventos() -> None:
    """Reinicia el contador de eventos (útil para tests)."""
    global _contador_eventos
    _contador_eventos = 0


def crear_evento(
    momento: int,
    tipo: TipoEvento,
    entidad_tipo: str,
    entidad_id: str,
    estado_antes: str,
    estado_despues: str,
    causa: str,
    datos_extra: Optional[Dict[str, Any]] = None
) -> Evento:
    """Crea un nuevo evento con ID automático."""
    return Evento(
        id=_siguiente_id_evento(),
        momento=momento,
        tipo=tipo,
        entidad_tipo=entidad_tipo,
        entidad_id=entidad_id,
        estado_antes=estado_antes,
        estado_despues=estado_despues,
        causa=causa,
        datos_extra=datos_extra or {}
    )


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
_CAMPOS_EXTRA_CAMBIO_ESTADO = ("ubicacion", "cuidador_asignado")


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
    for campo in _CAMPOS_EXTRA_CAMBIO_ESTADO:
        if campo in evento.datos_extra:
            if not hasattr(entidad, campo):
                raise ErrorDominio(
                    f"El campo {campo!r} no existe en {type(entidad).__name__} "
                    f"({evento.entidad_tipo}:{evento.entidad_id})"
                )
            kwargs[campo] = evento.datos_extra[campo]

    mundo.sustituir_entidad(attr_name, evento.entidad_id, replace(entidad, **kwargs))
    return mundo


def _aplicar_creacion(mundo: Mundo, evento: Evento) -> Mundo:
    """Aplica CREACION_ENTIDAD (no-op explícito: las entidades ya están en el mundo)."""
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
                 "animales", "equipos", "tareas", "incidentes", "sensores"]:
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
