# Megalodon — Plan maestro de motores propios de ingeniería y construcción

> Documento rector. Cada subsistema tendrá una entrega revisable, pruebas propias y criterios de aceptación independientes. Este plan describe trabajo pendiente; no afirma que las capacidades listadas ya existan.

**Objetivo:** Convertir Megalodon en una plataforma de ingeniería, construcción, BIM/CAD y geoespacial, con documentación técnica generada desde modelos IFC y motores de dominio bajo control del proyecto.

**Criterio de propiedad:** Megalodon será propietario de sus contratos de datos, geometría normalizada, algoritmos de medición y dibujo, documentos generados, reglas BIM, persistencia, trazabilidad, lógica de calidad y experiencia de producto. Las bibliotecas de bajo nivel quedan encapsuladas en adaptadores reemplazables. No se dependerá de un servicio SaaS externo para calcular geometría, producir dibujos, cuantificar, revisar o guardar la fuente maestra.

## Estado real al 2 de noviembre de 2026

Rama de trabajo: feat/native-ifc-drawing-engine-2026-11-02. PR #44, Draft, con base en PR #43. No es main, no es una release ni está desplegada.

Ya están incorporados en la rama:
- Núcleo geométrico independiente de IFC/CAD/render: mallas trianguladas normalizadas en metros, planos, marcos de vista, cortes, planta, sección y silueta de alzado.
- Serializadores propios SVG y DXF ASCII R2000 para entidades LINE y capas.
- Modelo persistente DibujoBIM, migración aditiva, servicio de generación, trabajo durable BIM_DRAWING y endpoints de creación/listado/estado/descarga.
- Pruebas unitarias para geometría y exportación, fixtures IFC en metros y milímetros, y pruebas añadidas para trabajo/aislamiento.
- Corrección del inventario de tablas nuevas en la práctica de restauración histórica: dibujos_bim debe existir y estar vacío al actualizar desde un respaldo anterior a esa función.

**Todavía no debe anunciarse como producto terminado:** la última ejecución completa de CI conocida falló en migration-recovery porque su allowlist no incluía dibujos_bim. La corrección y las pruebas están en la rama; el SHA posterior debe obtener un CI completo en verde. La interfaz de dibujos en navegador, PDF vectorial, eliminación de líneas ocultas, acotación y revisión profesional todavía no están cerradas.

Referencias principales:
- Núcleo: backend/app/engines/bim/drawing/
- Servicio: backend/app/services/bim_drawing_service.py
- API: backend/app/api/v1/bim.py
- Persistencia: backend/app/models/bim.py y backend/alembic/versions/20261102_bim_drawings.py
- Cola durable: backend/app/core/process_queue.py
- Diseño: docs/specs/2026-11-02-native-bim-cad-core-design.md
- Plan detallado: docs/plans/2026-11-02-native-bim-cad-core.md

## Reglas permanentes

1. No modificar directamente main, la rama estable ni PR #42/#43.
2. No fusionar ni desplegar sin autorización específica.
3. No truncar, reemplazar, volver a importar ni reindexar el catálogo existente de aproximadamente 23.000 precios. Las futuras integraciones APU serán de lectura/controlada y tendrán conciliación explícita.
4. Toda operación sobre modelos, dibujos, mediciones, incidencias y documentos comprueba tenant, expediente, identidad de fuente y permisos.
5. Las unidades geométricas canónicas son metros; las unidades de salida se declaran. Datos no finitos, índices inválidos, mallas degeneradas y geometría incompleta se reportan; no se maquillan.
6. Todo artefacto conserva revisión de modelo, parámetros, versión del algoritmo, unidades, tolerancias, cobertura y checksum. Cambios en la fuente marcan derivados como obsoletos; no reescriben documentos emitidos.
7. No se llama a un SaaS para generar geometría o dibujos. El núcleo no importa IfcOpenShell, Three.js, Shapely, SDK CAD ni clientes HTTP.
8. IfcOpenShell permanece aislado como adaptador temporal de importación mientras el lector IFC propio demuestra cobertura equivalente. No se elimina por calendario ni por preferencia.
9. No se hará ingeniería inversa de formatos cerrados. DWG, DWF, RVT y SKP solo se soportan mediante especificaciones e interfaces legalmente disponibles; no se afirmará lectura/escritura nativa hasta demostrarlo.
10. Una prueba con fixture sintético no certifica compatibilidad general, exactitud profesional ni operación productiva. Todo reporte declara su alcance.
11. Trabajos largos usan la cola durable existente; almacenamiento privado, idempotencia y limpieza de artefactos huérfanos forman parte de la aceptación.
12. Cada fase requiere pruebas enfocadas, integración, navegador cuando aplique, revisión de seguridad y CI completo en el SHA exacto.

