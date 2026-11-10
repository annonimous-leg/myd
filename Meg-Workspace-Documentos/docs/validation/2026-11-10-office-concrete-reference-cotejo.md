# Cotejo de referencia — oficina de concreto NordicLCA (2026-11-10)

## Fuentes

- Archicad: `Archicad2.zip` / `ARK_NordicLCA_Office_Concrete_BuildingPermit.pla`.
- Revit: `REVIT 2.zip` / `ARK_NordicLCA_Office_Concrete_BuildingPermit.rvt`.
- IFC: `IFC.zip` / `ARK_NordicLCA_Office_Concrete_BuildingPermit_Archicad.ifc` y `ARK_NordicLCA_Office_Concrete_BuildingPermit_Revit.ifc`.
- Estructura: `STRUCTURAL(1).zip` / `STRUC_NordicLCA_Office_Concrete_BuildingPermit.ifc`.
- Especificaciones: los PDF BIM del mismo proyecto dentro de `SPECIFICATIONS.zip`.

Los PDF de especificación describen ETRS-GK25, N2000 y siete cotas de referencia comunes. No son plantas constructivas ni prueban la equivalencia de láminas guardadas en los documentos nativos.

## Hallazgos verificados directamente en los IFC

| Nivel | Revit (m) | Archicad (m) | Delta Archicad − Revit (m) |
| --- | ---: | ---: | ---: |
| Basement | 51.700 | 51.700 | 0 |
| Level_01 | 55.500 | 55.500 | 0 |
| Level_02 | 59.700 | 59.700 | 0 |
| Level_03 | 63.650 | 63.650 | 0 |
| Level_04 | 67.600 | 67.650 | +0.050 |
| Level_05 | 71.920 | 71.920 | 0 |
| Roof | 77.890 | 75.920 | −1.970 |

Tolerancia de cotejo: 0.010 m. Cinco niveles coincidentes, dos discrepantes.
Revit declara además Sea Level, Foundation y Level_02a_Parking; Archicad declara Foundations y Garage_02 sin correspondencia nominal estricta. No se deben homologar nombres automáticamente.

- **Unidades:** el IFC Revit expresa coordenadas de longitud en milímetros; Archicad en metros. Convertir a metros antes del cotejo.
- **Transformaciones:** las entidades IfcMapConversion no son idénticas; Revit declara Eastings/Northings 0/0 y Archicad 25493950/6677600. No situar ambos modelos en el terreno por identidad directa de coordenadas sin resolver los sistemas locales y mapas.
- **Estructura:** el modelo Tekla debe cotejarse como disciplina separada; no inferir la igualdad de elementos estructurales únicamente por nombre de proyecto.
- **Versiones:** el IFC As-Built de Revit es otra fase y no sustituye al BuildingPermit.

## Láminas nativas

El RVT es un archivo Compound File con flujos `BasicFileInfo`, `ContentDocuments` y `RevitPreview4.0`. Esas entradas no acreditan que exista una lámina de planta, sección o alzado guardada. El PLA de Archicad también es nativo y requiere un lector compatible o una exportación para identificar las láminas. No se ha hecho cotejo visual plano-contra-plano; tampoco se han convertido vistas nativas sin prueba.

## Recomendación de puerta de calidad

1. Elegir revisión y software de origen; no mezclar objetos o niveles de proyectos distintos por defecto.
2. Ejecutar `cotejar_niveles` con tolerancia explícita; registrar diferencias y nombres sin correspondencia.
3. Bloquear cualquier confirmación **automática** cuando existan discrepancias. La resolución debe ser humana, con fuente y revisión.
4. Obtener desde Revit/Archicad una planta, sección y alzado con la misma orientación y rango que Megalodon.
5. Comparar huecos, aristas, cotas, niveles, anotaciones y escala; adjuntar resultados al expediente.
6. Resolver la transformada geográfica antes de enviar a Tezcatlipoca.

**Estado:** la revisión documental y de niveles es reproducible; la equivalencia visual del dibujo constructivo todavía no está verificada.
