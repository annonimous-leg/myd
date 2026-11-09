# Catálogos recuperados y límite del checkpoint

Revisión del código en `91472fe90ac1695b477d823b055a74ab88fca4a9` y de los
archivos aportados por el usuario. Megalodon prepara propuestas del licitante.
Este informe no declara GO de producción ni certifica todos los módulos.

## Corrección del alcance anterior

Los paquetes CMIC/CFE y Varela sí existen. El checkpoint anterior fue un archivo
del árbol Git: conservó código y correcciones, pero no incorporó estos datasets
privados. No acredita su instalación ni su uso en los recorridos de aceptación,
que emplearon catálogos sintéticos. Tampoco demuestra que se hayan perdido datos
en Supabase: esa base remota no se consultó.

Se recuperaron y abrieron los ZIP completos; ambos pasaron comprobación CRC.
No se ejecutaron los scripts ni SQL incluidos en los paquetes.

## Inventario contado desde los CSV

| Paquete | Contenido observado |
| --- | --- |
| MEGALODON_CATALOGOS_2026_AUTORRECUPERABLE(2).zip | 8 fuentes: 7 CMIC y 1 CFE; 4,757 partidas (3,425 CMIC y 1,332 CFE); 10,071 componentes de partidas; 1,939 registros de precios regionales; texto de 2,321 páginas |
| MEGALODON_CATALOGOS_POSTGRES_2026_VARELA_PDF_COMPLETO_REVISADO.zip | 42 fuentes: 34 secciones Varela y 8 CMIC/CFE; 4,692 partidas (1,366 Varela, 2,074 CMIC y 1,252 CFE); 105 modelos paramétricos Varela; 3,095 componentes de modelos; 945 registros de desglose y 167 factores geográficos |

Una fila de componente, un precio regional y un modelo no equivalen a un
concepto APU independiente. Los 16,767 registros de partidas/componentes/precios
del primer paquete no prueban la existencia de 16,767 conceptos únicos.
Tampoco se suman las partidas CMIC/CFE de ambos paquetes: son versiones que se
solapan y tienen coberturas diferentes. Sustituir el primero por el segundo
perdería partidas CMIC/CFE.

## Hallazgos comprobados

1. **Paquete Varela: manifiesto desactualizado.** Los archivos firmados coinciden
   en bytes y SHA-256, pero `desglose_modelo` declara 528 registros y contiene
   945; `factor_geografico` declara 67 y contiene 167. El verificador actual
   rechaza el original con `Conteo incorrecto: desglose_modelo`.
   Corregir únicamente esos dos conteos en una copia permite verificar la
   estructura. No cambia ningún CSV, precio, estado de revisión ni incidencia;
   no equivale a certificar las extracciones.
2. **Incidencias pendientes por versión.** El primer paquete conserva una
   incidencia bloqueante: infraestructura educativa publica $2,386.28 en resumen
   y $2,316.77 en el análisis. El paquete conjunto con Varela conserva 99
   incidencias bloqueantes abiertas, todas asociadas a sus versiones CMIC:
   86 de aritmética de componente y 13 de desglose. No son 99 errores Varela.
   Se mantienen como pendientes registrados; esta ronda no los reprodujo
   visualmente contra sus páginas originales ni los resuelve por inferencia.
3. **Datos privados ausentes del checkpoint Git.** El árbol actual sólo contiene
   los pequeños CSV de referencia y el esquema/verificador de paquetes. El
   lector `catalogo_libro.py` necesita `backend/data/private/catalogo.csv` o
   `CATALOGO_LIBRO_CSV`; ese archivo no estaba instalado en la copia examinada.
   Los paquetes de tablas extraídas no tienen ese formato de CSV del libro.
4. **Falta acreditar la integración.** El costeo consulta `CatalogoAPU`, las
   tablas de conceptos/insumos o el CSV del libro. `verify_catalog_package.py`
   valida paquetes; no importa automáticamente sus tablas a esas rutas. No se
   comprobó aquí una carga CMIC/Varela en la base operativa ni selección → APU
   → presupuesto → exportación usando sus registros auténticos.

El verificador pasó estructura del paquete CMIC/CFE y de la copia diagnóstica
con los dos conteos Varela corregidos. El primer cotejo de PDF se limitó a los
21 adjuntos presentes, que eran documentos diferentes de los originales de
extracción. El cotejo ampliado de biblioteca de la sección siguiente supera
ese límite. Las marcas `VALIDADO_ESTRUCTURAL` tampoco certifican revisión visual
completa.

## Cotejo ampliado de originales de biblioteca

Se encontraron los ocho PDF CMIC/CFE por sus nombres originales y el archivo
`libro-costos-ene-2026-dividido-por-secciones.zip`, que contiene las 34 secciones
Varela. Cada PDF recuperado coincide byte a byte mediante SHA-256 con su fuente
registrada; se abrió con un lector PDF y se comprobó el número de páginas.
No fue necesario reconstruir secciones ni aceptar otra edición por parecido
de nombre. No falta ninguno de los 42 originales de estos paquetes.

El verificador real, ejecutado contra esos originales, confirma ocho fuentes y
2,321 páginas para CMIC/CFE, y 42 fuentes y 2,985 páginas para el paquete conjunto
con los dos conteos corregidos. Sigue conservando la incidencia abierta del
primer paquete y las 99 del segundo. El detalle por fuente está en
`CATALOGOS_FUENTES_COTEJO_2026-10-08.json`.

La identidad de los originales está demostrada; no se convierte ese cotejo en
certificación visual de cada fila ni en prueba de importación/costeo operativo.
La ausencia de archivos deja de ser un pendiente de estos dos paquetes.

## Preservación y siguiente cierre

El checkpoint privado complementado conserva ambos ZIP originales sin alterar
sus bytes, junto al código actual, este informe y resultados de verificación.
El paquete Varela con reparación de conteos se identifica como copia derivada;
no sustituye al original ni cambia datos para hacer pasar la validación.
Los datos privados no se publican en GitHub.

Para cerrar el bloque falta seleccionar versiones por fuente, cotejar originales,
resolver o excluir las incidencias, importar de forma transaccional e idempotente
con unidades/IVA/fecha/zona/procedencia, y demostrar el recorrido de costeo con
esos datos. Los modelos paramétricos, costos horarios y factores geográficos
deben conservar su significado; no se convierten indiscriminadamente en APU.
La actualización de enero exige correspondencias por insumo/serie y fecha,
conservando precio base; no se aplica un aumento global.

Los otros motores, Supabase Storage real, corpus jurídico, carga concurrente y
restauración conservan los límites de `PRR-2026-10-08.md`. La revisión del último
bloque no permite afirmar que todo el sistema esté correctamente terminado.

## Identidad de originales

- CMIC/CFE ZIP SHA-256: `e4ac69ff562cd0f59c93fc2270d910f77e8e855b3f5615b57e0c933fe01a7a43`.
- Varela/CMIC/CFE ZIP SHA-256: `687347405867c9477d7ec2238a0c8c498c7e07306dddce57f4308845882a92e9`.
