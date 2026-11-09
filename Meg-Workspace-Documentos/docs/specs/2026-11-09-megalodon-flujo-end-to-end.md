# MEGALODON / MEGATEZCATLIPOCA: flujo funcional de referencia

Fecha: 2026-11-09. Prioridad actual: backend. Este documento registra el flujo solicitado y distingue capacidades esperadas de comprobaciones realizadas; no declara la plataforma terminada.

## Base de trabajo y decisiones confirmadas

Base inspeccionada: `annonimous-leg/myd`, rama `work/cierre-megalodon-desde-recalculo-2026-11-09`, commit `b290f2b4cc7a4485b2e878b69cd78c9221606e12`, fechado 2026-11-09 15:21:18 UTC. Es la punta con fecha de commit más reciente entre las cuatro ramas consultadas. El usuario escribió «repo mis»; la identidad del destino debe confirmarse antes de publicar esta continuación.

Se conserva el backend FastAPI existente y la autoridad financiera del servidor. El PDF RFP aportado es referencia funcional sobre documentos, revisiones y aprobaciones; su propuesta NestJS/Next.js no obliga a reescribir este proyecto.

El centro del producto se llama **Workspace**. La interfaz futura será blanca y sobria, con modo oscuro seleccionable y acabado profesional. La bandeja de Workspace, Tezcatlipoca y Firma / Field SAT se abre únicamente desde su botón de menú. Este incremento no cambia el frontend.

## Flujo completo solicitado

1. **Entrada documental.** Cargar requisitos y plantillas de la convocante; adjuntar opcionalmente la junta de aclaraciones. Conservar cada original y su hash, revisión, contexto de tenant/expediente y tipo de fuente. Enrutar documentos al Workspace y formatos económicos al contexto de presupuesto/BIM/costos.
2. **Preparación paralela.** El Workspace acomoda las plantillas y propone su llenado usando datos y documentos de empresa, personal, responsables, maquinaria, contratos y programa. Los resultados son borradores editables: no constituyen aprobaciones legales ni firmas.
3. **Datos clave y catálogo.** Recoger dependencia, obra y estado. Permitir catálogo adjunto o seleccionado mediante investigación de mercado. Compartir la versión seleccionada con el cálculo y conservar fuente, moneda, unidades, jurisdicción y vigencia. Las aclaraciones se incorporan como fuentes versionadas con impactos revisables.
4. **Entrada técnica.** Cargar IFC, CAD, PDF y DWG/DXF mediante adaptadores que declaren los formatos realmente soportados. Enviar a motores de cuantificación, BIM, costos y programación sin bloquear la interfaz. Un formato no soportado debe producir un diagnóstico explícito, no resultados simulados.
5. **Bienvenida y preparación.** Presentar la bienvenida «BIENVENIDO A MEGALODON» y la animación de escualo. La duración visual deseada de 5–15 segundos no sustituye el estado real de los trabajos ni implica que el servidor termine en ese plazo.
6. **Primera vista útil.** Mostrar Workspace o BIM según disponibilidad efectiva. Ofrecer «Verificar el presupuesto» cuando existan datos suficientes y mostrar pendientes. Las plantillas y cantidades deben pertenecer a la misma revisión que el presupuesto presentado.
7. **Vista dividida.** Mantener el visor 3D y el editor CAD ocultable junto al panel de presupuesto. El visor deberá permitir rotación, vistas interiores, ocultar elementos y cambios autorizados de diseño, con confirmación explícita. Ocultar un elemento visualmente y modificar una cantidad económica son operaciones diferentes que requieren trazabilidad.
8. **Análisis económico.** Desglose por partidas, maquinaria, salarios, costos de construcción, memoria explicativa, tiempo, curva S, Monte Carlo compacto, 4D/5D, cronograma, Gantt y calendario. Todo resultado vinculante procede del cálculo servidor y su snapshot.
9. **Revisión en Workspace.** Aceptar, solicitar cambios o editar a mano. Conservar nombres, contratos, CV, responsables y posiciones de firma. «Aceptar todo» debe respetar versiones, permisos y validaciones de cada elemento; no sustituye evidencia ausente.
10. **Tezcatlipoca.** Acceso al sistema solar, navegación entre cuerpos celestes y acercamiento a Tierra. En el globo, habilitar capas y búsqueda geográfica, con datos fechados y disponibilidad real de proveedores. Se solicitan aviación, sismos, conflictos, bases militares, volcanes/fallas, redes, ferrocarriles, embarcaciones, drones, polos, radiofrecuencia, topografía y BIM. Se descartan apuntado de misiles y rastreadores ofensivos.
11. **Contexto de obra y modelo.** Acercamiento tipo Earth, topografía/telemetría y navegación panorámica. Al colocar el modelo se bloquea temporalmente la navegación del fondo, conservándolo visible. Guardar ubicación, orientación, revisión y evidencia; exportarla al Workspace.
12. **Entrega.** Preparar el ZIP con artefactos, evidencias e índice/manifest y habilitar descarga después de validar la revisión correspondiente. Generar o descargar el ZIP no equivale a presentar la proposición ante la convocante.

