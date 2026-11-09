# Corrección de la auditoría BIM/costeo de octubre

Base: 51bcc08324183022a9f5867acc8f569deb99fb2c, rama codex/costeo-sesiones-2026-09-30.

- IFC: geometría SI sin segunda conversión; QTO usa unidad propia de longitud/área/volumen, incluida Unit explícita.
- Reprocesado: bloqueo del modelo con savepoint, actualización por GlobalId, conservación de identidad/enlaces/zonas y reemplazo atómico. Lecturas sin malla devuelven copias.
- Enlaces: validación completa del lote antes de escribir, mismo tenant y expediente; nueva migración PostgreSQL con identidad única, FK de modelo y triggers de integridad acotados a las filas afectadas y bloqueo compartido de los padres.
- Costeo: cantidades faltantes permanecen en cero y BORRADOR. Un grupo parcialmente medible también queda pendiente. No se valida/aprueba con cantidades/precios/importes incompletos.
- Acceso: API aplica el catálogo de módulos del launcher y roles de escritura; aprobación requiere revisor/admin/superadmin.
- Uso: crear, recalcular y cambiar parámetros reservan corridas en la misma transacción del presupuesto; las exportaciones de un presupuesto existente no consumen una nueva corrida.
- Storage: claves por UUID, independientes de nombre/contador; carga BIM sin sobrescribir y limpieza ante fallo de commit. Rechazo del broker queda como ERROR y HTTP 503.
- WebSocket: identidad resuelta por AuthService, revalidación en cada mensaje y cada 30 segundos de inactividad.
- CI: chequeo del intérprete .venv explícito y auditoría de las dependencias exportadas desde uv.lock.

## Validación y límites

Las pruebas SQLite usan modelos actuales y Redis real. Se incluyen pruebas para verificar los triggers y bloqueos PostgreSQL en CI con esquema migrado; no se consideran acreditados hasta que terminen satisfactoriamente. SQLite no acredita esas garantías ni sustituye PostGIS. La migración se detiene ante duplicados/enlaces históricos incompatibles; no elimina evidencia automáticamente. Antes de producción, respaldar la BD y reparar conflictos que reporte la migración.

El importador BIM recibe IFC. El DWG cs06 suministrado se inspecciona por separado; convertir un plano a DXF no aporta automáticamente cantidades BIM ni precios. Un fallo del proceso API entre commit y publicación al broker todavía requiere reconciliación operativa: no hay outbox transaccional en este bloque.


## Revisión final

La revisión Build en dos ejes detectó escaneo global y ausencia de bloqueo en la primera versión del trigger, logging incompatible al rechazar QTO y una carrera de ERROR después de rollback. Se corrigieron antes del checkpoint final: consulta por identidad afectada, FOR SHARE, QTO por cantidad, logging estándar, abortar extracción parcial y rollback de savepoint incluso tras fallo de flush. Mapeo y reprocesado adquieren primero el bloqueo del modelo. El worker no sustituye una extracción completada por un error tardío. La prueba de fallo de persistencia usa un trigger real SQLite.

CAD: cs06.dwg se convirtió con LibreDWG y se abrió con ezdxf. 4.164 entidades de modelspace, 33 capas, $INSUNITS=4 (milímetros declarados), DXF AC1018; audit estructural con cero errores. LibreDWG advierte clases DIMASSOC inestables: la conversión necesita contraste visual antes de considerarse equivalente al original. Todavía no hay importación DWG a cantidades BIM.

Prueba PostgreSQL local: pgserver descargó binarios, pero no pudo crear el usuario de servicio por las restricciones del entorno. No se afirma validación local de triggers PostgreSQL ni de PostGIS. Los nuevos tests PostgreSQL quedan incluidos para CI.


## Dependencias detectadas por la auditoría corregida

La primera ejecución real del nuevo CI encontró avisos en dnspython 2.4.2, PyNaCl 1.5.0 y source-map-js 1.2.1. Se actualiza la fuente de dependencias y los locks: dnspython 2.8.0, PyNaCl 1.6.2 y source-map-js 1.2.2. Se repiten chequeo de compatibilidad, pip-audit sobre uv.lock exportado, npm audit, tests backend, sesión frontend y build. No se añaden exclusiones de avisos.

## Standards

Revisión final: sin bloqueos concretos tras corregir alcance y bloqueo de triggers, rollback de savepoint, error tardío del worker y criterio compartido de completitud. La prueba concurrente PostgreSQL se incluye y espera ejecución.

## Spec

Revisión final: sin nuevas desviaciones concretas. Se conservan unidades, identidad y enlaces en reprocesado/fallos; acceso y límites se aplican del lado servidor. DWG sigue siendo evidencia de una conversión a DXF, no una importación a BIM. PostgreSQL/PostGIS y storage externo siguen sujetos a validación de infraestructura.

Resultado final de revisión: 0 bloqueos pendientes en Standards y 0 en Spec; permanece pendiente la acreditación de infraestructura.