---

# Entrega 0 — Cerrar la primera vertical de dibujo IFC

**Resultado:** un usuario selecciona un IFC procesado, pide planta o sección, recibe un documento vectorial privado, lo visualiza y descarga SVG/DXF con procedencia verificable.

### Tarea 0.1 — Cerrar pruebas geométricas del núcleo

Archivos: backend/app/engines/bim/drawing/core.py, backend/tests/unit/test_bim_drawing_core.py y backend/tests/integration/test_bim_drawing_ifc.py.

- [ ] Añadir casos adversariales: corte por arista, vértice coplanar, parches coplanares de más de dos triángulos, componentes desconectados, inversión de orientación y coordenadas grandes con tolerancia pequeña.
- [ ] Verificar invariancia frente a milímetros/metros, orden de triángulos y orden de elementos.
- [ ] Comprobar determinismo exacto de segmentos ordenados.
- [ ] Ejecutar: cd backend && uv run pytest tests/unit/test_bim_drawing_core.py tests/integration/test_bim_drawing_ifc.py -q
- [ ] Ejecutar regresiones IFC: cd backend && uv run pytest tests/unit/test_bim_units.py tests/integration/test_bim_regressions.py -q

Salida: resultados geométricos exactos, no solo “no lanzó excepción”.

### Tarea 0.2 — Cerrar exportadores SVG/DXF

Archivos: backend/app/engines/bim/drawing/exporters.py y backend/tests/unit/test_bim_drawing_exporters.py; crear backend/tests/integration/test_dxf_roundtrip.py.

- [ ] Validar entidades, coordenadas, capas, escapes XML, tamaño físico, viewBox y rechazo de documentos vacíos/no finitos.
- [ ] Añadir un parser DXF independiente como herramienta de prueba solamente; comprobar unidades, secciones, capas, entidades y EOF.
- [ ] Probar ida/vuelta del subconjunto DXF declarado. La prueba no amplía silenciosamente la lista de entidades admitidas.
- [ ] Probar nombres IFC largos, acentos, comillas y caracteres XML.
- [ ] Ejecutar: cd backend && uv run pytest tests/unit/test_bim_drawing_exporters.py tests/integration/test_dxf_roundtrip.py -q

Salida: SVG válido y DXF verificable en lectores independientes para el subconjunto declarado.

### Tarea 0.3 — Cerrar servicio, cola durable y almacenamiento

Archivos: backend/app/services/bim_drawing_service.py, backend/app/core/process_queue.py y backend/tests/integration/test_bim_drawing_jobs.py.

- [ ] Probar commit atómico de DibujoBIM y TrabajoProceso, entrega repetida, error de storage, geometría alterada, revisión IFC alterada, malla ausente y permiso de geometría parcial.
- [ ] Probar más de 500 elementos para demostrar que el worker no trunca la fuente.
- [ ] Probar tenant isolation en creación/consulta/descarga.
- [ ] Si el segundo formato falla o falla el commit de BD, borrar lo ya subido o registrar una limpieza durable. No dejar artefactos huérfanos sin trazabilidad.
- [ ] Probar reentrega concurrente, pérdida del worker y reintento.
- [ ] Ejecutar: cd backend && uv run pytest tests/integration/test_bim_drawing_jobs.py tests/integration/test_durable_bim_jobs.py -q

Salida: job reproducible, seguro y recuperable.

### Tarea 0.4 — Endurecer contrato HTTP

Crear backend/tests/integration/test_bim_drawing_api.py y ajustar backend/app/api/v1/bim.py.

