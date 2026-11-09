# Production gates pendientes y verificados

## Verificado en esta iteración
- El backend carga en entorno limpio sin romperse por dependencias opcionales de OpenTelemetry instrumentation.
- La suite completa de pruebas del backend pasa: 150 tests.
- `frontend/app/vite.config.ts` quedó compatible con ESM y deja de depender de `__dirname` inexistente en este contexto.
- `frontend/app/tailwind.config.js` quedó en formato ESM consistente con `"type": "module"`.

## Pendiente para cerrar producción industrial
### P0. Build reproducible
- Ejecutar `npm ci` real en entorno limpio con node_modules instalados.
- Confirmar `npm run build` del frontend.
- Ejecutar build de Docker sin depender del entorno local.
- Cerrar el manifiesto de dependencias Python con lock reproducible para despliegue.
- Mantener `plugin-inspect-react-code` solo en desarrollo.
- Garantizar que Tailwind use ESM puro dentro de `frontend/app`.
- Alinear `lang` y `referrer` del HTML de entrada con despliegue real.

### P1. Seguridad enterprise
- SBOM generado y archivado.
- `pip-audit`, `npm audit`, scanning de imágenes y secrets scanning.
- Verificación CSP/HSTS/headers.
- Revisión final RBAC/ABAC y rotación/revocación de credenciales.

### P2. Infraestructura de datos
- Migración desde una base vacía en PostgreSQL de producción.
- Validación de Redis en modo HA/persistente según SLA.
- Políticas reales de object storage/MinIO.

### P3. DR
- Restore completo desde backup con validación de integridad.
- Medición de RPO/RTO y consistencia DB + archivos + evidencias.

### P4. Observabilidad
- Exportación real a OTel Collector.
- Métricas por tenant, correlation IDs, latencias p50/p95/p99.
- Alertas y SLO/SLA por endpoint, workers, colas, Redis y DB.

### P5. Load/scale
- Pruebas de concurrencia, búsqueda, snapshots, jobs topográficos, OCR, BIM, CostOS y WebSockets.
- Tuning de pools, workers y puntos calientes.

### P6. Vertical slice
- AOI → observación → levantamiento → topografía → superficies/volúmenes → BIM → CostOS → evidencia → comparación → auditoría.

### P7. Contratos API
- Versionado `/api/v1`, `/api/v2`.
- OpenAPI, idempotencia, paginación, sorting, rate limits, retries deterministas.

### P8. Multi-tenant adversarial
- Aislamiento probado por API, SQL, cache, jobs, WebSockets, exports y logs.

### P9. Digital twin inicial
- Activo → geometría → estado → evidencia → historial → tiempo.

### P10. Release candidate
- PRR P0–P50 con PASS / FAIL / BLOCKED / EVIDENCE.
