"""
Máquinas de estado declarativas para el dominio de zoo-ops.

Cada entidad tiene una tabla de transiciones permitidas. La ÚNICA vía pública
para cambiar el estado de una entidad es `ejecutar_transicion`, que lee el
estado real del Mundo, valida, construye el evento, lo aplica con
`aplicar_evento` y lo anexa al registro de eventos.

Las funciones `validar_transicion_*_extra` son validadores de reglas de negocio:
devuelven un mensaje de error o `None`, y no mutan nada.
"""

from typing import Dict, FrozenSet, Optional
from zoo_ops.dominio.enums import (
    EstadoCuidador, EstadoAnimal, EstadoVehiculo, EstadoTarea, EstadoIncidente,
    Medio, TipoIncidente,
)
from zoo_ops.dominio.errores import (
    DependenciaInexistente, ErrorDominio, TiempoRetrocede, TransicionInvalida,
)
from zoo_ops.dominio.entidades import Animal, Incidente, Mundo
from zoo_ops.dominio.eventos import (
    Evento, TipoEvento, RegistroEventos, aplicar_evento, crear_evento,
)
from zoo_ops.dominio.catalogos import ESPECIES_CATALOGO


# ============================================================================
# Tablas de transiciones (estado_actual -> conjunto de estados permitidos)
# ============================================================================

# Cuidador
TRANSICIONES_CUIDADOR: Dict[EstadoCuidador, FrozenSet[EstadoCuidador]] = {
    EstadoCuidador.FUERA_DE_TURNO: frozenset({EstadoCuidador.DISPONIBLE}),
    EstadoCuidador.DISPONIBLE: frozenset({
        EstadoCuidador.ASIGNADO,
        EstadoCuidador.DESCANSANDO,
        EstadoCuidador.FUERA_DE_TURNO,
    }),
    EstadoCuidador.ASIGNADO: frozenset({
        EstadoCuidador.EN_CAMINO,
        EstadoCuidador.DISPONIBLE,
        EstadoCuidador.FUERA_DE_TURNO,
    }),
    EstadoCuidador.EN_CAMINO: frozenset({
        EstadoCuidador.EJECUTANDO,
        EstadoCuidador.FUERA_DE_TURNO,
    }),
    EstadoCuidador.EJECUTANDO: frozenset({
        EstadoCuidador.DISPONIBLE,
        EstadoCuidador.PAUSADO,
        EstadoCuidador.FUERA_DE_TURNO,
    }),
    EstadoCuidador.PAUSADO: frozenset({
        EstadoCuidador.EJECUTANDO,
        EstadoCuidador.FUERA_DE_TURNO,
    }),
    EstadoCuidador.DESCANSANDO: frozenset({
        EstadoCuidador.DISPONIBLE,
        EstadoCuidador.FUERA_DE_TURNO,
    }),
}

# Animal
TRANSICIONES_ANIMAL: Dict[EstadoAnimal, FrozenSet[EstadoAnimal]] = {
    EstadoAnimal.EN_RECINTO: frozenset({
        EstadoAnimal.ESCAPADO,
        EstadoAnimal.EN_OBSERVACION,
    }),
    EstadoAnimal.ESCAPADO: frozenset({
        EstadoAnimal.LOCALIZADO,
    }),
    EstadoAnimal.LOCALIZADO: frozenset({
        EstadoAnimal.TRANQUILIZADO,
        EstadoAnimal.EN_TRASLADO,
    }),
    EstadoAnimal.TRANQUILIZADO: frozenset({
        EstadoAnimal.EN_TRASLADO,
    }),
    EstadoAnimal.EN_TRASLADO: frozenset({
        EstadoAnimal.EN_RECINTO,
        EstadoAnimal.EN_CLINICA,
    }),
    EstadoAnimal.EN_CLINICA: frozenset({
        EstadoAnimal.EN_TRASLADO,
    }),
    EstadoAnimal.EN_OBSERVACION: frozenset({
        EstadoAnimal.EN_RECINTO,
        EstadoAnimal.EN_TRASLADO,
    }),
}