- [ ] Probar POST creación, GET lista, GET estado y descarga autenticada SVG/DXF.
- [ ] Probar otro tenant, otro expediente, modelo incompleto, dibujo pendiente, formato no generado, parámetros inválidos, formato duplicado y rate limit.
- [ ] La respuesta expone modo de visibilidad, revisión fuente, checksum y limitaciones.
- [ ] Ejecutar: cd backend && uv run pytest tests/integration/test_bim_drawing_api.py -q

Salida: contrato API probado en PostgreSQL.

### Tarea 0.5 — Workspace real en navegador

Crear frontend/app/src/apps/bim-calculator/components/DrawingWorkspace.tsx y frontend/app/tests/bim-drawing-browser.test.mjs; integrar en frontend/app/src/apps/bim-calculator/index.tsx y cliente API existente.

- [ ] Añadir controles reales para planta, sección y alzado, con parámetros requeridos por tipo.
- [ ] Mostrar estado del job, cobertura de mallas, revisión fuente, checksum, errores y obsolescencia.
- [ ] Previsualizar el SVG realmente generado en backend. No dibujar un sustituto en el navegador.
- [ ] Permitir descargar solo formatos existentes y completados.
- [ ] Aceptación browser: usuario autenticado genera planta y sección desde un IFC fixture, visualiza, descarga, recarga y ve el mismo documento; otro tenant es rechazado.
- [ ] Ejecutar: cd frontend/app && npm run build && node --test tests/bim-drawing-browser.test.mjs

Salida: flujo usable, sin botones decorativos ni fixtures presentados como planos oficiales.

### Tarea 0.6 — Lámina de impresión vectorial

Crear backend/app/engines/bim/drawing/sheets.py, backend/app/engines/bim/drawing/pdf_exporter.py y backend/tests/unit/test_bim_drawing_pdf.py.

- [ ] Definir hoja, escala, márgenes, orientación, cajetín, número, fecha, revisión, unidades y viewports.
- [ ] Generar PDF vectorial desde el documento de dibujo, no desde una captura rasterizada.
- [ ] Probar tamaños ISO A0–A4, escala física, textos, grosores, clipping, orientación y múltiples viewports.
- [ ] Abrir salida con parser independiente y verificar dimensiones de página y objetos vectoriales.

Gate de Entrega 0: todas las tareas 0.1–0.6 y CI completo pasan. La implementación actual cubre parte del núcleo y backend, no toda la entrega de producto. Los alzados actuales son siluetas, no HLR.

---

# Entrega 1 — Dibujo constructivo profesional

Resultado: plantas/secciones/alzados con líneas visibles/ocultas, cotas, niveles, detalles, anotaciones y actualización controlada.

### Tarea 1.1 — Eliminación de líneas ocultas (HLR)

Crear backend/app/engines/bim/drawing/visibility.py y occlusion.py.

- [ ] Proyectar triángulos y conservar profundidad.
- [ ] Dividir aristas candidatas en intervalos donde cambia la oclusión.
- [ ] Clasificar visible, oculta, coincidente y tangente con tolerancias declaradas.
- [ ] Resolver oclusión entre elementos distintos, no solo adyacencia de caras de una malla.
- [ ] Probar sólidos delante/detrás, superficies coplanares, contactos, huecos, perfiles delgados y rayos tangentes.
- [ ] Comparar contra dibujos patrón revisados y publicar cobertura por representación.

La silueta de una malla nunca se etiqueta como HLR.

### Tarea 1.2 — Acotación y anotación

Crear backend/app/engines/bim/drawing/annotations.py y dimensions.py.

- [ ] Añadir entidades independientes: texto, cota lineal/alineada/angular, nivel, eje, etiqueta y llamada.
- [ ] Separar cotas calculadas desde geometría de cotas introducidas por persona.
- [ ] Conservar unidad, precisión, elemento fuente y regla de redondeo.
- [ ] Detectar colisiones de texto y anotaciones fuera de hoja; advertir sin mover silenciosamente cotas revisadas.
- [ ] Probar redondeo, unidades, orientación, referencias y estabilidad entre revisiones.

