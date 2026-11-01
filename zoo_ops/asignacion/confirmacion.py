"""Confirmación y aplicación atómica por tarea de propuestas globales."""

from dataclasses import dataclass
from types import MappingProxyType
from typing import Mapping, Optional, Tuple

from zoo_ops.dominio.entidades import Mundo
from zoo_ops.dominio.errores import ErrorDominio, PlanInvalido, TiempoRetrocede
from zoo_ops.dominio.eventos import Evento, RegistroEventos
from zoo_ops.dominio.operaciones import asignar_plan
from zoo_ops.dominio.reservas import RegistroReservas
from zoo_ops.asignacion.planificacion import ResultadoGlobal
from zoo_ops.asignacion.puntaje import Perfil, Puntuado
from zoo_ops.asignacion.tiempos import Estimacion, reprogramar_plan


@dataclass(frozen=True)
class PropuestaPendiente:
    """Alternativas globales a la espera de su aplicación o confirmación."""

    id: str
    tarea_id: str
    perfil: Perfil
    alternativas: Tuple[Puntuado, ...]
    indice_propuesto: int
    generada_en: int
    vigencia: int
    requiere_confirmacion: bool


@dataclass(frozen=True)
class ResultadoAplicacion:
    """Resultado individual de intentar aplicar una propuesta."""

    propuesta_id: str
    tarea_id: str
    estado: str
    eventos: Tuple[Evento, ...]
    errores: Tuple[str, ...]
    estimacion: Optional[Estimacion]


@dataclass(frozen=True)
class InformeAplicacion:
    """Resultados del lote en orden determinista."""

    resultados: Tuple[ResultadoAplicacion, ...]

    def por_estado(self, estado: str) -> Tuple[ResultadoAplicacion, ...]:
        """Filtra resultados por el estado final de aplicación."""
        return tuple(
            resultado
            for resultado in self.resultados
            if resultado.estado == estado
        )


def generar_pendientes(
    resultado: ResultadoGlobal,
    ahora: int,
    vigencia_segundos: int = 120,
    perfiles_con_confirmacion: Tuple[Perfil, ...] = (Perfil.EMERGENCIA,),
) -> Tuple[PropuestaPendiente, ...]:
    """Prepara las asignaciones globales como propuestas pendientes."""
    pendientes = []
    for asignacion in resultado.asignaciones:
        alternativas = resultado.alternativas_por_tarea.get(
            asignacion.tarea_id,
            (),
        )
        try:
            indice_propuesto = alternativas.index(asignacion.puntuado)
        except ValueError as exc:
            raise ErrorDominio(
                f"La asignación de {asignacion.tarea_id} no está entre sus alternativas"
            ) from exc
        pendientes.append(PropuestaPendiente(
            id=f"{asignacion.tarea_id}@{ahora}",
            tarea_id=asignacion.tarea_id,
            perfil=asignacion.puntuado.perfil,
            alternativas=tuple(alternativas),
            indice_propuesto=indice_propuesto,
            generada_en=ahora,
            vigencia=vigencia_segundos,
            requiere_confirmacion=(
                asignacion.puntuado.perfil in perfiles_con_confirmacion
            ),
        ))
    return tuple(sorted(pendientes, key=lambda propuesta: propuesta.id))


def _errores_dominio(error: ErrorDominio) -> Tuple[str, ...]:
    if isinstance(error, PlanInvalido):
        return tuple(error.errores)
    errores = getattr(error, "errores", None)
    if isinstance(errores, (tuple, list)):
        return tuple(str(mensaje) for mensaje in errores)
    return (str(error),)


def aplicar_pendientes(
    mundo: Mundo,
    registro_eventos: RegistroEventos,
    registro_reservas: RegistroReservas,
    pendientes: Tuple[PropuestaPendiente, ...],
    tiempo: int,
    causa: str,
    confirmaciones: Optional[Mapping[str, Optional[int]]] = None,
) -> InformeAplicacion:
    """Aplica cada propuesta de manera independiente y todo o nada."""
    if tiempo < mundo.tiempo_actual:
        raise TiempoRetrocede(mundo.tiempo_actual, tiempo)
    confirmaciones_efectivas = (
        confirmaciones if confirmaciones is not None else MappingProxyType({})
    )
    resultados = []

    for propuesta in sorted(pendientes, key=lambda item: item.id):
        if tiempo - propuesta.generada_en > propuesta.vigencia:
            resultados.append(ResultadoAplicacion(
                propuesta.id,
                propuesta.tarea_id,
                "vencida",
                (),
                (),
                None,
            ))
            continue
        if (
            propuesta.requiere_confirmacion
            and propuesta.id not in confirmaciones_efectivas
        ):
            resultados.append(ResultadoAplicacion(
                propuesta.id,
                propuesta.tarea_id,
                "pendiente_de_confirmacion",
                (),
                (),
                None,
            ))
            continue

        indice = confirmaciones_efectivas.get(
            propuesta.id,
            propuesta.indice_propuesto,
        )
        if indice is None:
            indice = propuesta.indice_propuesto
        if (
            not isinstance(indice, int)
            or isinstance(indice, bool)
            or indice < 0
            or indice >= len(propuesta.alternativas)
        ):
            resultados.append(ResultadoAplicacion(
                propuesta.id,
                propuesta.tarea_id,
                "rechazada",
                (),
                ("Índice de alternativa fuera de rango",),
                None,
            ))
            continue

        elegida = propuesta.alternativas[indice]
        try:
            candidato = reprogramar_plan(
                mundo,
                elegida.candidato.plan,
                tiempo,
            )
        except ErrorDominio as exc:
            resultados.append(ResultadoAplicacion(
                propuesta.id,
                propuesta.tarea_id,
                "rechazada",
                (),
                _errores_dominio(exc),
                None,
            ))
            continue
        if candidato is None:
            resultados.append(ResultadoAplicacion(
                propuesta.id,
                propuesta.tarea_id,
                "rechazada",
                (),
                ("no_estimable",),
                None,
            ))
            continue

        try:
            eventos = asignar_plan(
                mundo,
                registro_eventos,
                registro_reservas,
                candidato.plan,
                tiempo,
                causa,
            )
        except ErrorDominio as exc:
            resultados.append(ResultadoAplicacion(
                propuesta.id,
                propuesta.tarea_id,
                "rechazada",
                (),
                _errores_dominio(exc),
                candidato.estimacion,
            ))
            continue
        resultados.append(ResultadoAplicacion(
            propuesta.id,
            propuesta.tarea_id,
            "aplicada",
            tuple(eventos),
            (),
            candidato.estimacion,
        ))

    return InformeAplicacion(tuple(resultados))
