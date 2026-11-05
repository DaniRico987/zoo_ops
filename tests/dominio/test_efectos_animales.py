"""Pruebas de aplicación transaccional de efectos de tareas sobre animales."""

import copy

import pytest

from zoo_ops.dominio.catalogos import ESPECIES_CATALOGO
from zoo_ops.dominio.entidades import (
    Animal, Arista, Cuidador, EfectoAnimal, Mundo, Nodo, Recinto, Tarea,
    Vehiculo,
)
from zoo_ops.dominio.enums import (
    Certificacion, EstadoAnimal, EstadoCuidador, EstadoTarea, EstadoVehiculo,
    MedioPermitido, TipoNodo, TipoRecinto, TipoVehiculo,
)
from zoo_ops.dominio.errores import ErrorDominio
from zoo_ops.dominio.eventos import (
    RegistroEventos, reconstruir_estado, verificar_reconstruccion,
)
from zoo_ops.dominio.invariantes import verificar_invariantes
from zoo_ops.dominio.operaciones import (
    asignar_plan, completar_plan, fallar_plan, iniciar_ejecucion,
    llegar_a_destino,
)
from zoo_ops.dominio.plan import PlanEjecucion
from zoo_ops.dominio.reservas import RegistroReservas
from zoo_ops.dominio.entidades import MomentoEfecto


def _mundo(estado_animal=EstadoAnimal.TRANQUILIZADO, efectos=None):
    especie_id = "jaguar"
    especie = ESPECIES_CATALOGO[especie_id]
    return Mundo(
        animales={
            "a1": Animal(
                "a1", especie, "r1", "n1", estado=estado_animal,
            ),
        },
        recintos={
            "r1": Recinto(
                "r1", TipoRecinto.ABIERTO,
                especies_admitidas=frozenset({especie_id}),
            ),
        },
        cuidadores={
            "c1": Cuidador(
                "c1", "Cuidador",
                certificaciones=frozenset({Certificacion.CAMION_TRASLADO}),
                ubicacion=("garaje",),
                estado=EstadoCuidador.DISPONIBLE,
            ),
        },
        vehiculos={
            "v1": Vehiculo(
                "v1", TipoVehiculo.CAMION_TRASLADO, 10.0, 2, 1,
                Certificacion.CAMION_TRASLADO, "garaje",
                estado=EstadoVehiculo.DISPONIBLE,
            ),
        },
        tareas={
            "t1": Tarea(
                "t1", "traslado", nodo_destino="destino",
                vehiculo_requerido=TipoVehiculo.CAMION_TRASLADO,
                efectos=tuple(efectos or ()),
            ),
        },
        nodos={
            "garaje": Nodo("garaje", TipoNodo.GARAJE, 0, 0),
            "destino": Nodo("destino", TipoNodo.RECINTO, 1, 1),
        },
        aristas={
            ("garaje", "destino"): Arista(
                "garaje", "destino", 10,
                frozenset({MedioPermitido.JEEP}),
            ),
        },
    )


def _efecto(estado, momento, recinto_destino=None, animal_id="a1"):
    return EfectoAnimal(
        animal_id, estado, momento, recinto_destino=recinto_destino,
    )


def _plan():
    return PlanEjecucion(
        tarea_id="t1",
        cuidadores=("c1",),
        desde=5,
        hasta=100,
        vehiculo_id="v1",
        ruta=("garaje", "destino"),
        animales_transportados=("a1",),
    )


def _preparar(
    estado_animal=EstadoAnimal.TRANQUILIZADO,
    efectos=None,
    hasta="asignada",
):
    inicial = _mundo(estado_animal, efectos)
    mundo = copy.deepcopy(inicial)
    eventos = RegistroEventos()
    reservas = RegistroReservas()
    asignar_plan(mundo, eventos, reservas, _plan(), 1, "asignar")
    if hasta in {"iniciada", "llegada", "completada"}:
        iniciar_ejecucion(mundo, eventos, reservas, "t1", 5, "iniciar")
    if hasta in {"llegada", "completada"}:
        llegar_a_destino(mundo, eventos, reservas, "t1", 6, "llegar")
    if hasta == "completada":
        completar_plan(mundo, eventos, reservas, "t1", 7, "completar")
    return inicial, mundo, eventos, reservas