### Tarea 1.3 — Detalles, estilos y plantillas

Crear backend/app/engines/bim/drawing/styles.py y templates.py.

- [ ] Definir capas y estilos versionados para arquitectura, estructura, MEP y obra civil.
- [ ] Añadir detalles y escalas independientes por viewport.
- [ ] Guardar plantillas por organización/proyecto con tenant isolation.
- [ ] Probar que modificar plantilla no cambia dibujos emitidos.
- [ ] Comparar revisiones de dibujo y modelo IFC.

---

# Entrega 2 — Motor CAD 2D propio

Resultado: modelo editable de dibujo técnico dentro de Megalodon; DXF es formato de intercambio, no la fuente de verdad.

### Tarea 2.1 — Documento CAD interno

Crear backend/app/engines/cad/document.py, entities.py, layers.py, blocks.py y transforms.py.

- [ ] Definir identificadores y entidades: punto, línea, polilínea, arco, círculo, texto, bloque, referencia, cota y viewport.
- [ ] Definir unidades, coordenadas, capas, estilos, visibilidad, grosores y orden de dibujo.
- [ ] Añadir serialización versionada del documento.
- [ ] Probar transformaciones, copia, borrado, selección, referencias y round-trip.
- [ ] Mantener documento CAD propio; exportar DXF no lo sustituye.

### Tarea 2.2 — Operaciones de edición

Crear backend/app/engines/cad/commands.py, snapping.py, constraints.py y history.py.

- [ ] Implementar comandos transaccionales de creación, movimiento, rotación, escala, recorte, extensión, copia y borrado.
- [ ] Añadir snaps y restricciones explícitas; no inferir restricciones silenciosamente.
- [ ] Añadir undo/redo por operación, auditoría y recuperación tras recarga.
- [ ] Probar geometría, concurrencia y edición simultánea.

### Tarea 2.3 — Intercambio DXF

Crear backend/app/engines/cad/dxf_reader.py, dxf_writer.py y backend/tests/integration/test_dxf_roundtrip.py.

- [ ] Definir versión y matriz de entidades admitidas.
- [ ] Leer/escribir entidades y bloques soportados; preservar entidades desconocidas como datos opacos cuando la especificación lo permita.
- [ ] Rechazar con diagnóstico entidades que no puedan preservarse sin pérdida.
- [ ] Probar ida/vuelta con parsers independientes.

---

# Entrega 3 — Importador IFC propio y modelo semántico

Resultado: reducir progresivamente IfcOpenShell sin perder propiedades, jerarquía, unidades ni geometría.

### Tarea 3.1 — STEP Part 21

Crear backend/app/engines/bim/ifc_native/part21_lexer.py, part21_parser.py y values.py.

- [ ] Implementar lexicalización y parsing de registros, referencias, cadenas escapadas, enumeraciones, listas, números y tipos complejos.
- [ ] Detectar referencias sin resolver, duplicados, truncamiento, registros inválidos y tamaños excesivos.
- [ ] Preservar ubicación de registro y errores para diagnóstico.
- [ ] Probar archivos válidos, corruptos y adversariales.

### Tarea 3.2 — Esquema y grafo IFC

Crear schema.py, entities.py, relationships.py, units.py y placements.py dentro de ifc_native.

- [ ] Introducir metadatos de esquema y tipos IFC; iniciar por los tipos/relaciones de documentación arquitectónica.
- [ ] Preservar GlobalId, árbol espacial, contención, materiales, propiedades, cantidades y relaciones.
- [ ] Normalizar unidades y placements sin perder coordenadas georreferenciadas.
- [ ] Validar IFC2x3, IFC4 e IFC4.3 mediante matriz explícita; no afirmar soporte global antes de comprobarlo.

### Tarea 3.3 — Tessellación propia por representación

Crear representations.py y tessellation.py.

