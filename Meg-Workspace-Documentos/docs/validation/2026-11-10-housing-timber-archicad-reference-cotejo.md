# Cotejo de referencia · vivienda de madera Archicad As-Built

Se aplicó `cotejar_niveles` con tolerancia de 0.010 m a las cotas de posición IFC obtenidas con `MotorBIM.cotas_niveles()` y a la tabla N2000 de la ficha BIM de Archicad. Los nombres se conservan como aparecen en las fuentes. El delta es IFC Archicad menos IFC Revit.

| Nivel en la ficha BIM | Ficha N2000 (m) | IFC Archicad (m) | IFC Revit (m) | Delta (m) |
| --- | ---: | ---: | ---: | ---: |
| Sea level | 0.000 | 0.000 (`Sea_Level`) | 0.000 | 0.000 |
| Foundations | 47.300 | 47.300 | 47.300 | 0.000 |
| Basement | 49.070 | 49.070 | 49.070 | 0.000 |
| Level_01 | 52.000 | 52.000 | 52.000 | 0.000 |
| Level_02 | 55.144 | 55.144 | 55.144 | 0.000 |
| Level_03 | 58.458 | 58.458 | 58.458 | 0.000 |
| Level_04 | 61.772 | 61.772 | 61.772 | 0.000 |
| Roof | 64.677 | 64.677 | 64.677 | 0.000 |

La primera fila muestra las dos cotas para revisión humana. El comparador conserva la distinción entre espacio y guion bajo.

| Par | Coincidencias estrictas | Diferencias de altura entre pares | Sin par nominal | Confirmación automática de niveles |
| --- | ---: | ---: | --- | --- |
| Ficha BIM / IFC Archicad | 7 | 0 | `Sea level` / `Sea_Level` | Bloqueada |
| Ficha BIM / IFC Revit | 8 | 0 | Ninguno | Apta según el comparador |
| IFC Revit / IFC Archicad | 7 | 0 | `Sea level` / `Sea_Level` | Bloqueada |

## Coordenadas y alcance

Archicad declara metros como unidad de longitud del proyecto y Revit declara milímetros. La ficha indica ETRS-GK25 y datum vertical N2000. La conversión cartográfica de Archicad declara Este/Norte de 25493950/6677600, mientras la de Revit declara 0/0. La coincidencia de cotas verticales no valida una superposición horizontal ni sustituye la resolución de la transformación para Tezcatlipoca.

El PLA se inspeccionó como contenedor nativo. No se identificaron exportaciones PDF, DWG o DXF directamente recuperables. Queda por abrir el Libro de Planos en Archicad y exportar una vista nativa para cotejar orientación, contornos, huecos, cotas y anotaciones contra la salida de Megalodon.

## Fuentes

- `ARCHICAD.zip` · `ARK_NordicLCA_Housing_Timber_As-Built.pla`.
- `REVIT 2.zip` · `ARK_NordicLCA_Housing_Timber_As-Built.rvt`.
- `IFC.zip` · `ARK_NordicLCA_Housing_Timber_As-built_Archicad.ifc` y `ARK_NordicLCA_Housing_Timber_As-Built_Revit.ifc`.
- `SPECIFICATIONS.zip` · `BIM_Specification_ARK_NordicLCA_Housing_Timber_As-built_Archicad.pdf`, página 2.
