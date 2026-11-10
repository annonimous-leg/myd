# Contrato de interacción · Workspace y BIM/CAD

Fuente funcional: [flujo end-to-end](Meg-Workspace-Documentos/docs/specs/2026-11-09-megalodon-flujo-end-to-end.md)
y decisiones del usuario del 2026-11-10. Intención visual: [DESIGN.md](DESIGN.md).

## Canonical UI Map

| Capability | Canonical owner | Source of truth | Allowed variants | Verification |
|---|---|---|---|---|
| Select/Listbox | Select HTML y Select Radix existentes | API del módulo y etiquetas es-MX | Nativo para filtros técnicos; Radix para menús | Navegador, teclado y móvil |
| Date | input type=date existente | Fechas aceptadas por backend | Calendario de plataforma y valor ISO | Flujo real 4D |
| Form | WorkspaceDocuments y PlanosA3 | Schemas y servicios del backend | Documento, plantilla y solicitud de plano | Historial, conflicto 409 y planos |
| Scrollbar | index.css y themes.css | Tokens semánticos | Inspector independiente; estudio apilado en móvil | styles-browser.test.mjs |
| CRUD | megalodon-client.ts y servicios procurement/BIM | Tenant, expediente, revisión y row_version del servidor | Guardar versión, revisar y descargar | bim-flow-browser.test.mjs y licitacion-flow.mjs |

## Navegación y estados

- Workspace es la entrada autenticada. Sin obra activa se ofrece elegir o crear
  una; no se inventa un contexto para guardar archivos.
- Workspace, Tezcatlipoca y Firma / Field SAT aparecen en una bandeja cerrada por
  defecto. Menú, Escape, teclado y restitución de foco pertenecen a Radix.
- BIM conserva el visor al cambiar de pestaña del inspector. Sus controles
  exponen selección con aria-pressed. Ajustes de vista no cambian cantidades.
- Los documentos muestran versión, bloqueo, historial y errores. Una actualización
  antigua devuelve 409; nunca se fuerza sobre una edición humana.
- Salir por navegación interna permite cancelar o descartar cambios sin guardar.
  La salida real de la página usa beforeunload. No perder datos por un menú.
- La carga de fuentes conserva pendientes si falla un archivo. Los aceptados
  quedan en el servidor y no se reenvían al reintentar los restantes.
- Si falla el vínculo de presupuesto, detener la compilación y mostrar el error.
  No continuar silenciosamente con un importe anterior.

## Límites de autoridad

`app/services/procurement` y la API BIM controlan tenant, permisos, readiness,
hashes, revisiones y transiciones. La aprobación conserva el manifiesto de
originales y exige readiness del servidor. Presentación visual y guardado no
equivalen a aprobación económica, firma ni presentación ante la dependencia.

Las preferencias visuales no guardan documentos, contraseñas ni claves de firma
en almacenamiento persistente del navegador. Los secretos no aparecen en URLs.

## Localización y recuperación

Interfaz es-MX, foco visible, estados en texto y controles nativos o Radix. Filtros
y fechas técnicos aceptan el popup de plataforma. Los errores conservan campos
editados. Los trabajos pendientes reflejan estados del servidor, no temporizadores.
El tema se comparte y persiste. Las pruebas Chromium no certifican por sí solas
accesibilidad completa ni todas las pantallas heredadas.