# Vehículo
TRANSICIONES_VEHICULO: Dict[EstadoVehiculo, FrozenSet[EstadoVehiculo]] = {
    EstadoVehiculo.DISPONIBLE: frozenset({
        EstadoVehiculo.RESERVADO,
        EstadoVehiculo.EN_MANTENIMIENTO,
    }),
    EstadoVehiculo.RESERVADO: frozenset({
        EstadoVehiculo.DISPONIBLE,
        EstadoVehiculo.EN_RUTA,
        EstadoVehiculo.EN_MANTENIMIENTO,
    }),
    EstadoVehiculo.EN_RUTA: frozenset({
        EstadoVehiculo.EN_USO,
    }),
    EstadoVehiculo.EN_USO: frozenset({
        EstadoVehiculo.DISPONIBLE,
        EstadoVehiculo.EN_MANTENIMIENTO,
    }),
    EstadoVehiculo.EN_MANTENIMIENTO: frozenset({
        EstadoVehiculo.DISPONIBLE,
    }),
}

# Tarea
TRANSICIONES_TAREA: Dict[EstadoTarea, FrozenSet[EstadoTarea]] = {
    EstadoTarea.PENDIENTE: frozenset({
        EstadoTarea.BLOQUEADA,
        EstadoTarea.ASIGNADA,
        EstadoTarea.CANCELADA,
    }),
    EstadoTarea.BLOQUEADA: frozenset({
        EstadoTarea.PENDIENTE,
        EstadoTarea.CANCELADA,
    }),
    EstadoTarea.ASIGNADA: frozenset({
        EstadoTarea.PENDIENTE,
        EstadoTarea.EN_CURSO,
        EstadoTarea.CANCELADA,
    }),
    EstadoTarea.EN_CURSO: frozenset({
        EstadoTarea.PAUSADA,
        EstadoTarea.COMPLETADA,
        EstadoTarea.FALLIDA,
        EstadoTarea.CANCELADA,
    }),
    EstadoTarea.PAUSADA: frozenset({
        EstadoTarea.EN_CURSO,
        EstadoTarea.CANCELADA,
    }),
    EstadoTarea.COMPLETADA: frozenset({
        EstadoTarea.CANCELADA,  # solo para revertir si es necesario
    }),
    EstadoTarea.FALLIDA: frozenset({
        EstadoTarea.CANCELADA,
    }),
    EstadoTarea.CANCELADA: frozenset(),
}

# Incidente
TRANSICIONES_INCIDENTE: Dict[EstadoIncidente, FrozenSet[EstadoIncidente]] = {
    EstadoIncidente.ABIERTO: frozenset({
        EstadoIncidente.EN_RESPUESTA,
    }),
    EstadoIncidente.EN_RESPUESTA: frozenset({
        EstadoIncidente.CONTENIDO,
    }),
    EstadoIncidente.CONTENIDO: frozenset({
        EstadoIncidente.CERRADO,
    }),
    EstadoIncidente.CERRADO: frozenset(),
}


# ============================================================================
# Funciones de validación de reglas extra
# ============================================================================

def _clave_especie_catalogo(especie) -> Optional[str]:
    """Devuelve la clave de catálogo de una especie (o None si no está)."""
    for clave, candidata in ESPECIES_CATALOGO.items():
        if candidata == especie:
            return clave
    return None


def _cuidador_tiene_tarea_activa(
    mundo: Mundo,
    cuidador_id: str,
    excluir_tarea_id: Optional[str] = None,
) -> bool:
    """Indica si el cuidador ya tiene una tarea en estado activo."""
    estados_activos = {EstadoTarea.ASIGNADA, EstadoTarea.EN_CURSO, EstadoTarea.PAUSADA}
    for tarea in mundo.tareas.values():
        if tarea.cuidador_asignado != cuidador_id:
            continue
        if tarea.estado not in estados_activos:
            continue
        if excluir_tarea_id and tarea.id == excluir_tarea_id:
            continue
        return True
    return False