def _assert_sin_violaciones(mundo, reservas):
    violaciones, _ = verificar_invariantes(mundo, reservas)
    assert violaciones == []


class _RegistroConFallo(RegistroEventos):
    def __init__(self, fallo_en=None):
        super().__init__()
        self.llamadas = 0
        self.fallo_en = fallo_en

    def anexar(self, evento):
        self.llamadas += 1
        if self.llamadas == self.fallo_en:
            raise RuntimeError(f"fallo de anexo {self.fallo_en}")
        super().anexar(evento)


def test_efectos_de_inicio_y_completado_actualizan_animal_y_reconstruyen():
    efectos = (
        _efecto(EstadoAnimal.EN_TRASLADO, MomentoEfecto.AL_INICIAR),
        _efecto(
            EstadoAnimal.EN_RECINTO, MomentoEfecto.AL_COMPLETAR, "r1",
        ),
    )
    inicial, mundo, eventos, reservas = _preparar(
        EstadoAnimal.TRANQUILIZADO, efectos,
    )

    iniciar_ejecucion(mundo, eventos, reservas, "t1", 5, "iniciar")
    assert mundo.animales["a1"].estado == EstadoAnimal.EN_TRASLADO
    _assert_sin_violaciones(mundo, reservas)
    llegar_a_destino(mundo, eventos, reservas, "t1", 6, "llegar")
    completar_plan(mundo, eventos, reservas, "t1", 7, "completar")

    assert mundo.animales["a1"].estado == EstadoAnimal.EN_RECINTO
    assert mundo.animales["a1"].ubicacion == "r1"
    assert verificar_reconstruccion(
        mundo, reconstruir_estado(eventos.obtener_todos(), inicial)
    ) == []

def test_varios_efectos_secuenciales_sobre_el_mismo_animal():
    efectos = (
        _efecto(EstadoAnimal.TRANQUILIZADO, MomentoEfecto.AL_INICIAR),
        _efecto(EstadoAnimal.EN_TRASLADO, MomentoEfecto.AL_INICIAR),
    )
    _, mundo, eventos, reservas = _preparar(
        EstadoAnimal.LOCALIZADO, efectos,
    )

    iniciar_ejecucion(mundo, eventos, reservas, "t1", 5, "iniciar")

    assert mundo.animales["a1"].estado == EstadoAnimal.EN_TRASLADO
    estados = [
        evento.estado_despues for evento in eventos
        if evento.entidad_tipo == "Animal"
    ]
    assert estados == ["TRANQUILIZADO", "EN_TRASLADO"]


def test_fallar_plan_no_aplica_efectos_animales():
    efectos = (
        _efecto(EstadoAnimal.EN_TRASLADO, MomentoEfecto.AL_INICIAR),
        _efecto(
            EstadoAnimal.EN_RECINTO, MomentoEfecto.AL_COMPLETAR, "r1",
        ),
    )
    _, mundo, eventos, reservas = _preparar(
        EstadoAnimal.TRANQUILIZADO, efectos, hasta="llegada",
    )

    fallar_plan(mundo, eventos, reservas, "t1", 7, "fallar")

    assert mundo.animales["a1"].estado == EstadoAnimal.EN_TRASLADO
    assert mundo.tareas["t1"].estado == EstadoTarea.FALLIDA
    _assert_sin_violaciones(mundo, reservas)


