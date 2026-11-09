# Continuidad SICT: extracción y revisión de pendientes

## Base comprobada

Trabajo sobre `fix/prr-regressions-2026-10-07`, base
`843d42f48c6204f2a5ca2edc0250639640750189`. Al comparar las nueve ramas,
esta contiene 156 commits adicionales a main y 94 a
`codex/costeo-sesiones-2026-09-30`, sin commits exclusivos en esas dos bases.
Las ramas de auditoría tienen pruebas divergentes; no se fusionaron ni se
presenta este trabajo como auditoría total del repositorio.

El importador SICT ya existía desde el 10 de octubre. Se revisaron extractor,
verificación de paquetes, proyección del catálogo, cálculo paramétrico,
consulta API y pantalla de importaciones antes de modificar esas rutas.

## Defectos corregidos y alcance

1. **70 carreteras hidráulicas quedaban bloqueadas por espacios del PDF.**
   El extractor entrega `CONCRETOHIDRÁULICO` en descripciones auténticas, pero
   el clasificador exigía `CONCRETO HIDR`. La clasificación ahora normaliza
   espacios y diacríticos sólo para comparar, conservando el texto original.
   Si aparecen ambos materiales, se mantiene pendiente en lugar de elegir
   asfalto por orden de evaluación. No se asignan FIC a estructuras o
   entronques cuya correspondencia no quedó acreditada.
2. **La unidad de seis entronques se incorporaba a la descripción.**
   El límite anterior de columna era x=451; `Entronque` comienza en x=446.47
   y la descripción termina cerca de x=441. El corte x=444 fue cotejado con
   la página 98 renderizada. Los seis conservan su unidad; siguen pendientes
   de clasificación, sin sustituirla por lote ni fabricar precios.
3. **La pantalla no mostraba todos los pendientes que contaba.**
   El total incluía modelos y factores, pero la consulta sólo traía partidas.
   La API permite consultar todas las tablas mediante `tabla=*`, devuelve
   el tipo de registro y ordena de forma estable para paginar. La consulta
   por tabla y su valor predeterminado conservan su comportamiento. La UI
   muestra tipos, nombres, motivos, valores, unidades y evidencia original;
   distingue carga, error y resultado vacío y permite reintentar.

La revisión visual se limitó a las páginas 84 y 98 de paramétricos; el
recorrido estructural cubrió las páginas y anclas de los tres PDF adjuntos
de construcción, servicios y paramétricos. Esto no certifica revisión visual
exhaustiva de las 701 páginas de los cuatro originales.

## Catálogo regenerado

Se recuperó además el original de maquinaria aportado previamente por el
usuario. Se cotejaron los cuatro SHA-256 con sus archivos originales, todos
de febrero de 2026. No se modificaron los PDF ni las ediciones importadas
anteriormente. La nueva extracción queda identificada como `sict-dgst-v2`.

| Resultado operativo | Cantidad |
| --- | ---: |
| Fuentes originales cotejadas | 4 |
| Páginas conservadas | 701 |
| Filas de partidas/insumos extraídas | 4,726 |
| Conceptos cotizables | 3,953 |
| Insumos horarios | 735 |
| Modelos paramétricos conservados | 417 |
| Modelos paramétricos habilitados | 344 |
| FIC por localidad/especialidad | 165 |
| Registros en cuarentena | 111 |

De los 73 modelos todavía pendientes, tres tienen códigos duplicados y 70
no tienen especialidad habilitada. Las 14 partidas con códigos repetidos y
24 insumos con columnas ambiguas permanecen bloqueados. No se inventaron
matrices APU para precios observados. Los modelos continúan siendo
antepresupuestos no aprobables como propuesta contractual.

Huella del paquete regenerado:
`0301e0f23ea716ddff87876d12287fa76d634ac4941a1b760dd0c9ef4dc6ab14`.
Los CSV y PDF se mantienen fuera del repositorio; el ZIP entregable contiene
el paquete importable y este informe, no los originales.

## Verificación ejecutada

- Instalación: `uv sync --frozen --extra dev`, salida 0.
- Antes de corregir: tres regresiones del extractor fallaron por clasificación
  vacía, selección indebida del material mixto y unidad vacía. La prueba de
  consulta de pendientes falló porque devolvía total 0 en lugar de 3.
- Después: 53 pruebas aprobadas, 4 omitidas. Comando:

```sh
MEGALODON_SICT_PACKAGE=/ruta/al/paquete \
MEGALODON_SICT_ORIGINALS=/ruta/a/originales \
.venv/bin/python -m pytest \
  tests/integration/test_sict_catalogo.py \
  tests/integration/test_catalogo_importacion.py \
  tests/unit/test_catalogo_package.py \
  tests/integration/test_catalogo_libro_costeo.py -q --disable-warnings
```

Las omisiones son tres pruebas que requieren PostgreSQL y una aceptación
privada CMIC/Varela cuyos paquetes no se suministraron a esta ejecución.
La aceptación SICT sí se ejecutó con los cuatro PDF reales. Usa la API real
y SQLite local; no demuestra bloqueos o migraciones PostgreSQL. Redis no
estaba disponible: el modo desarrollo utilizó su comportamiento existente
sin Redis; no se cambiaron cuotas ni controles de producción.

La aceptación conserva los recorridos de servicio CA1010.1010 y construcción
101.03.1100 hasta presupuesto, recálculo, aprobación y lectura de Excel/PDF;
comprueba los tres modos horarios y el modelo asfáltico A21A1P. Se añadió el
hidráulico ET42H1P de la página 84: 76,269,489 MXN/km × 2.4 km × 1.0970
= **200,802,310.64 MXN**, guardado y recuperado por API. Su evidencia mantiene
`apto_aprobacion_contractual=false`. ENTA42C conserva unidad Entronque y su
estado pendiente.

Frontend: `npm ci --no-audit --no-fund` y `npm run build`, salida 0. Hay avisos
existentes por bundles superiores a 500 kB. La instalación de Chromium falló
por un archivo descargado incompleto; no se certifica interacción visual
en navegador. Las pruebas emiten advertencias previas de Pydantic y ciclos
de claves foráneas SQLite. `git diff --check` sin errores.

## Pendientes delimitados

- Construcción de julio sigue sin incorporarse. La página oficial enlaza esa
  vigencia, pero el lector web rechaza el tamaño y la descarga local devolvió
  HTTP 502. El importador conserva su rechazo explícito a esa edición hasta
  cotejar su estructura. No se reetiquetó febrero como julio.
- No se actualizó crp-pa, no se importaron datos en producción ni se cambiaron
  estados de procedimientos externos.
- Conciliación documental de fechas, casos Corredor/CFE y dragado portuario
  del brief no forman parte de este cierre SICT. Tampoco se tocaron permisos
  de GitHub ni límites de PR.

Referencias oficiales consultadas el 11 de octubre de 2026:

- https://micrs.sct.gob.mx/infraestructura/direccion-general-de-servicios-tecnicos/tabulador/
- https://micrs.sct.gob.mx/images/DireccionesGrales/DGST/Tabulador/TCC_V1_6-Jul-26.pdf

Este documento acredita un cierre del flujo indicado; no declara el producto
completo listo para producción ni sustituye la verificación de CI del commit.
