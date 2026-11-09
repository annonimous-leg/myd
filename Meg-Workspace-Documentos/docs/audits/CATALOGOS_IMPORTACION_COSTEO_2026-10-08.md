# Importación y costeo de catálogos reales — checkpoint de implementación

Megalodon prepara propuestas del licitante. Esta implementación no convierte
la herramienta en una plataforma convocante ni publica catálogos privados.

## Problema reproducido y cambio

Los paquetes CMIC/CFE y Varela existían y sus 42 PDF originales fueron
cotejados, pero el verificador no alimentaba el catálogo de costeo. El CSV del
libro era otro contrato; copiar estos CSV a su ruta no constituía una importación.

Se añadió importación por tenant, edición y selección explícita de fuentes.
Guarda todas las filas seleccionadas, incluida evidencia de páginas, reglas,
componentes e incidencias. Identidades, hashes y estados permanecen consultables.
Solamente las proyecciones habilitadas alimentan `CatalogoAPU`; las pendientes
conservan sus datos y motivos. No se ejecuta SQL recibido.

Una transacción confirma edición, registros y proyecciones juntos. Un fallo
revierte todo. La clave única de edición y el bloqueo durante importación del
tenant protegen reintentos concurrentes. No se sobrescribe una edición anterior.
Las proyecciones importadas rechazan edición y borrado por API. Antes de costear
se contrastan con las filas y componentes de la edición persistida.

La ruta de crear presupuesto resuelve identidad, unidad, precio y APU en el
servidor. La ruta de agregar/asignar concepto usa la misma resolución; mantiene
la cantidad medida y su evidencia. Cada partida guarda un snapshot verificable.
Excel/PDF incluyen procedencia y páginas; Excel también guarda hashes de fila y
paquete. Cambiar otra edición no revaloriza presupuestos históricos.

## Precisión CMIC

Un consumo real de 0.227273 jornadas por unidad se perdía en `Numeric(18,4)`.
La API de insumos y `insumos.cantidad` ahora conservan seis decimales; las
cantidades de obra siguen teniendo cuatro. La migración impide un downgrade que
redondee consumos o elimine ediciones importadas con evidencia histórica.

La importación verifica el importe de cada componente y el cierre del APU.
Un rendimiento por división solo se normaliza a consumo si los seis decimales
persistibles reproducen exactamente el centavo publicado. Las fórmulas de costo
horario se conservan como evidencia de un insumo observado; no se inventa un APU.

## Evidencia con los paquetes auténticos

Ejecución contra API de la aplicación, SQLite de pruebas y Redis real, usando
los paquetes privados y sus PDF originales. Las identidades de usuarios y el
expediente de aceptación son sintéticos; los registros de catálogo de este caso
proceden de los paquetes recuperados, no de un seed de precios de mercado.

| Caso ejecutado | Resultado observado |
|---|---|
| CMIC educativa E01.024, cantidad 2.4 m³ | PU 152.43; importe 365.83; consumo 0.227273 persistido |
| Recarga y dos recálculos por API | Conservan el consumo y el importe |
| Validación y aprobación por usuario administrador de pruebas | Transiciones aceptadas en ese presupuesto completo |
| Excel/PDF descargados por API y reabiertos con lectores independientes | Importe, clave y procedencia presentes; hashes cotejados |
| Reimportar la misma selección | Recupera la edición existente sin duplicarla |
| Varela casa clase 2 SHF, modelo 01-002, 43 m², Aguascalientes FIC 0.897, ajuste 1 | Antepresupuesto persistido 333486.02 MXN |
| Varela casa clase 1, modelo 01-001 | Mantiene cuarentena por componentes pendientes; no se habilitó para hacer pasar la prueba |
| Incidencia CMIC educativa con costos de resumen/análisis distintos | Conserva cuarentena; no genera proyección cotizable |

La prueba auténtica requiere `MEGALODON_CMIC_PACKAGE`,
`MEGALODON_VARELA_PACKAGE` y `MEGALODON_CATALOG_ORIGINALS`. Sin los archivos
privados se omite explícitamente; los fixtures públicos se rotulan sintéticos.
Los datos privados y el informe completo de esa corrida no se añaden a Git.

## Cobertura de importación y pendientes reales

Para evitar sustituir datos recientes por un agregado antiguo se importaron
las ocho fuentes del paquete CMIC/CFE autorrecuperable y solamente las 34 fuentes
Varela del agregado cuyo manifiesto fue reparado en sus dos conteos. Ningún CSV,
precio, flag de revisión o incidencia fue modificado por esa reparación.

