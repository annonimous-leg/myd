# Megalodon · DOCX en Workspace y siguientes tramos

> Nota de vigencia, 2026-11-09: las etapas descritas a continuación son un registro histórico. El código actual ya incluye recálculo servidor y controles de promoción/bytes finales sujetos a validación. Para ejecutar el cierre vigente consultar [Aceptación del backend del licitante](ACEPTACION_BACKEND_LICITANTE.md) y sus resultados de pruebas; no interpretar todos los pendientes históricos como ausencias actuales.

© 2026 Carl Own Megalodon

## Activación por dependencia

En el perfil de jurisdicción, agrega `workspace_docx` a la definición existente del formato. El administrador puede instalar el perfil mediante la API de licitaciones. Las rutas y etiquetas salen de la configuración. Este ejemplo utiliza identificadores ilustrativos.

```json
{
  "version": "1",
  "source_sha256": "<SHA-256 del archivo Word original>",
  "fields": {
    "bidder.representative_name": {
      "tag": "firma.nombre",
      "label": "Representante legal",
      "required": true
    }
  }
}
```

Carga el archivo original como fuente de la licitación. En Workspace → Documentos, abre el anexo configurado, edita los campos y guarda. La revisión guarda su propio binario, separado de la fuente y del PDF habitual. La descarga verifica su huella antes de responder. Los valores DOCX se guardan separados de los valores que consume el compilador PDF. El DOCX sigue fuera del flujo de firma y empaquetado. El navegador ofrece el archivo para abrirlo en Word.

El alcance inicial cubre hasta diez controles Word de texto plano en línea y archivos de hasta 512 KiB. Los borradores de este tamaño se guardan con la revisión en la base de datos. La persistencia de volúmenes mayores requiere mover los binarios a almacenamiento de objetos y definir su ciclo de vida. La prueba de integración usa almacenamiento simulado y un DOCX sintético. La validación visual en Word y la activación con una plantilla oficial quedan pendientes.

## Diseño para los demás módulos

El PDF adjunto sobre automatización de RFP refuerza tres necesidades de Workspace que conviene abordar sobre los servicios existentes de Megalodon. Primero, una biblioteca de datos y respuestas corporativas aprobadas, donde cada uso fija la versión de la ficha de origen. Segundo, responsables y comentarios por anexo, con aprobación ligada a la revisión y el hash exactos. Tercero, un manifiesto de exportación que enumera los binarios aprobados y verifica su integridad antes de armar el ZIP. El PDF propone además importación y exportación XLSX. Esa etapa requiere un mapa por hoja y celda y pruebas de fórmulas y formato. El proyecto ya tiene perfiles de jurisdicción, evidencias, revisiones y aprobación de expediente, que son los puntos de integración para esas capacidades.

