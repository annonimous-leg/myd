# Auditoría del backend y comparación de ramas

Fecha de ejecución: 2026-11-09. Repositorio: `annonimous-leg/myd`.

**Resultado: parcial.** Existe un backend funcional con persistencia, preparación documental, cálculo, revisiones, controles de aprobación y empaquetado. La evidencia disponible no acredita todavía la automatización completa de una propuesta para cualquier dependencia, estado y proyecto, ni un despliegue integral aceptado con proveedores reales.

El incremento de ingreso Office conserva el trabajo anterior: la selección comparable agrega 18 pruebas aprobadas y mantiene el mismo fallo preexistente. No se modificó código de producción ni se repararon pruebas durante esta auditoría.

## 1. Referencias exactas y cambio publicado

| Referencia | Rama | SHA auditado |
|---|---|---|
| Base anterior | `work/cierre-megalodon-desde-recalculo-2026-11-09` | `b290f2b4cc7a4485b2e878b69cd78c9221606e12` |
| Continuación Office | `work/ingesta-office-segura-2026-11-09` | `850b00ba0ec35a3d9d41533a45d85ad8543ad1d1` |

La base es ancestro directo de la continuación; su merge-base es `b290f2b`. El [PR #2](https://github.com/annonimous-leg/myd/pull/2) contiene los commits `13f4c23` y `850b00b`; estaba abierto y sin fusionar al consultar el remoto. No está incorporado a `main` por el solo hecho de estar publicado.

La comparación contiene exactamente cinco archivos, 259 inserciones y dos eliminaciones:

- `backend/app/engines/procurement/source_extract.py`: validación previa de paquetes Office.
- `backend/app/services/procurement/service.py`: conversión de errores de validación a respuesta 422.
- `backend/tests/procurement/test_source_office_safety.py`: 18 casos.
- `docs/audits/2026-11-09-ingesta-office.md`: alcance de ese incremento.
- `docs/specs/2026-11-09-megalodon-flujo-end-to-end.md`: flujo funcional solicitado.

Los motores de costos, Workspace, recálculo, aprobaciones, firma y ZIP ya existían en la base. No son capacidades añadidas por `13f4c23`.

## 2. Hallazgos materiales

### F1. P1 — Los workflows no se ejecutan en la ubicación actual del repositorio

**Confirmado, confianza alta.** Los workflows versionados están en `Meg-Workspace-Documentos/.github/workflows/`; no hay `.github/workflows/` en la raíz Git. GitHub Actions descubre workflows en la raíz del repositorio. La consulta de runs de pull request para `850b00b` devuelve una lista vacía.

Además, esos YAML utilizan rutas como `backend/`, que tampoco son rutas desde la raíz Git actual. Mover los archivos sin adaptar las rutas dejaría otro problema.

**Consecuencia:** publicar el PR no ofrece actualmente una comprobación automática de los cambios. Una prueba estática que encuentra un YAML dentro del subproyecto no demuestra que GitHub lo ejecute.

**Corrección propuesta:** colocar workflows en la raíz Git, corregir rutas y directorios de trabajo, y exigir un run real con PostgreSQL/PostGIS y Redis aislados antes de integrar. Referencias: [security-hardening.yml](../../.github/workflows/security-hardening.yml), [supabase-preflight.yml](../../.github/workflows/supabase-preflight.yml).

### F2. P2 — XML interno Office inválido produce un error de servidor

**Reproducido en las dos ramas, confianza alta.** Se generaron DOCX y XLSX válidos y se sustituyó únicamente `word/document.xml` o `xl/workbook.xml` por `b'<broken>'`. Ambos conservan los miembros exigidos por el validador ZIP. Al invocar `ProcurementService.ingest_source`, las bibliotecas lanzan `lxml.etree.XMLSyntaxError`, sin `status_code`, y el servicio solo convierte `ValueError`. El handler general responde 500.

En las cuatro invocaciones —dos formatos por rama— no se llamó al almacenamiento ni a `commit`. No se reprodujo pérdida o corrupción de documentos. El fallo afecta el diagnóstico de archivos dañados y la estabilidad del contrato HTTP, no demuestra ejecución de macros.

**Corrección propuesta:** normalizar las excepciones esperadas de los parsers a errores documentales, sin capturar indiscriminadamente errores internos, y cubrir ambos formatos por la API. Referencias: [source_extract.py](../../backend/app/engines/procurement/source_extract.py), [ingest_source](../../backend/app/services/procurement/service.py), [handler general](../../backend/app/main.py).

### F3. P2 — Las pruebas dejan huecos reales en la verificación del cierre

**Confirmado, confianza alta.**

- `test_workspace_document_render.py` crea perfiles con `profile_version="1"`, aunque el modelo y PostgreSQL exigen un entero. Sus tres casos pasan con SQLite y fallan al preparar los datos en PostgreSQL. Todavía no prueban el renderizado en ese entorno. Usar `1` y volver a ejecutar; no relajar el tipo del producto para acomodar el fixture.
- `test_one_reviewer_cannot_satisfy_two_distinct_procurement_approval_roles` intenta aprobar sin artefactos elegibles ni el manifiesto esperado. Se bloquea antes de alcanzar la segunda aprobación. El servicio contiene el control de separación de funciones, pero ese caso ya no demuestra su comportamiento. Preparar originales verificables y confirmar el manifiesto antes de intentar el segundo rol.
- `test_no_python_pass_or_notimplemented_in_product` rechaza cuerpos vacíos de dos clases de excepción legítimas. Es el mismo fallo en ambas ramas, no una función de negocio incompleta. El gate también contiene `assert findings == findings`, que no comprueba una propiedad útil. Distinguir stubs de herencia declarativa.

Referencias: [fixtures de render](../../backend/tests/integration/test_workspace_document_render.py), [modelo](../../backend/app/models/procurement.py), [reproducción de roles](../../backend/tests/test_prr_reproductions_20261007.py), [gate estático](../../backend/tests/unit/test_phase_closure_contracts.py).

### F4. P2 — La documentación operativa mezcla estados históricos incompatibles

**Confirmado por código y documentos, confianza alta.** [WORKSPACE-DOCX-Y-SIGUIENTES-TRAMOS.md](../WORKSPACE-DOCX-Y-SIGUIENTES-TRAMOS.md) todavía describe recálculo servidor y promoción de borradores como pendientes, aunque el código auditado incorpora recálculo y validación de bytes finales bajo condiciones explícitas. [SUPABASE_DEPLOYMENT.md](../SUPABASE_DEPLOYMENT.md) incluye una aceptación de publicación de convocatoria, fallo y contrato que corresponde a la autoridad convocante; esos routers están deliberadamente desmontados en [router.py](../../backend/app/api/v1/router.py).

**Consecuencia:** el siguiente desarrollador puede repetir trabajo existente o probar un recorrido que la plataforma del licitante ya no expone.

**Corrección propuesta:** mantener notas históricas fechadas, pero añadir una guía vigente de aceptación basada en `/procurement`, referencias de código y evidencia por capacidad.

## 3. Inventario: qué existe y qué falta acreditar

"Implementado" describe código localizado; "verificado" se limita a los casos ejecutados. Ninguna fila equivale por sí sola a aceptación de producción.

| Capacidad | Código y comportamiento existente | Evidencia y límite actual |
|---|---|---|
| Identidad y empresas | Autenticación propia, permisos, tenant, expedientes y recursos acotados | Pruebas de aislamiento y cierre; no validación exhaustiva de todos los endpoints con el rol DML final |
| Esquema persistente | Cadena Alembic, PostgreSQL/PostGIS, 115 tablas del modelo | Instalación desde base vacía hasta `20261109_approved_artifact_bytes`; verificador de columnas aprobado. Son 116 tablas públicas incluyendo `alembic_version` |
| Configuración por dependencia | Perfiles de jurisdicción, paquetes, formatos, reglas y fuentes legales versionadas | Runtime dirigido por configuración. Requiere perfiles y mapas válidos; no convierte una dependencia desconocida en cobertura automática |
| Fuentes | PDF, DOCX, XLSX y texto mediante extractores explícitos; originales, hashes y coordenadas | Casos estructurales y de evidencia. OCR existe, pero cobertura y calidad de escaneos deben medirse con verdad de referencia |
| Nuevo ingreso Office | Límites de 1000 entradas y 64 MiB expandidos, rutas no ambiguas, rechazo de macros/componentes activos y cifrado | 18 casos aprobados; conserva originales válidos. No sustituye antivirus o aislamiento de workers. F2 sigue abierto |
| Requisitos y aclaraciones | Candidatos derivados de estructuras configuradas, referencias a fuente y confirmación humana | Extracción determinista; sin configuración aplicable puede devolver cero candidatos. Leer texto no acredita comprensión jurídica universal |
| Preparación y trabajos | Jobs persistidos, idempotencia, reclamo de intentos, recuperación y etapas registradas | Gate PostgreSQL con dos tenants aprobado. No acredita todavía el fan-out automático completo de todo el onboarding ni recuperación de un despliegue de workers real |
| Costos y catálogo | Catálogos, insumos, partidas, APU, parámetros, presupuesto y puente al modelo de propuesta | Pruebas de importación, costeo y consistencia; requiere selección, vigencia, unidades, revisión y datos válidos. No hay una tarifa universal por estado/obra |
| Workspace | Documentos, edición, historial, regeneración, bloqueo y conflictos por versión | Casos SQLite de render y revisión aprobados. Los tres casos de render PostgreSQL están bloqueados por F3 |
| Plantillas originales | DOCX con controles mapeados y XLSX con hoja/celda; fuente y mapa ligados por hash | No es un editor libre para cualquier plantilla o PDF oficial. Fidelidad visual y mapas oficiales requieren aceptación por formato |
| XLSX y entrega | Datos económicos desde servidor, recálculo con LibreOffice y validación de bytes finales | Existe implementación y pruebas. Falta aceptación visual con los formatos oficiales de cada convocatoria y con Storage real |
| Aprobaciones | Revisión, roles, segregación de funciones, snapshot de originales y hashes esperados | Pruebas de manifiesto e inmutabilidad. El escenario de dos roles necesita reparar su fixture; aprobar no debe sustituir documentos faltantes |
| Firma | Servicios y rutas para firma, rendiciones y enlace a originales aprobados | No se ejecutó aceptación criptográfica con certificados, revocación o TSA reales; Firma / Field SAT sigue requiriendo definición de producto |
| ZIP y descarga | Selección de artefactos elegibles, manifiesto, hashes de bytes y descarga verificada | Pruebas del dominio y controles; no se ejecutó aquí el recorrido completo con objetos privados de un proveedor real |
| Acuse | Registro de archivo y referencia de presentación, ligado a un paquete | El usuario aporta el acuse; no demuestra envío automático al portal ni autenticidad independiente del acuse |
| BIM y planos | Rutas IFC/BIM, cuantificación, mapeo/costeo, dibujos y jobs | Hay casos sintéticos de geometría, unidades y dibujos. La auditoría no certifica importación/edición arbitraria de todos los formatos CAD/DWG/DXF ni precisión para cualquier modelo |
| Programación y riesgo | Motores de programación, CPM, costos y Monte Carlo; rutas y pruebas existentes | Deben verificarse con cantidades, calendario y revisión del mismo expediente; no está demostrado el recorrido visual integrado 4D/5D solicitado |
| Tezcatlipoca | Routers geoespaciales, topografía, snapshots e integraciones con proveedores | Instanciar un componente con estado READY no acredita frescura de un feed. Capas externas dependen de credenciales, licencia, cobertura y fecha |
| Experiencia completa | Especificación funcional registrada y frontend existente | Bienvenida, elección automática de primera pantalla, vista dividida, edición general CAD, sistema solar y evidencia georreferenciada de vuelta a Workspace no quedaron aceptados end-to-end en esta auditoría |
| Street View casi en tiempo real | Objetivo pendiente de diseño de proveedor y cobertura | Imágenes NASA/GIBS no constituyen por sí solas panorámicas actuales a nivel de calle. Se conserva el alcance solicitado sin declararlo implementado |

Puntos de entrada principales: [ProcurementService](../../backend/app/services/procurement/service.py), [Workspace](../../backend/app/services/procurement/workspace.py), [jobs](../../backend/app/services/procurement/jobs.py), [orquestador](../../backend/app/engines/procurement/orchestrator.py), [manifiesto de aprobación](../../backend/app/services/procurement/approval_manifest.py), [bytes finales](../../backend/app/services/procurement/workspace_final_bytes.py).

## 4. Comprobaciones ejecutadas

Dependencias instaladas desde el lockfile con Python 3.12. Las bases y servicios de prueba fueron aislados. Las cifras son salidas de pytest; los cuatro subtests se informan aparte para no alterar el conteo de casos.

| Ejecución | Entorno | Resultado observado |
|---|---|---|
| Selección comparable, base `b290f2b` | SQLite desechable | 546 aprobadas, 1 fallida, 4 subtests |
| Misma selección, Office `850b00b` | SQLite desechable | 564 aprobadas, 1 fallida, 4 subtests |
| Suite `tests` completa, Office | SQLite; sin Redis inicial | 879 aprobadas, 5 fallidas, 27 omitidas, 4 subtests |
| Selección de cierre, manifiestos, bytes y Office | PostgreSQL 16/PostGIS con Alembic | 52 aprobadas, 3 fallidas por tipos de fixture de render |
| Rate limit, preflight y traza por etapas | Mismo PostgreSQL y Redis 7 reales | 4 aprobadas; resuelve los tres fallos de entorno de la suite SQLite e incluye un gate adicional |
| Alembic desde cero y verificación del esquema | PostgreSQL/PostGIS vacío | Revisión head correcta y columnas de 115 tablas del modelo comprobadas |
| Ruff F821/F822/F823 en `app` y `tezcatlipoca` | Python 3.12 | Aprobado |
| DOCX/XLSX con XML interno dañado | Invocación del servicio; ambas ramas | F2 reproducido en los cuatro casos; sin escritura de objetos ni commit |

No sumar las filas: varias selecciones repiten casos. No se obtuvo una suite completa verde. Las 27 omisiones permanecen como cobertura no ejecutada, no como aprobaciones.

Los cinco fallos iniciales de la suite completa se clasifican así: dos requieren Redis, uno exige PostgreSQL, uno es el fixture de aprobación sin artefactos y uno es el gate estático sobre clases de excepción. Los tres primeros pasaron al disponer del entorno requerido. Los dos restantes son deuda de verificación y ya están presentes en el código de la base, aunque la comparación ejecutada entre ambas ramas cubrió directamente solo el gate estático común.

Comandos reproducibles desde `Meg-Workspace-Documentos/backend`, con las conexiones de prueba inyectadas por el entorno y sin imprimir credenciales:

```sh
uv sync --frozen --extra dev
uv run pytest -q tests/procurement tests/unit \
  tests/integration/test_closure_two_tenants.py \
  tests/integration/test_workspace_document_render.py \
  tests/integration/test_catalogo_libro_costeo.py
uv run pytest -q tests
uv run alembic upgrade head
uv run python -m scripts.verify_migrated_schema
uv run pytest -q tests/integration/test_closure_two_tenants.py \
  tests/integration/test_workspace_document_render.py \
  tests/integration/test_supabase_preflight.py \
  tests/unit/test_procurement_approval_manifest.py \
  tests/unit/test_workspace_final_bytes.py \
  tests/procurement/test_source_office_safety.py
uv run pytest -q tests/integration/test_rate_limit_operation.py \
  tests/integration/test_supabase_preflight.py \
  tests/e2e/test_procurement_stage_trace_postgres.py
uv run ruff check app tezcatlipoca --select F821,F822,F823
```

Ejecutar migraciones y pruebas únicamente en bases desechables de aceptación, con la separación de credenciales y TLS requerida por el entorno. Los tests tienen escrituras y algunos fixtures limpian datos: no usar producción. La prueba PostgreSQL utilizada aquí corre con un usuario privilegiado de una base temporal; no demuestra aislamiento RLS del rol DML de producción.

## 5. Punto de continuación verificable

1. Resolver F1 y F3 para que GitHub ejecute controles útiles sobre el esquema migrado; corregir F2 con regresiones de la API.
2. Completar la aceptación de infraestructura: credenciales DDL/DML separadas, permisos y políticas del rol de ejecución, TLS, objetos privados, API, workers, Redis, reinicio y restauración. Crear tablas no acredita este despliegue.
3. Ejecutar una convocatoria completa con perfil y mapas explícitos: originales → requisitos confirmados → presupuesto servidor → documentos editables → revisión → aprobación de bytes exactos → firma cuando aplique → ZIP descargado y verificado.
4. Extender esa misma prueba a otra dependencia, otro estado y un proyecto de naturaleza distinta. Mantener una matriz de requisitos esperados y cotejo visual de anexos. Medir faltantes y errores; no usar el éxito de extracción como criterio de propuesta completa.
5. Conectar el onboarding y su progreso real con los jobs existentes y el Workspace. Mantener la edición humana y la revisión como parte del flujo.
6. Integrar BIM/cronograma/evidencia geográfica por revisión y transformación; después continuar el detalle de proveedores de Tezcatlipoca y Street View.

**Dictamen funcional:** parcial frente al [flujo solicitado](../specs/2026-11-09-megalodon-flujo-end-to-end.md). **Dictamen de ingeniería:** el parche Office pasa sus casos y no introduce fallos adicionales en la selección comparada; el conjunto mantiene hallazgos y cobertura pendiente. No se declara listo para producción.
