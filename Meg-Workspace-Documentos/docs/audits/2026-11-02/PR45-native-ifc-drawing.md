# Auditoría de correcciones del motor de dibujo IFC — PR #45

**Fecha:** 2026-11-02  
**Rama:** `fix/ifc-drawing-tolerance-edge-dedup-2026-11-02`  
**PR:** https://github.com/ytpremiumcr7-collab/Meg/pull/45  
**Base:** `feat/native-ifc-drawing-engine-2026-11-02`

## Incidente reproducido en Actions

La ejecución Security Hardening #469, sobre el SHA `bbe74fb4679fd742f27875367cbb2334d5f47695`, terminó con fallo en `backend-integration (api)`. El resto de los gates ejecutables terminó correctamente; `review-package` fue omitido por depender de los gates anteriores.

El log de PostgreSQL/pytest muestra que los tres casos de `tests/integration/test_bim_drawing_jobs.py` no podían crear el trabajo durable. La sentencia de inserción recibió:

- `tipo = BIM_DRAWING`
- `entidad_id = NULL`

La causa era registrar `TrabajoProceso` antes de materializar el identificador generado de `DibujoBIM`. El servicio añadía el dibujo al ORM y leía inmediatamente `drawing.id`, antes de un `flush()`.

## Corrección de persistencia

`BIMDrawingService.crear_dibujo()` ahora ejecuta `await self.db.flush()` después de `self.db.add(drawing)` y antes de llamar a `registrar_trabajo()`.

El flush no confirma la transacción. La fila del dibujo y la intención durable del worker continúan confirmándose o revirtiéndose juntas en el commit posterior.

## Corrección geométrica adicional

Se añade una prueba adversarial de dos triángulos coplanares con vértices duplicados separados menos que la tolerancia, pero situados a lados opuestos de una frontera de cuantización. La cuantización basada únicamente en `round(coordinate / tolerance)` puede clasificarlos como vértices distintos y conservar la diagonal interna.

El núcleo ahora calcula claves canónicas con búsqueda en celdas espaciales vecinas y comparación de distancia geométrica real en metros. Los representantes se eligen de manera determinista y no se permite que un grupo crezca más allá de la tolerancia desde su representante.

## Puertas aún necesarias

- CI completo verde sobre el SHA definitivo de PR #45.
- Verificar específicamente `test_bim_drawing_jobs.py` en PostgreSQL, no solo SQLite.
- Verificar `test_bim_drawing_core_tolerance.py` en el suite core.
- Completar validación DXF con parser independiente y round-trip.
- Completar compensación/limpieza durable si falla una segunda subida o el commit de base de datos.
- Crear workspace de dibujos y aceptación Playwright propia.

## Límites de esta corrección

No implementa HLR, cotas, PDF vectorial, láminas, editor CAD general ni lector IFC nativo. No modifica `main`, no ejecuta migraciones contra Supabase real y no altera el catálogo de precios.
