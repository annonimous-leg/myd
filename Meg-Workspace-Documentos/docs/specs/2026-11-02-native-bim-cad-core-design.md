# Diseño: núcleo BIM/CAD propio de Megalodon

**Fecha:** 2026-11-02  
**Estado:** diseño de ingeniería adoptado para ejecución incremental  
**Base de trabajo:** PR #43, commit `5118f73eeca1b13397b760ae5ecc4fcc908b2924`

## Objetivo

Construir dentro de Megalodon un conjunto de motores de dominio propios para procesar modelos BIM, producir documentación técnica verificable y conectar geometría, cantidades, costos, planificación, calidad, GIS y activos. El objetivo no es envolver un visor externo ni entregar una demostración: es mantener bajo control de Megalodon los algoritmos, el modelo interno, los documentos generados, la trazabilidad, las pruebas y los contratos de interoperabilidad.

## Decisión de arquitectura

Se separan tres capas para evitar que una biblioteca externa se convierta en el producto:

1. **Núcleo propio Megalodon.** Modelo geométrico normalizado en SI; identidad de elementos; topología de mallas; planos y sistemas de coordenadas; intersección y corte; proyección; medición; clasificación de aristas; composición de láminas; capas y estilos; serialización vectorial; historial y trazabilidad de revisiones. Las reglas de dibujo y geometría de dominio viven aquí y no importan IfcOpenShell, Three.js, SDK CAD ni servicios externos.
2. **Adaptadores de formatos.** IFC, DXF, PDF, SVG, nubes de puntos y futuros formatos se traducen a/desde contratos internos. El adaptador IFC actual utiliza IfcOpenShell porque el proyecto ya lo integra y necesita cobertura amplia de esquemas. El motor de dibujo consumirá la representación geométrica persistida de Megalodon, no llamará directamente a IfcOpenShell. Esto permite reemplazar el importador por etapas sin reescribir el motor de dibujo.
3. **Presentación y operación.** API multi-tenant, trabajos durables, almacenamiento privado, visor 2D/3D, herramientas de medición, láminas, descarga, permisos y auditoría. La interfaz no será la fuente de verdad de geometría o cantidades.

## Política de dependencia

- No se incorporará un servicio SaaS de terceros como motor principal de geometría, dibujo o almacenamiento del modelo.
- No se añadirá una dependencia Python/JS al núcleo geométrico salvo justificación documentada, licencia compatible, prueba comparativa y plan de sustitución.
- Las dependencias existentes pueden permanecer en adaptadores aislados mientras se desarrolla paridad propia. No se duplicarán ni se reescribirán precipitadamente.
- Se implementarán internamente los algoritmos de corte de malla, proyección, medición, composición de documentos y escritores SVG/DXF.
- El kernel inicial operará sobre geometría triangulada normalizada. Un kernel B-Rep/NURBS/operaciones booleanas exactas es una inversión posterior independiente; no se afirmará que existe antes de implementar y probar topología, tolerancias, intersecciones, sólidos y operaciones.
- No se implementará ingeniería inversa de formatos cerrados ni se anunciará edición nativa de DWG, RVT o SKP sin una implementación legal y técnicamente comprobada. Se ofrecerá interoperabilidad por formatos abiertos y adaptadores autorizados. Un formato interno propio se diseñará con versionado, especificación pública dentro del proyecto y pruebas de ida/vuelta.

## Primera entrega: motor de documentación vectorial derivada de IFC

La primera vertical funcional será generar dibujos vectoriales a partir de los meshes normalizados que ya persiste `ElementoBIM`.

### Tipos de vista

- **Planta:** corte horizontal a una elevación expresada en metros.
- **Sección:** corte por un plano vertical definido mediante origen y normal.
- **Alzado:** proyección ortográfica sobre un plano de vista, con clasificación explícita de contornos y aristas.

La primera versión de los algoritmos debe indicar con claridad el modo de visibilidad. Una salida de contornos/siluetas no se denominará eliminación de líneas ocultas. La eliminación vectorial exacta de líneas ocultas, proyección de elementos situados delante/detrás del plano de corte, anotaciones arquitectónicas automáticas y cotas reglamentarias son criterios de aceptación posteriores, no funciones que se puedan inferir por tener un SVG.

### Documento técnico

Cada documento debe conservar como metadatos: tenant, expediente, modelo fuente, revisión/fecha del modelo, parámetros de vista, unidades, escala, algoritmo y versión del motor, elementos incluidos, tolerancia geométrica, formato, checksum y estado de generación. Si cambia el modelo fuente, el dibujo queda marcado como obsoleto; nunca se modifica silenciosamente un plano ya emitido.

### Exportación

