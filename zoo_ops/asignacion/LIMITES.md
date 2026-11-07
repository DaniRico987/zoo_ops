# Límites de las estimaciones de asignación

Las distancias de `Arista` y las velocidades se expresan en las mismas unidades
de distancia por segundo; `segundos_de_viaje` redondea hacia arriba a segundos
enteros. `tiempo_llegada_cuidador` devuelve una duración estimada, no una hora
absoluta; `Estimacion.desde` se establece con el parámetro `ahora`. La
simulación debe iniciar la ejecución en `Estimacion.salida`, registrar la
llegada en `Estimacion.llegada` y completar el plan en `Estimacion.fin`.

Las rutas terrestres usan el grafo dirigido y `MedioPermitido.JEEP` para jeeps
y camiones. La recogida supone que el equipo sube al vehículo en su ubicación:
la espera no mueve a los cuidadores. Los cálculos no contemplan tráfico ni
pausas. El helicóptero vuela en línea recta, ignora el relieve y añade un tiempo
de preparación configurable, de 120 segundos por defecto.

Las ubicaciones de cuidadores sobre una arista no se estiman y producen `None`;
solo se admiten ubicaciones representadas por un nodo. Estas funciones calculan
rutas y tiempos sin mutar el mundo.

Para propuestas de tareas con efectos animales, `animal_id` de los efectos
`EN_TRASLADO` se combina con los animales explícitos de `proponer_planes`, sin
duplicados y en orden determinista; `planificar` deriva la lista desde la tarea.
El vehículo debe estar ya en el punto donde se recoge al animal. No se modelan
recorridos hasta el animal ni puntos de paso en las rutas.

La generación de candidatos solo considera recursos en estado `DISPONIBLE` en
el momento de estimar. Los cuidadores no cambian de ubicación durante la espera
de recogida; se supone que el equipo y los equipos de equipamiento viajan con el
vehículo desde su ubicación. El algoritmo voraz de equipos de cuidadores reduce
el coste de búsqueda cuando se supera `max_combinaciones`, pero no garantiza una
solución óptima; por defecto se enumeran hasta 2000 combinaciones.

Para `n` cuidadores elegibles y equipos de tamaño `k`, la generación enumera
`C(n, k)` combinaciones por opción de vehículo cuando ese número no supera
`max_combinaciones`; en caso contrario usa la construcción voraz. Los descartes
se agregan por motivo y vehículo, con el total de ocurrencias y hasta tres
ejemplos para evitar que la salida crezca con cada combinación.

## Puntaje y propuestas

Los pesos de `EMERGENCIA`, `RUTINA` y `MANTENIMIENTO` son valores iniciales de
diseño y deben afinarse con el simulador. El componente de tiempo se calcula
como `1 / (1 + max(0, t - t_min) / ESCALA_TIEMPO_SEGUNDOS)`, donde `t` es
`llegada - desde`, `t_min` el menor tiempo del conjunto evaluado y la escala
predeterminada es 60 segundos. Al cambiar los candidatos evaluados puede
cambiar `t_min` y, por tanto, el puntaje de tiempo. La carga cuenta solo tareas
`COMPLETADA` o `FALLIDA` que siguen en `mundo.tareas`.

Las propuestas excluyen helicópteros por defecto para perfiles distintos de
`EMERGENCIA`; el perfil de emergencia los permite. Esta política puede
sobrescribirse explícitamente. Un helicóptero exigido por el tipo de tarea se
mantiene como opción independientemente del perfil.

| Perfil | Tiempo | Habilidad | Carga | Fatiga | Continuidad |
|--------|-------:|----------:|------:|-------:|------------:|
| EMERGENCIA | 0.60 | 0.25 | 0.00 | 0.05 | 0.10 |
| RUTINA | 0.15 | 0.20 | 0.30 | 0.20 | 0.15 |
| MANTENIMIENTO | 0.10 | 0.30 | 0.25 | 0.20 | 0.15 |

La continuidad premia cuidadores ya ubicados en el destino o, cuando la tarea
tiene incidente de origen, ya asignados a otra tarea del mismo incidente. Los
componentes no consideran preferencias humanas ni una urgencia creciente. Una
propuesta solo presenta candidatos ordenados y descartes; no confirma ni ejecuta
asignaciones, que requieren confirmación explícita mediante `asignar_plan`.

## Planificación global

La planificación global usa búsqueda determinista porque cada alternativa es
un paquete indivisible de cuidadores, vehículo y equipos, no una pareja
independiente tarea-recurso como en el algoritmo húngaro. La búsqueda maximiza
lexicográficamente primero la suma de pesos de prioridad de las tareas
asignadas (BAJA < MEDIA < ALTA < CRITICA) y después la suma de sus puntajes.

Los niveles se procesan en orden EMERGENCIA, RUTINA y MANTENIMIENTO. Los
recursos comprometidos por niveles anteriores no se preemptan, y las tareas en
curso tampoco se interrumpen. Dentro de cada nivel, las propuestas se calculan
una vez por tarea contra el estado previo al nivel; luego se selecciona el
conjunto sin conflictos y se compromete únicamente en copias del mundo y de las
reservas.

`max_nodos` limita la búsqueda exacta por nivel. Si se supera, ese nivel usa el
baseline voraz, que recorre prioridad descendente, menor número de candidatos
primero e ID, y toma el primer candidato compatible. `nodos_explorados` suma
los nodos examinados en todos los niveles. `max_candidatos_por_tarea` limita el
ranking considerado por la búsqueda; ese recorte puede ocultar alternativas
compatibles. Si aparecen tareas con `recursos_comprometidos` que parezcan
sospechosas, conviene aumentar `max_candidatos_por_tarea`.

## Confirmación y aplicación

El flujo separa proponer de confirmar: `planificar` y `generar_pendientes`
presentan alternativas, y `aplicar_pendientes` solo aplica una alternativa
cuando corresponde. La vigencia se mide en tiempo simulado. Antes de aplicar,
la reprogramación conserva los recursos elegidos y recalcula tiempos y rutas
según el estado actual; por ello una confirmación puede ser rechazada si el
mundo cambió desde que se generó.

Las alternativas se validan y reservan al aplicarse, no al seleccionar el
lote. Por tanto, elegir una alternativa no garantiza que no choque con otra
confirmación del mismo lote: en ese caso se rechaza solo la asignación
conflictiva. No hay preempción de tareas en curso.

Si una tarea de un incidente falla, el incidente no puede cerrarse mientras
esa tarea siga en estado `FALLIDA`; la política de reintento aún no está
definida.
