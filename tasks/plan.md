# Implementation Plan: Correcciones al núcleo de dominio zoo_ops

## Overview
Implementar 9 cambios estructurales al dominio de zoo_ops tras la revisión:
1. Registro de reservas sin estado global (singleton → objeto explícito)
2. Reservas atómicas de verdad (solapamiento intra-paquete, reversión)
3. Dependencias de tarea calculadas por el dominio (sin booleano externo)
4. INV-3 e INV-6 preventivas (rechazo en transición)
5. INV-4 e INV-5 pasan a "no verificadas" (lista separada en verificar_invariantes)
6. Mundo honesto (quitar frozen, métodos de mutación centralizados)
7. Un solo Sensor (eliminar duplicado en catalogos.py)
8. Eventos y reconstrucción sin huecos (EventoNoSoportado, no-op explícitos)
9. Pruebas honestas (mundo vivo solo via aplicar_transicion_*, reconstrucción desde deepcopy inicial, prueba estática AST)

## Architecture Decisions
- RegistroReservas se pasa explícitamente como parámetro (dependency injection)
- Mundo deja de ser frozen y expone métodos `sustituir_entidad`, `agregar_entidad`, `eliminar_entidad`
- verificar_invariantes devuelve tupla (violaciones, no_verificadas)
- Sensor único en entidades.py; catalogos.py usa esa definición
- reconstruir_estado lanza EventoNoSoportado para tipos sin aplicador

## Task List

### Phase 1: Registro de reservas sin estado global
- [ ] Task 1.1: Eliminar `_registro_global`, `obtener_registro()`, `reiniciar_registro()` de reservas.py
- [ ] Task 1.2: Cambiar `reservar_atomico` para recibir `registro: RegistroReservas` como primer parámetro
- [ ] Task 1.3: Actualizar `liberar_reservas_tarea`, `verificar_disponibilidad_recurso`, `crear_reservas_para_tarea`, `validar_recursos_para_tarea` para recibir registro
- [ ] Task 1.4: Actualizar invariantes.py para recibir registro como parámetro
- [ ] Task 1.5: Actualizar tests para crear y pasar RegistroReservas explícitamente

### Phase 2: Reservas atómicas de verdad
- [ ] Task 2.1: Implementar detección de solapamiento intra-paquete en reservar_atomico
- [ ] Task 2.2: Implementar reversión (rollback) si falla inserción
- [ ] Task 2.3: Verificar/añadir validación en `agregar_reserva` para solapamientos
- [ ] Task 2.4: Crear `reservar_para_tarea(mundo, registro, tarea, paquete)` que valida recursos y reserva
- [ ] Task 2.5: Tests: solapamiento intra-paquete, reversión, reservar_para_tarea

### Phase 3: Dependencias de tarea calculadas por el dominio
- [ ] Task 3.1: Cambiar `validar_transicion_tarea_extra` para recibir `mundo` y calcular dependencias
- [ ] Task 3.2: Cambiar `aplicar_transicion_tarea` para recibir `mundo` y pasar a validación
- [ ] Task 3.2: Añadir excepción `DependenciaInexistente` en errores.py
- [ ] Task 3.4: Tests: dependencias válidas, dependencia inexistente

### Phase 4: INV-3 e INV-6 preventivas
- [ ] Task 4.1: Añadir validación en `aplicar_transicion_tarea` para INV-3 (cuidador ya tiene tarea activa)
- [ ] Task 4.2: Añadir validación en `aplicar_transicion_animal` para INV-6 (recinto admite especie)
- [ ] Task 4.3: Actualizar `verificar_invariantes` para mantener verificaciones a posteriori
- [ ] Task 4.4: INV-6: especie no en catálogo → violación/error
- [ ] Task 4.5: Tests: rechazo preventivo INV-3 e INV-6

### Phase 5: INV-4 e INV-5 a "no verificadas"
- [ ] Task 5.1: Cambiar `verificar_invariantes` para devolver tupla (violaciones, no_verificadas)
- [ ] Task 5.2: Mover código INV-4 e INV-5 a lista no_verificadas con motivo
- [ ] Task 5.3: Eliminar funciones `_verificar_invariante_4` y `_verificar_invariante_5`
- [ ] Task 5.4: Tests: verificar que aparecen en no_verificadas

### Phase 6: Mundo honesto
- [ ] Task 6.1: Quitar `frozen=True` de Mundo
- [ ] Task 6.2: Añadir métodos `sustituir_entidad`, `agregar_entidad`, `eliminar_entidad` a Mundo
- [ ] Task 6.3: Actualizar eventos.py y estados.py para usar métodos de Mundo
- [ ] Task 6.4: Tests: mutaciones via métodos de Mundo

### Phase 7: Un solo Sensor
- [ ] Task 7.1: Eliminar clase Sensor de catalogos.py
- [ ] Task 7.2: Ajustar imports en catalogos.py (usar Sensor de entidades)
- [ ] Task 7.3: Cambiar imports en __init__.py a explícitos (sin asterisco)
- [ ] Task 7.4: Ajustar tests para importar Sensor de entidades

### Phase 8: Eventos y reconstrucción sin huecos
- [ ] Task 8.1: Añadir excepción `EventoNoSoportado` en errores.py
- [ ] Task 8.2: Cambiar `reconstruir_estado` para lanzar EventoNoSoportado en tipos sin aplicador
- [ ] Task 8.2: Hacer no-op explícitos para CREACION_ENTIDAD, RESERVA_CREADA, RESERVA_LIBERADA
- [ ] Task 8.4: Asegurar que reconstruir_estado no modifica mundo recibido (deepcopy inicial)
- [ ] Task 8.5: Documentar en informe qué cambios NO generan evento (ubicación, fatiga, cuidadores_asignados, etc.)

### Phase 9: Pruebas honestas
- [ ] Task 9.1: Refactor test_hypothesis.py: mundo vivo solo via aplicar_transicion_*
- [ ] Task 9.2: Reconstrucción desde deepcopy del mundo inicial
- [ ] Task 9.3: Propiedades con tareas, reservas, asignaciones reales
- [ ] Task 9.4: Tests nuevos: solapamiento intra-paquete, reversión, dependencias calculadas, rechazo INV-3/INV-6, EventoNoSoportado, INV-4/5 no_verificadas
- [ ] Task 9.5: Prueba estática AST que detecte `replace(..., estado=...)` fuera de estados.py y eventos.py

## Checkpoint: After Phase 3
- [ ] Tests pass for reservation and state changes

## Checkpoint: After Phase 6
- [ ] Mundo honesto funciona, invariantes preventivas activas

## Checkpoint: Complete
- [ ] All acceptance criteria met
- [ ] Tests pass

## Risks and Mitigations
| Risk | Impact | Mitigation |
|------|--------|------------|
| Cambios en firma de funciones rompen tests | High | Actualizar tests en paralelo |
| Eliminar singleton de reservas rompe invariantes | Medium | Pasar registro explícitamente en todos lados |
| Mundo mutable puede introducir bugs | Medium | Centralizar mutaciones en métodos de Mundo |
| Tests hypothesis dependen de estado global | High | Refactor completo de test_hypothesis.py |

## Open Questions
- ¿Cómo manejar `tiempo_actual` en Mundo si se usa para validaciones?
- ¿La excepción `DependenciaInexistente` debe ser distinta de `DependenciasPendientes`?
- ¿INV-6 preventiva también para traslados a EN_CLINICA? (espec especifica recinto destino)