- SVG vectorial: escritor propio, determinista y verificable.
- DXF: escritor propio para entidades explícitamente soportadas, unidades y capas. La compatibilidad se probará abriendo los archivos con parsers independientes en CI; eso no convierte al parser de prueba en dependencia de runtime.
- PDF: salida vectorial con escala de papel, márgenes, orientación y cuadro de datos. El generador PDF se aislará del motor geométrico.
- DWG/DWF: no se declarará soporte nativo hasta disponer de un formato escritor/lector legal, probado y con cobertura suficiente.

## Alcance posterior del producto

La plataforma se divide en motores de dominio, no en una colección de pantallas sin contrato común:

1. **IFC y modelo interno:** importación, validación, GUID persistentes, árbol espacial, relaciones, propiedades, unidades, geometría y revisión.
2. **Geometría y topología:** mallas, planos, cortes, intersecciones, medición, tolerancias, referencias espaciales y, posteriormente, B-Rep/NURBS.
3. **Dibujo/CAD:** plantas, secciones, alzados, detalles, cotas, anotaciones, capas, estilos, layouts, escalas, impresión, DXF y un documento interno editable.
4. **Visor:** selección, aislamiento, filtros por disciplina/nivel/sistema/material, comparación de revisiones y superposición 2D/3D.
5. **BIM 4D/5D:** vínculos auditables con actividades, programa, cantidades, análisis de costos y avance; no calcular duraciones o precios no suministrados.
6. **GIS y topografía:** CRS, georreferenciación, coordenadas, superficies, TIN, volúmenes, infraestructura y puentes con Tezcatlipoca.
7. **Nubes de puntos:** LAS/LAZ, registro, clasificación, medición y comparación con diseño; este motor requiere una fase independiente.
8. **CDE, calidad y activos:** documentos, versiones, incidencias, listas de defectos, inspecciones, aprobaciones y activos con trazabilidad al elemento y ubicación.
9. **Gemelo digital y analítica:** series temporales, telemetría, indicadores y visualización; únicamente cuando existan fuentes y acuerdos de calidad de datos.

## Límites y decisiones explícitas

- El proyecto ya usa IfcOpenShell para importar IFC y Three.js para renderizar el visor. No se ocultará esa realidad. En esta arquitectura son adaptadores/presentación reemplazables, no el núcleo de dibujo propio.
- IFC 4.3.2.0 (ISO 16739-1:2024) será el objetivo normativo prioritario, manteniendo compatibilidad con versiones IFC 2x3 e IFC4 que ya admiten los modelos de prueba. La aceptación se medirá por fixtures y matrices de entidades/representaciones, no por una afirmación general de compatibilidad.
- Las cantidades declaradas en QTO IFC conservarán su procedencia; una medida geométrica calculada se etiquetará como calculada y no sustituirá silenciosamente una cantidad declarada.
- Se conserva la malla original y la fuente del modelo; el motor de dibujo no altera IFC ni los datos de costos.
- El catálogo de precios existente, incluidas las aproximadamente 23.000 referencias que el proyecto debe conservar, queda fuera de toda migración destructiva, reimportación o reindexación de esta iniciativa.
- Ningún trabajo se integra en `main` ni se despliega sin autorización específica.

## Criterios de aceptación de la primera vertical

1. El núcleo geométrico funciona con meshes normalizados sin importar IfcOpenShell, Three.js, Shapely ni servicios remotos.
2. Las unidades internas son metros; la normalización de planos, vectores, vértices y tolerancias rechaza NaN, infinito, normales nulas, índices inválidos y triángulos degenerados según una política explícita.
3. Los cortes atraviesan triangulaciones, aristas coincidentes, vértices en el plano y caras coplanares sin duplicar segmentos ni generar líneas de longitud cero.
4. Los resultados son deterministas para el mismo input y tolerancia.
5. SVG y DXF se serializan en forma vectorial, con capas y unidades documentadas.
6. Las pruebas usan tanto mallas sintéticas adversariales como IFC de fixtures reales de Megalodon; deben verificar geometría resultante y no solamente que el proceso no falle.
7. La generación se ejecuta como trabajo durable, tenant-scoped, idempotente y con artefactos privados cuando se conecte a la API.
8. El documento queda vinculado a una revisión de modelo y puede identificarse como obsoleto.
9. Los errores de geometría incompleta se reportan por elemento; no se inventan contornos ni se silencian pérdidas de cobertura.
10. CI prueba el motor sin conexión y prueba integración en PostgreSQL/worker con el harness del repositorio.

## Secuencia de ejecución

La primera rama desarrolla el núcleo geométrico y escritores vectoriales y los integra en el flujo BIM bajo trabajos durables. Las funciones de edición CAD general, kernel B-Rep, DWG/RVT/SKP nativos, nube de puntos, GIS avanzado, CDE completo y gemelo digital se entregan en planes independientes una vez que la vertical anterior tenga pruebas y criterios medibles.
