# SICT DGST — importación y costeo operativo, 10 de octubre de 2026

Megalodon prepara propuestas de licitación. Este trabajo incorpora referencias
SICT al catálogo del licitante; no convoca, adjudica ni publica procedimientos.
Los PDF y las tablas extraídas siguen privados. Sólo código, fixtures sintéticas
identificadas y esta evidencia resumida se versionan en GitHub.

## Ediciones contrastadas

Se recuperaron los cuatro originales aportados: construcción (485 páginas),
servicios (57), maquinaria (52) y paramétricos (107). **Los cuatro PDF recibidos
son de febrero de 2026**, aplicables desde el 1 de febrero. El inventario oficial
SICT actualmente enlaza otra edición de construcción, aplicable desde julio:

- Inventario: https://micrs.sct.gob.mx/infraestructura/direccion-general-de-servicios-tecnicos/tabulador/
- Construcción julio: https://micrs.sct.gob.mx/images/DireccionesGrales/DGST/Tabulador/TCC_V1_6-Jul-26.pdf
- Servicios: https://micrs.sct.gob.mx/images/DireccionesGrales/DGST/Tabulador/TServicio-2026.pdf
- Maquinaria: https://micrs.sct.gob.mx/images/DireccionesGrales/DGST/Tabulador/TCMaquinaria_2026.pdf
- Paramétricos: https://micrs.sct.gob.mx/images/DireccionesGrales/DGST/Tabulador/TCParametricos_2026.pdf

El archivo de julio **no se obtuvo**: el lector web rechaza su tamaño y las
solicitudes locales devolvieron HTTP 502. No se reetiqueta febrero como julio,
no se inventa su actualización y el extractor rechaza esa edición hasta
verificar su estructura. No falta el original de maquinaria: se recuperó de
los archivos del usuario. Las identidades SHA-256 cotejadas son:

| Fuente original | SHA-256 |
| --- | --- |
| Construcción febrero | 09e89c5b02bad5f9899d3962ea0f78a14887d362b6cdadac41c61d0c438fe72f |
| Servicios febrero | 6eefa2aef4e98038c70dc62f985883dbd864d72db7be72b26d2a710c2a50e4f6 |
| Maquinaria febrero | a5eb2d793a6bd7934c409297d612198b838571ff122f7ecb8240fc5729d83609 |
| Paramétricos febrero | 45be5ec460bf30f3a513d5383eb799954f4df9fda7123cd1d7906df3d593b8c1 |

## Comportamiento implementado

El adaptador PDF usa las columnas del catálogo, excluye cuadros resumidos y
precios de ejemplo, guarda todas las páginas, coordenadas y palabras de cada
fila y genera los doce CSV del contrato ya importable por API/CLI. Los archivos
fuente no se modifican. Vigencia e identidad pertenecen a cada documento, y
la importación conserva la edición previa, su aislamiento y atomicidad.
No se ejecutan SQL ni scripts recibidos.

Los servicios conservan unidades como km-carril, sondeo, análisis, muestra o
informe; no se convierten a lote. Construcción conserva m³, dm³, m³/hm y otras
unidades documentales. El precio observado no fabrica un desglose de insumos.
La base sin IVA de servicios consta expresamente en su metodología. Para
construcción/maquinaria se exige simultáneamente declaración de costo directo,
metodología de deducción del impuesto y perfil de fuente SICT correspondiente.
Se conserva esa evidencia y sus excepciones (combustibles/IEPS, bienes exentos),
sin descontar IVA otra vez ni recalcular el precio publicado. Esto documenta
cómo usar el precio observado; no constituye auditoría fiscal del tabulador.

Maquinaria mantiene tres insumos distintos por serie: ACTIVO, ESPERA y RESERVA.
Los valores de adquisición USD/MXN siguen como evidencia y no se confunden con
costos horarios. Se asignan por posición de columna; una celda ausente no
desplaza las siguientes. Filas ambiguas permanecen en cuarentena.

Los modelos paramétricos no se convierten en APU contractual. Los FIC conservan
sus cinco columnas por ciudad: general, carretera asfáltica, carretera hidráulica,
estructuras de concreto y metálicas. Para calcular se exige la especialidad
correspondiente y la misma fuente SICT del modelo; se rechazan General y otras
especialidades. También se rechazan familias de fuentes distintas aunque estén
en el mismo lote. Se conservan acarreos incluidos a 10 km y no se añade inflación.
Las estructuras cuya especialidad no quedó inequívoca siguen pendientes.

La pantalla consulta todos los modelos/factores paginados, filtra FIC según
modelo y borra la elección anterior al cambiarlo. El presupuesto paramétrico
se presenta como tal, conserva alcance/fuente y requiere análisis contractual.

## Resultado de importación privada

La extracción conserva 701 páginas, 4,726 filas de precio, 417 modelos,
165 factores y 68 referencias/encabezados. Estas cantidades **no equivalen a
APU completos ni a revisión visual exhaustiva**.

