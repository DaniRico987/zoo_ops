"""Algoritmos puros de rutas sobre el grafo del mundo."""

import heapq
from typing import Optional, Tuple

from zoo_ops.dominio.entidades import Mundo
from zoo_ops.dominio.enums import MedioPermitido
from zoo_ops.dominio.errores import ErrorDominio


def ruta_mas_corta(
    mundo: Mundo,
    origen: str,
    destino: str,
    medio: MedioPermitido,
) -> Optional[Tuple[Tuple[str, ...], float]]:
    """Calcula una ruta dirigida de distancia mínima para el medio indicado."""
    for nodo_id in (origen, destino):
        if nodo_id not in mundo.nodos:
            raise ErrorDominio(f"El nodo {nodo_id} no existe en el mundo")
    if origen == destino:
        return (origen,), 0.0

    adyacencias = {}
    for (nodo_origen, nodo_destino), arista in mundo.aristas.items():
        if arista.bloqueada or medio not in arista.medios_permitidos:
            continue
        if arista.distancia < 0:
            raise ErrorDominio(
                f"La distancia de la arista {nodo_origen} -> {nodo_destino} "
                "no puede ser negativa"
            )
        adyacencias.setdefault(nodo_origen, []).append(
            (nodo_destino, arista.distancia)
        )
    for vecinos in adyacencias.values():
        vecinos.sort(key=lambda vecino: vecino[0])

    distancias = {origen: 0.0}
    rutas = {origen: (origen,)}
    pendientes = [(0.0, (origen,), origen)]

    while pendientes:
        distancia_actual, ruta_actual, nodo_actual = heapq.heappop(pendientes)
        if (
            distancia_actual != distancias.get(nodo_actual)
            or ruta_actual != rutas.get(nodo_actual)
        ):
            continue
        if nodo_actual == destino:
            return ruta_actual, distancia_actual

        for siguiente, distancia_arista in adyacencias.get(nodo_actual, ()):
            if siguiente in ruta_actual:
                continue
            nueva_distancia = distancia_actual + distancia_arista
            nueva_ruta = ruta_actual + (siguiente,)
            distancia_anterior = distancias.get(siguiente, float("inf"))
            ruta_anterior = rutas.get(siguiente)
            if (
                nueva_distancia > distancia_anterior
                or (
                    nueva_distancia == distancia_anterior
                    and ruta_anterior is not None
                    and nueva_ruta >= ruta_anterior
                )
            ):
                continue
            distancias[siguiente] = nueva_distancia
            rutas[siguiente] = nueva_ruta
            heapq.heappush(
                pendientes,
                (nueva_distancia, nueva_ruta, siguiente),
            )

    return None
