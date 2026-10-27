"""Pruebas de rutas del paquete de asignación."""

import pytest

from zoo_ops.dominio.entidades import Arista, Mundo, Nodo
from zoo_ops.dominio.enums import MedioPermitido, TipoNodo
from zoo_ops.dominio.errores import ErrorDominio
from zoo_ops.asignacion.grafo import ruta_mas_corta


def _nodos(*ids):
    return {
        nodo_id: Nodo(nodo_id, TipoNodo.CRUCE, index, 0)
        for index, nodo_id in enumerate(ids)
    }


def _arista(origen, destino, distancia, medios=None, bloqueada=False):
    return Arista(
        origen,
        destino,
        distancia,
        frozenset(medios or {MedioPermitido.PIE}),
        bloqueada,
    )


def test_ruta_mas_corta_encuentra_camino_simple():
    mundo = Mundo(
        nodos=_nodos("a", "b", "c"),
        aristas={
            ("a", "b"): _arista("a", "b", 3),
            ("b", "c"): _arista("b", "c", 4),
        },
    )

    assert ruta_mas_corta(mundo, "a", "c", MedioPermitido.PIE) == (
        ("a", "b", "c"),
        7.0,
    )


def test_ruta_mas_corta_elige_camino_de_menor_distancia():
    mundo = Mundo(
        nodos=_nodos("a", "b", "c", "d"),
        aristas={
            ("a", "b"): _arista("a", "b", 2),
            ("b", "d"): _arista("b", "d", 5),
            ("a", "c"): _arista("a", "c", 3),
            ("c", "d"): _arista("c", "d", 1),
        },
    )

    assert ruta_mas_corta(mundo, "a", "d", MedioPermitido.PIE) == (
        ("a", "c", "d"),
        4.0,
    )


def test_ruta_mas_corta_rodea_arista_bloqueada():
    mundo = Mundo(
        nodos=_nodos("a", "b", "c"),
        aristas={
            ("a", "b"): _arista("a", "b", 1, bloqueada=True),
            ("a", "c"): _arista("a", "c", 2),
            ("c", "b"): _arista("c", "b", 2),
        },
    )

    assert ruta_mas_corta(mundo, "a", "b", MedioPermitido.PIE) == (
        ("a", "c", "b"),
        4.0,
    )


@pytest.mark.parametrize(
    "aristas",
    [
        {},
        {("a", "b"): _arista("a", "b", 1, medios={MedioPermitido.JEEP})},
    ],
)
def test_ruta_mas_corta_devuelve_none_si_no_hay_camino_o_medio(aristas):
    mundo = Mundo(nodos=_nodos("a", "b"), aristas=aristas)

    assert ruta_mas_corta(mundo, "a", "b", MedioPermitido.PIE) is None


def test_ruta_mas_corta_resuelve_empates_de_forma_determinista():
    mundo = Mundo(
        nodos=_nodos("a", "b", "c", "d"),
        aristas={
            ("a", "c"): _arista("a", "c", 1),
            ("c", "d"): _arista("c", "d", 1),
            ("a", "b"): _arista("a", "b", 1),
            ("b", "d"): _arista("b", "d", 1),
        },
    )

    assert ruta_mas_corta(mundo, "a", "d", MedioPermitido.PIE) == (
        ("a", "b", "d"),
        2.0,
    )


def test_ruta_mas_corta_prefiere_secuencia_lexicografica_en_empate():
    mundo = Mundo(
        nodos=_nodos("a", "b", "c", "z", "destino"),
        aristas={
            ("a", "z"): _arista("a", "z", 1),
            ("z", "destino"): _arista("z", "destino", 9),
            ("a", "b"): _arista("a", "b", 5),
            ("b", "destino"): _arista("b", "destino", 5),
        },
    )

    assert ruta_mas_corta(
        mundo, "a", "destino", MedioPermitido.PIE,
    ) == (("a", "b", "destino"), 10.0)


def test_ruta_mas_corta_origen_igual_destino():
    mundo = Mundo(nodos=_nodos("a"))

    assert ruta_mas_corta(mundo, "a", "a", MedioPermitido.PIE) == (
        ("a",),
        0.0,
    )


def test_ruta_mas_corta_respeta_aristas_dirigidas():
    mundo = Mundo(
        nodos=_nodos("a", "b"),
        aristas={("a", "b"): _arista("a", "b", 1)},
    )

    assert ruta_mas_corta(mundo, "b", "a", MedioPermitido.PIE) is None


def test_ruta_mas_corta_rechaza_nodos_inexistentes():
    mundo = Mundo(nodos=_nodos("a"))

    with pytest.raises(ErrorDominio, match="no existe"):
        ruta_mas_corta(mundo, "ausente", "a", MedioPermitido.PIE)
