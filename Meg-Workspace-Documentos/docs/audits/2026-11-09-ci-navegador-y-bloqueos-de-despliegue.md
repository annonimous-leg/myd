# CI de navegador y bloqueos de despliegue — Megalodon

Fecha: 2026-11-09. Continuación **sin modificar `main`** de la rama
`work/cierre-validacion-y-catalogos-2026-11-09` (`e457e9d`).

## 1. Evidencia y diagnóstico reproducido

Referencia original: [Security Hardening, ejecución 42672214118](https://github.com/annonimous-leg/myd/actions/runs/42672214118).
El trabajo `bim-browser-acceptance` falló con **0/2 subtests de navegador**. En la misma
ejecución, los trabajos observados `production-compose-config`,
`backend-integration (api)`, `backend-integration (core)` y
`backend-sqlite-regressions` terminaron correctamente. No equivale a que
**toda** la matriz del workflow haya quedado verde.

El ZIP `bim-browser-42672214118` incluye `last-screen.png`,
`bidder-last-screen.png`, trazas Playwright, registros de API/worker/proxy y
salidas XLSX/PDF sintéticas.

| Caso | Registro y evidencia | Causa verificada / alcance |
|---|---|---|
| BIM 4D `bim-flow-browser.test.mjs:152` | `locator.waitFor` agotó 60 s esperando «Abrir cronograma en Programación»; la captura muestra «Editar cronograma en Workspace» y una actividad 4D generada. | **Selector y ruta desactualizados.** `bim-calculator/index.tsx` usa `abrirModulo('licitaciones-obra', programa_id, 'cronograma')`; `licitaciones-obra/index.tsx` renderiza `ProgramacionObra workspace`; `programacion-obra/index.tsx` resuelve el programa por query `programa`. No se acreditó fallo de cálculo 4D. |
| Licitante `helpers/licitacion-flow.mjs:97` | `locator.waitFor` agotó 30 s esperando «Workspace documental» tras `POST /procurement/tenders` 201; la captura muestra «Automatización de proposición», «1. Fuentes», bloqueo `OFFICIAL_SOURCE_REQUIRED` y botón «Abrir Documentos». | **Expectativa de pantalla antigua.** Crear la licitación mantiene el panel de fuentes/requisitos; el editor de anexos se abre explícitamente. `WorkspaceDocuments.tsx` muestra «Documentos» y campos provenientes de un mapa de formato. |

El artefacto `api.log` también registra intentos de exportación OpenTelemetry
con endpoint vacío y errores gRPC `dns:///`. Esto es ruido/configuración
de observabilidad del proceso de prueba; debe revisarse separadamente y no
confundirse con la causa probada de los dos timeouts. `preview.log` muestra
dos rechazos de conexión al reiniciar deliberadamente la API durante el caso
de recuperación. El origen de cada error adicional requiere correlación con
la traza, no inferencias por un mensaje aislado.

## 2. Cambios acotados

- La prueba BIM espera el botón actual **Editar cronograma en Workspace**, conserva
  la recarga que prueba recuperación 4D y comprueba `app=licitaciones-obra`,
  `seccion=cronograma`, `programa` no vacío y que el selector de
  `ProgramacionObra` realmente selecciona ese mismo ID.
- La prueba del licitante verifica el panel de propuesta, la carga de fuente,
  los candidatos y la confirmación humana antes de entrar en anexos. Para el
  fixture sintético `CI-TECHNICAL-MEMO` (**text/plain sin mapa editable**),
  conserva el cambio humano versionado mediante el `PUT` soportado por la API,
  añade comprobación de conflicto HTTP 409 con `row_version` obsoleta y comprueba
  que el documento/revisión aparecen en la interfaz «Documentos».
- **No** se simula que un documento sin mapa tenga editor genérico: el
  frontend actual limita la edición visual a campos declarados y el test
  constata explícitamente ese límite. La aceptación de edición real DOCX/XLSX
  requiere la fuente original y su mapa verificable; este fixture no la cubre.
- No cambian API, modelo de datos, fórmulas, reglas de aprobación ni lógica
  de generación. No se realizan migraciones ni despliegues.

## 3. Bloqueos de entrega y criterios para levantarlos

| Prioridad | Bloqueo de aceptación | Evidencia de salida requerida |
|---|---|---|
| P0 | CI del commit de entrega | `Security Hardening` completo en verde para el SHA de la rama de revisión; conservar artefactos y causas de cualquier job omitido/fallido. Un rerun del SHA anterior no valida estos cambios. |
| P0 | Supabase/DB de destino | Preflight de solo lectura, TLS verificado, separación de roles DDL/DML, permisos/RLS de dos tenants, migraciones desde copia restaurable y comprobación de tablas sin usar datos reales en CI. El despliegue de esquema no implica API operativa. |
| P0 | Objetos privados y binarios | Probar Storage con credenciales y bucket de staging, hash de originales y exactitud byte a byte de las versiones aprobadas, aislamiento por tenant, revocación y descarga del paquete. |
| P0 | Flujo real del licitante | Correr convocatoria, aclaraciones, anexos oficiales DOCX/XLSX, recálculo LibreOffice, presupuesto/programa coherentes, aprobación humana, ZIP, faltantes y acuse; repetir en **dos** perfiles de dependencia/jurisdicción con matrices de requisitos. No declarar cobertura universal. |
| P1 | Firma y validez probatoria | Validar certificados, cadena de confianza, revocación, TSA y configuración de producción. Los certificados sintéticos no acreditan firma oficial. |
| P1 | BIM/Programación | Prueba de recuperación, IFC y 4D/5D sobre modelos de referencia con mediciones revisadas, edición de precedencias y calendario; contraste con resultados esperados y revisión técnica humana. |
| P1 | Observabilidad y operaciones | Corregir endpoint OTLP vacío o deshabilitar exportadores explícitamente en CI, verificar healthchecks, alarmas, reintentos, recuperación de workers, backups y restauración probada. |
| P1 | Seguridad de publicación | Revisar secretos, licencias, permisos de Actions, dependencias/SAST y clasificación del repositorio público antes de distribuir documentación o datos reales. |

Las condiciones de despliegue y las pruebas funcionales se detallan en
[ACEPTACION_BACKEND_LICITANTE.md](../ACEPTACION_BACKEND_LICITANTE.md)
y [SUPABASE_DEPLOYMENT.md](../SUPABASE_DEPLOYMENT.md). Los datos aportados
y evidencia privada no deben subirse a GitHub.

## 4. Ejecución y límites del resultado

El workflow se activa mediante PR **apilada contra la rama de cierre**, no
mediante fusión a `main`. El caso relevante se ejecuta en GitHub con
PostgreSQL/PostGIS, Redis, API, worker, frontend y Playwright reales:

```sh
# En el runner, con servicios/credenciales sintéticas ya establecidos:
cd Meg-Workspace-Documentos/frontend/app
node --test tests/bim-flow-browser.test.mjs
```

No convertir en aprobada ninguna prueba que GitHub informe como fallida,
cancelada u omitida. La comprobación local estática no sustituye la ejecución
de navegación real, Storage, persistencia ni integración.

**Estado:** cambios de los tests propuestos; aceptación final sujeta al
workflow real de la PR. No hay aprobación para producción ni fusión a main.
