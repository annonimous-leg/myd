# Workspace · Documentos

Copyright © 2026 Carl Own Megalodon

Base: `Meg-Correcciones-Auditoria.zip`. La pantalla se abre desde
**Licitaciones de Obra → Abrir Documentos**, con un expediente de
automatización ya creado. Una vez compilado, el Workspace lista sus anexos.

## Recorrido

1. Selecciona el anexo en la columna izquierda. Si su revisión referencia
   un PDF generado, se carga y se verifica su hash. Un XLSX existente está
   disponible para descargar.
2. Edita los campos habilitados por el formato. Los valores iniciales
   proceden del modelo canónico y de las correcciones de ese documento.
3. Pulsa **Guardar y previsualizar**. El servidor valida el permiso, el
   catálogo y la versión, genera un PDF de trabajo y guarda sus bytes y
   huella en la revisión. Un conflicto se muestra antes de guardar.
4. **Descargar revisión** usa el mismo blob mostrado por la vista previa.
   El endpoint también permite recuperar una versión anterior por su
   número de revisión, con autorización por tenant y expediente.

El modo se elige inicialmente según la preferencia del sistema y puede
cambiarse en la cabecera. En escritorio hay tres columnas. En pantallas
estrechas, el editor y la vista previa se colocan uno debajo del otro.

## Habilitar campos

La primera entrega admite anexos ligados a `compile_annex_pdf`. Los
campos deben estar en `canonical_paths` de la definición del formato y
en la lista de campos textuales soportados por el editor. Ejemplos:

- `bidder.representative_name` y `bidder.representative_role`.
- `bidder.representative.name` y `bidder.representative.role`.
- `bidder.legal_name`, `technical.planning` y
  `technical.construction_method`.

El formato puede tener otros campos que sigan siendo de solo lectura o
se manejen en su módulo de origen. Los montos del presupuesto quedan
fuera de este editor. Los archivos que requieren reproducir una
plantilla oficial en Word, Excel o PDF de la dependencia quedan
pendientes de su adaptador y prueba de fidelidad.

## Límites y pruebas

El PDF nuevo es **borrador de trabajo**. El guardado no publica ni firma
un artefacto de presentación. Las correcciones se conservan como
`field_overrides` y la compilación existente toma la revisión humana
más reciente cuando el binding la admite. Firmar y empaquetar siguen
sus flujos de aprobación existentes.

Se reutiliza el historial de documentos para guardar borradores de hasta
128 KiB. No se agrega una migración. La edición usa las mismas reglas de
técnico o administrador del Workspace. La prueba de integración cubre
lectura de campos, cambios reales en el PDF, identidad de bytes de
vista previa y descarga, historial inmutable, conflicto de versiones y
denegación entre tenants.

Ejecuta `pytest tests/integration/test_workspace_document_render.py
tests/integration/test_closure_two_tenants.py tests/procurement` desde
backend y `npm run build` desde frontend/app. Queda pendiente probar en
un navegador con el despliegue real y con anexos oficiales. Este tramo
no cambia BIM, sus migraciones ni sus procesos.
