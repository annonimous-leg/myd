# Cobertura operativa y decisiones de medición BIM

La especificación MEGALODON/MEGATEZCATLIPOCA sigue abierta a ajustes. La prioridad de esta entrega es convertir la auditoría de cobertura en operaciones reales de BIM, sin adelantar el CAD editable ni dar por resuelto el tramo geoespacial.

## Contrato de revisión

Cada procesamiento satisfactorio conserva una instantánea inmutable con SHA-256 del IFC, huella de geometría persistible, cantidades y tipos incorporados, y el inventario completo. Un reintento idéntico conserva identidad de revisión; cambiar geometría, cantidades, archivo o selección produce otra revisión. Un fallo no sustituye la última instantánea válida.

La aplicación consulta las revisiones y su cobertura paginada, con admitidos, representaciones pendientes, conjuntos, causas y procedencia. La incorporación conserva los tipos anteriores y añade únicamente los solicitados. Se empieza por IfcMember/IfcPlate y después muros cortina, rampa y sus componentes. Proxy permanece pendiente de clasificación funcional antes de mapeo económico.

## Decisión por familia

Se registra pago por conjunto o por componentes. Cada línea identifica el elemento, concepto, cantidad revisada, alcance y referencia de medición; se permiten conceptos diferentes sobre un mismo elemento para unidades de pago distintas. No se permiten líneas de un padre y su descendiente en la misma política. Los componentes no medidos deben quedar cubiertos por un representante o excluidos con sustento.

Sin documentos de esta obra y conceptos vinculados se guarda una propuesta, no una decisión confirmada. Confirmar requiere documento contractual del mismo expediente, hash/versión, referencia, conceptos vigentes, cantidades y responsable. Cada cambio agrega una versión; no modifica la anterior. El catálogo de referencia no equivale a contratación.

Las decisiones confirmadas pueden producir un presupuesto nuevo. La cobertura restante mantiene el presupuesto parcial cuando corresponde. Modelo, decisión, alcance, precio o documento cambiados señalan obsolescencia; una versión obsoleta no se aprueba ni se exporta como vigente. 4D utiliza importes de las líneas de la versión por decisiones, incluyendo conceptos múltiples para un elemento.

## Verificación de esta etapa

La migración se ensaya en PostgreSQL/PostGIS real, incluyendo ida/vuelta y verificación de esquema. Se prueban persistencia, reintentos, historial, aislamiento entre organizaciones, bloqueo de borradores y cambios de concepto, documento y modelo. La prueba del IFC grande y la aceptación de interfaz se registran por commit antes del cierre de la entrega.

El CSV adjunto contiene identidades estables y roles distintos de catálogo. Sus conceptos, partidas, componentes de modelo, insumos APU y precios regionales deben conservar sus identidades y contexto. No se aplica a BIM4LCA ni se promueven precios por el mero hecho de adjuntarlo.

## Continuidad de la especificación

Después viene el documento CAD editable con operaciones, historial y Confirmar diseño sobre geometría concreta. CostOS, Workspace y Tezcatlipoca consumirán esa revisión y sus transformaciones, no capturas del visor como fuente de verdad.

La entrada guiada abrirá un expediente compartido: requisitos/plantillas, anotaciones y catálogo, después técnicos, con trabajos durables paralelos y resultados editables. El splash de bienvenida no fingirá que un IFC grande terminó en 5–15 segundos: la transición mostrará el trabajo real y abrirá primero el módulo disponible. Workspace conservará los documentos y decisiones; los paneles BIM serán vistas del mismo estado, con visor fijo y panel de revisión desplazable. Tema blanco sobrio predeterminado, oscuro seleccionable y bandeja Workspace/Tezcatlipoca/Firma desde el menú.

El tramo Tezcatlipoca conservará navegación espacial/terrestre, capas, georreferenciación de una revisión BIM, colocación con panorama inmóvil, evidencia al expediente y ZIP final. Las imágenes NASA de observación terrestre no constituyen Street View casi en tiempo real. La arquitectura deberá combinar proveedores e imágenes de campo, teselas, niveles de detalle, caché y fecha/latencia visible; se evaluarán fuentes abiertas y alojamiento propio con licencias comerciales verificadas por fuente. No se promete una fuente mundial gratuita que no haya sido comprobada. Las decisiones de UX y proveedor siguen abiertas; no se reduce el alcance por esa incertidumbre.
