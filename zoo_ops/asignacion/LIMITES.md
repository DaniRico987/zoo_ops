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
