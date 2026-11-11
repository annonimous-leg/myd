# BIM4LCA: cobertura y propuestas de medición económica

Base aceptada: `7bbc389`, con 868 elementos admitidos. Este cierre registra los 573 IfcBuildingElement restantes, sus relaciones y reglas candidatas. No hay partidas contractuales vinculadas a BIM4LCA. Los catálogos ORO son de otras obras y no se aplican sin vinculación expresa.

## Inventario del IFC de prueba

| Tipo | Restantes | Cubiertos por malla de conjunto | Representación propia pendiente | Conjunto pendiente |
| --- | ---: | ---: | ---: | ---: |
| IfcMember | 452 | 8 | 444 | 0 |
| IfcPlate | 78 | 0 | 78 | 0 |
| IfcCurtainWall | 27 | 0 | 0 | 27 |
| IfcStairFlight | 11 | 11 | 0 | 0 |
| IfcBuildingElementProxy | 3 | 0 | 3 | 0 |
| IfcRamp | 1 | 0 | 0 | 1 |
| IfcRampFlight | 1 | 0 | 1 | 0 |
| Total | 573 | 19 | 526 | 28 |

545 de los restantes declaran representación propia: los 526 pendientes más los 19 ya cubiertos. Se confirma cobertura únicamente cuando un producto figura entre los componentes usados en una malla real del conjunto. El parentesco IFC por sí solo no basta. Los 526 requieren incorporar el tipo y verificar su geometría, unidad y alcance; los tres Proxy requieren además clasificación funcional/material. Los 27 muros cortina y la rampa necesitan tratamiento de sus componentes. Esta auditoría conserva los 868 admitidos y no amplía automáticamente la selección.

También hay 25 relaciones padre/componente entre los admitidos. Se registran aunque los elementos tengan APU distintos: dos APU no demuestran que los alcances sean disjuntos.

## Reglas candidatas y fuente

Cada producto conserva GUID, identificador STEP, representación propia, padres, hijos, ancestros, descendientes, relaciones IFC de origen, cobertura demostrada, tratamiento adicional y regla candidata. Los registros detallados permanecen locales; este documento no contiene coordenadas ni identificadores del modelo privado.

- Conjunto: candidato a pagar el padre si el concepto contratado es integral; candidato a pagar componentes si el contrato desglosa conceptos.
- Componente: candidato a medición separada solo si el concepto contratado y sus inclusiones/exclusiones lo sustentan, sin repetir lo comprendido en el padre.
- Elemento independiente: medir conforme a unidad y alcance del concepto, sin deducirlos únicamente del tipo IFC.

La fuente de estas hipótesis son las relaciones IFC y los componentes de malla. No son reglas contractuales aprobadas. La decisión final necesita el catálogo contratado de esta obra, especificaciones de medición y pago, APU y aclaraciones. Por ejemplo, una escalera integral por pieza y conceptos separados de concreto, acero o cimbra requieren políticas de medición diferentes.

Todos los casos de BIM4LCA mantienen `partida_contractual=null`, `sustento_contractual=null` y aprobación económica pendiente. Las familias muestran advertencia de posible doble conteo. La revisión contractual posterior debe vincular expresamente el concepto, identificar si paga padre o componentes y conservar la referencia que sustenta esa decisión.

## Volúmenes geométricos

Se revisaron los 360 volúmenes propuestos por geometría con topología indexada cerrada, orientación de aristas y un cálculo independiente mediante tetraedros con origen trasladado. Los 360 pasan consistencia numérica, con tolerancias de comparación de 1e-8 m³ absoluta y 1e-6 relativa. Se conservan 500 volúmenes QTO y ocho no disponibles; las 868 mallas siguen presentes.

Esto no certifica ausencia de toda autointersección ni solapamiento entre sólidos, ni decide volumen neto/bruto, material o alcance de pago. Cero cantidades de BIM4LCA quedan aprobadas económicamente por esta auditoría.

## Protección aplicada al presupuesto

Un volumen `GEOMETRIA_CALCULADA` positivo queda pendiente al costear en m³. La revisión usa la captura existente con cantidad revisada, referencia, usuario y fecha; conserva el valor y la fuente originales. La interfaz identifica la propuesta y permite revisarla. Esa captura no asigna por sí sola una partida contractual a BIM4LCA.

Si un presupuesto incluye padre y componentes de una misma familia sin política resuelta, ambos lados quedan pendientes y no se cobran juntos. El presupuesto conserva las parejas, la regla candidata, su fuente y el sustento contractual pendiente. No se selecciona automáticamente uno de los dos lados.

Las mediciones admitidas para cada versión se guardan en `mediciones_economicas`. 4D usa esas mediciones para su costo y no vuelve a introducir cantidades pendientes desde el modelo. La generación real de una nueva versión y su aprobación siguen siendo acciones explícitas.

## Reproducción

Desde el backend:

```sh
python -m scripts.audit_bim_coverage /ruta/privada/model.ifc --output-dir /ruta/privada/auditoria
```

Produce resumen JSON, inventario, 573 restantes en JSON/CSV, revisión de volúmenes en JSON/CSV y relaciones entre admitidos. Estos archivos contienen identificadores BIM y deben conservarse junto al expediente de revisión. El comando no consulta catálogos, no crea partidas y no aprueba pagos.

La verificación local incluye regresiones económicas con base desechable, unidades y planos IFC, exportación del informe y revisión de linaje; pruebas de navegador de escritorio/móvil y del encuadre; compilación TypeScript/Vite y ESLint sin errores. La CI de PostgreSQL y la aceptación de navegador se registran por SHA en la PR.
