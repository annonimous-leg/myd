# Plan: cierre de integración Supabase y aceptación del workspace licitante

**Fecha:** 2026-11-02  
**Rama de trabajo:** `feat/supabase-readiness-and-bidder-e2e-2026-11-02`  
**Base inmutable:** `dc4707c94f706e661a144b6a52614de1e2854efb` (PR #42)  
**Objetivo:** dejar el backend preparado para usar PostgreSQL/PostGIS y Storage de Supabase sin perder ni duplicar el catálogo preexistente de aproximadamente 23.000 precios, y ampliar la aceptación del workspace para licitaciones.

## Reglas de seguridad y datos

- No crear, borrar, truncar, volver a sembrar ni importar precios en la base existente durante la preparación.
- El primer acceso al proyecto Supabase será de solo lectura. El inventario informará conteos, revisión Alembic, fuentes, vigencias, índices, RLS/grants observables y duplicados; no expondrá importes/fichas de usuario ni secretos.
- Alembic será la única autoridad de DDL. La aplicación y los workers usarán un rol DML separado; las migraciones usarán un rol DDL explícito.
- Megalodon seguirá siendo la autoridad de autenticación, autorización y tenancy. La service-role key de Supabase se limitará a Storage y nunca se enviará al navegador.
- No se aplicará ninguna migración ni se desplegará sobre Supabase real sin backup recuperable, inventario revisado, proyecto/entorno objetivo confirmado y aprobación explícita.
- Las credenciales no se guardarán en el repositorio ni se pedirán en el chat. Se inyectarán por el gestor de secretos del despliegue.

## Tareas

### 1. Pruebas de configuración antes de cambiar el runtime (TDD)
- Añadir pruebas de normalización de DSN PostgreSQL a asyncpg y de eliminación/traducción de `sslmode` a argumentos TLS soportados por asyncpg.
- Verificar que SQLite de pruebas no recibe opciones TLS.
- Verificar que `MIGRATION_DATABASE_URL` se usa en Alembic y que una configuración de producción no comparte accidentalmente el usuario de runtime DML como migrador.
- Verificar que los módulos de Tezcatlipoca comparten el engine de `app.models.base`, sin crear un segundo pool ni aceptar un endpoint alternativo inadvertido.
- Observar primero el fallo de las pruebas nuevas en CI antes de implementar.

### 2. Un solo runtime PostgreSQL seguro
- Añadir un helper de conexión que convierta los DSN PostgreSQL a `postgresql+asyncpg`, traduzca `sslmode`/configuración TLS a `connect_args` y permita una CA explícita.
- Añadir configuración validada de `MIGRATION_DATABASE_URL`, `DATABASE_SSL_MODE` y `DATABASE_SSL_ROOT_CERT`.
- Usar la conexión común en el engine SQLAlchemy de Megalodon, Alembic, verificación de esquema y runtime Tezcatlipoca.
- Mantener compatibilidad SQLite solo para desarrollo/pruebas.
- Mantener la separación DDL/DML en producción y fallar cerrado si las credenciales de migración no están configuradas.

### 3. Preflight de la base existente de Supabase (solo lectura)
- Crear `backend/scripts/supabase_preflight.py`.
- Reportar de forma sanitizada: motor/versiones/extensiones, revisión Alembic presente y esperada, tablas de catálogo presentes, conteos por tabla, número de fuentes, intervalo de vigencias, duplicados por clave natural, RLS/policies y grants a roles de Data API que existan.
- La consulta debe ser estrictamente de lectura y omitir tablas/campos inexistentes sin intentar crearlos.
- Añadir pruebas unitarias para el formateo del informe y pruebas de integración con PostgreSQL temporal.
- No suponer que el total de filas equivale al número de precios; separar `catalogos_apu`, `conceptos_catalogo`, `insumos_catalogo` y las filas crudas de `catalogo_registros`.

### 4. Conectar Storage y documentar el runbook
- Añadir una plantilla de variables sin secretos para conexión directa y pooler de sesión, usuario DDL, usuario DML, TLS/CA, buckets privados y claves del servicio de Storage.
- Actualizar Compose para que el servicio de migración reciba explícitamente `MIGRATION_DATABASE_URL` y la configuración TLS; runtime y workers reciben solo `DATABASE_URL`.
- Actualizar `docs/SUPABASE_DEPLOYMENT.md` con el orden obligatorio: backup/verificación de restore, preflight, comparar conteos/ediciones, decidir migración, ejecutar Alembic solo en entorno aprobado, verificar esquema, revisar RLS/grants y probar Storage.
- Dejar claro que la Data API/RLS son controles del proyecto y deben configurarse/revisarse desde Supabase; no activar acceso de navegador a las tablas de dominio.

### 5. Aceptación del workspace de licitante
- Reutilizar el browser harness y fixture existente `frontend/app/tests/helpers/licitacion-flow.mjs`; no crear una segunda ruta de aceptación paralela.
- Extender el flujo desde la confirmación humana de requisitos hasta los pasos de preparación disponibles en la UI/API: ejecutar el motor, revisión semiautomática, crear/revisar documentos de workspace, compilar artefactos y validar el gate de firma/paquete.
- Comprobar que el QA-REPORT/interno nunca se marque como presentable, que los artefactos que requieren firma no se envíen sin firma válida, y que el ZIP/recibo no se presente como envío real al portal.
- Para CI usar solo jurisdicción, convocatoria y contenido sintéticos. Nunca generar una FIEL falsa ni decir que una firma o presentación es oficial.
- Preservar evidencia de navegador, trazas y resultado de API en el job de aceptación existente.

### 6. Verificación y salida
- Ejecutar CI de la nueva rama/PR y revisar todos los jobs y logs de cualquier fallo.
- Verificar el SHA exacto que termina verde, no solo el estado general del PR.
- No integrar ni desplegar este stack automáticamente. La integración sigue siendo hoja-a-raíz después de aprobación humana.
- La conexión real a Supabase y la conservación de los 23.000 precios solo se considerarán verificadas cuando el preflight se ejecute con el proyecto real y el informe concuerde con el inventario esperado, y después exista aceptación de lectura/escritura/backup/restore en un entorno de staging aislado.
