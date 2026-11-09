# Ingesta Office: primer incremento sobre el backend vigente

Base: `b290f2b4cc7a4485b2e878b69cd78c9221606e12`, rama `work/cierre-megalodon-desde-recalculo-2026-11-09`. Continuación local: `work/ingesta-office-segura-2026-11-09`. Destino confirmado por el usuario: `annonimous-leg/myd`. Se verificó la base contra las ramas remotas antes de publicar una continuación separada.

## Problema demostrado y cambio

El editor Workspace tenía controles de descompresión y componentes activos, pero el extractor de fuentes abría DOCX/XLSX directamente. Un documento válido con un `vbaProject.bin` añadido, rutas ambiguas o límites de expansión excedidos seguía siendo leído. Las pruebas nuevas reprodujeron 13 fallos antes del cambio y dos controles positivos pasaron.

Se validan los metadatos ZIP y los tipos de contenido antes de invocar python-docx/openpyxl. Se reutilizan los límites del perfil Office del Workspace: 1000 entradas y 64 MiB expandidos. Los errores de documento pasan a `ARCHIVO_ERROR` con estado 422 antes de almacenar o confirmar la fuente. No se alteran fórmulas, catálogos, modelos, migraciones ni archivos originales; tampoco se interpreta una firma pasiva como autorización.

Compatibilidad: las fuentes `.xlsm` y otros tipos declarados con macros dejan de admitirse en esta entrada documental. El rechazo es explícito; no se eliminan macros ni se transforma el archivo silenciosamente. Se mantienen DOCX/XLSX ordinarios y fuentes con firmas pasivas, sin certificar su autenticidad.

## Verificación fresca

- **42 pruebas pasan, 4 subtests pasan**, con las fixtures SQLite del backend: extracción estructural, fuentes, seguridad Office, bytes humanos revisados, recálculo Office y render DOCX. El recálculo se ejecutó en este entorno; no se marcó como omitido.
- Las 18 pruebas nuevas cubren fuentes válidas, partes activas, límites de expansión/entradas, rutas ZIP ambiguas, extensión con macros, archivos corruptos, firma pasiva y errores 422 sin escritura ni commit. Los dos casos de servicio usan dependencias de almacenamiento/DB controladas; no son pruebas HTTP ni de aislamiento entre tenants.
- Ruff (`--select F`) pasa en extractor y pruebas nuevas. El servicio mantiene cuatro hallazgos previos, confirmados ejecutando Ruff sobre el archivo original del commit base; no se presenta el lint global como verde.
- Aparecen 52 warnings previos de Pydantic/SQLAlchemy. No se ejecutó la suite completa del sistema ni una restauración PostgreSQL.

Selección ejecutada desde `backend/`, en un entorno de pruebas con DATABASE_URL y TEZCATLIPOCA_DATABASE_URL apuntando a SQLite desechable, Redis/Celery locales y claves sintéticas:

```sh
.venv/bin/python -m pytest -q \
  tests/procurement/test_source_office_safety.py \
  tests/procurement/test_structural_source_extraction.py \
  tests/procurement/test_source_requirement_extraction.py \
  tests/unit/test_workspace_final_bytes.py \
  tests/unit/test_workspace_office.py \
  tests/unit/test_workspace_docx.py
```

La primera ejecución sin permiso de red del sandbox quedó bloqueada y se interrumpió. La ejecución aislada con red habilitada, conservando únicamente servicios y base locales, terminó correctamente en 23,73 segundos. El entorno se instaló con `uv sync --frozen --extra dev`, sin modificar el lockfile.

## Comprobación de los documentos aportados

Se verificaron los SHA-256 de las seis fuentes contra su manifiesto. Los originales no se agregaron al repositorio.

| Fuente | Resultado observado |
|---|---|
| Manual DOCX (`bbb92dad…93d184`) | Extracción: 66 577 caracteres, 1478 bloques; bytes originales conservados |
| Guía DOCX (`1d1ba757…daafec`) | Extracción: 43 663 caracteres, 989 bloques; bytes originales conservados |
| Convocatoria Tlaxcala PDF (`55f5b08f…60a1f`) | Dos páginas escaneadas, OCR ejecutado: 6393 caracteres, 76 bloques; bytes originales conservados |

El OCR demuestra extracción de texto, no revisión jurídica ni separación correcta de todos los procedimientos de esa convocatoria. Los anexos salariales/indirectos se inventariaron y verificaron por hash; no se aplicaron como reglas financieras universales.

## Reversión y continuación

La reversión consiste en revertir el commit de este incremento; no hay migraciones ni cambios de datos existentes. Pendiente: orquestación de la entrada y preparación automática con jobs existentes, paridad de presupuesto, controles concurrentes y pruebas tenant/expediente antes de ampliar el flujo. El detalle funcional solicitado se conserva en `docs/specs/2026-11-09-megalodon-flujo-end-to-end.md`.