def validar_transicion_animal_extra(
    animal: Animal,
    estado_actual: EstadoAnimal,
    estado_nuevo: EstadoAnimal,
    mundo: Mundo,
    recinto_destino_id: Optional[str] = None,
) -> Optional[str]:
    """
    Valida reglas extra para transiciones de Animal.
    Retorna mensaje de error si inválido, None si válido.

    INV-6: toda transición a EN_RECINTO exige `recinto_destino_id`, que debe
    existir en el mundo y admitir la especie del animal.
    """
    # Regla: Animal acuático NO puede pasar a escapado
    if estado_nuevo == EstadoAnimal.ESCAPADO and animal.especie.medio == Medio.ACUATICO:
        return f"Animal de medio acuático ({animal.especie.nombre}) no puede escapar"

    # Regla: Si especie requiere_tranquilizante, localizado NO puede ir a en_traslado directamente
    if (estado_actual == EstadoAnimal.LOCALIZADO
            and estado_nuevo == EstadoAnimal.EN_TRASLADO
            and animal.especie.requiere_tranquilizante):
        return (f"Especie {animal.especie.nombre} requiere tranquilizante: "
                f"debe pasar por TRANQUILIZADO antes de EN_TRASLADO")

    # INV-6: el recinto destino debe existir y admitir la especie
    if estado_nuevo == EstadoAnimal.EN_RECINTO:
        if not recinto_destino_id:
            return "Transición a EN_RECINTO requiere un recinto destino"

        recinto = mundo.recintos.get(recinto_destino_id)
        if recinto is None:
            return f"Recinto destino {recinto_destino_id} no existe"

        clave_especie = _clave_especie_catalogo(animal.especie)
        if clave_especie is None:
            return f"Especie {animal.especie.nombre} no está en el catálogo"

        if clave_especie not in recinto.especies_admitidas:
            return (f"Recinto {recinto_destino_id} no admite la especie "
                    f"{animal.especie.nombre} (admite: {sorted(recinto.especies_admitidas)})")

    return None


def validar_transicion_tarea_extra(
    tarea_id: str,
    estado_actual: EstadoTarea,
    estado_nuevo: EstadoTarea,
    mundo: Mundo,
    cuidador_id: Optional[str] = None,
) -> Optional[str]:
    """
    Valida reglas extra para transiciones de Tarea.
    Las dependencias y la asignación se calculan desde el mundo.

    INV-3: transición a ASIGNADA exige `cuidador_id` existente y sin otra tarea
    activa.
    """
    tarea = mundo.tareas.get(tarea_id)
    if tarea is None:
        return f"Tarea {tarea_id} no existe en el mundo"

    if estado_nuevo == EstadoTarea.ASIGNADA:
        if not cuidador_id:
            return f"Transición a ASIGNADA requiere cuidador_id (tarea {tarea_id})"
        cuidador = mundo.cuidadores.get(cuidador_id)
        if cuidador is None:
            return f"Cuidador {cuidador_id} no existe"
        if cuidador.estado != EstadoCuidador.DISPONIBLE:
            return (
                f"Cuidador {cuidador_id} no está DISPONIBLE "
                f"(estado: {cuidador.estado.name})"
            )
        if _cuidador_tiene_tarea_activa(mundo, cuidador_id, excluir_tarea_id=tarea_id):
            return f"Cuidador {cuidador_id} ya tiene una tarea activa (INV-3)"

    # Regla: No puede pasar a EN_CURSO ni COMPLETADA si tiene dependencias pendientes
    if estado_nuevo in {EstadoTarea.EN_CURSO, EstadoTarea.COMPLETADA}:
        for dep_id in tarea.dependencias:
            dep_tarea = mundo.tareas.get(dep_id)
            if dep_tarea is None:
                raise DependenciaInexistente(tarea_id, dep_id)
            if dep_tarea.estado != EstadoTarea.COMPLETADA:
                return (f"Tarea {tarea_id} tiene dependencias pendientes: "
                        f"{dep_id} (estado: {dep_tarea.estado.name})")

    return None


