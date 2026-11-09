-- Verificación de FKs compuestas tenant-aware (migración 20260826_rule_execution_tenant_hardening)
\echo '--- Constraints multi-columna (tenant_id + id / tenant_id + fk) ---'
SELECT conname, conrelid::regclass AS table_name, pg_get_constraintdef(oid) AS def
FROM pg_constraint
WHERE contype = 'f'
  AND conname LIKE 'fk_%tenant%'
ORDER BY conname;

\echo '--- Unique (tenant_id, id) ---'
SELECT conname, conrelid::regclass, pg_get_constraintdef(oid)
FROM pg_constraint
WHERE contype = 'u'
  AND conname LIKE 'uq_%tenant_id'
ORDER BY conname;

\echo '--- Test: intentos cross-tenant deben fallar (ejecutar solo si hay datos seed; aquí solo estructura) ---'
-- Ejemplo (comentado; descomentar tras seed de tenants A/B):
-- BEGIN;
-- INSERT INTO tender_rule_definitions (id, tenant_id, tender_id, ...)
-- VALUES (..., 'tenant-B', (SELECT id FROM tender_packages WHERE tenant_id = 'tenant-A' LIMIT 1), ...);
-- -- debe levantar: insert or update on table "tender_rule_definitions" violates foreign key constraint "fk_tender_rule_def_tenant_tender"
-- ROLLBACK;