- [ ] Implementar progresivamente extrusiones, swept solids, perfiles, mapeos, boolean clipping y representaciones trianguladas.
- [ ] Preservar precisión, orientación, materiales y transformaciones.
- [ ] Reportar representación no soportada con GlobalId; nunca omitir silenciosamente elementos.
- [ ] Ejecutar ambos importadores sobre una batería común y comparar identidad, dimensiones, volumen, área, bbox y malla.
- [ ] Cambiar importador preferido solo tras demostrar cobertura equivalente en la matriz soportada.

---

# Entrega 4 — Kernel geométrico 3D propio

Resultado: operaciones topológicas robustas para edición, análisis e interoperabilidad.

### Tarea 4.1 — Estructura topológica

Crear backend/app/engines/geometry/topology.py, half_edge.py y brep.py.

- [ ] Introducir vértices, aristas, half-edges, loops, shells, caras y sólidos con invariantes.
- [ ] Validar manifold, orientación, límites abiertos, caras degeneradas y referencias huérfanas.
- [ ] Probar cubos, prismas, cilindros, sólidos con agujeros y geometría inválida.

### Tarea 4.2 — Predicados y operaciones

Crear predicates.py, intersections.py, booleans.py y tessellate.py.

- [ ] Definir política de precisión/tolerancia y predicados robustos.
- [ ] Implementar intersección, unión y diferencia en el subconjunto B-Rep declarado.
- [ ] Probar degeneraciones, tangencias, caras coincidentes, escalas extremas y operaciones repetidas.
- [ ] Mantener trazabilidad entre geometría resultante y elementos fuente.

### Tarea 4.3 — Superficies avanzadas

- [ ] Añadir superficies analíticas (plano, cilindro, cono y esfera) con pruebas de evaluación, normal y proyección.
- [ ] Añadir NURBS después de definir parametrización, knots, pesos, continuidad y tolerancia.
- [ ] Publicar límites de operaciones soportadas; no llamar kernel industrial al subconjunto parcial.

---

# Entrega 5 — BIM 4D/5D y control económico

Resultado: conectar BIM, catálogo, presupuesto, programa y ejecución sin inventar precios ni rendimientos.

Archivos existentes: backend/app/services/bim_service.py, backend/app/models/bim.py, frontend/app/src/apps/bim-calculator/, catálogo APU y programación.

- [ ] Definir reglas IFC → concepto/APU con procedencia, unidad y revisión.
- [ ] Diferenciar QTO declarado de cantidad calculada geométricamente.
- [ ] Mantener incompletos como pendientes; cantidad desconocida no puede habilitar aprobación.
- [ ] Añadir auditoría de partida, cantidad, precio, fuente, fecha, región y usuario.
- [ ] Vincular elementos a actividades, dependencias y secuencias 4D.
- [ ] Comparar avance ejecutado, estimación, presupuesto aprobado y geometría as-built.
- [ ] Leer el catálogo existente sin modificarlo; toda migración futura requiere inventario, backup, conciliación y aprobación.
- [ ] Probar cobertura, unidades, redondeos, precios faltantes y reestimación.

---

# Entrega 6 — GIS, topografía e infraestructura

Resultado: modelo espacial consistente desde levantamientos hasta infraestructura y activos georreferenciados.

Integración existente: backend/app/models/topografia.py y Tezcatlipoca.

- [ ] Definir contrato espacial con CRS horizontal/vertical, datum, unidades, eje y época.
- [ ] Validar transformaciones contra puntos de control conocidos; CRS desconocido no se presume.
- [ ] Desarrollar TIN, perfiles, curvas, áreas, volúmenes de corte/relleno y superficies con error cuantificado.
- [ ] Integrar geometría BIM con GIS sin mezclar coordenadas locales y geográficas.
- [ ] Añadir corredores, vialidades, puentes, redes y activos lineales con modelo topológico.
- [ ] Probar CRS, precisión, unidades, geometrías inválidas y comparación de control.

---

# Entrega 7 — Motor de nubes de puntos

Resultado: ingesta, indexación, consulta, medición y comparación de escaneos de obra.

