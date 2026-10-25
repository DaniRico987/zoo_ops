"""
Pruebas de eventos: inmutabilidad, registro, aplicación y reconstrucción.

`aplicar_evento` es la única lógica de aplicación; `reconstruir_estado` debe
usarla y rechazar explícitamente los eventos no reproducibles.
"""

import copy
from dataclasses import FrozenInstanceError

import pytest

from zoo_ops.dominio.catalogos import ESPECIES_CATALOGO
from zoo_ops.dominio.entidades import Animal, Cuidador, Lectura, Mundo, Tarea
from zoo_ops.dominio.enums import EstadoAnimal, EstadoCuidador, EstadoTarea
from zoo_ops.dominio.errores import ErrorDominio, EventoDuplicado, EventoNoSoportado
from zoo_ops.dominio.eventos import (
    EVENTOS_NO_RECONSTRUIBLES, Evento, RegistroEventos, TipoEvento,
    aplicar_evento, crear_evento, reconstruir_estado, verificar_reconstruccion,
)


def _evento(tipo, entidad_tipo="Cuidador", entidad_id="c1", **kwargs):
    """Construye un Evento con valores por defecto explícitos."""
    datos = dict(
        id=kwargs.pop("id", 1),
        momento=kwargs.pop("momento", 100),
        tipo=tipo,
        entidad_tipo=entidad_tipo,
        entidad_id=entidad_id,
        estado_antes=kwargs.pop("estado_antes", ""),
        estado_despues=kwargs.pop("estado_despues", ""),
        causa=kwargs.pop("causa", "test"),
        datos_extra=kwargs.pop("datos_extra", {}),
    )
    datos.update(kwargs)
    return Evento(**datos)


# ============================================================================
# Evento y registro
# ============================================================================

class TestEvento:
    def test_crear_evento_asigna_id_y_campos(self):
        registro = RegistroEventos()

        evento = crear_evento(
            registro,
            momento=100,
            tipo=TipoEvento.CAMBIO_ESTADO,
            entidad_tipo="Cuidador",
            entidad_id="c1",
            estado_antes="FUERA_DE_TURNO",
            estado_despues="DISPONIBLE",
            causa="inicio turno",
        )

        assert evento.id == 1
        assert evento.momento == 100
        assert evento.estado_antes == "FUERA_DE_TURNO"
        assert evento.estado_despues == "DISPONIBLE"

    def test_evento_es_inmutable(self):
        evento = _evento(TipoEvento.CAMBIO_ESTADO)

        with pytest.raises(FrozenInstanceError):
            evento.momento = 200
        with pytest.raises(FrozenInstanceError):
            evento.causa = "otra"

    def test_datos_extra_se_copian(self):
        registro = RegistroEventos()
        evento = crear_evento(
            registro, 1, TipoEvento.LECTURA_SENSOR, "Sensor", "s1", "", "", "lectura",
            datos_extra={"valor": 25.5},
        )
        assert evento.datos_extra["valor"] == 25.5


class TestRegistroEventos:
    def test_registros_independientes_inician_ids_independientes(self):
        registro_a = RegistroEventos()
        registro_b = RegistroEventos()

        evento_a = crear_evento(
            registro_a, 10, TipoEvento.CAMBIO_ESTADO, "Cuidador", "c1",
            "A", "B", "test",
        )
        evento_b = crear_evento(
            registro_b, 10, TipoEvento.CAMBIO_ESTADO, "Cuidador", "c1",
            "A", "B", "test",
        )

        assert evento_a.id == evento_b.id == 1

    def test_anexar_id_duplicado_falla(self):
        registro = RegistroEventos()
        e1 = _evento(TipoEvento.CAMBIO_ESTADO, id=7)
        e2 = _evento(TipoEvento.CAMBIO_ESTADO, id=7)
        registro.anexar(e1)

        with pytest.raises(EventoDuplicado, match="7"):
            registro.anexar(e2)

        assert len(registro) == 1
        assert registro[0] is e1

    def test_anexar_obtener_e_iterar(self):
        registro = RegistroEventos()
        e1 = crear_evento(registro, 100, TipoEvento.CAMBIO_ESTADO, "Cuidador", "c1", "A", "B", "c")
        e2 = crear_evento(registro, 200, TipoEvento.CAMBIO_ESTADO, "Animal", "a1", "C", "D", "c")

        registro.anexar(e1)
        registro.anexar(e2)

        assert len(registro) == 2
        assert registro[0] is e1
        assert list(registro) == [e1, e2]

    def test_obtener_todos_devuelve_copia(self):
        registro = RegistroEventos()
        registro.anexar(_evento(TipoEvento.CAMBIO_ESTADO))

        copia = registro.obtener_todos()
        copia.append("intruso")

        assert len(registro) == 1

    def test_filtros(self):
        registro = RegistroEventos()
        registro.anexar(crear_evento(registro, 100, TipoEvento.CAMBIO_ESTADO, "Cuidador", "c1", "A", "B", "c"))
        registro.anexar(crear_evento(registro, 150, TipoEvento.RESERVA_CREADA, "Vehiculo", "v1", "", "", "c"))
        registro.anexar(crear_evento(registro, 200, TipoEvento.CAMBIO_ESTADO, "Cuidador", "c1", "B", "C", "c"))

        assert len(registro.obtener_por_entidad("Cuidador", "c1")) == 2
        assert len(registro.obtener_por_tipo(TipoEvento.RESERVA_CREADA)) == 1
        assert len(registro.obtener_desde_momento(150)) == 2