| Selección | Registros conservados | Conceptos cotizables | Insumos | Modelos paramétricos | Factores FIC |
|---|---:|---:|---:|---:|---:|
| CMIC/CFE | 19151 | 1186 | 373 | 0 | 0 |
| Varela | 6464 | 0 | 0 | 28 | 167 |

Estos conteos describen registros y proyecciones diferentes; no equivalen a
25615 APU independientes. No acreditan cobertura total de precios revisados.

CMIC/CFE conserva 3198 partidas en cuarentena: 1332 por tratamiento de IVA sin
declaración en el paquete CFE, 688 por unidades no interpretables, 545 por tipo
insumo/concepto ambiguo, 301 por cierre aritmético, 179 por tipo de componente,
151 por importe no reproducible y dos por otros bloqueos. Los motivos pueden
superponerse. Son diagnósticos de importabilidad, no una afirmación de que los
catálogos originales sean inauténticos. Hay que cotejar los registros afectados
y resolver la extracción con evidencia antes de habilitarlos.

Varela conserva 1366 ensambles sin precio como referencias y no como APU. Sus
105 modelos no se declararon todos operables: el estado de componentes y unidades
deja 28 habilitados para estimación. El cálculo paramétrico guarda modelo,
localidad, FIC, cantidad, ajuste, justificación, actor y hash. Su resultado declara
`apto_aprobacion_contractual=false`; no se convierte automáticamente en un precio
contractual. Revisar unidades/componentes pendientes sigue siendo trabajo abierto.

Los precios conservan su fecha original. Este checkpoint no aplica inflación
uniforme ni acredita nuevas series oficiales; la actualización por insumo,
ubicación y período requiere su correspondencia y evidencia independientes.

## Operación y verificación

En pantalla: **Presupuesto → Catálogos CMIC / fuentes** ofrece verificación de
ZIP, selección explícita de fuentes, edición importada, consulta de pendientes,
selección de conceptos y estimación paramétrica. Los precios enviados por la UI
son informativos: guardar siempre vuelve a resolverlos desde el catálogo.

`CATALOGO_ORIGINALES_DIR` debe apuntar al directorio privado de PDF originales
del servidor. Una instalación sin esa configuración responde 503 al importar.
La importación por CLI exige un usuario existente y fuentes explícitas:

```sh
python -m scripts.import_catalog_package --package /privado/paquete \
  --originals /privado/pdf --user-id UUID --source cmic_educativa_2026
```

Las regresiones públicas ejecutan importación, rollback, reintento, aislamiento,
permisos, rechazo de manifiesto alterado, costeo desde catálogo y exportaciones.
La concurrencia exige PostgreSQL y se omite en SQLite; no se acredita con esa
omisión. CI de navegador incorpora carga/importación/estimación/costeo por la UI
contra API, PostgreSQL y Redis reales, con paquete sintético explícito.

**NO GO de producción general.** La evidencia auténtica local no demuestra
Supabase real, todos los precios revisados, los restantes motores ni la operación
con todos los catálogos, usuarios, modelos grandes y escenarios de recuperación.
Los resultados definitivos de PostgreSQL/migraciones/navegador del commit deben
registrarse por ejecución; compilar la interfaz o acumular tests no los sustituye.

## Seguimiento de ejecución — 9 de octubre

La ejecución 156 sobre `7563d81` terminó con integración core/API/Procurement,
frontend, auditoría Python y análisis estático aprobados. Dos jobs fallaron:
el generador del catálogo sintético no creaba un directorio padre inexistente,
y el ensayo de recuperación histórica no incluía las tres tablas nuevas en su
inventario esperado. El recorrido BIM de esa ejecución **no llegó a ejecutarse**.

Se corrigió el generador con una regresión que verifica el paquete desde un
directorio nuevo. El ensayo histórico exige las tablas nuevas vacías, compara
todos los valores históricos y rechaza decimales adicionales inventados antes
de normalizar la representación textual. El consumo se migra a `numeric(20,6)`:
conserva los 14 dígitos enteros anteriores, además de los seis decimales. La
prueba PostgreSQL incluye el máximo histórico `99999999999999.9999` y exige que
un downgrade con consumo `0.227273` falle sin cambiar datos ni esquema.

Los PDF, CSV y paquetes auténticos utilizados permanecen privados. El repositorio
contiene código, fixtures sintéticas explícitas y el alcance de las comprobaciones.

