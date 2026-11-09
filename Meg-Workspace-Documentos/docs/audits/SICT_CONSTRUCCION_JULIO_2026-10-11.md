# SICT construcción: incorporación de la edición de julio de 2026

Continuación del cierre de febrero documentado en
`SICT_CONTINUIDAD_2026-10-11.md`. Base de código:
`e1d5fe2580536315810cb86e67219102f0afb0cd`, rama
`fix/prr-regressions-2026-10-07`.

## Fuente y alcance

El usuario aportó `TCC_V1_6-Jul-26.pdf`. Se leyeron sus 485 páginas mediante
extracción de texto; las páginas 2 y 3 declaran edición julio y aplicación
a partir del **1 de julio de 2026**. Huella del original:

`91240656edcc3c7dbeb92c1765ab61fe37e7019419392828835951624b62d772`.

Esta entrega resuelve la ausencia del PDF señalada en el informe anterior.
Se habilita exclusivamente construcción de julio; servicios, maquinaria y
paramétricos de julio siguen sin perfil documental verificado. Las ediciones
de febrero mantienen su vigencia y sus identidades, sin reetiquetarse.

## Cotejo de estructura y diferencias

El catálogo comienza en la página PDF 88. Conserva los límites de columna
del perfil de construcción. Se recorrieron todas las anclas de código desde
la página 87: **3,825 extraídas y ninguna omitida**. Cada fila tiene una
columna monetaria y unidad. Un cotejo independiente mediante PyMuPDF de esas
3,825 parejas de precio/unidad coincidió con la extracción pdfplumber.

Se inspeccionaron visualmente las páginas 88, 91 y 141. Esto **no certifica
revisión visual de las 485 páginas ni de todas las descripciones**. La
validación del catálogo sigue marcada como estructural.

Respecto del paquete de febrero:

- Julio tiene 3,825 filas frente a 3,828 de febrero.
- Ya no aparecen `102.10.1110`, `302.06.1110` y `302.09.1100`; no se copian
  desde la edición anterior para rellenar la nueva.
- Entre 3,811 códigos únicos comparables, 3,508 precios cambiaron y 303
  permanecieron iguales. Se compararon valores publicados, sin inflación
  estimada ni multiplicador general.
- Siguen repetidos siete códigos: `107.05.2040`, `107.05.2041`,
  `107.05.2042`, `107.05.2043`, `107.07.2040`, `107.07.2045` y
  `107.07.2050`. Sus 14 filas quedan en cuarentena.

## Paquete y comportamiento

El extractor `sict-dgst-v3` registra fecha documental, SHA-256, páginas y
coordenadas de las filas. El paquete suplementario contiene sólo julio:
12 CSV, manifiesto de integridad y este informe. No incluye el PDF original.

| Resultado | Cantidad |
| --- | ---: |
| Fuentes cotejadas contra original | 1 |
| Páginas de evidencia | 485 |
| Filas de precios conservadas | 3,825 |
| Conceptos cotizables estructuralmente | 3,811 |
| Filas en cuarentena | 14 |

Huella del paquete:
`6613caa236ce9faf394593838b3859ef426a9599fd0033753f1b0ff33dbf725e`.

Identidad de fuente: `SICT_DGST_CONSTRUCCION_91240656edcc3c7d`.
Se conservan las condiciones originales de costo directo; no se fabrican
componentes APU ni se aplican factores regionales automáticamente.

Las importaciones existentes de febrero no se borran ni modifican. Julio se
importa como edición distinta y repetir exactamente su importación devuelve
la misma identidad. El usuario selecciona la fuente aplicable; esta entrega
no introduce selección automática de la edición más reciente ni reclasifica
presupuestos históricos. No se cargaron datos en producción.

## Verificación del flujo

Antes del cambio, las nuevas pruebas de construcción fallaron porque el
extractor rechazaba julio. Después se verificaron tanto PDF sintéticos
explícitos para CI como las dos ediciones auténticas suministradas.

Caso documental `101.03.1100`, página 91 de julio:

| Edición | Precio publicado por m³ | Cantidad | Total de costo directo |
| --- | ---: | ---: | ---: |
| Febrero | 92.07 MXN | 2.4 m³ | 220.97 MXN |
| Julio | 92.31 MXN | 2.4 m³ | 221.54 MXN |

El recorrido ejecuta importación, presupuesto por API, dos recálculos,
validación, aprobación y lectura de Excel/PDF. Tras importar julio se vuelve
a exportar el presupuesto aprobado de febrero y se comprueban su importe
original y la huella de su fuente. También se comprueban las dos fechas,
identidades distintas y la idempotencia de ambas importaciones.

Resultado local: **56 aprobadas, 4 omitidas**. Las omisiones son tres pruebas
de bloqueo PostgreSQL y una aceptación privada CMIC/Varela. Las aceptaciones
auténticas SICT de febrero y julio sí se ejecutaron. Se usa SQLite local y
el comportamiento existente de desarrollo sin Redis; esto no acredita
infraestructura de producción. La suscripción del tenant desechable de
prueba se registra como sintética y sin pago; los cálculos y exportaciones
usan los servicios reales.

```sh
MEGALODON_SICT_PACKAGE=/ruta/paquete-febrero \
MEGALODON_SICT_JULY_PACKAGE=/ruta/paquete-julio \
MEGALODON_SICT_ORIGINALS=/ruta/originales \
.venv/bin/python -m pytest \
  tests/integration/test_sict_catalogo.py \
  tests/integration/test_catalogo_importacion.py \
  tests/unit/test_catalogo_package.py \
  tests/integration/test_catalogo_libro_costeo.py -q --disable-warnings
```

Para regenerar julio, desde `backend`:

```sh
.venv/bin/python -m scripts.prepare_sict_catalog \
  --construccion /ruta/TCC_V1_6-Jul-26.pdf \
  --destination /ruta/nueva-edicion-julio
```

El destino debe ser nuevo. La importación requiere cotejar el PDF original
y elegir expresamente un usuario existente y la fuente mediante el flujo
de importaciones o `scripts.import_catalog_package`.

El frontend y el esquema de base de datos no cambian. La conciliación de
licitaciones, el caso portuario y la revisión integral de MEGALODON siguen
fuera de este bloque.