- [ ] Implementar lector LAS 1.4 por especificación, validando encabezado, VLR/EVLR, escala, offset, clasificación, retorno, color y límites.
- [ ] Diseñar almacenamiento por bloques y niveles de detalle; no cargar millones de puntos en el navegador.
- [ ] Añadir filtros, selección espacial, secciones, perfiles, densidad y medición.
- [ ] Registrar alineación entre levantamiento y modelo BIM con error residual y puntos de control.
- [ ] Comparar diseño/as-built y generar desviación con tolerancia por disciplina.
- [ ] Añadir LAZ con códec especificado y aislado; LAS no se presenta como lector LAZ.
- [ ] Probar integridad, escalas, streaming y memoria.

---

# Entrega 8 — CDE, calidad y activos

Resultado: entorno de datos común multiusuario con versiones, emisión documental e incidencias ligadas a geometría.

- [ ] Definir revisión, estado, clasificación, transmittal, aprobador, firma, retención y ciclo de vida documental.
- [ ] Vincular defectos, inspecciones y checklists a elemento IFC, ubicación, documento y fotografía.
- [ ] Implementar workflows con permisos por organización, expediente, disciplina y rol.
- [ ] Añadir historial inmutable de operaciones, comentarios y evidencias.
- [ ] Gestionar activos: identificador, ubicación, sistema, fabricante, mantenimiento, garantía y estado.
- [ ] Probar concurrencia, permisos, retención, cambios de revisión y exportación de auditoría.

---

# Entrega 9 — Gemelo digital e inteligencia empresarial

Resultado: relacionar modelo y activos con telemetría, operación y métricas sin fabricar datos ni indicadores.

- [ ] Definir conectores de telemetría autenticados y esquemas versionados.
- [ ] Almacenar series temporales con timestamp, unidad, dispositivo, activo y calidad.
- [ ] Vincular señales a activos y visualizar estado temporal sobre el modelo.
- [ ] Definir indicadores reproducibles desde fuentes trazables.
- [ ] Añadir alertas por reglas explícitas, auditoría y revisión humana.
- [ ] Probar pérdida de datos, duplicados, retrasos, cambios de unidades y desconexión.

---

# Entrega 10 — Interoperabilidad y política de formatos

- IFC: formato BIM de intercambio prioritario; lector propio conforme a versiones y representaciones aceptadas.
- DXF: lector/escritor propio por subconjunto probado; extender versión y cobertura progresivamente.
- SVG/PDF: documentos vectoriales propios.
- LAS: lector propio; LAZ como códec separado.
- DWG/DWF/RVT/SKP: no anunciar compatibilidad nativa sin documentación y derechos de implementación. Se ofrecen adaptadores permitidos y flujos neutrales; el modelo interno es fuente de verdad.

Cada adaptador tiene contrato, matriz de cobertura, preservación de propiedades, política para datos desconocidos, tests round-trip y límites explícitos.

## Gate de producción para cada entrega

1. Tests unitarios con entradas válidas, límites y datos corruptos.
2. Integración contra PostgreSQL/PostGIS y storage privado de test.
3. Redelivery, pérdida de worker, reintento, timeout y recuperación.
4. Tenant isolation y pruebas negativas.
5. Navegador para todo flujo operado por usuario.
6. Artefactos inspeccionables y checksums; logs sin datos sensibles.
7. Revisión de licencias y dependencias.
8. Benchmark sobre modelos reales de distintos tamaños con memoria/tiempo medidos.
9. CI completo en SHA exacto; no se omiten pruebas para conseguir verde.
10. Aprobación independiente antes de merge o despliegue.

## Política de releases y datos

Cada vertical usa PR y rama revisable. Los subsistemas independientes se implementan en planes separados; no se acumulan en una sola migración. Antes de migrar datos reales se requiere inventario de solo lectura, backup verificado, ensayo de restauración y conciliación. El catálogo preexistente se preserva sin sustitución ni reimportación.

## Próximo orden de ejecución

1. Cerrar Gate de Entrega 0: CI, pruebas de worker/tenant/storage y UI browser.
2. Cerrar HLR y PDF vectorial antes de anunciar planos imprimibles de construcción.
3. Construir editor CAD 2D interno y contrato DXF.
4. Desarrollar lector IFC nativo por esquema y cobertura comparativa.
5. Abrir planes independientes para B-Rep, GIS/topografía, nube de puntos y CDE.