_TIPOS_INCIDENTE_ESCAPE = frozenset({
    TipoIncidente.ESCAPE_TERRESTRE,
    TipoIncidente.ESCAPE_AEREO,
})


def validar_transicion_incidente_extra(
    incidente: Incidente,
    estado_actual: EstadoIncidente,
    estado_nuevo: EstadoIncidente,
    mundo: Mundo,
) -> Optional[str]:
    """
    Valida reglas extra para transiciones de Incidente leyendo el mundo.

    Al cerrar (CERRADO):
    - todas las tareas vinculadas al incidente deben estar COMPLETADA o CANCELADA;
    - si el incidente es de escape, el animal vinculado (`animal_relacionado`)
      debe existir y estar EN_RECINTO.

    No acepta banderas del llamador: el estado se calcula desde el mundo.
    """
    if estado_nuevo != EstadoIncidente.CERRADO:
        return None

    tareas_incidente = set(incidente.tareas_generadas)
    tareas_incidente.update(
        tarea.id for tarea in mundo.tareas.values()
        if tarea.incidente_origen == incidente.id
    )
    pendientes = []
    for tarea_id in sorted(tareas_incidente):
        tarea = mundo.tareas.get(tarea_id)
        if tarea is None:
            raise ErrorDominio(
                f"Incidente {incidente.id}: la tarea {tarea_id} no existe en el mundo"
            )
        if tarea.estado not in {EstadoTarea.COMPLETADA, EstadoTarea.CANCELADA}:
            pendientes.append(f"{tarea_id} ({tarea.estado.name})")

    if pendientes:
        return (
            f"Incidente {incidente.id}: tareas pendientes: "
            f"{', '.join(pendientes)}"
        )

    if incidente.tipo in _TIPOS_INCIDENTE_ESCAPE:
        if not incidente.animal_relacionado:
            raise ErrorDominio(
                f"Incidente {incidente.id} de escape requiere animal_relacionado"
            )
        animal = mundo.animales.get(incidente.animal_relacionado)
        if animal is None:
            raise ErrorDominio(
                f"Incidente {incidente.id}: el animal "
                f"{incidente.animal_relacionado} no existe en el mundo"
            )
        if animal.estado != EstadoAnimal.EN_RECINTO:
            return (
                f"Incidente {incidente.id}: animal {animal.id} no está en "
                f"recinto (estado: {animal.estado.name})"
            )

    return None


# ============================================================================
# Función pública única: ejecutar_transicion
# ============================================================================

# Parámetros obligatorios para ciertas transiciones.
_PARAMETROS_REQUERIDOS = {
    ("Animal", EstadoAnimal.EN_RECINTO): ("recinto_destino",),
    ("Tarea", EstadoTarea.ASIGNADA): ("cuidador_id",),
}


