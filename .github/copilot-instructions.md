# Reglas del proyecto zoo_ops

- Python 3.11, solo biblioteca estándar más pytest e hypothesis. No añadas dependencias sin que se pida.
- El núcleo está en zoo_ops/dominio. No añadas API, base de datos ni interfaz salvo que la tarea lo pida expresamente.
- Todo cambio de estado de una entidad pasa por ejecutar_transicion. Nunca uses dataclasses.replace(..., estado=...) ni cuidadores_asignados=... fuera de eventos.py.
- Las invariantes se imponen en el código, no solo en pruebas. Si una regla no puede imponerse todavía, anótalo en zoo_ops/dominio/LIMITES.md; no dejes código con "pass" ni comentarios tipo "por ahora".
- Nunca modifiques el código de producción ni las tablas de transiciones para que una prueba pase. Si una prueba falla, indica si el error está en la prueba o en el código y por qué.
- Si algo es ambiguo, no inventes la regla: anótalo como duda al final de la respuesta.
- No afirmes que las pruebas pasan ni cites líneas o salidas que no hayas obtenido ejecutando realmente el comando. La suite la ejecuta el desarrollador.
- Responde en español; docstrings en español.
