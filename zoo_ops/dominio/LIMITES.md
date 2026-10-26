# Límites y decisiones de diseño del núcleo de dominio zoo_ops

## (a) Lo que el lenguaje no garantiza

**Mundo mutable por convención**: `Mundo` no es `frozen=True` (se quitó intencionadamente). Sus colecciones internas (`dict`, `list`) son mutables. La inmutabilidad de las entidades (`frozen=True`) protege la identidad de cada entidad, pero el contenedor `Mundo` es un agregado mutable por diseño. Todas las mutaciones DEBEN canalizarse por los métodos de `Mundo` (`sustituir_entidad`, `agregar_entidad`, `eliminar_entidad`, `obtener_entidad`). No hay garantía del lenguaje que impida `mundo.cuidadores["c1"] = ...` directamente.

**`replace(..., estado=...)` y `replace(..., cuidadores_asignados=...)` vigilados por prueba estática**: el uso de `dataclasses.replace` con esos campos fuera de `eventos.py` está prohibido por convención. La prueba estática AST `test_ast_no_se_cambian_campos_de_estado_con_replace` (en `tests/dominio/test_hypothesis.py`) analiza `zoo_ops/dominio/` y `tests/dominio/` y falla si detecta esas llamadas fuera de `eventos.py`. Es una convención vigilada por test, no una garantía del lenguaje.

**Límites de la prueba AST**: la prueba no detecta `replace(..., **kwargs)` cuando el campo prohibido viaja dentro del diccionario, ni la construcción directa de entidades pasando `estado=` (o `cuidadores_asignados=`) al constructor, ni llamadas directas a `Mundo.sustituir_entidad` (o a otros métodos de mutación de `Mundo`) desde fuera de `eventos.py`. Esas vías siguen dependiendo de revisión y convención.

**`cuidadores_asignados` como dato histórico**: el campo se conserva en estados terminales (`COMPLETADA`, `FALLIDA`, `CANCELADA`) y no se limpia automáticamente. Volver a `PENDIENTE` lo vacía. INV-3 solo cuenta tareas en estados activos (`ASIGNADA`, `EN_CURSO`, `PAUSADA`), por lo que esas tareas terminales no bloquean a los cuidadores.

**RegistroReservas sin singleton**: no hay estado global. El registro se crea y se pasa explícitamente por parámetro (inyección de dependencias).

**Mutación y `reconstruir_estado`**: `aplicar_evento` muta el `Mundo` recibido. Por eso `reconstruir_estado` parte de `copy.deepcopy(estado_inicial)`; el llamador conserva el mundo inicial intacto, pero debe saber que el mundo devuelto es una copia nueva, no el mismo objeto.

## (b) INV-4, INV-5 e INV-7

**INV-4 (capacidad del vehículo)** y **INV-5 (ruta terrestre)** se verifican a partir de `Mundo.planes`. Las tareas activas que aún no tienen plan aparecen en `no_verificadas` para ambas invariantes; se resolverá al introducir la operación compuesta de la entrega 1c. Los planes con referencias a vehículos ausentes generan violaciones, y INV-9 comprueba todas las referencias de planes.

**INV-7 (mundo vivo == reconstruido)**: `verificar_invariantes` solo puede comprobarla si el llamador aporta el estado inicial (`estado_inicial=`); el estado inicial no puede inferirse del estado vivo. Si se pasa `registro_eventos` sin `estado_inicial`, INV-7 aparece en `no_verificadas` en lugar de dar un resultado falso.

**Simplificación del plan**: se asume que todo el equipo de cuidadores viaja en el vehículo seleccionado. La ruta terrestre comienza en la ubicación actual del vehículo y no incluye un tramo de recogida de cuidadores. `MedioPermitido.JEEP` representa la red vial utilizada por cualquier vehículo terrestre, incluido el camión; el helicóptero no requiere ruta.

## (c) Cambios de entidad que NO generan evento (no reconstruibles)

Solo `CAMBIO_ESTADO` escribe campos de entidad, y únicamente en `Cuidador`, `Animal`, `Vehiculo`, `Tarea` e `Incidente`. Además de `estado`, solo escribe `ubicacion` (Animal) y `cuidadores_asignados` (Tarea; el evento usa `cuidadores_ids`). Todo lo demás que cambie fuera de esos eventos no es reproducible por `reconstruir_estado`:

| Entidad | Campo(s) no reconstruible(s) | Motivo |
|---------|------------------------------|--------|
| Cuidador | `ubicacion`, `fatiga` | Movimiento y simulación continua; no hay evento de movimiento |
| Cuidador | `nombre`, `habilidades`, `certificaciones`, `velocidad_base`, `turno` | Datos estáticos; si se mutan directamente, no hay evento |
| Animal | `ubicacion` salvo transición a `EN_RECINTO` | El movimiento por nodos/aristas no genera evento |
| Animal | `salud` (peso, consumo, actividad), `recinto_origen`, `especie` | Salud continua y datos estáticos |
| Vehiculo | `ubicacion` | Movimiento no genera evento `CAMBIO_ESTADO` |
| Vehiculo | `tipo`, `velocidad`, `capacidad_personas`, `capacidad_animales`, `certificacion_requerida` | Datos estáticos |
| Equipo | `estado`, `ubicacion`, `tipo` | `aplicar_evento` no soporta `CAMBIO_ESTADO` para `Equipo` |
| Tarea | `cuidadores_asignados` fuera de `ASIGNADA` / vuelta a `PENDIENTE` | Solo esas transiciones lo escriben |
| Tarea | `personas_minimas` | Dato de planificación estático; no hay evento que lo cambie |
| Tarea | `prioridad_base`, `urgencia`, `nodo_destino`, `duracion_estimada`, `habilidades_requeridas`, `certificaciones_requeridas`, `vehiculo_requerido`, `equipos_requeridos`, `ventana_tiempo`, `dependencias`, `interrumpible`, `incidente_origen` | Datos de planificación estáticos; no hay evento que los cambie |
| Mundo | `planes` | Los planes se registran en memoria y todavía no generan eventos |
| Incidente | `tareas_generadas`, `animal_relacionado`, `ubicacion`, `tipo`, `severidad` | No hay evento que los cambie; solo `estado` es reconstruible |
| Recinto | `estado`, `especies_admitidas`, `capacidad`, `tipo` | `aplicar_evento` no soporta `CAMBIO_ESTADO` para `Recinto` |
| Nodo / Arista | Todos sus campos, incluido `Arista.bloqueada` | No hay eventos de grafo |
| Sensor | Todos sus campos | No hay eventos de sensor; solo `LECTURA_SENSOR` añade lecturas |
| Mundo | `lecturas` (solo por `LECTURA_SENSOR`), `tiempo_actual` (se fija al `momento` del evento) | El resto de colecciones solo cambia por creación/eliminación, que no se reconstruyen |

**Campos extra sí reproducibles**: `Animal.ubicacion` cuando la transición es `EN_RECINTO` (vía `recinto_destino`) y `Tarea.cuidadores_asignados` en `ASIGNADA` / `PENDIENTE` (vía `datos_extra["cuidadores_ids"]`). Son los únicos campos que un `CAMBIO_ESTADO` escribe además de `estado`.

**Atomicidad por entidad, no por operación compuesta**: `ejecutar_transicion` es atómica para una entidad y un evento: valida antes de mutar y revierte la entidad y el reloj si `RegistroEventos.anexar` falla. La validación y reserva del plan son atómicas respecto al registro de reservas, pero registrar el plan y asignar estados aún no forman una única transacción; se resolverá con la operación compuesta de la entrega 1c.

## (d) Eventos: aplicación y reconstrucción

`aplicar_evento` es la única lógica de aplicación y cubre todos los `TipoEvento`:

- `CAMBIO_ESTADO`: aplica estado + `ubicacion`/`cuidadores_ids` si vienen en `datos_extra` (el último se guarda como `cuidadores_asignados`). Si la entidad o el tipo no existen, o el estado no pertenece al enum, lanza error (`EventoNoSoportado` o `ErrorDominio`); nunca ignora el evento.
- `CREACION_ENTIDAD`: no-op explícito (las entidades ya están en el `Mundo`; no hay factoría).
- `RESERVA_CREADA` / `RESERVA_LIBERADA`: no-op explícito (las reservas viven en `RegistroReservas`, no en `Mundo`).
- `LECTURA_SENSOR`: añade una `Lectura` a `mundo.lecturas` usando `entidad_id` como sensor, `momento` como instante y `datos_extra["valor"]` como valor. Sin `valor` lanza `ErrorDominio`.
- `ELIMINACION_ENTIDAD`, `TAREA_ASIGNADA`, `TAREA_DESASIGNADA`, `INCIDENTE_GENERADO`, `TICK_RELOJ`: no-op explícito en `aplicar_evento`.

