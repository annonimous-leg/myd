# Instalación de Meg en Supabase

Estado al 2026-10-15: el propietario autorizó la organización `Tio-cpu's` (`cztytulwkmcgoknbxjnz`) y región `us-east-1`. El conector devuelve `projects: []`. La consulta de coste falla con `UNAVAILABLE: MCP tool get_cost was not returned by tools/list`. No se recibió coste ni `confirm_cost_id`; no se creó un proyecto. El plan free de la organización no acredita el coste del proyecto. Este documento prepara la instalación y no acredita un despliegue ejecutado.

## Autoridades del sistema

- PostgreSQL/PostGIS aloja el dominio. Alembic es la única autoridad del esquema; no crear una segunda historia de migraciones ni usar `create_all` para instalar.
- FastAPI conserva autenticación, tenant, permisos y transacciones. Sus usuarios y JWT no son usuarios ni JWT de Supabase Auth.
- Supabase Storage conserva objetos privados. La clave de servicio se entrega únicamente al backend y a sus workers mediante el gestor de secretos.
- Redis y Celery requieren un servicio separado; crear Supabase no despliega el API, los workers ni el frontend.

## Proyecto y conectividad

Crear un proyecto dedicado, inicialmente de aceptación, en la organización y región autorizadas, después de obtener y confirmar el coste requerido por el conector. No activar datos de producción hasta cumplir las pruebas del cierre.

Usar conexión directa de PostgreSQL para migraciones y copias; para procesos persistentes usar conexión directa o el pooler en modo sesión cuando se necesite IPv4. No usar el pooler de transacciones con la configuración actual de SQLAlchemy/asyncpg. Mantener TLS y comprobar la CA y el nombre del servidor; no desactivar la verificación para resolver errores de conexión. Configurar la URL para el driver `postgresql+asyncpg`, sin copiar opciones de otro driver sin validarlas.

Antes de instalar tablas, desactivar la Data API de Supabase: Meg utiliza su propio API y no necesita exponer las tablas por REST/GraphQL. Revocar los privilegios automáticos y existentes de `anon` y `authenticated` sobre las tablas de dominio; configurar los privilegios por defecto del rol que ejecutará Alembic. Mantener RLS habilitado en las tablas que se expongan y verificar explícitamente sus políticas. No crear políticas basadas en `auth.uid()` para la identidad propia de Meg sin una migración de identidad diseñada y probada.

Separar credenciales de migración (DDL) y ejecución (DML) del backend. `MIGRATION_DATABASE_URL` es obligatoria al ejecutar Alembic en producción y debe usar un usuario distinto del que utiliza `DATABASE_URL`. El rol DML necesita únicamente las tablas, secuencias y funciones realmente utilizadas, sin permiso para crear o alterar el esquema. API, workers, dispatcher y release gate reciben solo `DATABASE_URL`; únicamente el servicio `migrate` recibe también `MIGRATION_DATABASE_URL`. El engine común convierte `sslmode=require` a TLS con verificación de CA y hostname; también admite `DATABASE_SSL_MODE=verify-ca|verify-full` y un CA explícito mediante `DATABASE_SSL_ROOT_CERT`. Producción rechaza TLS deshabilitado o sin verificación. Si se habilita RLS en tablas internas, definir y comprobar la política del rol de ejecución antes del arranque; el rol DML no omite RLS por tener permisos sobre la tabla.

## Variables para Supabase

La plantilla sin secretos está en `backend/.env.supabase.example`. Sustituye los dominios, usuarios y marcadores de contraseña por las conexiones del proyecto y conserva los valores reales solo en el almacén de secretos. Usa una URL de pooler **session** para los procesos persistentes únicamente si necesitas el pooler, y conexión directa para Alembic/backup. El driver de la aplicación es asyncpg; no utilizar el pooler de transacciones.

