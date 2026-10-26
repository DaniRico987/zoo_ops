"""
zoo_ops.dominio - Núcleo de dominio del sistema de coordinación y simulación de zoológico.

Módulos:
- enums: Enumeraciones base
- catalogos: Catálogos y datos semilla (especies, habilidades, certificaciones, equipos)
- entidades: Entidades del dominio (dataclasses frozen)
- estados: Máquinas de estado declarativas
- eventos: Eventos inmutables y reconstrucción de estado
- reservas: Sistema de reservas atómicas
- plan: Planes de ejecución y validación de requisitos de recursos
- invariantes: Verificación de invariantes del sistema
- errores: Excepciones personalizadas
"""

from .enums import (
    TipoNodo, TipoRecinto, Medio, Peligrosidad, TipoVehiculo, TipoEquipo,
    Habilidad, Certificacion, EstadoCuidador, EstadoAnimal, EstadoVehiculo,
    EstadoEquipo, EstadoTarea, EstadoIncidente, TipoIncidente, TipoSensor, MedioPermitido,
    PrioridadTarea,
)
from .catalogos import (
    ESPECIES_CATALOGO, HABILIDADES_CATALOGO, CERTIFICACIONES_CATALOGO,
    EQUIPOS_CATALOGO, Especie, DefinicionHabilidad, DefinicionCertificacion,
    DefinicionEquipo, obtener_especie, listar_especies,
)
from .entidades import (
    Nodo, Arista, Recinto, Cuidador, Vehiculo, IndicadoresSalud, Animal,
    Equipo, Tarea, HabilidadRequerida, Incidente, Sensor, Lectura, Mundo,
    esta_en_nodo, esta_en_arista, obtener_nodo_actual, obtener_arista_actual,
)
from .estados import (
    TRANSICIONES_CUIDADOR, TRANSICIONES_ANIMAL, TRANSICIONES_VEHICULO,
    TRANSICIONES_TAREA, TRANSICIONES_INCIDENTE,
    ejecutar_transicion, validar_transicion_animal_extra,
    validar_transicion_tarea_extra, validar_transicion_incidente_extra,
)
from .eventos import (
    TipoEvento, Evento, RegistroEventos, crear_evento, aplicar_evento,
    reconstruir_estado, verificar_reconstruccion,
    plan_a_datos_extra, plan_desde_datos_extra, EVENTOS_NO_RECONSTRUIBLES,
)
from .reservas import (
    TipoRecurso, Reserva, RegistroReservas,
    reservar_atomico, liberar_reservas_tarea, verificar_disponibilidad_recurso,
    paquete_de_reservas, reservar_plan,
)
from .plan import (
    PlanEjecucion, cubre_requisitos_cuidadores, validar_capacidad_vehiculo,
    validar_ruta_terrestre, validar_plan, exigir_plan_valido,
    registrar_plan_con_evento, liberar_plan_con_evento,
)
from .invariantes import (
    verificar_invariantes, ViolacionInvariante, NoVerificada,
    formatear_violaciones, formatear_no_verificadas, assert_sin_violaciones,
)
from .errores import (
    ErrorDominio, TransicionInvalida, ReservaInvalida, ReservaAtomicaFallida,
    RecursosInvalidos, InvarianzaViolada, RecursoNoDisponible, HabilidadInsuficiente,
    CertificacionFaltante, DependenciasPendientes, DependenciaInexistente,
    EventoNoSoportado, EventoDuplicado, TiempoRetrocede, PlanInvalido,
)

__all__ = [
    # enums
    "TipoNodo", "TipoRecinto", "Medio", "Peligrosidad", "TipoVehiculo", "TipoEquipo",
    "Habilidad", "Certificacion", "EstadoCuidador", "EstadoAnimal", "EstadoVehiculo",
    "EstadoEquipo", "EstadoTarea", "EstadoIncidente", "TipoIncidente", "TipoSensor", "MedioPermitido",
    "PrioridadTarea",
    # catalogos
    "ESPECIES_CATALOGO", "HABILIDADES_CATALOGO", "CERTIFICACIONES_CATALOGO",
    "EQUIPOS_CATALOGO", "Especie", "DefinicionHabilidad", "DefinicionCertificacion",
    "DefinicionEquipo", "obtener_especie", "listar_especies",
    # entidades
    "Nodo", "Arista", "Recinto", "Cuidador", "Vehiculo", "IndicadoresSalud", "Animal",
    "Equipo", "Tarea", "HabilidadRequerida", "Incidente", "Sensor", "Lectura", "Mundo",
    "esta_en_nodo", "esta_en_arista", "obtener_nodo_actual", "obtener_arista_actual",
    # estados
    "TRANSICIONES_CUIDADOR", "TRANSICIONES_ANIMAL", "TRANSICIONES_VEHICULO",
    "TRANSICIONES_TAREA", "TRANSICIONES_INCIDENTE",
    "ejecutar_transicion", "validar_transicion_animal_extra",
    "validar_transicion_tarea_extra", "validar_transicion_incidente_extra",
    # eventos
    "TipoEvento", "Evento", "RegistroEventos", "crear_evento", "aplicar_evento",
    "reconstruir_estado", "verificar_reconstruccion",
    "plan_a_datos_extra", "plan_desde_datos_extra",
    "EVENTOS_NO_RECONSTRUIBLES",
    # reservas
    "TipoRecurso", "Reserva", "RegistroReservas",
    "reservar_atomico", "liberar_reservas_tarea", "verificar_disponibilidad_recurso",
    "paquete_de_reservas", "reservar_plan",
    # plan
    "PlanEjecucion", "cubre_requisitos_cuidadores",
    "validar_capacidad_vehiculo", "validar_ruta_terrestre", "validar_plan",
    "exigir_plan_valido", "registrar_plan_con_evento",
    "liberar_plan_con_evento",
    # invariantes
    "verificar_invariantes", "ViolacionInvariante", "NoVerificada",
    "formatear_violaciones", "formatear_no_verificadas", "assert_sin_violaciones",
    # errores
    "ErrorDominio", "TransicionInvalida", "ReservaInvalida", "ReservaAtomicaFallida",
    "RecursosInvalidos", "InvarianzaViolada", "RecursoNoDisponible", "HabilidadInsuficiente",
    "CertificacionFaltante", "DependenciasPendientes", "DependenciaInexistente",
    "EventoNoSoportado", "EventoDuplicado", "TiempoRetrocede",
    "PlanInvalido",
]