# ============================================================================
# aplicar_evento
# ============================================================================

class TestAplicarEvento:
    def test_cambio_estado_muta_el_mundo(self):
        mundo = Mundo(cuidadores={"c1": Cuidador(id="c1", nombre="C")})
        evento = _evento(
            TipoEvento.CAMBIO_ESTADO,
            estado_antes="FUERA_DE_TURNO",
            estado_despues="DISPONIBLE",
        )

        resultado = aplicar_evento(mundo, evento)

        assert resultado is mundo
        assert mundo.cuidadores["c1"].estado == EstadoCuidador.DISPONIBLE

    def test_cambio_estado_actualiza_campos_extra(self):
        mundo = Mundo(
            tareas={"t1": Tarea(
                id="t1", tipo="test", estado=EstadoTarea.ASIGNADA,
                cuidador_asignado="c1",
            )}
        )
        evento = _evento(
            TipoEvento.CAMBIO_ESTADO, entidad_tipo="Tarea", entidad_id="t1",
            estado_antes="ASIGNADA", estado_despues="PENDIENTE",
            datos_extra={"cuidador_asignado": None},
        )

        aplicar_evento(mundo, evento)

        assert mundo.tareas["t1"].estado == EstadoTarea.PENDIENTE
        assert mundo.tareas["t1"].cuidador_asignado is None

    def test_tipo_de_entidad_desconocido(self):
        with pytest.raises(EventoNoSoportado):
            aplicar_evento(Mundo(), _evento(
                TipoEvento.CAMBIO_ESTADO, entidad_tipo="Planta", entidad_id="p1",
                estado_despues="DISPONIBLE",
            ))

    def test_entidad_inexistente(self):
        with pytest.raises(EventoNoSoportado):
            aplicar_evento(Mundo(), _evento(
                TipoEvento.CAMBIO_ESTADO, entidad_tipo="Cuidador", entidad_id="c_no",
                estado_despues="DISPONIBLE",
            ))

    def test_estado_fuera_del_enum(self):
        mundo = Mundo(cuidadores={"c1": Cuidador(id="c1", nombre="C")})

        with pytest.raises(ErrorDominio, match="no pertenece"):
            aplicar_evento(mundo, _evento(
                TipoEvento.CAMBIO_ESTADO,
                estado_despues="NO_EXISTE",
            ))

    def test_lectura_sensor_agrega_lectura(self):
        mundo = Mundo()
        evento = _evento(
            TipoEvento.LECTURA_SENSOR, entidad_tipo="Sensor", entidad_id="s1",
            momento=42, datos_extra={"valor": 25.5},
        )

        aplicar_evento(mundo, evento)

        assert mundo.lecturas == [Lectura(sensor_id="s1", valor=25.5, momento=42)]

    def test_lectura_sensor_sin_valor_falla(self):
        with pytest.raises(ErrorDominio, match="valor"):
            aplicar_evento(Mundo(), _evento(
                TipoEvento.LECTURA_SENSOR, entidad_tipo="Sensor", entidad_id="s1",
            ))


# ============================================================================
# reconstruir_estado
# ============================================================================