El preflight manual de GitHub Actions se activa con el workflow `Supabase read-only preflight` después de guardar `SUPABASE_DML_DATABASE_URL` como secreto del repositorio/entorno. Para comprobar también Storage, guardar `SUPABASE_PROJECT_URL` y `SUPABASE_SERVICE_KEY` como secretos; ambos son opcionales para la inspección SQL. El paso de Storage solo hace un GET de la lista de buckets, no crea ni modifica objetos, y marca cualquier bucket faltante o público. El informe solo contiene metadatos y conteos por tabla; aun así, debe tratarse como evidencia interna del proyecto.

## Instalación reproducible

En `backend/`, con el proyecto objetivo confirmado y las credenciales cargadas desde el gestor de secretos:

```sh
uv sync --frozen --extra dev
uv run python -m scripts.supabase_preflight
```

El preflight usa solo `DATABASE_URL`, abre una transacción PostgreSQL `READ ONLY` y no ejecuta DDL/DML. Devuelve conteos separados, rangos de vigencia, distribución por fuente, duplicados de claves naturales, extensiones, revisión Alembic, grants de `anon`/`authenticated` y estado RLS observado. No exporta filas ni precios. Guarda y revisa el informe antes de avanzar.

Los aproximadamente 23.000 precios preexistentes deben reconciliarse contra estos conteos y su fuente. `catalogos_apu`, `conceptos_catalogo`, `insumos_catalogo`, `catalogo_registros`, `catalogo_importaciones` y `precios_unitarios_asignados` son entidades distintas; sus filas no se suman para inventar un total. Si el catálogo ya existe, no ejecutar semillas, reimportaciones, truncados ni scripts de reconstrucción. No se debe usar `alembic stamp` para ocultar una revisión o esquema faltante.

Antes de migrar: obtener un backup lógico y copia de los objetos privados, comprobar que ambos pueden restaurarse en un entorno aislado y registrar revisión/conteos del destino. Solo después, y primero en un proyecto Supabase de staging, ejecutar:

```sh
uv run alembic upgrade head
uv run python -m scripts.verify_migrated_schema
uv run python -m scripts.supabase_preflight --require-head
```

Registrar revisión Alembic, versiones reales de PostgreSQL/PostGIS y extensiones, fecha y resultado. Usar `CREATE EXTENSION` sin fijar una versión: el proveedor mantiene las versiones de sus extensiones. El registro de Alembic debe quedar en la única revisión head del código instalado. Si el preflight inicial muestra discrepancias con los datos esperados, detenerse y reconciliar primero; no usar `stamp` ni reimportar para “arreglar” conteos.

Configurar buckets privados `documentos`, `bim-modelos` y `exportaciones`, o los nombres explícitos de `SUPABASE_BUCKET_*`. Comprobar además cualquier bucket configurado por ingesta antes de habilitar ese flujo. El almacenamiento de catálogo original exige persistencia y respaldo independientes cuando use `CATALOGO_ORIGINALES_DIR`.

Cargar en API y workers `DATABASE_URL`, los tres endpoints Redis, `SUPABASE_URL`, `SUPABASE_SERVICE_KEY`, secretos de firma/cifrado y orígenes HTTPS exactos. Conservar las claves de cifrado junto con su procedimiento de recuperación; una copia de objetos cifrados sin claves no es recuperable. No incluir secretos en commits, ZIP ni evidencia de CI.

## Configuración del despliegue Compose

Usar Docker Compose >= 2.24.4 y pasar las variables explícitamente desde `backend/`:

```sh
docker compose --env-file .env.production -f docker-compose.prod.yml config --quiet
docker compose --env-file .env.production -f docker-compose.prod.yml up -d --build
```

`--env-file` alimenta la interpolación; sólo las variables declaradas en cada servicio llegan al proceso. El compose exige y propaga `CORS_ALLOWED_ORIGINS` como array JSON y `ENCRYPTION_MASTER_KEY` a API, workers, dispatcher, scheduler y comprobaciones previas. Ejemplo: `CORS_ALLOWED_ORIGINS='["https://app.example.com"]'`; sustituir por los orígenes HTTPS exactos del navegador desplegado.

