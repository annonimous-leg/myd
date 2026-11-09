# Arquitectura de Unificación: Megalodon + Tezcatlipoca

Este documento reemplaza al PDF/diagrama de arquitectura "visión" como
fuente de verdad operativa. Ese documento describe el norte a largo
plazo (SSO, Kafka, Kubernetes multi-región, marketplace, IA en cada
hub); esto describe lo que **ya existe en código** y lo que falta
decidir para la Fase 2, con menos IA y más determinismo, como se pidió.

## Estado actual (Fase 1 — completada en este pase)

**Un solo backend, un solo proceso.** `backend/tezcatlipoca/` es el
backend de TU-OSINT copiado tal cual (con sus 3 bugs de la auditoría ya
corregidos: import faltante en `cyber.py`, 8 rutas duplicadas en
`ai_channel.py`, carpeta de backup de 620KB eliminada). Se monta como
routers adicionales sobre la misma app de FastAPI en
`backend/app/main.py`, bajo el prefijo `/api/tezcatlipoca/*`.
`pyproject.toml` ya trae las dependencias nuevas que esto requiere.

**Lo que NO se tocó, a propósito:** el sistema de autenticación de
Tezcatlipoca (cookie httpOnly + fallback a Bearer, `User`/DB propios,
SQLAlchemy síncrono) sigue funcionando de forma completamente
independiente del auth de Megalodon (Bearer/OAuth2, `User`/DB propios,
SQLAlchemy asíncrono, multi-tenant). Fusionar esto a ciegas —sin poder
correr ninguno de los dos backends en este entorno (sin red, no se
instalan dependencias)— hubiera sido la parte más riesgosa de todo el
trabajo: es la superficie de seguridad más sensible del sistema. Se
dejó preparado (`JWT_SECRET` en tezcatlipoca ahora también lee la
variable `SECRET_KEY` de Megalodon como fallback) pero no activado.

**Verificado:** todo compila limpio (`py_compile`) sobre el árbol
completo, sin colisión de nombres de paquete entre `app.*` y las
carpetas que trae tezcatlipoca (`routers`, `services`, `core`, `db`,
`middleware`). **No verificado:** arranque real (`uvicorn app.main:app`)
— hace falta un entorno con las dependencias instaladas y Postgres real
para confirmar que no hay errores de runtime que un chequeo estático no
detecta.

## Lo que falta decidir (Fase 2 — requiere una decisión de producto, no solo código)

1. **¿Los recursos de Tezcatlipoca son por tenant, por usuario, o
   globales?** Megalodon es multi-tenant (cada expediente/documento
   pertenece a un `tenant_id`). Tezcatlipoca no tiene ese concepto —
   sus datos (rastreo de vuelos, barcos, amenazas cyber) son en su
   mayoría de fuentes externas compartidas. Antes de fusionar tablas de
   usuario hay que decidir si un reporte OSINT o una sesión de mesh
   pertenece a un tenant de Megalodon o es global de la plataforma.
2. **Login único.** Una vez resuelto el punto 1: apuntar
   `tezcatlipoca/db/models.py` a la tabla `users` de Megalodon (o
   generar un JWT desde el login de Megalodon que Tezcatlipoca acepte
   sin volver a consultar su propia tabla). Es un cambio quirúrgico una
   vez decidido el punto 1, pero toca código de autenticación —
   requiere pruebas reales, no solo lectura de código.
3. **Frontend:** Tezcatlipoca (SPA React 18.2 + MapLibre) y
   `solar-geo-platform` (TypeScript + Three.js puro, sin React) todavía
   no están envueltos como apps dentro del shell de Megalodon
   (`frontend/app/src/apps/*`). Es un trabajo aparte del backend: cada
   uno necesitaría su propio `apps/<id>/index.tsx` que monte el
   componente correspondiente (wrapper imperativo para el caso de
   Three.js puro, ya que Megalodon usa React 19 con
   `@react-three/fiber`).
4. **Base de datos física.** Por ahora tezcatlipoca sigue con su propio
   motor de conexión (`psycopg2`/SQLite, síncrono) separado del de
   Megalodon (`asyncpg`, asíncrono) — pueden coexistir apuntando a la
   misma instancia de Postgres con tablas separadas sin problema, pero
   no comparten sesión ni transacciones. Unificar eso (si hace falta)
   es un cambio de infraestructura, no de aplicación.

## Qué partes del documento de arquitectura "visión" ya están cubiertas

De las ~20 secciones del documento original, lo que ya tiene código
real detrás: Legal Hub, Procurement Hub, Costos Hub, Engineering Hub,
BIM Hub, Survey Hub (todo del lado Megalodon); Geo Hub, GIS Hub,
Photogrammetry Hub, SAR Hub, Transport & Aviation Hub, OSINT Hub, Cyber
Hub (del lado Tezcatlipoca, con los matices de madurez ya reportados:
~35-45% listo para producción). El resto — Identity/SSO/SAML,
Licensing con feature flags, Kafka/Service Mesh, Kubernetes
multi-región, Marketplace, apps móviles, SDKs en 5 lenguajes, Digital
Twin, Telemetría/SCADA real, Fiscalización, Sustainability, Financial
Hub, y casi toda la sección de agentes de IA — sigue siendo roadmap, no
código.