def ejecutar_transicion(
    mundo: Mundo,
    registro_eventos: RegistroEventos,
    entidad_tipo: str,
    entidad_id: str,
    estado_nuevo,
    tiempo: int,
    causa: str,
    **parametros,
) -> Evento:
    """
    Ejecuta una transición de estado de forma atómica y consistente.

    Es la ÚNICA vía pública para cambiar estados. En este orden:
    1. Lee la entidad y su estado REAL del mundo (no lo recibe del llamador)
    2. Valida el tipo de estado, los parámetros y la tabla de transiciones
    3. Valida las reglas extra (INV-3, INV-6, dependencias, incidentes)
    4. Construye el Evento con los datos_extra relevantes
    5. Valida que el evento pueda anexarse (por ejemplo, ID único)
    6. Lo aplica con `aplicar_evento` (mutando el mundo)
    7. Lo anexa al registro; si el anexo falla, revierte entidad y reloj

    Si cualquier validación falla, ni el mundo ni el registro se modifican.

    Args:
        mundo: Mundo donde operar (se muta)
        registro_eventos: Registro de eventos (se muta)
        entidad_tipo: "Cuidador", "Animal", "Vehiculo", "Tarea", "Incidente"
        entidad_id: ID de la entidad
        estado_nuevo: Estado objetivo (miembro del enum correspondiente)
        tiempo: Tiempo simulado actual
        causa: Texto explicativo
        **parametros: Parámetros adicionales según entidad_tipo:
            - Animal: recinto_destino (obligatorio para EN_RECINTO)
            - Tarea: cuidador_id (obligatorio para ASIGNADA)
            - Incidente: sin parámetros; el cierre se calcula desde el mundo

    Returns:
        Evento generado

    Raises:
        ErrorDominio: Si la entidad no existe, el estado no pertenece al enum
            o falta un parámetro obligatorio
        TiempoRetrocede: Si `tiempo` es menor que `mundo.tiempo_actual`
        TransicionInvalida: Si la transición no está permitida por la tabla o
            por una regla extra
        DependenciaInexistente: Si una dependencia de la tarea no existe
    """
    if tiempo < mundo.tiempo_actual:
        raise TiempoRetrocede(mundo.tiempo_actual, tiempo)

    # 1. Leer entidad y estado REAL del mundo
    entidad, estado_actual, enum_estado = _obtener_entidad_y_estado(
        mundo, entidad_tipo, entidad_id
    )

    if not isinstance(estado_nuevo, enum_estado):
        raise ErrorDominio(
            f"Estado {estado_nuevo!r} no pertenece a {enum_estado.__name__} "
            f"({entidad_tipo}:{entidad_id})"
        )

    _exigir_parametros(entidad_tipo, estado_nuevo, parametros)

    # 2. Obtener tabla de transiciones y validación extra
    tabla, validacion_extra, datos_extra_builder = _obtener_config_entidad(entidad_tipo)

    # 3. Validar contra la tabla de transiciones
    permitidos = tabla.get(estado_actual, frozenset())
    if estado_nuevo not in permitidos:
        raise TransicionInvalida(
            entidad=entidad_tipo,
            estado_actual=estado_actual.name,
            estado_intentado=estado_nuevo.name,
            mensaje=f"Transición no permitida desde {estado_actual.name}",
        )

    # 4. Validación extra (reglas de negocio, INV-3, INV-6, dependencias)
    if validacion_extra is not None:
        args_extra = _construir_args_validacion(
            entidad_tipo, entidad, estado_actual, estado_nuevo, mundo, parametros
        )
        error = validacion_extra(*args_extra)
        if error:
            raise TransicionInvalida(
                entidad=entidad_tipo,
                estado_actual=estado_actual.name,
                estado_intentado=estado_nuevo.name,
                mensaje=error,
            )

    # 5. Construir datos_extra para el evento
    datos_extra = {}
    if datos_extra_builder is not None:
        datos_extra = datos_extra_builder(entidad, estado_nuevo, parametros)

    # 6. Crear evento
    evento = crear_evento(
        registro_eventos,
        momento=tiempo,
        tipo=TipoEvento.CAMBIO_ESTADO,
        entidad_tipo=entidad_tipo,
        entidad_id=entidad_id,
        estado_antes=estado_actual.name,
        estado_despues=estado_nuevo.name,
        causa=causa,
        datos_extra=datos_extra,
    )

    # 7. Validar el anexo ANTES de mutar el mundo (p. ej. ID duplicado)
    registro_eventos.validar_anexo(evento)

    # 8. Aplicar evento (mutar mundo) y actualizar el reloj
    entidad_antes = entidad
    tiempo_antes = mundo.tiempo_actual
    aplicar_evento(mundo, evento)
    mundo.tiempo_actual = tiempo

    # 9. Anexar al registro; si falla, revertir la entidad y el reloj
    try:
        registro_eventos.anexar(evento)
    except Exception:
        mundo.sustituir_entidad(
            _ENTIDADES_ESTADO[entidad_tipo][0], entidad_id, entidad_antes
        )
        mundo.tiempo_actual = tiempo_antes
        raise

    return evento