`reconstruir_estado` **rechaza** con `EventoNoSoportado` los cinco tipos de la última lista (`EVENTOS_NO_RECONSTRUIBLES`). Los demás se reproducen con `aplicar_evento`. No hay parámetro `aplicadores`: la reconstrucción no admite lógica personalizada, precisamente para que no existan dos verdades.

**El tiempo se fija al momento del último evento aplicado** (`mundo.tiempo_actual = evento.momento`), no se incrementa.

`RegistroEventos.anexar` rechaza eventos con un ID ya presente mediante `EventoDuplicado` y mantiene `_ultimo_id_evento` al menos en el máximo ID anexado. `siguiente_id_evento` incrementa ese contador, así que crear un evento tras anexar manualmente el ID 5 produce el ID 6. `ejecutar_transicion` valida esa condición antes de mutar el mundo y revierte entidad y reloj si el anexo falla por otra causa.

**Huecos en la numeración de IDs**: si `validar_anexo` o `anexar` rechaza una transición, el ID ya fue consumido al crear el evento y puede quedar un hueco. El orden determinista por `(momento, id)` no se ve afectado.

## (e) Reservas

`paquete_de_reservas(plan)` construye una reserva por cada cuidador, por el vehículo si se especifica, y por cada equipo, todos en el intervalo `[desde, hasta)` del plan. `reservar_plan(mundo, registro, plan)` resuelve la tarea desde el mundo, exige que `validar_plan` no encuentre errores y luego delega el paquete a `reservar_atomico`; un solapamiento no deja reservas parciales. No registra el plan ni cambia estados; eso se resolverá con la operación compuesta de la entrega 1c.

`PlanEjecucion` exige cuidadores no vacíos y únicos, IDs de equipo y animales únicos, y `hasta > desde`; `desde` y `hasta` son obligatorios. El vehículo y los equipos concretos son opcionales cuando la tarea no los requiere; los requisitos se expresan mediante `vehiculo_requerido` y `equipos_requeridos`. Los requisitos repetidos de un tipo de equipo representan una cantidad mínima. Los animales transportados deben existir y requieren vehículo.

## (f) Dudas abiertas

1. **EN_TRASLADO sin destino**: la transición `Animal.EN_TRASLADO` no exige `recinto_destino`. El destino se determina en el plan de ejecución. Pendiente decidir si debe validarse aquí.
2. **EN_CLINICA y INV-6**: `EN_CLINICA` tampoco exige recinto destino; la especificación solo menciona `EN_RECINTO`.
3. **`Especie.minimo_personas_traslado`**: el plan valida `Tarea.personas_minimas`, pero no deriva automáticamente ese valor desde el mínimo definido para la especie transportada.
4. **Relación entre capacidad animal y transporte**: el plan valida la capacidad animal cuando se especifica vehículo, y los animales transportados requieren vehículo. No se deriva automáticamente `Tarea.vehiculo_requerido` por incluir animales en el plan; queda por definir si la tarea debe exigirlo siempre.
5. **`LECTURA_SENSOR`**: se asume `entidad_tipo == "Sensor"` y `datos_extra["valor"]` numérico. La unidad y la calidad de la lectura no se modelan.
6. **Reconstrucción de `CREACION_ENTIDAD`**: para reconstruir desde un mundo vacío haría falta una factoría por tipo de entidad. Hoy se parte de un mundo inicial que ya contiene las entidades.
7. **Planes y reconstrucción**: los planes se guardan en `Mundo.planes`, pero todavía no generan eventos, así que no se reproducen mediante `reconstruir_estado`.
8. **Vínculo del incidente con el animal**: se reutiliza `Incidente.animal_relacionado` en lugar de añadir un campo `animal_id` duplicado. No se valida al crear el incidente; al cerrar un incidente de escape se exige que exista y que el animal esté `EN_RECINTO`. Pendiente decidir si la obligatoriedad debe imponerse también en la creación.
9. **Tareas del incidente**: para cerrar se considera la unión sin duplicados de `Incidente.tareas_generadas` y las tareas cuyo `incidente_origen` coincide con el ID del incidente.
10. **Estado de Equipo**: `Equipo.estado` usa `EstadoEquipo`, pero todavía no hay una máquina de estados para Equipo.
