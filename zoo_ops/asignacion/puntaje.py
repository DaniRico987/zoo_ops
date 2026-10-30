"""Perfiles, componentes y ranking explicable de candidatos."""

from dataclasses import dataclass
from enum import Enum, auto
from math import isfinite
from types import MappingProxyType
from typing import Mapping, Optional, Tuple

from zoo_ops.dominio.entidades import Mundo, Tarea, nodo_de_ubicacion
from zoo_ops.dominio.enums import EstadoTarea
from zoo_ops.dominio.errores import ErrorDominio
from zoo_ops.asignacion.candidatos import Candidato


NIVEL_MAXIMO_HABILIDAD = 5
ESCALA_TIEMPO_SEGUNDOS = 60


class Perfil(Enum):
    """Prioridad que determina los pesos usados al puntuar una tarea."""

    EMERGENCIA = auto()
    RUTINA = auto()
    MANTENIMIENTO = auto()


@dataclass(frozen=True)
class Pesos:
    """Pesos no negativos cuya suma debe ser uno."""

    tiempo: float
    habilidad: float
    carga: float
    fatiga: float
    continuidad: float

    def __post_init__(self) -> None:
        valores = (
            self.tiempo,
            self.habilidad,
            self.carga,
            self.fatiga,
            self.continuidad,
        )
        if any(
            not isinstance(valor, (int, float))
            or isinstance(valor, bool)
            or not isfinite(valor)
            or valor < 0
            for valor in valores
        ):
            raise ErrorDominio("Los pesos deben ser finitos y no negativos")
        if abs(sum(valores) - 1.0) > 1e-9:
            raise ErrorDominio("Los pesos deben sumar 1.0")


PERFILES: Mapping[Perfil, Pesos] = MappingProxyType({
    Perfil.EMERGENCIA: Pesos(0.60, 0.25, 0.00, 0.05, 0.10),
    Perfil.RUTINA: Pesos(0.15, 0.20, 0.30, 0.20, 0.15),
    Perfil.MANTENIMIENTO: Pesos(0.10, 0.30, 0.25, 0.20, 0.15),
})


def perfil_de_tarea(
    tarea: Tarea,
    perfiles_por_tipo: Optional[Mapping[str, Perfil]] = None,
) -> Perfil:
    """Resuelve el perfil explícito por tipo o aplica las reglas predeterminadas."""
    if perfiles_por_tipo is not None and tarea.tipo in perfiles_por_tipo:
        return perfiles_por_tipo[tarea.tipo]
    if tarea.incidente_origen is not None:
        return Perfil.EMERGENCIA
    if tarea.tipo == "mantenimiento":
        return Perfil.MANTENIMIENTO
    return Perfil.RUTINA


@dataclass(frozen=True)
class Componentes:
    """Componentes normalizados del puntaje; en todos, un valor mayor es mejor."""

    tiempo: float
    habilidad: float
    carga: float
    fatiga: float
    continuidad: float

    def __post_init__(self) -> None:
        if any(
            not isfinite(valor) or not 0.0 <= valor <= 1.0
            for valor in (
                self.tiempo,
                self.habilidad,
                self.carga,
                self.fatiga,
                self.continuidad,
            )
        ):
            raise ErrorDominio("Cada componente debe estar entre 0 y 1")


@dataclass(frozen=True)
class Puntuado:
    """Candidato con perfil, pesos, componentes y puntuación final."""

    candidato: Candidato
    perfil: Perfil
    pesos: Pesos
    componentes: Componentes
    puntaje: float


def _nivel_habilidad(
    mundo: Mundo,
    cuidador_ids: Tuple[str, ...],
    habilidad,
) -> int:
    niveles = []
    for cuidador_id in cuidador_ids:
        cuidador = mundo.cuidadores.get(cuidador_id)
        if cuidador is None:
            raise ErrorDominio(
                f"El candidato referencia al cuidador inexistente {cuidador_id}"
            )
        niveles.append(cuidador.habilidades.get(habilidad, 0))
    return max(niveles, default=0)


