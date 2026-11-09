# PR #5 — Restauración de aceptación real y conexión del Workspace al backend

Fecha: 2026-11-09. **Rama objetivo:**
`fix/ci-browser-workspace-4d-2026-11-09` (PR #5).
Respaldo anterior a esta intervención:
`backup/pr5-before-workspace-improvements-2026-11-09`,
commit `a13859eff11d964f7ad69bc2e1040a86f908efda`.
**No fusionar a `main`; no realizar despliegue automático.**

## Comparación con PR #4

GitHub `compare` confirmó que, al iniciar, la diferencia de contenido entre la
cabeza de PR #4 (`e457e9d...`) y la de PR #5 (`a13859e...`) era **cero archivos**:
los 9 commits adicionales de PR #5 eran la historia de modificaciones/reversiones
previas. Esto no autoriza a sustituir PR #5 por PR #4. La implementación presente
parte de PR #5 y conserva explícitamente su base, no de `main`.

## Contrato real del producto (sin doblez demo)

1. `GET /api/v1/procurement/tenders/{id}/workspace/documents/{id}` devuelve
   `media_type`, `content_text`, `content_model`, `row_version`, `version`,
   `locked` y estado. El backend implementaba ya `PUT` con
   `expected_row_version`, registro de `HUMAN_EDIT` y `409` por concurrencia.
2. Los documentos internos `text/plain` **ahora se editan visualmente**, no por
   un atajo en Playwright: campo controlado, bloqueo por rol/expediente congelado,
   aviso de cambios sin guardar, nueva revisión en servidor, vista previa
   literal y consulta del historial inmutable con versiones anteriores.
3. Los anexos oficiales **DOCX, XLSX y PDF** conservan su editor de campos
   autorizados por el mapa del catálogo. El endpoint `render` mantiene el
   recálculo del servidor, token de plantilla y control de concurrencia; el
   guardado de notas de texto no altera esta ruta ni finge producir anexos.
4. La vista editorial ligera/oscura se mejora sin bibliotecas nuevas, sin
   imágenes falsas y sin sacrificar el diseño adaptable. El contenido de texto
   se presenta por React como texto, **no como HTML sin sanitizar**.
5. Se pasan al editor los bloqueos del expediente (`tender.frozen`), además
   del estado `locked` del documento y los permisos de rol.

## Expectativas verificables de aceptación del navegador

- BIM: importar IFC, aprobar/exportar presupuesto, generar cronograma 4D,
  recargar y abrir `app=licitaciones-obra&seccion=cronograma&programa=ID`.
  El selector de Programación debe apuntar a ese mismo ID de backend.
- Catálogos: el fixture creado exclusivamente por CI debe identificarse como
  `CI sintético: catálogo de aceptación`, nunca como una publicación comercial.
  Las fuentes reales y sus fechas, precios, metadatos y títulos de
  Investigación de mercado permanecen sin alterar.
- Licitante: crear `TenderPackage` real, ingresar convocatoria sintética,
  verificar manifiesto con hash, revisar/confirmar requisitos humanos y bloqueo
  de submission prematuro. Abrir `Documentos`, editar un `text/plain`
  desde el textarea, pulsar **Guardar versión** y observar el `PUT` real
  `200`, versión 2, `HUMAN_EDIT`, revisión 1 en el historial y rechazo
  `409` de una edición obsoleta. La versión vigente debe permanecer intacta.
- Las pruebas no interceptan rutas ni reemplazan API o workers por mocks:
  siguen el workflow con PostGIS/Redis, servicio y navegador.

## Bloqueos de despliegue que CI no puede levantar automáticamente

| Área | Falta acreditar sobre infraestructura y fuentes reales |
|---|---|
| Supabase/RLS | TLS, separación de roles DDL/DML, migraciones con respaldo y restauración, aislamiento de dos tenants y permisos de Storage |
| Documentos oficiales | Comparación byte a byte con formatos originales de convocatorias reales, mapa/versionado de campos, cálculo XLSX/LibreOffice, PDF final y revisión legal |
| Firma y evidencia | Cadena de certificados, revocación, sello de tiempo/TSA y firma validada en destino; sin equiparar certificados de CI a firma oficial |
| Operaciones | API, workers, storage y observabilidad desplegados, secretos privados, backups restaurables, alarmas, recuperación y acceso operacional |
| Alcance | Validación independiente de cada jurisdicción/plantilla real; los catálogos sintéticos y el programa BIM generado no certifican universalidad |
| UI de aceptación | Revisión manual de contraste visual y accesibilidad en móvil/escritorio, flujos de error y roles; CI de dos casos no prueba todas las pantallas |

## Criterio de cierre

El **único** estado de CI que puede presentarse como evidencia es el
del commit final exacto de esta PR, con la matriz completa y el recorrido
Playwright aprobado. Aunque pase, el resultado acredita pruebas sintéticas
integradas, **no autorización de producción**. La PR permanecerá abierta.
