# Motor propio de dibujos técnicos IFC — Plan de ejecución detallado

> **Ejecución por tareas:** cada cambio debe pasar su prueba enfocada, la integración afectada y CI del SHA resultante antes de continuar a la siguiente puerta.

**Objetivo:** entregar la primera capacidad funcional de documentación técnica dentro de Megalodon: solicitar planta/sección/alzado desde un modelo IFC procesado, producir geometría vectorial mediante motores propios, conservar fuente/checksum/revisión y operar el flujo desde navegador con artefactos privados.

**Arquitectura:** el núcleo geométrico Python consume mallas normalizadas en metros. El adaptador IFC actual alimenta elementos y geometría persistidos. Servicio y worker durable producen un documento intermedio y serializadores propios SVG/DXF. La API controla tenant/expediente/revisión y el frontend muestra únicamente artefactos producidos por el backend.

**Stack:** Python 3.12, SQLAlchemy async, PostgreSQL/PostGIS, Alembic, FastAPI, cola durable TrabajoProceso, storage privado existente, pytest, SVG y DXF ASCII. La UI usa React/Vite y Playwright del repositorio.

## Restricciones globales

- Rama: feat/native-ifc-drawing-engine-2026-11-02; PR Draft #44; base PR #43.
- No modificar main, PR #42, PR #43 ni la rama candidata estable directamente.
- No fusionar ni desplegar.
- No alterar el catálogo existente de aproximadamente 23.000 precios.
- Núcleo independiente de IfcOpenShell, Three.js, Shapely, SDK CAD y servicios remotos.
- IfcOpenShell permanece como adaptador de importación hasta que el lector propio demuestre cobertura.
- No declarar HLR, PDF, acotación profesional, DWG/RVT/SKP nativo ni CAD paramétrico antes de aceptación específica.
- Geometría inválida/incompleta se informa por elemento; no se fabrican contornos.
- Cada dibujo conserva tenant, expediente, modelo fuente, revisión, parámetros, tolerancia, motor, versión, cobertura y checksum.
- Los trabajos largos son durables e idempotentes; fallos de storage/commit no pueden publicar resultados parciales.

## Estado observado en esta rama

| Componente | Implementación existente | Estado de cierre |
|---|---|---|
| Núcleo geométrico | drawing/core.py | Implementado; falta CI verde del SHA final y ampliar casos adversariales |
| SVG/DXF | drawing/exporters.py | Implementado para SVG y DXF LINE/layers; falta validación con parser independiente |
| Persistencia | modelo DibujoBIM y migración 20261102_bim_drawings | Implementado; falta cerrar recuperación CI |
| Servicio | BIMDrawingService | Implementado; falta test exhaustivo de fallos de storage/cleanup |
| Cola durable | job BIM_DRAWING en process_queue | Implementado; falta acceptance de redelivery y fallos específicos |
| API | endpoints POST/list/get/download | Implementados; faltan pruebas API dedicadas |
| Browser workspace | no existe aún | Pendiente |
| PDF/HLR/cotas | no existe aún | Fuera del primer incremento del motor |

---

## Tarea 1 — Cerrar geometría y cortes IFC

**Archivos:**
- Modificar: backend/app/engines/bim/drawing/core.py
- Modificar: backend/tests/unit/test_bim_drawing_core.py
- Modificar: backend/tests/integration/test_bim_drawing_ifc.py

**Interfaces:**
- Entradas: MeshElement, Plane, ViewFrame.
- Salidas: cut_mesh_with_plane, build_plan_document, build_section_document, build_elevation_document.

- [ ] Añadir pruebas para triángulos coplanares adyacentes en parche grande, corte por arista, corte por vértice, componentes desconectados, caras con winding invertido, coordenadas grandes y malla no manifold.
- [ ] Ejecutar:
  cd backend && uv run pytest tests/unit/test_bim_drawing_core.py tests/integration/test_bim_drawing_ifc.py -q
- [ ] Asegurar que la tolerancia se expresa en metros y no se incrementa para tapar defectos.
- [ ] Ejecutar regresiones IFC existentes:
  cd backend && uv run pytest tests/unit/test_bim_units.py tests/integration/test_bim_regressions.py -q
- [ ] Commit independiente solo cuando todo pase.

## Tarea 2 — Cerrar formato vectorial

**Archivos:**
- Modificar: backend/app/engines/bim/drawing/exporters.py
- Modificar: backend/tests/unit/test_bim_drawing_exporters.py
- Crear: backend/tests/integration/test_dxf_roundtrip.py

- [ ] Añadir parser DXF independiente solo en entorno de pruebas.
- [ ] Validar encabezado, unidades, capas, entidades, escala de coordenadas, EOF y caracteres XML.
- [ ] Probar escritura, lectura independiente y round-trip del subconjunto admitido.
- [ ] Probar rechazo explícito de entidades/formas no soportadas y coordenadas no finitas.
- [ ] Ejecutar:
  cd backend && uv run pytest tests/unit/test_bim_drawing_exporters.py tests/integration/test_dxf_roundtrip.py -q
- [ ] Documentar la versión DXF y la tabla exacta de entidades que produce el escritor.

## Tarea 3 — Cerrar servicio, almacenamiento y cola

**Archivos:**
- Modificar: backend/app/services/bim_drawing_service.py
- Modificar: backend/app/core/process_queue.py
- Modificar: backend/tests/integration/test_bim_drawing_jobs.py

