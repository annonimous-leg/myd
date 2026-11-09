# Verificación del checkpoint y migración de estilos — 5 de octubre de 2026

## Alcance

Base remota revisada: `ecd81da5815ab97f839da5ae4df329a26944e752`, rama
`codex/costeo-sesiones-2026-09-30`, PR #2. Se verificó la ingestión de niveles
mensuales INEGI y se eliminó la cadena vulnerable del compilador Tailwind 3.
No se activaron series oficiales ni catálogos a partir de datos simulados.

## Hallazgos y cambios

- El run remoto `37341238429` pasó migraciones/recuperación, auditoría Python y
  CodeQL. El arranque HTTP pasó; la suite de backend quedó cancelada. Sus logs
  no estaban disponibles, por lo que la causa de cancelación no se atribuye a
  un defecto concreto. Se reprodujo el bloque completo en PostgreSQL real.
- La auditoría npm reportaba seis vulnerabilidades altas por `braces` y sus
  dependientes. El aviso GHSA-vfj7-8cjw-p6xm no ofrecía versión corregida.
- Se migró a Tailwind 4 con su plugin Vite y configuración CSS mediante
  `@theme`, `@theme inline` y variantes nativas. Se retiraron los archivos de
  configuración JavaScript y PostCSS del compilador anterior y el plugin de
  animación antiguo. `tw-animate-css` proporciona las animaciones CSS nativas.
- Se revisaron las conversiones automáticas de clases. El migrador cambió
  accidentalmente la variante de negocio `outline` de paginación; se restauró
  su nombre, sin introducir alias. Los colores se resuelven en el elemento,
  se consolidaron fuentes/radios y se definió la paleta semántica de sidebar.
- Las dos revisiones independientes encontraron una segunda conversión
  incorrecta: el indicador discontinuo de tooltip tomaba el borde global en
  vez del color de su serie. Se corrigió la variable local del indicador y
  se comprobó su color en Chromium. La detección de clases sólo lee `src/`
  e `index.html`: las fixtures de pruebas no generan CSS del producto.
- La comprobación visual descubrió el pie de versión posicionado sobre el
  botón de acceso. Se corrigió su flujo y se permite desplazamiento vertical
  cuando la pantalla es baja.
- La CI verifica el bundle de producción en Chromium: formulario de acceso,
  escritorio/móvil/pantalla baja, controles, ausencia de superposición,
  colores semánticos, fuente, animaciones y contorno en colores forzados.
  Las respuestas anónimas de API en estas pruebas son fixtures declaradas;
  no representan una prueba de acceso autenticado de extremo a extremo.
- El run `37353623827` volvió a quedarse esperando durante pytest, aunque
  migración, esquema, smoke HTTP, recuperación, auditorías y frontend pasaron.
  Se limitan los locks y sentencias exclusivamente en conexiones de pruebas,
  la importación concurrente tiene plazo explícito y las pruebas de
  inmutabilidad exigen el mensaje del trigger. La CI conserva stdout/stderr y
  el volcado de hilos, y termina incluso si el proceso ignora SIGTERM. Estos
  límites hacen observable el fallo; no prueban que su causa esté resuelta.

## Evidencia local

- Migración Alembic hasta `20261005_ingesta_inegi` y comprobación del esquema:
  aprobadas con PostgreSQL 16.15 / PostGIS 3.4.2.
- Cinco pruebas de ingestión: aprobadas, incluyendo concurrencia, precisión
  decimal, reimportación, rollback y restricciones SQL sobre evidencia.
- Suite completa tras los límites de diagnóstico: **412 aprobadas, 2 omitidas,
  71 avisos**, 43.37 segundos.
  Las dos omitidas requieren servicios externos opcionales; el smoke HTTP se
  ejecutó por separado contra Uvicorn y Redis reales.
- Smoke de runtime: aprobado con rol DML sin propiedad del esquema. Tezcatlipoca
  quedó degradado como subsistema opcional. No certifica despliegue productivo.
- Instalación frontend mediante `npm ci`, build TypeScript/Vite, tres pruebas
  del cliente de sesión y auditoría npm: aprobadas, **0 vulnerabilidades**.
- La verificación local usa instancias desechables, datos sintéticos y sólo
  loopback. Este entorno sólo mapea UID 0: se adaptó exclusivamente la primera
  consulta UID al arrancar los binarios PostgreSQL de pruebas. El motor SQL,
  las extensiones, los locks y los triggers son los binarios oficiales sin
  modificaciones. Ese arnés temporal no pertenece al repositorio ni al
  despliegue; la CI utiliza el contenedor PostGIS normal.

## Referencias contrastadas

- [Aviso de seguridad de braces](https://github.com/advisories/GHSA-vfj7-8cjw-p6xm).
- [Guía oficial de migración Tailwind](https://tailwindcss.com/docs/upgrade-guide).
- [Variables de tema y resolución inline](https://tailwindcss.com/docs/theme).
- [Tema de la implementación oficial](https://github.com/tailwindlabs/tailwindcss/blob/main/packages/tailwindcss/theme.css).
- [Implementación CSS de animaciones](https://github.com/Wombosvideo/tw-animate-css).
- [Servidor de pruebas Playwright](https://playwright.dev/docs/test-webserver).
- [Límites por conexión PostgreSQL](https://www.postgresql.org/docs/16/runtime-config-client.html).
- [Parámetros server_settings de asyncpg](https://magicstack.github.io/asyncpg/current/api/index.html).

Tailwind 4 requiere Safari 16.4+, Chrome 111+ y Firefox 128+. No se añadió una
capa del compilador antiguo para navegadores anteriores.

## Puerta de producción pendiente

Esta verificación cierra el bloque de código probado, no una certificación
GO de todo Megalodon. Se requiere confirmar la CI del nuevo commit, ensayar
recuperación con un backup histórico real, revisar/activar catálogos y
correspondencias con series oficiales de materiales, completar los flujos
reales de documentos/BIM y validar seguridad y despliegue. Salarios/FASAR,
maquinaria y energía requieren sus propios modelos y evidencia; no reciben
un porcentaje agregado de inflación de materiales.
