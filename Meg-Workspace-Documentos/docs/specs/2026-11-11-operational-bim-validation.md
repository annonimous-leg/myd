# Verificación de cobertura operativa BIM

Fecha: 11 de noviembre de 2026. Continuación de `3b2040d` en la PR #11, rama `feat/bim-cad-continuacion`.

## IFC BIM4LCA de 85 MB

Se ejecutaron tres procesamientos reales con el servicio transaccional del worker, PostgreSQL/PostGIS y almacenamiento de archivos aislados. No se sustituyó el motor geométrico. Cada etapa conservó su revisión y cobertura.

| Selección | Elementos admitidos | Con malla | Tiempo del procesamiento |
| --- | ---: | ---: | ---: |
| Tipos iniciales | 868 | 868 | 147,6 s |
| Incorporación de IfcMember e IfcPlate | 1.398 | 1.398 | 225,8 s |
| Incorporación de muro cortina, rampa y componentes admitidos | 1.438 | 1.438 | 163,6 s |

El inventario final conserva 1.441 productos: 1.438 admitidos y tres IfcBuildingElementProxy con representación pendiente de clasificación funcional. La etapa inicial distribuía los otros 573 entre representación propia pendiente (526), conjuntos pendientes (28) y cobertura por conjuntos (19). Incorporar componentes cambia esa clasificación; no equivale a añadir 573 partidas de cobro.

Una propuesta de medición guardada en la revisión inicial permaneció en el historial y pasó a obsoleta por cambio de revisión. Se registraron **cero aprobaciones económicas** para este edificio. La disponibilidad de una malla tampoco valida el volumen como cantidad de pago: los 360 volúmenes geométricos identificados anteriormente siguen requiriendo revisión.

## Controles económicos y de persistencia

Las pruebas de integración usan familias y contratos sintéticos, separados de BIM4LCA. Comprueban decisiones por conjunto/componentes, conceptos múltiples sobre un elemento, bloqueo de padre y descendiente, presupuesto y 4D con el mismo importe, borradores que conservan la última decisión confirmada e invalidación por cambio de modelo, concepto/precio y documento contractual. También cubren aislamiento entre organizaciones, reintento idéntico, procesamiento fallido y protección de instantáneas inmutables en PostgreSQL.

La prueba de navegador utiliza el IFC sintético de aceptación y una familia de cubierta con Member/Plate para probar la carga durable, recuperación tras reiniciar servicios, planos, presupuesto, 4D, incorporación de tipos e historial de una propuesta obsoleta. El IFC grande se mide por separado con el servicio real; sus tiempos no proceden de esa pequeña prueba de navegador.

La migración de las dos tablas nuevas se ensayó con avance, retroceso, nuevo avance y verificación del esquema. El ensayo de recuperación histórica mantiene la comparación de los datos originales e identifica ambas tablas como adiciones inicialmente vacías.

## Catálogo adjunto

El CSV se inspeccionó como referencia sin importarlo a BIM4LCA: 16.581 identidades únicas, distribuidas en 6.499 conceptos, 2.924 partidas, 506 componentes de modelo, 6.307 insumos APU y 345 precios regionales. Las 8.489 filas sin código de concepto y las 6.683 sin la tríada completa cantidad/precio/importe necesitan interpretación según su rol; por sí solas no demuestran un error económico.

Su aplicación a esta obra requiere vinculación expresa con los conceptos contratados y su medición/pago. No se publican el CSV original, las coordenadas ni los identificadores del modelo en este informe.

## Límites de esta entrega

La clasificación funcional de los tres Proxy, la validación económica de cantidades y el sustento contractual real siguen pendientes. El CAD editable y Confirmar diseño, la entrada automática al Workspace y la colocación georreferenciada con retorno de evidencia a Tezcatlipoca conservan el orden de desarrollo descrito en la especificación viva; esta verificación no los declara terminados.