- [ ] Probar request y trabajo durable creados en la misma transacción.
- [ ] Probar generación real SVG/DXF desde una malla proveniente de IFC fixture.
- [ ] Probar que una segunda entrega no genera un segundo artefacto.
- [ ] Probar modificación geométrica posterior al request: el worker debe rechazar la salida por checksum distinto.
- [ ] Probar revisión IFC/updated_at cambiada antes de ejecutar.
- [ ] Probar más de 500 elementos: no limitar ni truncar el conjunto consultado.
- [ ] Probar malla faltante, malla inválida, geometría parcial permitida y no permitida.
- [ ] Probar aislamiento entre tenant A y tenant B en creación, consulta y descarga.
- [ ] Probar fallo en la segunda subida, fallo en flush/commit y limpieza de archivos ya subidos. Si no se puede limpiar en el mismo proceso, registrar una intención de limpieza durable con reintentos.
- [ ] Probar worker muerto, reentrega, publicación fallida y ejecución concurrente.
- [ ] Ejecutar:
  cd backend && uv run pytest tests/integration/test_bim_drawing_jobs.py tests/integration/test_durable_bim_jobs.py -q

## Tarea 4 — Cerrar contrato HTTP

**Archivos:**
- Modificar: backend/app/api/v1/bim.py
- Crear: backend/tests/integration/test_bim_drawing_api.py

- [ ] Probar POST creación, GET colección, GET objeto y descarga autenticada para SVG/DXF.
- [ ] Probar 404 al cruzar tenant/expediente y 409 para modelo incompleto o dibujo no terminado.
- [ ] Probar formato no generado, formatos duplicados, tipo desconocido, parámetros incompletos, tolerancia no finita y ausencia de permisos de escritura.
- [ ] Probar que la respuesta expone estado, elementos con/sin malla, revision, checksum, modo de visibilidad y limitaciones del algoritmo.
- [ ] Ejecutar:
  cd backend && uv run pytest tests/integration/test_bim_drawing_api.py -q

## Tarea 5 — Workspace de dibujos en navegador

**Archivos:**
- Crear: frontend/app/src/apps/bim-calculator/components/DrawingWorkspace.tsx
- Modificar: frontend/app/src/apps/bim-calculator/index.tsx
- Modificar: cliente API BIM existente
- Crear: frontend/app/tests/bim-drawing-browser.test.mjs

- [ ] Añadir selector de planta/sección/alzado, elevación o plano vertical, tolerancia y título.
- [ ] Mostrar lista de dibujos, estado del job, fecha/revisión, checksum, cobertura y aviso obsoleto.
- [ ] Mostrar el SVG real devuelto por API; no calcular una vista alternativa en cliente.
- [ ] Habilitar descarga únicamente de formatos generados.
- [ ] Prueba browser: autenticar usuario, abrir modelo, crear planta y sección, esperar worker, visualizar, descargar, recargar y comprobar misma revisión.
- [ ] Prueba negativa: otro tenant no puede consultar ni descargar el dibujo.
- [ ] Ejecutar:
  cd frontend/app && npm run build
  cd frontend/app && node --test tests/bim-drawing-browser.test.mjs

## Tarea 6 — PDF vectorial y láminas

**Archivos propuestos:**
- Crear: backend/app/engines/bim/drawing/sheets.py
- Crear: backend/app/engines/bim/drawing/pdf_exporter.py
- Crear: backend/tests/unit/test_bim_drawing_pdf.py

- [ ] Definir modelo de hoja con ISO A0–A4, orientación, escala, márgenes, cajetín, número, título, revisión y viewports.
- [ ] Generar trazos/textos vectoriales desde DrawingDocument; no rasterizar el plano.
- [ ] Probar escala física, clipping, fuentes, grosores, múltiples viewports y páginas.
- [ ] Abrir PDF con lector independiente y validar dimensión, vector content y fonts.
- [ ] Incorporar PDF a la API solo después de que el writer y el parser independiente pasen.

## Tarea 7 — HLR y anotación profesional

**Archivos propuestos:**
- Crear: backend/app/engines/bim/drawing/visibility.py
- Crear: backend/app/engines/bim/drawing/occlusion.py
- Crear: backend/app/engines/bim/drawing/dimensions.py
- Crear: backend/tests/unit/test_bim_drawing_visibility.py
- Crear: backend/tests/unit/test_bim_drawing_dimensions.py

- [ ] Clasificar aristas y subdividir intervalos en función de oclusión entre mallas distintas.
- [ ] Probar superficies coincidentes, tangencias, huecos, objetos delante/detrás y geometría coplanar.
- [ ] Modelar cotas, niveles, ejes, textos y llamadas como entidades independientes.
- [ ] Separar dimensiones calculadas de anotaciones introducidas por persona.
- [ ] Verificar contra dibujos patrón revisados por ingeniería. No llamar HLR a siluetas ni “plano constructivo listo” a un SVG sin anotaciones.

## Aceptación de esta primera capacidad

- Usuario autenticado abre un IFC procesado.
- Solicita planta o sección definida en metros.
- Worker durable genera salida desde geometría persistida con el motor propio.
- SVG/DXF válidos según parser independiente.
- Artefacto privado, recuperable, idempotente, ligado a revisión/checksum.
- Cambios en geometría invalidan derivado anterior.
- UI browser prueba el flujo y tenant isolation.
- CI completo en verde en el SHA exacto.

Fuera de esta primera capacidad: HLR, cotas automáticas, PDF, impresión completa, CAD editable, B-Rep, parser IFC propio, DWG/RVT/SKP, GIS avanzado, nubes de puntos, CDE y gemelo digital. Esas entregas están secuenciadas en el plan maestro.
