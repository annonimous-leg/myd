# Verificación real de IFC y continuación Workspace

Base: `d7206165ea65fb0c9710b3bf4b99a17ad430ad92`, rama
`feat/bim-cad-continuacion`, PR #11. Fecha: 2026-11-10.

## IFC utilizado y ejecución real

El adjunto `wall_millimetres.ifc` coincide byte por byte con el fixture del
repositorio: SHA-256
`883b58f40ddda07d29eecb0435701e805185be709a5385d2e4978ebae2da1234`.
La prueba acepta ahora `BIM_ACCEPTANCE_IFC` para cargar explícitamente un archivo
externo; mantiene el fixture original cuando esa variable no se especifica.

Primero se ejecutó el flujo existente sobre `d720616`: **1 prueba real aprobada**.
Después de las correcciones se ejecutaron las dos pruebas de
`tests/bim-flow-browser.test.mjs`: **2 aprobadas, 0 fallidas**, sin interceptar HTTP.
Se usó el adjunto del usuario, PostgreSQL/PostGIS 16/3.4, Redis 7, API FastAPI,
dispatcher, Celery, almacenamiento de IFC en disco y Supabase Storage 1.74.0 real
con bucket privado para los documentos. Todas las identidades y precios fueron
sintéticos; no se accedió a una cuenta cloud ni a datos de producción.

Las imágenes Docker por capas excedieron el espacio local. Se ejecutaron las
mismas versiones oficiales aplanadas en una sola capa; un proxy HTTP local añadió
el prefijo `/storage/v1` para el servidor Storage. No simuló sus respuestas.
Se verificó después que las 115 tablas migradas conservaban sus columnas.

La siembra admite `BIM_LOCAL_ACCEPTANCE=1` en staging para reproducir la prueba
local. Conserva la comprobación de base exacta `bim_acceptance` y host local.

## Correcciones observadas

- **Orientación:** el muro estaba acostado. IFC utiliza Z vertical; Three.js y
  sus controles utilizaban Y vertical. La transformación se aplica exclusivamente
  en el grupo de escena. La prueba geométrica comprueba vertical de 3 m y
  conservación de distancias.
- **Originales y cantidades:** ocultar tipos, cambiar colores y girar la vista
  no altera el servidor. La prueba real oculta/restaura el muro, compara todos
  los elementos recibidos y descarga el IFC original verificando sus bytes.
- **Móvil:** visor e inspector se recorren con el estudio completo bajo 1024 px;
  en escritorio el inspector mantiene desplazamiento independiente. Los factores
  económicos ajustan sus columnas a un mínimo de 115 px.
- **Tema:** claro predeterminado y oscuro seleccionable, compartido entre
  cabecera, BIM y documentos. Conserva la selección al recargar. El estudio ya
  no bloquea el tema con variables locales blancas.
- **Workspace:** entrada autenticada predeterminada y nombre visible correcto.
  Bandeja cerrada por defecto para Workspace, Tezcatlipoca y Firma / Field SAT,
  con teclado, Escape y foco del menú gestionados por Radix.
- **Edición:** confirmaciones dentro de la aplicación; el editor intercepta
  navegación interna con cambios pendientes. La prueba intenta salir a
  Tezcatlipoca, cancela y verifica que el texto sigue presente. Guardado de nueva
  versión, historial y rechazo de actualización obsoleta con 409 pasan contra API.
- **Errores:** el fallo del vínculo de presupuesto deja de ocultarse antes de
  compilar. La carga múltiple retira de la cola cada archivo aceptado y conserva
  los pendientes si uno falla.

## Verificación complementaria

- `npm run build`: aprobado; permanece la advertencia de Vite por chunks grandes.
- `npm run test:browser`: disposición, tema, recarga, menú y controles de vista en
  1440×900, 1024×768, 390×844 y 390×500; también login y estilos semánticos.
- `node --test tests/bim-view.test.mjs tests/session-client.test.mjs tests/expediente-store.test.mjs`:
  aprobado.
- `pytest tests/unit/test_bim_units.py tests/integration/test_bim_drawing_ifc.py -q`:
  **9 aprobadas**, con advertencias de deprecación existentes.
- ESLint de nuevos componentes, hook de tema, cabecera y navegación revisados:
  sin errores ni advertencias.
- `designmd lint DESIGN.md`: **0 errores, 0 advertencias**.
- Auditor estático de interfaz en modo estricto: **24 hallazgos**, sin propietarios
  canónicos sin resolver. Incluye formularios y textareas heredados y falsos
  positivos en primitivas que reciben acciones por props. No se presenta la
  auditoría global como aprobada ni se desactiva validación de otros módulos.

Las capturas y trazas completas permanecen locales en `/tmp/meg-review-final` y
`/tmp/meg-review-layout-final`, con logs separados. La disposición usa fixtures
HTTP; se distingue expresamente de las dos pruebas de backend real.

## Estado frente al flujo solicitado

| Capacidad | Estado de esta continuación |
|---|---|
| Workspace como núcleo, blanco y oscuro seleccionable | Implementado y probado para las superficies indicadas |
| Carga de requisitos, extracción y revisión humana | Flujo existente probado con fuente real sintética, versiones e historial |
| Entrada inicial guiada que distribuya todos los documentos, catálogo y técnicos | Pendiente de integración; el acceso orienta hacia una obra real, sin simular carga |
| Preparación automática completa y en paralelo de todas las plantillas | Hay jobs y servicios existentes; no se acepta integralmente en esta ronda |
| Bienvenida con escualo y elección de primera vista por disponibilidad | Conservado en la especificación; pendiente |
| Visor, ocultación de elementos, color, giro y panel económico independiente | Implementado; ajustes de vista separados de cantidades |
| Edición CAD persistente y confirmación de una revisión de diseño | Pendiente; las herramientas actuales son de revisión visual |
| Resolución 4K garantizada y exportación CAD general | Pendiente de aceptación específica; planos PDF/SVG/DXF e IFC original sí probados |
| Presupuesto, planos, cantidades faltantes, 4D y apertura en Workspace | Flujo real probado, incluidos límites de permisos y recuperación tras reinicio |
| Aceptar/pedir cambios, contratos, CV y posiciones de firma de todos los formatos | No aceptado integralmente; no sustituir por aprobación masiva sin versiones |
| Sistema solar integrado y todas las capas Tezcatlipoca | Pendiente del desarrollo e integración completos |
| Street View, colocación de BIM y bloqueo del fondo | Alcance conservado, pendiente del plan detallado del usuario y proveedores |
| Evidencia georreferenciada → Workspace → ZIP final completo | Pendiente de aceptación integral; no se declara cumplido por una descarga de presupuesto |

Decisión de navegación: scroll independiente del inspector en escritorio;
cronograma y presupuesto siguen accesibles junto al visor y el programa se edita
en Workspace. No se reduce el alcance del sistema solicitado ni se declara la
plataforma completa o lista para producción con esta prueba.