@pytest.mark.parametrize(
    ("estado_animal", "animal_id", "estado_destino", "momento"),
    [
        (EstadoAnimal.TRANQUILIZADO, "ausente", EstadoAnimal.EN_TRASLADO,
         MomentoEfecto.AL_INICIAR),
        (EstadoAnimal.ESCAPADO, "a1", EstadoAnimal.EN_TRASLADO,
         MomentoEfecto.AL_INICIAR),
    ],
)
def test_efecto_imposible_se_rechaza_sin_mutar_ni_consumir_ids(
    estado_animal, animal_id, estado_destino, momento,
):
    efectos = (_efecto(estado_destino, momento, animal_id=animal_id),)
    _, mundo, eventos, reservas = _preparar(
        estado_animal, efectos, hasta="asignada",
    )
    mundo_antes = mundo.instantanea()
    eventos_antes = eventos.instantanea()
    reservas_antes = reservas.instantanea()

    with pytest.raises(ErrorDominio):
        iniciar_ejecucion(mundo, eventos, reservas, "t1", 5, "iniciar")

    assert mundo == mundo_antes
    assert eventos.instantanea() == eventos_antes
    assert reservas.instantanea() == reservas_antes


def test_prevalida_toda_la_secuencia_de_efectos_para_un_animal():
    efectos = (
        _efecto(EstadoAnimal.TRANQUILIZADO, MomentoEfecto.AL_INICIAR),
        _efecto(EstadoAnimal.EN_CLINICA, MomentoEfecto.AL_INICIAR),
    )
    _, mundo, eventos, reservas = _preparar(
        EstadoAnimal.LOCALIZADO, efectos,
    )
    mundo_antes = mundo.instantanea()
    eventos_antes = eventos.instantanea()
    reservas_antes = reservas.instantanea()

    with pytest.raises(ErrorDominio, match="Animal:a1"):
        iniciar_ejecucion(mundo, eventos, reservas, "t1", 5, "iniciar")

    assert mundo == mundo_antes
    assert eventos.instantanea() == eventos_antes
    assert reservas.instantanea() == reservas_antes


def test_regla_extra_de_tranquilizante_se_valida_antes_de_mutar():
    efectos = (
        _efecto(EstadoAnimal.EN_TRASLADO, MomentoEfecto.AL_INICIAR),
    )
    _, mundo, eventos, reservas = _preparar(
        EstadoAnimal.LOCALIZADO, efectos,
    )
    mundo_antes = mundo.instantanea()
    eventos_antes = eventos.instantanea()
    reservas_antes = reservas.instantanea()

    with pytest.raises(ErrorDominio, match="tranquilizante"):
        iniciar_ejecucion(mundo, eventos, reservas, "t1", 5, "iniciar")

    assert mundo == mundo_antes
    assert eventos.instantanea() == eventos_antes
    assert reservas.instantanea() == reservas_antes


def test_efecto_al_completar_imposible_deja_recursos_en_uso_y_permite_fallar():
    efectos = (
        _efecto(
            EstadoAnimal.EN_TRASLADO, MomentoEfecto.AL_COMPLETAR,
        ),
    )
    _, mundo, eventos, reservas = _preparar(
        EstadoAnimal.ESCAPADO, efectos, hasta="llegada",
    )
    mundo_antes = mundo.instantanea()
    eventos_antes = eventos.instantanea()
    reservas_antes = reservas.instantanea()

    with pytest.raises(ErrorDominio):
        completar_plan(mundo, eventos, reservas, "t1", 7, "completar")

    assert mundo == mundo_antes
    assert mundo.vehiculos["v1"].estado == EstadoVehiculo.EN_USO
    assert eventos.instantanea() == eventos_antes
    assert reservas.instantanea() == reservas_antes

    fallar_plan(mundo, eventos, reservas, "t1", 7, "fallar")

    assert mundo.vehiculos["v1"].estado == EstadoVehiculo.DISPONIBLE
    assert mundo.animales["a1"].estado == EstadoAnimal.ESCAPADO
    assert reservas.obtener_reservas_de_tarea("t1") == []