def _componente_habilidad(
    mundo: Mundo,
    tarea: Tarea,
    candidato: Candidato,
    perfil: Perfil,
) -> float:
    if not tarea.habilidades_requeridas:
        return 1.0
    puntuaciones = []
    for requisito in tarea.habilidades_requeridas:
        nivel = _nivel_habilidad(
            mundo, candidato.plan.cuidadores, requisito.habilidad,
        )
        if perfil == Perfil.EMERGENCIA:
            puntuacion = min(1.0, max(0.0, nivel / NIVEL_MAXIMO_HABILIDAD))
        else:
            exceso = max(0, nivel - requisito.nivel_minimo)
            puntuacion = 1.0 - min(1.0, exceso / 4)
        puntuaciones.append(puntuacion)
    return sum(puntuaciones) / len(puntuaciones)


def _componente_carga(
    mundo: Mundo,
    candidato: Candidato,
    cargas: Mapping[str, int],
) -> float:
    if not candidato.plan.cuidadores:
        raise ErrorDominio("El candidato debe incluir al menos un cuidador")
    carga_equipo = sum(
        cargas.get(cuidador_id, 0)
        for cuidador_id in candidato.plan.cuidadores
    ) / len(candidato.plan.cuidadores)
    carga_maxima = max(cargas.values(), default=0)
    return 1.0 - carga_equipo / max(1, carga_maxima)


def _componente_fatiga(
    mundo: Mundo,
    candidato: Candidato,
) -> float:
    fatigas = []
    for cuidador_id in candidato.plan.cuidadores:
        cuidador = mundo.cuidadores.get(cuidador_id)
        if cuidador is None:
            raise ErrorDominio(
                f"El candidato referencia al cuidador inexistente {cuidador_id}"
            )
        fatigas.append(cuidador.fatiga)
    return min(1.0, max(0.0, 1.0 - sum(fatigas) / len(fatigas) / 100))


def _componente_continuidad(
    mundo: Mundo,
    tarea: Tarea,
    candidato: Candidato,
    indice_continuidad: Mapping[str, Mapping[str, frozenset[str]]],
) -> float:
    continuos = 0
    for cuidador_id in candidato.plan.cuidadores:
        cuidador = mundo.cuidadores.get(cuidador_id)
        if cuidador is None:
            raise ErrorDominio(
                f"El candidato referencia al cuidador inexistente {cuidador_id}"
            )
        esta_en_destino = (
            nodo_de_ubicacion(cuidador.ubicacion) == tarea.nodo_destino
        )
        tareas_del_incidente = (
            indice_continuidad.get(tarea.incidente_origen, {})
            .get(cuidador_id, frozenset())
            if tarea.incidente_origen is not None
            else frozenset()
        )
        continua_incidente = any(
            tarea_id != tarea.id for tarea_id in tareas_del_incidente
        )
        if esta_en_destino or continua_incidente:
            continuos += 1
    return continuos / len(candidato.plan.cuidadores)


def _cargas_cuidadores(mundo: Mundo) -> dict[str, int]:
    terminales = {EstadoTarea.COMPLETADA, EstadoTarea.FALLIDA}
    cargas = {cuidador_id: 0 for cuidador_id in mundo.cuidadores}
    for tarea in mundo.tareas.values():
        if tarea.estado in terminales:
            for cuidador_id in set(tarea.cuidadores_asignados):
                if cuidador_id in cargas:
                    cargas[cuidador_id] += 1
    return cargas


def _indice_continuidad(
    mundo: Mundo,
) -> dict[str, dict[str, frozenset[str]]]:
    acumulado: dict[str, dict[str, set[str]]] = {}
    for tarea in mundo.tareas.values():
        if tarea.incidente_origen is None:
            continue
        por_cuidador = acumulado.setdefault(tarea.incidente_origen, {})
        for cuidador_id in set(tarea.cuidadores_asignados):
            por_cuidador.setdefault(cuidador_id, set()).add(tarea.id)
    return {
        incidente_id: {
            cuidador_id: frozenset(tarea_ids)
            for cuidador_id, tarea_ids in por_cuidador.items()
        }
        for incidente_id, por_cuidador in acumulado.items()
    }