class TestReconstruccion:
    def test_reconstruye_cambios_de_estado(self):
        inicial = Mundo(cuidadores={"c1": Cuidador(id="c1", nombre="C")})
        eventos = [
            _evento(TipoEvento.CAMBIO_ESTADO, estado_despues="DISPONIBLE",
                    momento=100, id=1),
            _evento(TipoEvento.CAMBIO_ESTADO, estado_despues="ASIGNADO",
                    momento=200, id=2),
        ]

        resultado = reconstruir_estado(eventos, inicial)

        assert resultado.cuidadores["c1"].estado == EstadoCuidador.ASIGNADO
        assert resultado.tiempo_actual == 200

    def test_no_muta_el_estado_inicial(self):
        inicial = Mundo(cuidadores={"c1": Cuidador(id="c1", nombre="C")})
        antes = copy.deepcopy(inicial)
        eventos = [_evento(TipoEvento.CAMBIO_ESTADO, estado_despues="DISPONIBLE")]

        reconstruir_estado(eventos, inicial)

        assert inicial == antes
        assert inicial.cuidadores["c1"].estado == EstadoCuidador.FUERA_DE_TURNO

    def test_ordena_por_momento_y_luego_por_id(self):
        inicial = Mundo(cuidadores={"c1": Cuidador(id="c1", nombre="C")})
        e1 = _evento(TipoEvento.CAMBIO_ESTADO, id=1, momento=100, estado_despues="DISPONIBLE")
        e2 = _evento(TipoEvento.CAMBIO_ESTADO, id=2, momento=100, estado_despues="ASIGNADO")

        resultado = reconstruir_estado([e2, e1], inicial)

        assert resultado.cuidadores["c1"].estado == EstadoCuidador.ASIGNADO

    def test_reconstruye_animal_y_ubicacion(self):
        inicial = Mundo(animales={"a1": Animal(
            id="a1", especie=ESPECIES_CATALOGO["jaguar"],
            recinto_origen="rec1", ubicacion="campo",
            estado=EstadoAnimal.EN_CLINICA,
        )})
        evento = _evento(
            TipoEvento.CAMBIO_ESTADO, entidad_tipo="Animal", entidad_id="a1",
            estado_despues="EN_TRASLADO", momento=50,
        )
        evento_ubicacion = _evento(
            TipoEvento.CAMBIO_ESTADO, entidad_tipo="Animal", entidad_id="a1",
            estado_despues="EN_RECINTO", momento=60, id=2,
            datos_extra={"ubicacion": "rec1"},
        )

        resultado = reconstruir_estado([evento, evento_ubicacion], inicial)

        assert resultado.animales["a1"].estado == EstadoAnimal.EN_RECINTO
        assert resultado.animales["a1"].ubicacion == "rec1"

    @pytest.mark.parametrize("tipo", sorted(
        EVENTOS_NO_RECONSTRUIBLES, key=lambda t: t.name
    ))
    def test_rechaza_eventos_no_reconstruibles(self, tipo):
        with pytest.raises(EventoNoSoportado, match=tipo.name):
            reconstruir_estado([_evento(tipo)], Mundo())

    @pytest.mark.parametrize("tipo", [
        TipoEvento.CREACION_ENTIDAD,
        TipoEvento.RESERVA_CREADA,
        TipoEvento.RESERVA_LIBERADA,
    ])
    def test_noops_explicitos(self, tipo):
        evento = _evento(tipo, momento=100)

        resultado = reconstruir_estado([evento], Mundo())

        assert resultado.tiempo_actual == 100
        assert resultado.cuidadores == {}

    def test_cambio_estado_sobre_tipo_desconocido_falla(self):
        with pytest.raises(EventoNoSoportado):
            reconstruir_estado(
                [_evento(TipoEvento.CAMBIO_ESTADO, entidad_tipo="Planta", entidad_id="p1",
                         estado_despues="DISPONIBLE")],
                Mundo(),
            )

    def test_cambio_estado_sobre_id_inexistente_falla(self):
        with pytest.raises(EventoNoSoportado):
            reconstruir_estado(
                [_evento(TipoEvento.CAMBIO_ESTADO, entidad_id="c_no",
                         estado_despues="DISPONIBLE")],
                Mundo(),
            )

    def test_cambio_estado_fuera_del_enum_falla(self):
        inicial = Mundo(cuidadores={"c1": Cuidador(id="c1", nombre="C")})

        with pytest.raises(ErrorDominio, match="no pertenece"):
            reconstruir_estado(
                [_evento(TipoEvento.CAMBIO_ESTADO, estado_despues="NO_EXISTE")],
                inicial,
            )


# ============================================================================
# verificar_reconstruccion
# ============================================================================

class TestVerificarReconstruccion:
    def test_sin_diferencias(self):
        c = Cuidador(id="c1", nombre="C", estado=EstadoCuidador.DISPONIBLE)
        m1 = Mundo(cuidadores={"c1": c}, tiempo_actual=100)
        m2 = Mundo(cuidadores={"c1": c}, tiempo_actual=100)

        assert verificar_reconstruccion(m1, m2) == []

    def test_detecta_entidad_distinta(self):
        m1 = Mundo(cuidadores={"c1": Cuidador(id="c1", nombre="C")})
        m2 = Mundo(cuidadores={"c1": Cuidador(
            id="c1", nombre="C", estado=EstadoCuidador.ASIGNADO,
        )})

        diferencias = verificar_reconstruccion(m1, m2)

        assert any("difieren" in d for d in diferencias)

    def test_detecta_entidades_faltantes_y_sobrantes(self):
        m1 = Mundo(cuidadores={"c1": Cuidador(id="c1", nombre="C")})
        m2 = Mundo(cuidadores={"c2": Cuidador(id="c2", nombre="C")})

        diferencias = verificar_reconstruccion(m1, m2)

        assert any("faltan" in d for d in diferencias)
        assert any("sobran" in d for d in diferencias)

    def test_detecta_tiempo_distinto(self):
        m1 = Mundo(tiempo_actual=100)
        m2 = Mundo(tiempo_actual=200)

        assert any("tiempo_actual" in d for d in verificar_reconstruccion(m1, m2))