| Fuente | Habilitados | Pendientes conservados |
| --- | --- | --- |
| Construcción febrero | 3,814 conceptos con precio observado | 14 filas con códigos repetidos |
| Servicios febrero | 139 conceptos con precio observado | 0 filas de precio pendientes en este corte |
| Maquinaria febrero | 735 insumos horarios | 24 filas con columnas ambiguas |
| Paramétricos febrero | 274 modelos y 165 FIC por columna/localidad | 143 modelos por especialidad pendiente/códigos repetidos |

En total: 3,953 conceptos, 735 insumos, 274 modelos y 181 registros en cuarentena.
Tres modelos comparten el código impreso PSV6C4C en la misma página: se conservan
los tres con identidades distintas y se bloquean. Los registros sin precio se
conservan como referencia; no se presentan como precio cero cotizable.

## Operaciones ejecutadas

La aceptación privada importa los cuatro documentos y usa sesiones/roles
reales contra API, SQLite y Redis de pruebas:

- Servicio CA1010.1010, estudio topográfico, página 43: 2.4 km × 33,532.23
  = **80,477.35 MXN**. Presupuesto guardado, recargado/recalculado dos veces,
  validado/aprobado y Excel/PDF descargados y leídos, con fuente/hash.
- Construcción 101.03.1100, corte en material tipo A, página 91: 2.4 m³ × 92.07
  = **220.97 MXN**, con el mismo recorrido hasta leer los entregables.
- Maquinaria 1011: 100.81 activo, 83.85 espera, 3.22 reserva por hora, verificados
  en las proyecciones persistidas. Esto no acredita un APU específico con
  rendimientos de obra, ni que todos los costos horarios sean correctos.
- Paramétrico A21A1P, página 42: 30,037,837 MXN/km × 2.4 km × FIC asfáltico
  Aguascalientes 1.1155 = **80,417,297.22 MXN**. Guardado y recargado como
  antepresupuesto no contractual, conservando acarreos a 10 km.

La regresión de especialidad contra el runtime anterior b90ba7e falló por
**DID NOT RAISE**: aceptaba FIC general para un modelo asfáltico. La nueva
implementación rechaza General/hidráulico sin guardar estimaciones y admite
la correspondencia correcta. Se prueban además identidad/vigencia, ausencia
de unidades, separación de columnas, códigos duplicados y PDF→importación→
recálculo→aprobación→lectura de entregables con fixtures sintéticas explícitas.

## Uso y pendientes

Preparar los originales privados sin sobrescribir ediciones:

```sh
cd backend
python -m scripts.prepare_sict_catalog \
  --construccion /private/TCD_Cons-2026.pdf \
  --servicios /private/TServicio-2026.pdf \
  --maquinaria /private/TCMaquinaria_2026.pdf \
  --parametricos /private/TCParametricos_2026.pdf \
  --destination /private/edicion-sict-febrero
```

El paquete generado se importa con `scripts.import_catalog_package` o por el
panel de catálogos ZIP, conservando los PDF originales en CATALOGO_ORIGINALES_DIR.
El directorio se puede comprimir sin los PDF ni dependencias: manifiesto + data.
La lectura en pantalla de los registros se soporta; esta ronda no acredita aún
un navegador completo específicamente con los cuatro originales privados.

**NO GO general permanece.** Falta la edición de julio, revisión visual/ingeniería
de todos los registros, restricciones de aplicación a un proyecto real,
aceptación privada en pantalla, carga integral y servicios de preproducción
con Supabase real. El caso portuario y los cambios de calendario/fuentes del
informe diario siguen pendientes; no se registran como casos operativos probados.
El número de filas, modelos o tests no sustituye esas operaciones.

## Evidencia del checkpoint

Runtime publicado: `9a13da16ebc12a261ca0b8990df67b8305772983`.
Batería completa local: 564 aprobadas, 18 omitidas, cero fallos/errores, 94.61 s.
El XML confirma que los casos auténticos CMIC/Varela y SICT se ejecutaron y no
fueron omitidos. Build frontend aprobado; revisión de nombres/imports Ruff (F)
aprobada. Las omisiones no acreditan PostgreSQL.

La primera corrida ampliada falló al perder el Redis externo y encontrar SQLite
en sólo lectura. Se repitió con Redis y SQLite aislados dentro de la misma
ejecución. Esa corrida encontró una aserción de la nueva prueba que contaba
estimaciones de otros casos: se restringió al modelo probado, conservando la
exigencia de cero escrituras por rechazo. La corrida completa final fue exitosa.

[CI 162](https://github.com/ytpremiumcr7-collab/Meg/actions/runs/38042275760)
terminó con los ocho jobs aprobados sobre ese runtime, incluidos migraciones,
core/API/Procurement y navegador. API ejecutó 135 pruebas aprobadas y seis
omitidas; las nuevas regresiones SICT sintéticas pasaron en PostgreSQL. El
navegador recorrió BIM, recuperación, topografía y el catálogo sintético importado
por pantalla hasta guardar el presupuesto. No certifica una sesión de navegador
con los cuatro PDF privados ni los proyectos del informe diario. Las entradas privadas no se subieron a GitHub y
se omiten explícitamente en CI público. El ZIP normalizado privado se comprobó
con CRC y SHA-256 `7b92b5384dde749d4a459594ee09ef8ced13a1d53739964c6765ff0d65f79730`.
