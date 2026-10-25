"""
Excepciones personalizadas para el dominio de zoo-ops.
"""


class ErrorDominio(Exception):
    """Excepción base para errores del dominio."""
    pass


class TransicionInvalida(ErrorDominio):
    """Lanzada cuando una transición de estado no está permitida."""
    def __init__(self, entidad: str, estado_actual: str, estado_intentado: str, mensaje: str = ""):
        self.entidad = entidad
        self.estado_actual = estado_actual
        self.estado_intentado = estado_intentado
        msg = f"Transición inválida para {entidad}: {estado_actual} -> {estado_intentado}"
        if mensaje:
            msg += f". {mensaje}"
        super().__init__(msg)


class ReservaInvalida(ErrorDominio):
    """Lanzada cuando una reserva no puede realizarse por solapamiento."""
    def __init__(self, recurso: str, desde: int, hasta: int, mensaje: str = ""):
        self.recurso = recurso
        self.desde = desde
        self.hasta = hasta
        msg = f"Reserva inválida para {recurso}: [{desde}, {hasta})"
        if mensaje:
            msg += f". {mensaje}"
        super().__init__(msg)


class ReservaAtomicaFallida(ErrorDominio):
    """Lanzada cuando una reserva atómica falla (todo o nada)."""
    def __init__(self, reservas_fallidas: list, mensaje: str = ""):
        self.reservas_fallidas = reservas_fallidas
        msg = "Reserva atómica fallida: no se pudo reservar todo el paquete"
        if mensaje:
            msg += f". {mensaje}"
        super().__init__(msg)


class RecursosInvalidos(ErrorDominio):
    """Lanzada cuando los recursos para una tarea no son válidos."""
    def __init__(self, errores: list):
        self.errores = errores
        msg = "Recursos inválidos para la tarea: " + "; ".join(errores)
        super().__init__(msg)


class InvarianzaViolada(ErrorDominio):
    """Lanzada cuando se viola una invariante del sistema."""
    def __init__(self, invariante: str, detalle: str = ""):
        self.invariante = invariante
        self.detalle = detalle
        msg = f"Invariante violada: {invariante}"
        if detalle:
            msg += f". {detalle}"
        super().__init__(msg)


class RecursoNoDisponible(ErrorDominio):
    """Lanzada cuando un recurso no está disponible para la operación."""
    def __init__(self, recurso: str, mensaje: str = ""):
        self.recurso = recurso
        msg = f"Recurso no disponible: {recurso}"
        if mensaje:
            msg += f". {mensaje}"
        super().__init__(msg)


class HabilidadInsuficiente(ErrorDominio):
    """Lanzada cuando un cuidador no tiene la habilidad o nivel requerido."""
    def __init__(self, cuidador_id: str, habilidad: str, nivel_requerido: int, nivel_actual: int):
        self.cuidador_id = cuidador_id
        self.habilidad = habilidad
        self.nivel_requerido = nivel_requerido
        self.nivel_actual = nivel_actual
        super().__init__(
            f"Cuidador {cuidador_id} no tiene nivel suficiente de {habilidad}: "
            f"requerido {nivel_requerido}, actual {nivel_actual}"
        )


class CertificacionFaltante(ErrorDominio):
    """Lanzada cuando un cuidador no tiene la certificación requerida."""
    def __init__(self, cuidador_id: str, certificacion: str):
        self.cuidador_id = cuidador_id
        self.certificacion = certificacion
        super().__init__(f"Cuidador {cuidador_id} no tiene certificación {certificacion}")


class DependenciasPendientes(ErrorDominio):
    """Lanzada cuando se intenta iniciar una tarea con dependencias no completadas."""
    def __init__(self, tarea_id: str, dependencias_pendientes: list):
        self.tarea_id = tarea_id
        self.dependencias_pendientes = dependencias_pendientes
        super().__init__(
            f"Tarea {tarea_id} tiene dependencias pendientes: {dependencias_pendientes}"
        )


class DependenciaInexistente(ErrorDominio):
    """Lanzada cuando una tarea depende de otra que no existe en el mundo."""
    def __init__(self, tarea_id: str, dependencia_id: str):
        self.tarea_id = tarea_id
        self.dependencia_id = dependencia_id
        super().__init__(
            f"Tarea {tarea_id} tiene dependencia inexistente: {dependencia_id}"
        )


class EventoNoSoportado(ErrorDominio):
    """Lanzada cuando reconstruir_estado encuentra un tipo de evento sin aplicador."""
    def __init__(self, tipo_evento: str, entidad_tipo: str = "", entidad_id: str = ""):
        self.tipo_evento = tipo_evento
        self.entidad_tipo = entidad_tipo
        self.entidad_id = entidad_id
        msg = f"Tipo de evento no soportado en reconstrucción: {tipo_evento}"
        if entidad_tipo:
            msg += f" (entidad: {entidad_tipo}"
            if entidad_id:
                msg += f":{entidad_id}"
            msg += ")"
        super().__init__(msg)


class EventoDuplicado(ErrorDominio):
    """Lanzada cuando se intenta anexar un evento con un ID ya registrado."""

    def __init__(self, evento_id: int):
        self.evento_id = evento_id
        super().__init__(f"Ya existe un evento con id {evento_id} en el registro")