`DATABASE_URL` es obligatoria y configura el rol DML de API, workers, dispatcher, scheduler y release gate. `MIGRATION_DATABASE_URL` también es obligatoria y configura el rol DDL, únicamente en el servicio `migrate`; producción no permite reutilizar el usuario DML ni recurrir a un fallback implícito. Ambos URLs deben apuntar al mismo proyecto/base, usar TLS validado y tener usuarios distintos. Compose propaga `DATABASE_SSL_MODE=verify-full` por defecto; si el proveedor requiere un CA privado, montar el archivo y establecer `DATABASE_SSL_ROOT_CERT` con su ruta dentro del contenedor. Los tres endpoints Redis también son configurables. El compose conserva servicios locales para topologías heredadas, pero no los usa como fallback de PostgreSQL en producción; su presencia no acredita conexión al proveedor.

El fichero funciona solo o como segundo fichero sobre `docker-compose.yml`. El overlay cierra los puertos de db/Redis/MinIO y selecciona Supabase para BIM. La API publica el puerto 8000; faltan la configuración y aceptación del proxy HTTPS, certificados y entrada de red del despliegue. Verificar TLS de PostgreSQL con el driver y proveedor reales. MinIO sigue sin ser el almacenamiento activo.

En instalaciones nuevas, usar una clave de cifrado independiente de `SECRET_KEY` y conservar su recuperación. Para objetos existentes que usaban el fallback histórico a `SECRET_KEY`, configurar primero `ENCRYPTION_MASTER_KEY` con el valor efectivo que ya cifró esos objetos. No sustituirlo ni rotarlo sin un re-wrap verificado de todas las DEKs y una recuperación comprobada. Este corte no migra claves ni cambia el fallback histórico.

El job `production-compose-config` comprueba el render con valores ficticios, sin daemon ni red: destinos DML/DDL, propagación JSON/cifrado, storage y puertos internos, en modo independiente y overlay. No acredita conectividad, TLS, almacenamiento, persistencia Redis ni aceptación de un proveedor real.

## Aceptación antes del tráfico real

1. Arrancar API y workers con el esquema ya migrado; comprobar `/health` y `/ready` con dependencias reales.
2. Crear identidades de aceptación de dos organizaciones. Confirmar aislamiento de expedientes, documentos, sesiones, tareas y eventos.
3. Subir, recuperar y verificar SHA-256 de PDF e IFC por el API. Confirmar que los objetos son privados y conservan sus referencias tras reiniciar procesos.
4. Ejecutar dos cofirmas simultáneas sobre el mismo PDF; recuperar ambas rendiciones, verificar la cadena, cifrado y firmas. Probar confianza/revocación de certificados y la TSA configurada con el proveedor real.
5. Ejecutar licitación con bases congeladas, revisión documental, tres dictámenes, fallo y contrato; conservar las evidencias y los errores de los casos rechazados. No reutilizar el questionnaire como evidencia legal.
6. Ejecutar IFC → cantidades → mapeo APU → presupuesto → exportación desde navegador, con recarga y recuperación de tareas.
7. Restaurar copia de base y objetos en un entorno separado, comprobar hashes y acceso, y registrar tiempos de recuperación. Las pruebas destructivas de recuperación de CI se ejecutan únicamente en sus bases desechables.

Guardar resultados con SHA del código, revisión de base, identificadores del proyecto, versiones y fecha. Un resultado de CI correcto acredita el alcance de sus casos, no sustituye esta aceptación del proveedor.

## Fuentes oficiales consultadas

- [Conexión a PostgreSQL](https://supabase.com/docs/guides/database/connecting-to-postgres)
- [Protección de Data API, grants y RLS](https://supabase.com/docs/guides/api/securing-your-api)
- [Row Level Security](https://supabase.com/docs/guides/database/postgres/row-level-security)
- [Cambios de versiones de extensiones](https://supabase.com/changelog/extension-version-pinning-ignored)
- [Cambio de cifrados TLS HTTP](https://supabase.com/changelog/cbc-tls-ciphers-deprecated)

La retirada de cifrados CBC de TLS 1.2 en HTTP no requiere cambiar a conexiones inseguras: los runtimes actuales deben negociar cifrados admitidos. Verificar la conexión del entorno desplegado.
