# Cierre de validación documental y presentación de catálogos

Continuación de `a426de9`, sobre el backend auditado `850b00b`. Fecha: 2026-11-09.

## Resultado

Se corrige el error de servidor al ingresar DOCX/XLSX con XML principal inválido: la API devuelve 422 y conserva el expediente sin fuentes ni objetos parciales. La regresión se reprodujo antes del cambio: dos casos fallaron por XML inválido y dos casos de partes ausentes ya pasaban; los cuatro pasan después.

Los fixtures de render ahora respetan el entero `profile_version` de PostgreSQL. La prueba de segregación de aprobadores primero verifica y aprueba un manifiesto real del servicio con bytes sintéticos almacenados por su colaborador de pruebas; después exige 403 al intentar cubrir un segundo rol con la misma persona. También comprueba que solo quedó la primera aprobación. El gate AST permite cuerpos declarativos de excepciones y mantiene el rechazo de funciones, métodos y servicios vacíos, con cinco casos de caracterización.

Los workflows y reglas SAST se trasladan a `.github/` de la raíz Git. Se corrigen directorios de ejecución, cachés, rutas de escaneo, contexto de la imagen API y artefactos. El paquete de evidencia depende también del SAST local; la integración instala LibreOffice Calc para el recálculo XLSX. La activación efectiva de GitHub se registra mediante su run, separada de la validación sintáctica local.

El API agrega nombres comerciales de lectura a catálogos e importaciones. Costos, inventario y selector BIM muestran `Investigación de mercado Megalodon · mes año`, usando la fecha de la edición y una referencia para distinguir fuentes. No se reemplazan títulos ni identidades originales, no se reescriben snapshots, no se fusionan ediciones, ni se cambian precios. Una fecha ausente o inválida se presenta como pendiente de verificar, sin inventar el mes actual. El endpoint de detalle conserva la procedencia.

## Verificación ejecutada

| Comprobación | Resultado |
|---|---|
| Regresiones de ingreso, render, aprobaciones, gate AST y cambio Office en PostgreSQL | 52 aprobadas |
| Suite completa `pytest tests` con PostgreSQL 16/PostGIS, Redis 7 y LibreOffice | 921 aprobadas, 7 omitidas, 4 subtests aprobados; 203.62 segundos |
| Presentación por API y nombres mensuales, ejecutados después | 9 aprobadas, con solapamiento de 8 unitarias con la suite completa |
| Dos inyecciones de fallos que requieren SQLite | 2 aprobadas |
| Ruff F821/F822/F823 de `app` y `tezcatlipoca` | Aprobado |
| Actionlint 1.7.7 de ambos workflows, sin analizadores externos de shell/Python | Aprobado |
| `npm run build` | Aprobado: TypeScript y bundle de producción |
| ESLint de los seis archivos frontend modificados | Sin errores; 150 advertencias existentes en esos archivos |

No sumar las filas porque se repiten casos. Las siete omisiones de PostgreSQL fueron: dos inyecciones exclusivas de SQLite, dos pruebas que exigen credenciales de un API desplegado y tres casos de ediciones privadas específicas con sus PDF originales. Las dos pruebas SQLite se ejecutaron aparte. La prueba sintética de PAdES no equivale a aceptar certificados o TSA de producción.

Las pruebas, logs y conexiones usaron servicios aislados de aceptación. El esquema de Supabase creado anteriormente requiere todavía aceptación del rol DML, conectividad TLS del driver, API y objetos privados; este cambio no lo convierte en un despliegue terminado.

## Continuación

La [guía de aceptación del licitante](../ACEPTACION_BACKEND_LICITANTE.md) sustituye las instrucciones históricas de cierre convocante. Mantiene el flujo completo solicitado y los criterios para comparar dependencias/estados/proyectos diferentes. El posible motor de texto se integrará como generador de borradores trazables cuando se disponga de su contrato real; no reemplazará reglas, evidencia, cálculos ni aprobaciones.

Los archivos aportados y los resultados de su cotejo se conservan fuera del repositorio público. Se mantiene la cuarentena del importador existente: los registros sin evidencia original comprobada no habilitan precios de presupuesto automáticamente.
