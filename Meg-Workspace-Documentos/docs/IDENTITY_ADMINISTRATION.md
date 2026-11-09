# Administración de identidades

MEGALODON administra los usuarios por UUID en `/api/v1/users`. Tezcatlipoca mantiene
solo el espejo necesario para sus relaciones locales. Se eliminaron las rutas que
escribían usuarios espejo (`/api/admin/users`); los consumidores deben usar la API IAM.

PATCH autenticado por cookie exige un único Origin exacto del servidor o de la lista
CORS configurada; se rechazan origen ausente, null, subdominios ajenos y encabezados
duplicados. Bearer explícito conserva el flujo de SDK. Esto cubre la API IAM;
la revisión de CSRF en los demás módulos sigue pendiente.

GET lista únicamente el tenant del administrador autenticado, con paginación validada.
PATCH acepta `role`, `is_active` y `reason` obligatorio. Campos desconocidos, null,
estados convertidos desde texto y peticiones sin cambio se rechazan.
Los roles de plataforma no pueden concederse ni modificarse desde esta API.
Otro administrador debe modificar el rol o estado del propio administrador.
La organización conserva al menos un administrador de tenant activo.

Un bloqueo de la organización serializa cambios concurrentes. Actor y objetivo se
vuelven a consultar después del bloqueo, evitando autorizar con una identidad que
otra transacción acaba de deshabilitar. Usuario, versión de sesión y auditoría se
confirman en una sola transacción; un fallo de auditoría revierte todo.

Access y refresh JWT incluyen `auth_version`. Cualquier cambio efectivo de rol o
estado incrementa la versión persistida e invalida ambos tipos de token.
Rehabilitar un usuario no reactiva sus sesiones anteriores. Los tokens anteriores
a esta migración tampoco se aceptan: todos los usuarios deben iniciar sesión de nuevo.

El servidor comprueba la revisión Alembic y las columnas requeridas antes de
recibir peticiones. No aplica migraciones al arrancar. Tezcatlipoca también verifica
su esquema sin modificarlo. La ausencia de su esquema lo degrada como servicio
opcional; una falta de esquema del núcleo impide iniciar la API.

Despliegue: aplicar `alembic upgrade head` antes de arrancar la nueva API y renovar
las sesiones. No desplegar la nueva API contra una base sin `users.auth_version`.
La migración de autoridad es irreversible mediante `alembic downgrade`: eliminar
el contador y recrearlo en cero puede rehabilitar JWT revocados. La reversión se
rechaza antes de modificar el esquema. Consultar `MIGRATION_RECOVERY.md` para
recuperación aislada, rotación de claves y límites de la evidencia de CI.
El dashboard y contador consultan los usuarios reales, aunque nunca hayan usado
Tezcatlipoca. Se retiró la cifra global de blacklist SQL: la revocación real usa Redis.

Referencias consultadas:
- PostgreSQL 16, Explicit Locking: https://www.postgresql.org/docs/16/explicit-locking.html
- SQLAlchemy, populate_existing: https://docs.sqlalchemy.org/en/20/orm/queryguide/api.html#populate-existing
- OWASP, CSRF: https://cheatsheetseries.owasp.org/cheatsheets/Cross-Site_Request_Forgery_Prevention_Cheat_Sheet.html
- OWASP, Authorization: https://cheatsheetseries.owasp.org/cheatsheets/Authorization_Cheat_Sheet.html
- Keycloak, UserResource: https://github.com/keycloak/keycloak/blob/main/services/src/main/java/org/keycloak/services/resources/admin/UserResource.java

Límites pendientes para GO del producto: ensayo sobre una copia de los datos reales,
recuperación completa de infraestructura y artefactos, catálogo privado revisado/activado, documentos/BIM y
smoke de API desplegada. La suite HTTP ASGI se complementa con un proceso Uvicorn real en CI: arranque con
lifespan, TCP HTTP, health/ready, login, cookies, cambio IAM y cierre ordenado.
Las identidades de ese smoke son fixtures de CI; no certifican un despliegue real.
