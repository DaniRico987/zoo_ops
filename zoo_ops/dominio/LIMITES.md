# Límites y decisiones de diseño del núcleo de dominio zoo_ops

## (a) Lo que el lenguaje no garantiza

**Mundo mutable por convención**: `Mundo` no es `frozen=True` (se quitó intencionadamente). Sus colecciones internas (`dict`, `list`) son mutables. La inmutabilidad de las entidades (`frozen=True`) protege la identidad de cada entidad, pero el contenedor `Mundo` es un agregado mutable por diseño. Todas las mutaciones DEBEN canalizarse por los métodos de `Mundo` (`sustituir_entidad`, `agregar_entidad`, `eliminar_entidad`, `obtener_entidad`). No hay garantía del lenguaje que impida `mundo.cuidadores["c1"] = ...` directamente.

**`replace(..., estado=...)` y `replace(..., cuidadores_asignados=...)` vigilados por prueba estática**: el uso de `dataclasses.replace` con esos campos fuera de `eventos.py` está prohibido por convención. La prueba estática AST `test_ast_no_se_cambian_campos_de_estado_con_replace` (en `tests/dominio/test_hypothesis.py`) analiza `zoo_ops/dominio/` y `tests/dominio/` y falla si detecta esas llamadas fuera de `eventos.py`. Es una convención vigilada por test, no una garantía del lenguaje.

**Límites de la prueba AST**: la prueba no detecta `replace(..., **kwargs)` cuando el campo prohibido viaja dentro del diccionario, ni la construcción directa de entidades pasando `estado=` (o `cuidadores_asignados=`) al constructor, ni llamadas directas a `Mundo.sustituir_entidad` (o a otros métodos de mutación de `Mundo`) desde fuera de `eventos.py`. Esas vías siguen dependiendo de revisión y convención.

**`cuidadores_asignados` como dato histórico**: el campo se conserva en estados terminales (`COMPLETADA`, `FALLIDA`, `CANCELADA`) y no se limpia automáticamente. Volver a `PENDIENTE` lo vacía. INV-3 solo cuenta tareas en estados activos (`ASIGNADA`, `EN_CURSO`, `PAUSADA`), por lo que esas tareas terminales no bloquean a los cuidadores.

**RegistroReservas sin singleton**: no hay estado global. El registro se crea y se pasa explícitamente por parámetro (inyección de dependencias).

**Mutación y `reconstruir_estado`**: `aplicar_evento` muta el `Mundo` recibido. Por eso `reconstruir_estado` parte de `copy.deepcopy(estado_inicial)`; el llamador conserva el mundo inicial intacto, pero debe saber que el mundo devuelto es una copia nueva, no el mismo objeto.

## (b) INV-4, INV-5 e INV-7 no verificadas por defecto

**INV-4 (capacidad vehículo)**: requiere plan de ejecución (cuidadores asignados, vehículo seleccionado, ruta planeada), que se definirá con el motor de asignación. La implementación actual era una aproximación y podía dar falsos positivos/negativos. Se reporta en `no_verificadas`.

**INV-5 (jeep en aristas válidas)**: requiere seguimiento de la ruta real, que pertenece al motor de asignación. Se reporta en `no_verificadas`.

**INV-7 (mundo vivo == reconstruido)**: `verificar_invariantes` solo puede comprobarla si el llamador aporta el estado inicial (`estado_inicial=`); el estado inicial no puede inferirse del estado vivo. Si se pasa `registro_eventos` sin `estado_inicial`, INV-7 aparece en `no_verificadas` en lugar de dar un resultado falso.

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
| Tarea | `prioridad_base`, `urgencia`, `nodo_destino`, `duracion_estimada`, `habilidades_requeridas`, `certificaciones_requeridas`, `recursos_requeridos`, `ventana_tiempo`, `dependencias`, `interrumpible`, `incidente_origen` | Datos de planificación estáticos; no hay evento que los cambie |
| Incidente | `tareas_generadas`, `animal_relacionado`, `ubicacion`, `tipo`, `severidad` | No hay evento que los cambie; solo `estado` es reconstruible |
| Recinto | `estado`, `especies_admitidas`, `capacidad`, `tipo` | `aplicar_evento` no soporta `CAMBIO_ESTADO` para `Recinto` |
| Nodo / Arista | Todos sus campos, incluido `Arista.bloqueada` | No hay eventos de grafo |
| Sensor | Todos sus campos | No hay eventos de sensor; solo `LECTURA_SENSOR` añade lecturas |
| Mundo | `lecturas` (solo por `LECTURA_SENSOR`), `tiempo_actual` (se fija al `momento` del evento) | El resto de colecciones solo cambia por creación/eliminación, que no se reconstruyen |

**Campos extra sí reproducibles**: `Animal.ubicacion` cuando la transición es `EN_RECINTO` (vía `recinto_destino`) y `Tarea.cuidadores_asignados` en `ASIGNADA` / `PENDIENTE` (vía `datos_extra["cuidadores_ids"]`). Son los únicos campos que un `CAMBIO_ESTADO` escribe además de `estado`.

**Atomicidad por entidad, no por operación compuesta**: `ejecutar_transicion` es atómica para una entidad y un evento: valida antes de mutar y revierte la entidad y el reloj si `RegistroEventos.anexar` falla. Pero asignar una tarea implica varias transiciones (tarea, cuidador, vehículo) y reservas que hoy son llamadas separadas. No existe todavía una transacción que abarque todas ellas; se resolverá con una operación compuesta en el motor de asignación.

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