def puntuar_candidatos(
    mundo: Mundo,
    tarea_id: str,
    candidatos: Tuple[Candidato, ...],
    perfil: Optional[Perfil] = None,
    pesos: Optional[Pesos] = None,
    escala_tiempo_segundos: float = ESCALA_TIEMPO_SEGUNDOS,
) -> Tuple[Puntuado, ...]:
    """Puntúa y ordena candidatos, sin cambiar el mundo."""
    if (
        not isinstance(escala_tiempo_segundos, (int, float))
        or isinstance(escala_tiempo_segundos, bool)
        or not isfinite(escala_tiempo_segundos)
        or escala_tiempo_segundos <= 0
    ):
        raise ErrorDominio("La escala de tiempo debe ser finita y mayor que cero")
    tarea = mundo.tareas.get(tarea_id)
    if tarea is None:
        raise ErrorDominio(f"La tarea {tarea_id} no existe en el mundo")
    if tarea.estado != EstadoTarea.PENDIENTE:
        raise ErrorDominio(
            f"La tarea {tarea_id} debe estar PENDIENTE; "
            f"está {tarea.estado.name}"
        )
    if any(candidato.plan.tarea_id != tarea_id for candidato in candidatos):
        raise ErrorDominio(
            f"Cada candidato debe pertenecer a la tarea {tarea_id}"
        )
    if not candidatos:
        return ()

    perfil_elegido = perfil if perfil is not None else perfil_de_tarea(tarea)
    pesos_elegidos = pesos if pesos is not None else PERFILES[perfil_elegido]
    tiempos = tuple(
        candidato.estimacion.llegada - candidato.estimacion.desde
        for candidato in candidatos
    )
    tiempo_minimo = min(tiempos)
    cargas = _cargas_cuidadores(mundo)
    indice_continuidad = _indice_continuidad(mundo)

    puntuados = []
    for candidato, tiempo in zip(candidatos, tiempos):
        componente_tiempo = 1.0 / (
            1.0
            + max(0, tiempo - tiempo_minimo) / escala_tiempo_segundos
        )
        componentes = Componentes(
            tiempo=componente_tiempo,
            habilidad=_componente_habilidad(
                mundo, tarea, candidato, perfil_elegido,
            ),
            carga=_componente_carga(mundo, candidato, cargas),
            fatiga=_componente_fatiga(mundo, candidato),
            continuidad=_componente_continuidad(
                mundo, tarea, candidato, indice_continuidad,
            ),
        )
        puntaje = round(
            pesos_elegidos.tiempo * componentes.tiempo
            + pesos_elegidos.habilidad * componentes.habilidad
            + pesos_elegidos.carga * componentes.carga
            + pesos_elegidos.fatiga * componentes.fatiga
            + pesos_elegidos.continuidad * componentes.continuidad,
            9,
        )
        puntuados.append(Puntuado(
            candidato=candidato,
            perfil=perfil_elegido,
            pesos=pesos_elegidos,
            componentes=componentes,
            puntaje=puntaje,
        ))

    puntuados.sort(
        key=lambda puntuado: (
            -puntuado.puntaje,
            puntuado.candidato.estimacion.hasta,
            puntuado.candidato.plan.cuidadores,
            puntuado.candidato.plan.vehiculo_id or "",
        )
    )
    return tuple(puntuados)


def explicar(puntuado: Puntuado) -> str:
    """Explica cada componente, su peso y su contribución en español."""
    nombres = ("tiempo", "habilidad", "carga", "fatiga", "continuidad")
    lineas = [
        (
            f"{nombre}: componente={getattr(puntuado.componentes, nombre):.12f}; "
            f"peso={getattr(puntuado.pesos, nombre):.12f}; "
            f"contribución="
            f"{getattr(puntuado.componentes, nombre) * getattr(puntuado.pesos, nombre):.12f}"
        )
        for nombre in nombres
    ]
    lineas.append(f"Puntaje total={puntuado.puntaje:.9f}")
    return "\n".join(lineas)