La ejecución 157 sobre `b252d09` aprobó recuperación histórica, integración
core/API/Procurement y auditorías. El navegador reprodujo un defecto de diseño:
el panel de importación se contraía dentro de una columna flex al coexistir
con el panel de índices, y otros controles interceptaban sus clics. Se cambió
el presupuesto a un flujo de contenido con desplazamiento vertical y altura
reservada para las barras de navegación. Se mantiene la regresión con ambos
paneles abiertos y clics normales, sin `force`. La rejilla muestra hasta cuatro
decimales de cantidad; el recorrido añade `0.0420` y exige que se vea `0.042`,
se persista y produzca 6.40 MXN al aplicar PU 152.43. El resultado de ese nuevo
recorrido debe registrarse después de ejecutarlo.

La ejecución 158 sobre `ef34a4a` confirmó que el solapamiento estaba corregido:
el navegador abrió el panel, verificó el ZIP e importó la edición. Después
falló al localizar el selector de modelo por su nombre accesible. Los selectores
anidados en labels incorporaban el texto de sus opciones a ese nombre; ahora
declaran explícitamente el mismo nombre que su etiqueta visible. No se sustituyen
los controles por llamadas API en la aceptación.

Una regresión adicional reprodujo una escritura con la identidad previamente
cargada después de revocarle el rol en otra sesión. Importar y estimar ahora
bloquean organización → usuario, vuelven a leer actividad, rol y versión de
sesión y mantienen esos locks hasta confirmar o revertir. El orden coincide
con administración de identidades. Las regresiones cubren rol, desactivación,
revocación de sesión y, en PostgreSQL, revocación mientras ambas operaciones
esperan el lock de la organización. Los rechazos deben dejar cero nuevas
ediciones/estimaciones; la validación también revierte la transacción.

La ejecución 159 sobre `2a8a33e` aprobó las ocho regresiones de permisos en
PostgreSQL y la reimportación concurrente. El navegador importó, estimó y
seleccionó ambos consumos; guardar encontró otro defecto real: GET y POST del
mismo path compartían contador Redis, aunque tenían políticas de 100/min y
10/min respectivamente. La traza registra 14 consultas y un primer POST
rechazado con 429, sin escrituras anteriores en ese endpoint. La clave ahora
incluye el método HTTP. Una API de regresión usa el limiter y Redis reales:
permite 100 lecturas y diez escrituras independientes y rechaza la siguiente
de cada clase con 429 y `Retry-After: 60`. No aumenta cuotas, cambia políticas
de fallo ni deshabilita la protección para pasar el navegador.

## Checkpoint confirmado — 10 de octubre

Runtime: `44cfccd93133d0eea40686514d621e0102a6e323`. La
[ejecución 160](https://github.com/ytpremiumcr7-collab/Meg/actions/runs/37884794571)
terminó con los ocho jobs aprobados, incluido el navegador contra API,
PostgreSQL, Redis y workers reales. El recorrido importa la edición por pantalla,
persiste la estimación paramétrica de 130128.36 MXN como no contractual, selecciona
el concepto importado y guarda cantidades 2.4 y 0.0420: importes 365.83 y 6.40,
total 372.23 MXN. También ejecuta el flujo BIM, recuperación de workers, bloqueo
de cobertura incompleta, aprobación, lectura de Excel/PDF, 4D y topografía
descritos en la aceptación. Los datos de esta ejecución pública son sintéticos
y están identificados como tales; no son los catálogos privados.

La batería local final terminó con 553 aprobadas, 18 omitidas y cero fallos
en 99.10 s. Las regresiones de PostgreSQL prueban importación concurrente,
revocación de permisos y revocación mientras se espera el lock. Las pruebas
privadas de CMIC/Varela se ejecutaron por separado con los PDF originales y
sus registros: el costeo contractual CMIC de 365.83 MXN llegó a aprobación y
exportaciones leídas; Varela conservó 333486.02 MXN como antepresupuesto, sin
autorizar aprobación contractual. No se subieron esas fuentes a GitHub.

Este checkpoint cierra las rutas y defectos enumerados en este informe.
**NO GO general permanece** por los límites registrados: Supabase real, escala,
cobertura de los restantes motores y fuentes aún pendientes de revisión.
Los cuatro tabuladores SICT del informe diario constituyen trabajo siguiente,
no se declaran importados ni certificados por esta ejecución.