## Contratos e invariantes del backend

- Originales inmutables y derivados trazables. Las transformaciones no borran datos humanos ni reemplazan silenciosamente versiones aprobadas.
- Contexto de tenant/expediente comprobado en API, jobs y almacenamiento. El identificador enviado por el cliente no es autorización.
- Estados y errores reales de jobs: progreso, fallos, reintentos y deduplicación. Los módulos avanzan en paralelo sin presentar un trabajo pendiente como terminado.
- Cantidades, catálogo, presupuesto y formatos se vinculan por revisión y procedencia. Los importes finales se calculan y verifican en el servidor.
- Edición con control de versiones, conflictos explícitos y revisión de cambios antes de regenerar. Las firmas y aprobaciones cubren contenido específico.
- Archivos analizados con límites de recursos y rechazo explícito de contenido incompatible. La conservación de evidencia no prueba autenticidad criptográfica.

## Decisiones abiertas y alcance conservado

Quedan por precisar la regla exacta de destino tras la bienvenida, navegación por scroll o Siguiente, ubicación de cronogramas/4D/5D, nombre y alcance de Firma / Field SAT y política de advertencia/bloqueo de zonas de conflicto. La seguridad de API y archivos permanece activa en toda ubicación geográfica; la navegación a un mapa no demuestra infección por malware.

Street View casi en tiempo real permanece como objetivo pendiente del plan del usuario: proveedor, licencias, cobertura, fecha de captura, volumen, caché y costos. Las imágenes NASA no constituyen por sí solas un servicio panorámico de calle en tiempo real. Tampoco se considerarán mediciones topográficas sin escala, CRS, calibración y error verificables. No se elimina la capacidad solicitada ni se declara implementada sin esas condiciones.

## Fuentes nuevas y primer incremento de backend

El paquete prioritario contiene seis fuentes y su manifiesto; se comprobaron sus seis SHA-256. Los anexos salariales y de indirectos corresponden a supuestos específicos de CDMX en 2026. La convocatoria de Tlaxcala es histórica y no contiene todas las bases; las dos guías DOCX son referencias funcionales, no normas jurídicas ejecutables. No se aplican sus cifras universalmente.

Las fuentes originales se conservan fuera del repositorio. Este incremento utiliza documentos Office generados como fixtures y comprueba por separado que ambos DOCX aportados se pueden extraer sin modificar sus bytes. No incorpora adjuntos originales a un repositorio público.

**Incremento preparado:** validar paquetes Office antes de abrirlos en los extractores de fuentes: límites de expansión/entradas del perfil Workspace (64 MiB, 1000 entradas), rutas no ambiguas, rechazo de cifrado, compresión no soportada, macros y componentes activos. Los originales válidos no se reescriben. Los errores de validación se convierten en respuesta 422 antes de almacenar o confirmar una fuente inválida. Las firmas pasivas pueden conservarse como evidencia sin tratarlas como aprobación.

Esta protección de ingreso no sustituye antivirus, workers aislados, revisión jurídica, pruebas PostgreSQL ni el desarrollo del flujo completo. La siguiente continuación deberá conectar la preparación documental y sus estados reales con los jobs existentes, conservando la edición humana y la revisión del presupuesto.