## (e) Reservas

`reservar_para_tarea(mundo, registro, tarea, paquete)` no construye el paquete: lo recibe ya creado (normalmente con `crear_reservas_para_tarea`). Extrae los IDs por `TipoRecurso`, comprueba que todas las reservas pertenecen a `tarea.id`, rechaza más de un cuidador o vehículo, valida habilidades/certificaciones/estados con `validar_recursos_para_tarea` y delega en `reservar_atomico`. `validar_recursos_para_tarea` recibe solo un `Mundo` y exige que el cuidador propuesto esté `DISPONIBLE`. Un paquete vacío es no-op solo si la tarea no declara recursos ni certificaciones requeridas; si declara alguno de los dos, se rechaza con `RecursosInvalidos`.

La firma vigente es esa, sin `desde`/`hasta`, porque el intervalo se fija una sola vez al construir el paquete con `crear_reservas_para_tarea`, que exige ambos valores y rechaza el intervalo invertido o vacío. Así `reservar_para_tarea` no puede reconstruir reservas con valores por defecto (por ejemplo, `0`) ni aceptar un intervalo distinto del que ya validó el llamador; además, la misma lista se puede inspeccionar antes de reservar y se delega en `reservar_atomico` sin duplicar la construcción.

`Reserva` ya validaba `desde < hasta` con `ReservaInvalida` antes de esta ronda; se mantiene. `crear_reservas_para_tarea` exige `desde` y `hasta` sin valores por defecto y rechaza el intervalo invertido o vacío. Como `reservar_para_tarea` recibe el paquete, no tiene parámetros `desde`/`hasta` que puedan quedar a 0 por defecto: el intervalo se fija al construir el paquete.

`reservar_atomico` comprueba solapamiento intra-paquete, disponibilidad contra el registro e inserta con rollback si una inserción falla. El rollback elimina las reservas ya insertadas mediante `RegistroReservas.eliminar_reserva`.

## (f) Dudas abiertas

1. **EN_TRASLADO sin destino**: la transición `Animal.EN_TRASLADO` no exige `recinto_destino`. El destino se determina en el plan de ejecución. Pendiente decidir si debe validarse aquí.
2. **EN_CLINICA y INV-6**: `EN_CLINICA` tampoco exige recinto destino; la especificación solo menciona `EN_RECINTO`.
3. **Estado del cuidador al asignar**: tanto la transición a `ASIGNADA` como `validar_recursos_para_tarea` exigen `DISPONIBLE`.
4. **Limpiar `cuidadores_asignados` al cancelar**: el campo solo se limpia al volver a `PENDIENTE`. En `CANCELADA` queda con los últimos cuidadores como dato histórico; como `CANCELADA` no es un estado activo, INV-3 no se ve afectada.
5. **`LECTURA_SENSOR`**: se asume `entidad_tipo == "Sensor"` y `datos_extra["valor"]` numérico. La unidad y la calidad de la lectura no se modelan.
6. **Reconstrucción de `CREACION_ENTIDAD`**: para reconstruir desde un mundo vacío haría falta una factoría por tipo de entidad. Hoy se parte de un mundo inicial que ya contiene las entidades.
7. **Paquetes de reserva con varios cuidadores**: la tarea y su transición a `ASIGNADA` ya admiten varios cuidadores, sujetos a `personas_minimas` y a la disponibilidad individual. `reservar_para_tarea` sigue rechazando paquetes con más de un cuidador; esa restricción se levantará en la siguiente entrega. `Especie.minimo_personas_traslado` todavía no se consume y se resolverá con el plan de ejecución.
8. **IDs de evento duplicados**: `RegistroEventos.anexar` los rechaza con `EventoDuplicado` y `ejecutar_transicion` valida antes de mutar. `reconstruir_estado` sigue aceptando una lista arbitraria de eventos; si el llamador construye eventos a mano con el mismo ID, el orden por `(momento, id)` queda indefinido.
9. **Vínculo del incidente con el animal**: se reutiliza `Incidente.animal_relacionado` en lugar de añadir un campo `animal_id` duplicado. No se valida al crear el incidente; al cerrar un incidente de escape se exige que exista y que el animal esté `EN_RECINTO`. Pendiente decidir si la obligatoriedad debe imponerse también en la creación.
10. **Tareas del incidente**: para cerrar se considera la unión sin duplicados de `Incidente.tareas_generadas` y las tareas cuyo `incidente_origen` coincide con el ID del incidente.
11. **Paquete vacío y habilidades**: el rechazo del paquete vacío solo mira `recursos_requeridos` y `certificaciones_requeridas`, según lo pedido. No mira `habilidades_requeridas`; pendiente decidir si una tarea que solo declara habilidades también debe exigir un cuidador en el paquete.
12. **Alcance de `validar_recursos_para_tarea`**: valida los recursos presentes en el paquete, pero no comprueba que este cubra todos los requisitos de la tarea. Por ejemplo, acepta un paquete que solo incluye equipo aunque la tarea exija un cuidador certificado. Tampoco valida la certificación requerida por el vehículo si el paquete no incluye cuidador.
13. **Estado de Equipo**: `Equipo.estado` usa `EstadoEquipo`, pero todavía no hay una máquina de estados para Equipo.
14. **Requisitos de habilidad en equipos**: INV-1 verifica habilidades y certificaciones de cada cuidador asignado por separado; no combina las capacidades del equipo para cubrir en conjunto los requisitos de una tarea.