# ============================================================================
# Helpers privados para ejecutar_transicion
# ============================================================================

# Tipo de entidad -> (colección del Mundo, enum de estado)
_ENTIDADES_ESTADO = {
    "Cuidador": ("cuidadores", EstadoCuidador),
    "Animal": ("animales", EstadoAnimal),
    "Vehiculo": ("vehiculos", EstadoVehiculo),
    "Tarea": ("tareas", EstadoTarea),
    "Incidente": ("incidentes", EstadoIncidente),
}


def _obtener_entidad_y_estado(mundo: Mundo, entidad_tipo: str, entidad_id: str):
    """Obtiene la entidad, su estado actual y el enum de estado del mundo."""
    config = _ENTIDADES_ESTADO.get(entidad_tipo)
    if config is None:
        raise ErrorDominio(f"Tipo de entidad desconocido: {entidad_tipo}")

    attr, enum_estado = config
    entidad = getattr(mundo, attr).get(entidad_id)
    if entidad is None:
        raise ErrorDominio(f"Entidad {entidad_tipo}:{entidad_id} no existe en el mundo")

    return entidad, entidad.estado, enum_estado


def _obtener_config_entidad(entidad_tipo: str):
    """Obtiene tabla de transiciones, validador extra y builder de datos_extra."""
    if entidad_tipo == "Cuidador":
        return TRANSICIONES_CUIDADOR, None, None
    if entidad_tipo == "Animal":
        return TRANSICIONES_ANIMAL, validar_transicion_animal_extra, _datos_extra_animal
    if entidad_tipo == "Vehiculo":
        return TRANSICIONES_VEHICULO, None, None
    if entidad_tipo == "Tarea":
        return TRANSICIONES_TAREA, validar_transicion_tarea_extra, _datos_extra_tarea
    if entidad_tipo == "Incidente":
        return TRANSICIONES_INCIDENTE, validar_transicion_incidente_extra, None

    raise ErrorDominio(f"Tipo de entidad desconocido: {entidad_tipo}")


def _exigir_parametros(entidad_tipo: str, estado_nuevo, parametros: dict) -> None:
    """Lanza ErrorDominio si falta un parámetro obligatorio para la transición."""
    for nombre in _PARAMETROS_REQUERIDOS.get((entidad_tipo, estado_nuevo), ()):
        if nombre not in parametros:
            raise ErrorDominio(
                f"Transición {entidad_tipo}:{estado_nuevo.name} requiere "
                f"el parámetro '{nombre}'"
            )


def _construir_args_validacion(
    entidad_tipo: str,
    entidad,
    estado_actual,
    estado_nuevo,
    mundo: Mundo,
    parametros: dict,
):
    """Construye los argumentos posicionales para el validador extra."""
    if entidad_tipo == "Animal":
        return (
            entidad,
            estado_actual,
            estado_nuevo,
            mundo,
            parametros.get("recinto_destino"),
        )
    if entidad_tipo == "Tarea":
        return (
            entidad.id,
            estado_actual,
            estado_nuevo,
            mundo,
            parametros.get("cuidador_id"),
        )
    if entidad_tipo == "Incidente":
        return (
            entidad,
            estado_actual,
            estado_nuevo,
            mundo,
        )
    return ()


def _datos_extra_animal(entidad, estado_nuevo, parametros: dict) -> dict:
    """Datos que el evento debe escribir en el Animal."""
    if estado_nuevo == EstadoAnimal.EN_RECINTO:
        return {"ubicacion": parametros["recinto_destino"]}
    return {}


def _datos_extra_tarea(entidad, estado_nuevo, parametros: dict) -> dict:
    """Datos que el evento debe escribir en la Tarea."""
    if estado_nuevo == EstadoTarea.ASIGNADA:
        return {"cuidador_asignado": parametros["cuidador_id"]}
    if estado_nuevo == EstadoTarea.PENDIENTE:
        return {"cuidador_asignado": None}
    return {}
