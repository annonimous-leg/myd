# Aceptación del backend del licitante

Estado de referencia: 2026-11-09. Continuación de la auditoría de `850b00b`.

El núcleo es Workspace y el dominio activo es `/api/v1/procurement`. El flujo de referencia completo permanece en [la especificación funcional](specs/2026-11-09-megalodon-flujo-end-to-end.md). Este documento ordena la aceptación backend sin sustituir el alcance del producto.

## Cambios posteriores a la auditoría

- Ingreso DOCX/XLSX: errores esperados de XML interno o referencias ausentes se normalizan como errores documentales 422 antes de persistir fuentes. Se conservan errores internos inesperados y los límites existentes.
- Los fixtures de render usan el entero definido por el modelo. La regresión de segregación de funciones obtiene un manifiesto de originales verificables, aprueba el primer rol y exige rechazo 403 del segundo rol por la misma persona.
- El gate de código incompleto distingue declaraciones de excepciones de funciones o clases de servicio vacías.
- Los workflows se ubican en `.github/workflows/` de la raíz Git, con rutas al subproyecto. Las integraciones instalan LibreOffice Calc para ejecutar el recálculo servidor.
- Los catálogos presentan `Investigación de mercado Megalodon · mes año`. La fecha sale de la edición fuente; si no es válida se muestra `fecha por verificar`. Identidades, títulos originales, evidencia, precios, hashes, jurisdicción y vigencia se conservan. La etiqueta comercial no fusiona fuentes ni acredita derechos sobre documentos de terceros.

## Infraestructura de aceptación

Alembic conserva la autoridad del esquema. Usar una base PostgreSQL/PostGIS desechable y credenciales DDL/DML distintas en el entorno de despliegue. La identidad propia de Megalodon no se convierte implícitamente en Supabase Auth. Revisar políticas/permisos del rol DML y mantener los datos privados fuera de Data API pública.

La prueba local de integración y la aceptación de Supabase son comprobaciones diferentes. Crear el esquema remoto no despliega API, frontend, Redis, workers ni Storage. Registrar por separado revisión, conexión TLS del driver, privacidad e integridad de objetos, recuperación y evidencias de firma.

## Recorrido que debe cerrar cada caso

1. Instalar un perfil explícito para dependencia, jurisdicción, procedimiento, contrato y tipo de proyecto. Registrar reglas, fuentes legales y mapas de formatos versionados; una dependencia no configurada debe explicar qué falta.
2. Cargar bases, plantillas y aclaraciones como fuentes originales. Confirmar contexto de empresa/expediente, extracción, candidatos y faltantes. Ninguna omisión silenciosa equivale a cumplimiento.
3. Seleccionar catálogo y precios con unidad, zona, vigencia, naturaleza del costo y evidencia. Mantener en cuarentena lo no cotejado o aritméticamente inconsistente. Un CSV recuperado sin edición fuente verificable no se transforma automáticamente en APU aprobado.
4. Generar el presupuesto servidor y el programa de la misma revisión. Verificar cantidades, partidas, parámetros y totales antes de poblar anexos.
5. Abrir Workspace, editar y regenerar conservando cambios humanos y conflictos por versión. Verificar visualmente DOCX/PDF y fórmulas/valores XLSX recalculados contra la plantilla oficial.
6. Ejecutar preparación con estado y traza de trabajos reales. Revisar bloqueos, evidencias y pendientes; no sustituirlos por un temporizador de bienvenida.
7. Presentar el manifiesto de originales al revisor, confirmar su hash y aprobar con las personas/roles exigidos. Un cambio de bytes o revisión invalida el alcance anterior.
8. Firmar cuando corresponda; verificar certificados, confianza, revocación y TSA con el proveedor configurado. Preparar el ZIP con los binarios exactos aprobados y comprobar manifiesto y descarga.
9. Registrar el acuse aportado después de la presentación externa. Generar el ZIP o guardar un acuse no demuestra envío automático al portal.
10. Repetir con otra dependencia, estado y naturaleza de proyecto, y probar dos empresas, concurrencia, reintentos, reinicio y restauración. Guardar la matriz de requisitos esperados y los faltantes observados.

## Motor de redacción técnica

Un motor probabilístico puede proponer redacción a partir de requisitos confirmados, documentos corporativos aprobados y resultados verificables. No debe decidir por sí mismo precios, normas aplicables, cumplimiento, experiencia inexistente, aprobaciones ni firmas.

Antes de integrar el motor aportado se necesita conocer su interfaz, despliegue, licencias, tratamiento de datos y límites. El contrato de salida debe vincular cada borrador a requisito, fuente/página, revisión y versión del motor; distinguir afirmaciones sin evidencia y admitir abstención. Sus resultados entrarán como borradores editables de Workspace, con revisión humana y control de versiones. No se añade un motor ficticio mientras esa interfaz no esté disponible.

El plan mantiene BIM/CAD, programación 4D/5D, capas geográficas, colocación del modelo, evidencia y Street View casi en tiempo real como alcance pendiente de sus respectivas integraciones y aceptación.
