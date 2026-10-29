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
diseño y deben afinarse con el simulador. El componente de tiempo es relativo
al conjunto de candidatos evaluado: si cambia ese conjunto, pueden cambiar
los componentes y el ranking. La carga cuenta solo tareas `COMPLETADA` o
`FALLIDA` que siguen en `mundo.tareas`.

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