| Módulo | Siguiente corte verificable |
|---|---|
| BIM y planos | Ejecutar el motor sobre IFC2X3 y mantener el bloqueo de descarga de planos pendientes. Se añadió un IFC2X3 sintético para verificar extracción de malla, dimensiones y PDF A3. La integración del motor del Candidato queda como cambio independiente. |
| Cuantificación y presupuesto | Presentar un inventario único con cantidad, unidad, origen 2D/3D, versión del modelo, partida y precio aplicado. El backend ya cuenta con catálogo y costeo parcial. El siguiente cierre es aprobar una revisión y llevar su desglose a los anexos con sus faltantes visibles. Referencia de agrupación e inventario: [Autodesk Takeoff](https://help.autodesk.com/cloudhelp/ENU/Takeoff-Takeoff/files/Inventory.html). |
| Cronograma y 4D/5D | Mantener el visor visible mientras se desplaza el panel lateral de presupuesto. Colocar ahí un resumen de plazos y acceso al Gantt. Abrir el calendario detallado en Workspace. Usar relaciones versionadas entre elementos, partidas y actividades para producir la curva S y la simulación. Referencia: [Navisworks TimeLiner](https://help.autodesk.com/cloudhelp/2026/ENU/Navisworks-Timeliner/files/GUID-D0D36E3D-F1D0-43B6-AB4E-2E7799B340A3.htm). |
| Tezcatlipoca | Aprovechar el API existente de snapshots para la primera integración de evidencia. El primer flujo debe ubicar una revisión concreta del modelo, registrar la transformación geográfica y devolver la captura al expediente. Cada capa identifica proveedor, cobertura y fecha. Referencia de visualización BIM y metadatos: [Cesium BIM/CAD](https://cesium.com/learn/bim-cad/). |

## Piloto XLSX

El archivo `reference/plantillas-aportadas/piloto-xlsx-imss.json` contiene el mapa piloto para la réplica económica del IMSS del libro aportado. Agrega su objeto `workspace_xlsx` a la definición del anexo aplicable, carga el libro original como fuente y abre el anexo en Workspace. Los destinos se fijan por hoja y celda. El precio unitario se captura como número con punto decimal. Cada revisión devuelve sus propios bytes y su huella.

El piloto usa la réplica para verificar la generación de borradores. La conexión automática con el motor de costos, el recálculo de fórmulas en Excel y la validación para presentación quedan pendientes. Los ZIP aportados también contienen seis DOCX de generación de evidencia para Sinaloa y dos guías Word. Esos documentos sirven como referencias de prueba y contexto.

## Presupuesto y manifiesto

En una plantilla XLSX, configura `partida_numero` con el número exacto de una partida del presupuesto vinculado. Usa `type: "number"` y uno de los campos `economic.precio_unitario`, `economic.cantidad` o `economic.importe`. Workspace obtiene el valor del modelo de la licitación generado por el flujo de costeo. Cada campo queda en solo lectura y el guardado pide recargar si cambia el valor. Una partida ausente o ambigua bloquea el guardado. El piloto IMSS sigue disponible como ejemplo manual mientras se define su correspondencia con las partidas de una licitación concreta.

El manifiesto de entrega incluye `packaged_files`, con ruta interna, versión, tamaño y SHA-256 de los bytes incorporados al ZIP. Cuando un documento tiene firma, esta huella corresponde a la copia firmada que se incorporó. Los borradores de Workspace requieren todavía una política de validación y promoción para ser elegibles para entrega.

Para cerrar el flujo en una convocatoria concreta se requiere cotejar las réplicas contra sus originales, verificar visualmente los documentos y fijar qué versiones entran a firma y empaquetado. Quedan también por implementar el recálculo de XLSX, la biblioteca corporativa, la revisión por anexo, el visor con cronograma y las capturas georreferenciadas vinculadas al expediente. El motor del Candidato expone cortes, secciones y elevaciones en TypeScript. La cobertura IFC2X3 y de dibujos pendientes verifica el motor integrado. El cambio al motor del Candidato requiere comparar sus salidas contra esa referencia.

## FE-9 y recálculo

Se cotejó visualmente la página 22 del PDF oficial de bases FPFC/CO/003/2026. El FE-9 exige considerar el anticipo, conciliar las estimaciones con el programa de montos e identificar la tasa y el indicador. La página confirma un plazo máximo de 15 días hábiles desde la aceptación y firma del residente. Es una página de instrucciones. Sigue pendiente localizar el formato editable y compararlo contra la salida de Megalodon. [Bases originales](https://www.puentesfronterizos.gob.mx/docs/licitaciones/FPFC-CO-003-2026_bases-de-la-convocatoria.pdf)

Al editar un XLSX con fórmulas, Megalodon retira los resultados de fórmula en caché y solicita recálculo completo al abrirlo. Se verificó en LibreOffice con una fórmula que pasó de 6 a 12 al modificar su entrada. Los consumidores que solo leen valores en caché deben esperar a que el archivo se abra y se guarde desde una aplicación de hoja de cálculo. Sigue pendiente el recálculo del lado del servidor y la validación del binario resultante para firma.