def test_recinto_no_admitido_rechaza_efecto_de_completado_sin_mutar():
    efectos = (
        _efecto(
            EstadoAnimal.EN_RECINTO, MomentoEfecto.AL_COMPLETAR, "incompatible",
        ),
    )
    _, mundo, eventos, reservas = _preparar(
        EstadoAnimal.EN_TRASLADO, efectos, hasta="llegada",
    )
    mundo.recintos["incompatible"] = Recinto(
        "incompatible", TipoRecinto.ABIERTO, especies_admitidas=frozenset(),
    )
    mundo_antes = mundo.instantanea()
    eventos_antes = eventos.instantanea()
    reservas_antes = reservas.instantanea()

    with pytest.raises(ErrorDominio, match="no admite"):
        completar_plan(mundo, eventos, reservas, "t1", 7, "completar")

    assert mundo == mundo_antes
    assert eventos.instantanea() == eventos_antes
    assert reservas.instantanea() == reservas_antes


@pytest.mark.parametrize(
    ("operacion", "fallo_en"),
    [
        ("iniciar", indice) for indice in range(1, 5)
    ] + [
        ("completar", indice) for indice in range(1, 5)
    ],
)
def test_fallo_en_cada_anexo_restaura_operacion_completa(
    operacion, fallo_en,
):
    efectos = (
        _efecto(EstadoAnimal.EN_TRASLADO, MomentoEfecto.AL_INICIAR),
        _efecto(
            EstadoAnimal.EN_RECINTO, MomentoEfecto.AL_COMPLETAR, "r1",
        ),
    )
    fase = "asignada" if operacion == "iniciar" else "llegada"
    _, mundo, registro_base, reservas = _preparar(
        EstadoAnimal.TRANQUILIZADO, efectos, hasta=fase,
    )
    eventos = _RegistroConFallo()
    eventos.restaurar(registro_base.instantanea())
    mundo_antes = mundo.instantanea()
    eventos_antes = eventos.instantanea()
    reservas_antes = reservas.instantanea()
    eventos.fallo_en = fallo_en

    funcion = iniciar_ejecucion if operacion == "iniciar" else completar_plan
    tiempo = 5 if operacion == "iniciar" else 7
    with pytest.raises(RuntimeError, match=f"fallo de anexo {fallo_en}"):
        funcion(mundo, eventos, reservas, "t1", tiempo, "fallo")

    assert mundo == mundo_antes
    assert eventos.instantanea() == eventos_antes
    assert reservas.instantanea() == reservas_antes


def test_ciclo_con_efectos_reconstruible_y_sin_violaciones_tras_cada_paso():
    efectos = (
        _efecto(EstadoAnimal.EN_TRASLADO, MomentoEfecto.AL_INICIAR),
        _efecto(
            EstadoAnimal.EN_RECINTO, MomentoEfecto.AL_COMPLETAR, "r1",
        ),
    )
    inicial, mundo, eventos, reservas = _preparar(
        EstadoAnimal.TRANQUILIZADO, efectos,
    )

    _assert_sin_violaciones(mundo, reservas)
    iniciar_ejecucion(mundo, eventos, reservas, "t1", 5, "iniciar")
    _assert_sin_violaciones(mundo, reservas)
    llegar_a_destino(mundo, eventos, reservas, "t1", 6, "llegar")
    _assert_sin_violaciones(mundo, reservas)
    completar_plan(mundo, eventos, reservas, "t1", 7, "completar")
    _assert_sin_violaciones(mundo, reservas)

    assert mundo.animales["a1"].estado == EstadoAnimal.EN_RECINTO
    assert mundo.animales["a1"].ubicacion == "r1"
    reconstruido = reconstruir_estado(eventos.obtener_todos(), inicial)
    assert verificar_reconstruccion(mundo, reconstruido) == []
