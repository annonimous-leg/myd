# Investigación de índices por insumo para Megalodon

Fecha de corte: 30 de septiembre de 2026, hora de México. Investigación descriptiva; no se cambiaron precios ni se implementó un motor con estos hallazgos.

## Charter

Objetivo: localizar y contrastar fuentes originales de variación de costos por insumo o familia para actualizar las estimaciones de los catálogos de enero de 2026 al mes destino, sin aplicar un porcentaje global a todos los componentes.

Scope: actualización de estimaciones de construcción en México. Object: Megalodon y sus catálogos con fecha base de enero. Subject: publicaciones CMIC, Varela e INEGI de 2026.

Preguntas: Q1, ¿el mes del título es de publicación o de observación? Q2, ¿hay desglose y son niveles de índice, tasas mensuales, anuales o acumuladas? Q3, ¿qué acceso, metodología y metadatos están disponibles? Q4, ¿qué datos pueden utilizarse y cuáles faltan?

Orden de evidencia: 1, fuente originadora; 2, metodología original; 3, tabla original; 4, comunidad o distribuidores para localizar y contrastar originales. Los resultados de buscador no sustituyen la lectura de la fuente.

## Canonical sources

| ID | Fuente original abierta | Alcance comprobado |
|---|---|---|
| V1 | [Software m2](https://varela.com.mx/software-m2/) | Descripción del sistema, periodicidad de actualizaciones y acceso por suscripción. |
| V2 | [Índice Varela, septiembre 2018](https://varela.com.mx/indice-varela-2018-septiembre/) | Comparación anual entre septiembre de 2017 y septiembre de 2018. |
| V3 | [Tema índiceVarela](https://varela.com.mx/tema/indicevarela/) | Artículos históricos de 2017 y 2018; no se verificó allí una tabla de 2026. |
| V4 | [Archivo 2026](https://varela.com.mx/2026/) | Artículos publicados durante 2026. La entrada de septiembre trata errores de IA en ingeniería de costos. |
| V5 | [Archivo de actualizaciones 2007–2014](https://varela.com.mx/software-m2/actualizaciones-2007-2014/) | Archivo histórico al que redirigieron los enlaces abiertos de actualizaciones. |
| V6 | [Contrato del editor](https://varela.com.mx/contrato/) | Clases de publicaciones, frecuencia declarada y condiciones de acceso/uso. |
| C1 | [CMIC/CEICO septiembre 2026](https://www.cmic.org.mx/comisiones/Tematicas/costosyp/Informes_CEICO/INEGI/2026/09_Septiembre/CEICO_Informe_Septiembre_2026_Variacion_precio_materiales.pdf) | Publicado el 11 de septiembre; referencia agosto 2025–agosto 2026; siguiente actualización anunciada el 16 de octubre. PDF original abierto completo como texto. |
| C2 | [CMIC/CEICO agosto 2026](https://www.cmic.org.mx/comisiones/Tematicas/costosyp/Informes_CEICO/INEGI/2026/08_Agosto/CEICO_Informe_Agosto_2026_Variacion_precio_materiales.pdf) | Desglose por insumo y discrepancia interna del periodo. PDF original abierto completo como texto. |
| I1 | [INEGI INPP, septiembre 2026](https://www.inegi.org.mx/contenidos/saladeprensa/boletines/2026/inpp/inpp2026_09.pdf) | Publicación 9 de septiembre, observaciones agosto; siguiente publicación anunciada 8 de octubre. Cuadros mensuales y anuales diferenciados. |

CMIC C1/C2 utiliza datos de INEGI: dos editores no equivalen a dos mediciones estadísticas independientes. Varela aporta otra metodología/editor; no se obtuvo una serie numérica pública actual comparable. Rango 1 para los documentos de sus respectivos autores; comunidad/distribuidores tienen rango 4 y sólo sirven para ubicar originales.

## Findings ledger

| ID | Afirmación verificable | Evidencia / rango | Responde |
|---|---|---|---|
| C01 | Existe el informe CMIC de septiembre de 2026; su observación corresponde a agosto, no a septiembre. Anuncia 16 de octubre como próxima actualización, sin acreditar que ya exista esa edición. | C1, portada y páginas 2–3 / 1 | Q1, Q3 |
| C02 | Las variaciones publicadas por insumo son distintas: tubos de cobre 22.27%; cables con aislamiento 17.15%; lubricantes 16.88%; tubería de plástico 16.35%; aluminio 11.62%. Todas son anuales agosto 2025–agosto 2026. | C1, páginas 2–3 / 1 | Q2 |
| C03 | El mismo gráfico presenta gasolina 9.49%, soldaduras 8.53%, asfalto/mezclas 8.44%, otros productos de concreto 8.30% y cal hidratada 7.77%. Son tasas anuales, no factores enero–agosto. | C1, página 3, etiquetas en extracción de texto / 1 | Q2 |
| C04 | C1 distingue precios al productor LAB sin impuestos y precios mayoristas del ICC con impuestos y entrega en obra. No son bases intercambiables por tener nombres similares. | C1, página 4 / 1 | Q3, Q4 |
| C05 | C2 página 2 escribe julio 2025–junio 2026; su gráfico de página 3 y texto de página 5 indican julio 2025–julio 2026. La discrepancia requiere contraste antes de ingesta. | C2, páginas 2, 3 y 5 / 1; observación de texto | Q1, Q4 |
| I01 | I1 confirma para agosto Construcción 0.16% mensual y 5.91% anual; el 5.91% coincide con C1, pero ambos remiten a la misma medición. | I1, cuadro 1, página 2; C1, página 2 / 1 | Q1, Q3 |
| I02 | I1 cuadro 3 registra en agosto gasolina +4.96% mensual y diésel −11.90% mensual. Un motor debe admitir decrementos y no confundir tasas mensuales con anuales. | I1, página 5 / 1 | Q2, Q4 |

La extracción textual de los gráficos no acredita revisión visual completa: el servicio de capturas devolvió referencias de imagen sin entregar píxeles utilizables en esta ronda. Se transcriben sólo valores con etiquetas legibles y se mantiene pendiente la gráfica comparativa completa de materiales, página 4. No se certifica todo el PDF ni se modificó el CSV del usuario.

Hallazgos de la revisión de Varela (documentos originales abiertos por el investigador encargado):

| Hallazgo | Evidencia | Estado e implicación |
|---|---|---|
| Varela anuncia para m2 actualizaciones en enero, abril, julio y octubre. | V1, apartado de características y Actualizaciones. | Verificado. La periodicidad declarada es trimestral, no mensual. Que octubre sea uno de los meses programados no acredita que la edición octubre 2026 ya esté publicada. |
| Las actualizaciones de m2 requieren suscripción vigente. | V1, apartado Actualizaciones. | Verificado. No se descargó ni se adquirió una actualización. |
| El índice público de septiembre que se encontró corresponde a 2018. | V2 y V3, fecha y comparación explícita. | Verificado. No sirve como observación de septiembre de 2026 ni como tasa mensual de 2026. |
| La entrada de septiembre de 2026 del archivo anual es un artículo sobre errores de IA. | V4, fecha y texto. | Verificado. Un enlace con septiembre 2026 en archivos o navegación no demuestra un informe de variaciones de precios. |
| Los enlaces de actualización abiertos llevan a archivos 2007–2014. | V5, destino de redirección y fechas de versiones. | Verificado para las rutas revisadas. No demuestra que el editor carezca de actualizaciones privadas actuales. |
| El contrato distingue actualizaciones trimestrales de clase A y semestrales de clase C. | V6, definición de obras y frecuencia. | Verificado. No extrapolar la frecuencia de m2 a todos los libros de costos unitarios. |
| No se encontró una tabla primaria pública verificable de Varela, septiembre 2026, con series mensuales por insumo. | Tres rondas acotadas de localización y apertura de V1–V6. | No encontrado en esta revisión; no es una afirmación de inexistencia. No permite inventar coeficientes ni convertir índices agregados históricos en cambios actuales por material. |

## Scope filter

Se excluyen índices de Argentina, personas homónimas y enlaces que sólo mencionan 2026 en navegación. Se conserva V2 únicamente para acreditar la existencia histórica de Ivar y demostrar el riesgo de confundir fechas. No se emplea como dato operativo.

Se conserva C02/C03 como evidencia de variación desigual por insumo, nunca como factores desde enero. No se interpreta la comparación de dos tasas anuales sucesivas como cambio mensual. Se descartan resultados de afiliaciones, facturación, producción física y actividad económica que no son índices de precios. Las copias comunitarias no convierten una medición INEGI en corroboración independiente.

## Object filter

Los catálogos existentes y su precio original permanecen intactos. Las frecuencias de publicación, factores interciudad, índices de inflación y precios de ensamble son objetos diferentes; no deben combinarse como si fueran una misma serie. No se verificó una correspondencia entre ítems del catálogo de Megalodon y familias de un índice Varela actual.

La recomendación se restringe a actualizar estimaciones con series pertinentes. No basta el índice nacional de Construcción para actualizar todos los componentes de Megalodon. El factor enero→destino de cada insumo requiere niveles de índice de esos dos meses o una cadena completa de tasas mensuales de la misma serie. La existencia de un informe de septiembre no demuestra que ya haya precios observados de septiembre en él. C05 debe quedar como conflicto de metadatos, con la fuente intacta, hasta resolverlo con la serie originaria. Se permiten bajas de precios (I02).

## Conclusions

1. **El informe de septiembre solicitado sí existe** y ofrece desglose por insumo. Su referencia es agosto de 2026 y contiene tasas anuales; confirma la necesidad de tratar los insumos por separado (C01–C03).
2. **Octubre tiene fechas anunciadas diferentes**: CMIC 16 de octubre; INEGI 8 de octubre. Son calendarios declarados, no observaciones futuras verificadas (C01, I1).
3. **La selección de serie importa tanto como la fecha**: productor sin impuestos y mayorista con impuestos/entrega no deben mezclarse indiscriminadamente. El motor debe admitir movimientos negativos (C04, I02).
4. **Todavía no hay un conjunto operativo completo enero→destino por todos los insumos de Megalodon**: faltan niveles o tasas mensuales, cobertura y correspondencias verificadas. Los diez insumos destacados no cubren un catálogo entero (C02–C04 y preguntas abiertas de Q4).

La evidencia abierta de Varela confirma productos de costos con actualizaciones periódicas y un índice histórico, pero no acredita una serie mensual pública de 2026 por insumo utilizable ahora en Megalodon. La vía pública verificada para actualización mensual debe resolverse con las tablas e índices originarios disponibles; una fuente privada puede agregarse si se dispone de sus datos y condiciones de uso aplicables. No se debe sustituir una categoría sin datos por el porcentaje global de construcción.

## Next steps / Risks

- Consolidación CMIC/INEGI/Varela realizada en este único documento; las cifras siguen siendo evidencia de investigación, no entradas activadas de producción.
- Seleccionar tablas con niveles o cambios mensuales realmente comparables y documentar la correspondencia de cada insumo.
- Conservar fecha base, fuente, serie, unidad, ámbito geográfico y versiones metodológicas; una variación anual no puede encadenarse como si fuera mensual.
- No presentar una actualización Varela octubre 2026 como disponible hasta abrir la edición o el registro original correspondiente.
- Parallel Search alcanzó el límite gratuito; las verificaciones restantes se realizaron con apertura directa y otro servicio de búsqueda. La restricción de una herramienta no prueba ausencia de una fuente.

### Protocolo propuesto para la siguiente implementación

1. Obtener la serie completa por material/familia y ámbito aplicable; guardar identificador, descripción, metodología, mes observado y fecha de publicación. Elegir según las condiciones de precio documentadas, no por similitud de etiquetas (C04).
2. Acreditar el mes de precios de cada catálogo, separándolo del mes de edición. El usuario establece enero para el CSV y la mayoría de CMIC; no extender esa fecha a todas las fuentes sin confirmación.
3. Registrar correspondencias revisadas entre insumo y serie. Cuando no haya una correspondencia sustentada, indicar falta de cobertura; no aplicar un porcentaje global oculto (C02–C04).
4. Calcular precio_original × índice_destino / índice_base, o su equivalente con tasas mensuales completas. Usar decimales, política de redondeo explícita y origen inmutable. No usar C02/C03 como sustituto de esa cadena.
5. Con desglose APU válido, actualizar cada componente y recalcular el concepto conservando cantidades/rendimientos. Combustible, lubricantes, operación y costos fijos de maquinaria requieren su propio modelo; no multiplicar todo por el diésel (C02, I02; decisión de diseño derivada).
6. Conservar las versiones utilizadas en cada presupuesto para reproducirlo aunque una serie sea revisada; registrar conflictos como C05 antes de activar datos.

### Criterios de aceptación pendientes

- [ ] Serie y metadatos originales completos para cada familia activada; meses enero→destino sin huecos.
- [ ] Correspondencias por insumo con alcance y procedencia; cobertura y ausencias visibles.
- [ ] Contraste de resultados con fuente original para meses, tasas mensuales/anuales y condiciones de impuestos/entrega.
- [ ] Resolución de la discrepancia C05 y revisión visual de tablas/gráficos utilizados en ingesta.
- [ ] Pruebas de mismo mes, movimientos negativos, periodos incompletos, cambios metodológicos y doble actualización.
- [ ] APU válido antes de recomponer; conservar precios impresos y CSV original sin inferencias.
- [ ] Separar resultados con observaciones publicadas de pronósticos; ninguna funcionalidad predictiva fue ejecutada en esta investigación.

### Límites abiertos

No se descargaron las series completas por insumo ni se calcularon factores enero→agosto por material. No se acreditó una tabla Varela septiembre 2026. El informe residencial CMIC de septiembre no pudo abrirse por la ruta revisada; no se afirma que no exista. Los resultados de comunidad no aportaron una serie nueva independiente y verificable. La búsqueda pública fue acotada, no exhaustiva.

Revisión de evidencia: afirmaciones C01–C05/I01–I02 contrastadas con texto de los originales; fechas de portada separadas del periodo medido. El juicio sobre la discrepancia C05 es observación textual, no corrección del original. Las conclusiones numéricas se limitan a los datos legibles y su periodo declarado. El documento constituye investigación y especificación condicionada; no prueba integración ni preparación para producción.

## Ampliación: salarios, obligaciones y costo horario

Corte: 30 de septiembre de 2026 en México / 1 de octubre UTC. Esta ampliación incorpora revisión paralela de salarios/FASAR, maquinaria/energía y publicaciones Varela. Las reglas de diseño siguientes son propuestas derivadas; no se presentan como funcionalidad implementada.

### Charter y canon de la ampliación

Q5: ¿qué parte del salario es mínimo, mercado, prestación, cuota o productividad? Q6: ¿qué parámetros tienen vigencias distintas? Q7: ¿cómo actualizar maquinaria, alquiler, energía y divisas sin duplicar cargos? Q8: ¿las afirmaciones atribuidas a Varela tienen evidencia original?

Orden: originales del emisor, metodología/normativa original, documentos originales suministrados y, finalmente, publicaciones secundarias para localizar originales. CMIC y el boletín INEGI no constituyen mediciones independientes cuando remiten a la misma serie. Se contrastaron procedimientos con normas y con la descripción de consumo operativo del fabricante, sin trasladar sus cifras extranjeras al mercado mexicano.

### Canonical sources adicionales

| ID | Original abierto | Uso / localizador |
|---|---|---|
| C3 | [CMIC marzo 2026](https://www.cmic.org.mx/comisiones/Tematicas/costosyp/Informes_CEICO/INEGI/2026/03_Marzo/Variacion_precio_insumos.pdf) | Páginas 2–6; referencia febrero 2025–febrero 2026. |
| C4 | [CMIC julio 2026](https://www.cmic.org.mx/comisiones/Tematicas/costosyp/Informes_CEICO/INEGI/2026/07_Julio/CEICO_Informe_Julio_2026_Variacion_precio_materiales.pdf) | Páginas 2–3; referencia junio 2025–junio 2026. |
| I2 | [INEGI metodología INPP 2025](https://inegi.org.mx/contenidos/programas/inpp/2019a/doc/889463924807.pdf) | §§6.4.1–6.4.3, páginas impresas 34–38, PDF 45–49. |
| S1 | [CONASAMI, resolución 2026](https://sidof.segob.gob.mx/notas/docFuente/5775534) | Publicación DOF 9-12-2025; resolutivos y tabla profesional, vigencia 1-1-2026. |
| S2 | [INEGI UMA 2026](https://www.inegi.org.mx/contenidos/saladeprensa/boletines/2026/uma/uma2026.pdf) | Vigencia 1-2-2026. |
| S3 | [Ley del Seguro Social](https://www.diputados.gob.mx/LeyesBiblio/pdf/LSS.pdf) | Texto servido: reforma 15-1-2026; artículos 27, 28, 36, 72, 106, 107, 147, 168, 211 y transitorios aplicables. |
| S4 | [Ley Infonavit](https://www.diputados.gob.mx/LeyesBiblio/pdf/LIFNVT.pdf) | Artículo 29, integración y aportación. |
| S5 | [Decreto pensiones 2020](https://sidof.segob.gob.mx/notas/docFuente/5607729) | Segundo transitorio, tabla CEAV 2023–2030. Tabla original inspeccionada visualmente. |
| S6 | [Ley Federal del Trabajo](https://www.diputados.gob.mx/LeyesBiblio/pdf/LFT.pdf) | Artículos 74, 76, 80, 87 y vigencias/transitorios. |
| S7 | [Decreto jornada, mayo 2026](https://sidof.segob.gob.mx/notas/docFuente/5786537) | Segundo y séptimo transitorios; gradualidad. |
| S8 | [IMSS SUA](https://www.imss.gob.mx/patrones/sua) | Herramienta oficial para contrastar casos de cuotas; no se ejecutó SUA. |
| R1 | [RLOPSRM](https://www.diputados.gob.mx/LeyesBiblio/regley/Reg_LOPSRM.pdf) | Original servido: reforma 24-2-2023; artículos 190–209. Fórmula FSR inspeccionada visualmente. |
| E1 | [CNE precios por estación](https://www.cne.gob.mx/ConsultaPrecios/GasolinasyDiesel/GasolinasyDiesel.html) | Precios reportados por producto/estación, actualización diaria. |
| E2 | [Acuerdo tarifas eléctricas 2026](https://dof.gob.mx/nota_detalle_popup.php?codigo=5783862) | Determinación/publicación mensual de tarifas finales; no equivale a una tarifa única por kWh. |
| E3 | [Banxico CF102](https://www.banxico.org.mx/SieInternet/consultarDirectorioInternetAction.do?accion=consultarCuadro&idCuadro=CF102&locale=es&sector=6) | Diferencia FIX, liquidación, interbancario y cierre. |
| V7 | [Varela, teoría y praxis, fragmento](https://varela.com.mx/wp-content/uploads/CostosDeConstruccionParaArquitectosEIngenieros.pdf) | Edición agosto 2023, §1.3, página impresa 22, PDF 17; Pareto. |
| V8 | [Varela, construcción pesada, fragmento](https://varela.com.mx/wp-content/uploads/CostosDeConstruccionPesada1.pdf) | Edición 2023, páginas impresas 17–18; salario de mercado y prestaciones. |
| V9 | [Varela, caso ultralujo](https://varela.com.mx/presupuesto-del-costo-de-reposicion-para-efecto-de-avaluo-de-casa-de-ultra-lujo-ul/) | Caso particular fechado 31-7-2026; no serie de inflación. |
| M1 | [Caterpillar, estimar ofertas](https://www.cat.com/en_US/articles/ci-articles/accurate-job-bids.html) | 6-3-2024; consumo por máquina, trabajo y tiempo ocioso. Contraste técnico, no precios mexicanos. |

### Findings ledger adicional

| ID | Hallazgo | Evidencia / rango | Pregunta |
|---|---|---|---|
| A01 | 4.08% construcción, 4.72% residencial y 17.42% cables son tasas anuales febrero 2025–febrero 2026. No representan enero–septiembre de 2026. | C3, pp. 2–3 / 1 | Q1–Q2 |
| A02 | C4 publicado en julio observa junio: construcción 5.20%, tubos cobre 26.01%, diésel 17.55%, cables 17.40%, tubería plástico 14.97%; tasas anuales. | C4, pp. 2–3 / 1 | Q1–Q2 |
| A03 | ICC captura salarios pagados por contratistas por ciudad; admite destajo, generalmente sin prestaciones. No es sólo una tabla de mínimos. | I2, §§6.4.1–6.4.2 / 1–2 | Q5 |
| A04 | Mínimo general 2026: 315.04 MXN/día ZSMG (+13%); frontera 440.87 (+5%). 6.5% es componente de fijación junto con MIR, no incremento total general. | S1, resolutivo tercero / 1 | Q5–Q6 |
| A05 | UMA diaria 117.31 desde febrero; enero conserva 113.14. Salario y UMA tienen calendarios diferentes. | S2; aviso original UMA/contraste IMSS revisados por investigador / 1 | Q6 |
| A06 | Aportación Infonavit patronal 5% de la base aplicable; amortización del crédito de la persona trabajadora es objeto separado. | S4, art. 29 / 1 | Q5 |
| A07 | CEAV patronal depende del año y tramo salarial; riesgos de trabajo dependen del patrón. | S3 y S5 / 1 | Q5–Q6 |
| A08 | Semana máxima del decreto: 2026 48 h, 2027 46, 2028 44, 2029 42, 2030 40, sin reducción salarial por la transición. | S7, transitorios 2 y 7 / 1 | Q6 |
| A09 | Consumo de combustible, operador, desgaste y cargos fijos son componentes distintos del costo horario. | R1 arts. 194–206; M1 / 1–2 | Q7 |
| A10 | No se acreditan primas Varela +4.5% laborales ni +6.2% acumulado de lujo con las páginas originales revisadas. V9 es un caso, no un índice. | V1–V9; búsqueda acotada / 1 | Q8 |
| A11 | Pareto aparece en V7 como criterio de relevancia; no acredita cobertura completa de un presupuesto omitiendo su resto. | V7, §1.3 / 1 | Q8 |

### Salarios utilizables como mínimos, no como cotizaciones

Importes diarios de S1 vigentes desde enero. La ZLFN corresponde a los municipios enumerados, no al estado completo.

| Categoría | ZSMG MXN/día | ZLFN MXN/día |
|---|---:|---:|
| General | 315.04 | 440.87 |
| Oficial albañil | 363.44 | 440.87 |
| Carpintero obra negra | 363.44 | 440.87 |
| Colocador mosaicos/azulejos | 356.19 | 440.87 |
| Yesero construcción | 339.20 | 440.87 |
| Electricista instalaciones | 356.19 | 440.87 |
| Herrero | 351.59 | 440.87 |
| Soldador arco/soplete | 359.63 | 440.87 |
| Operador buldózer/traxcavo | 380.74 | 440.87 |

No aplicar el aumento de enero nuevamente a un catálogo ya fechado en enero de 2026. La fórmula general de fijación es `(278.80 + 17.01) × 1.065`, redondeada a 315.04; el MIR no es referente automático de otros salarios. Para estimaciones se necesitan sueldo local, categoría, condiciones y evidencia; el mínimo sirve para comprobar límites (A04).

### Cargas sociales: tasas, bases y vigencias separadas

Resumen de S3: E&M requiere artículo 106 **y transitorio decimonoveno original de 1995**, no el transitorio homónimo de otra reforma. SBC se integra; no equivale automáticamente al nominal.

| Concepto | Patronal | Obrera | Base |
|---|---:|---:|---|
| E&M fija | 20.40% | — | UMA |
| E&M excedente | 1.10% | 0.40% | max(SBC − 3 UMA, 0) |
| E&M dinero | 0.70% | 0.25% | SBC |
| Gastos médicos pensionados | 1.05% | 0.375% | SBC |
| Invalidez/vida | 1.75% | 0.625% | SBC |
| Guarderías/sociales | 1.00% | — | SBC |
| Retiro | 2.00% | — | SBC |
| CEAV | Tramo/año | 1.125% | SBC |
| Riesgos de trabajo | Prima del patrón | — | SBC |

S3 art. 36 contempla absorción de cuota obrera para salario mínimo. Separar retención, absorción y costo patronal; respetar límites, incidencias y días de cotización. No sumar mecánicamente toda la columna obrera a cualquier APU. Infonavit se trata conforme S4 (A06).

Tabla S5, columna 2026 transcrita del original:

| Etiqueta legal de rango | CEAV patronal 2026 |
|---|---:|
| 1.0 SM | 3.150% |
| 1.01 SM a 1.50 UMA | 3.676% |
| 1.51 a 2.00 UMA | 4.851% |
| 2.01 a 2.50 UMA | 5.556% |
| 2.51 a 3.00 UMA | 6.026% |
| 3.01 a 3.50 UMA | 6.361% |
| 3.51 a 4.00 UMA | 6.613% |
| 4.01 UMA en adelante | 7.513% |

La transcripción no es un selector operativo: mezcla SM y UMA y deja etiquetas que no deben reinterpretarse arbitrariamente. Validar límites, precisión, mínimo integrado y frontera con casos reproducibles contra S8 antes de producción. No se ejecutó esa comparación.

Prestaciones de S6: vacaciones iniciales mínimas 12 días y progresión por antigüedad; prima vacacional mínima 25%; aguinaldo mínimo 15 días, con proporcionalidad cuando proceda. El calendario debe representar descansos y festivos reales sin deducir dos veces coincidencias. Debe conservar antigüedad, régimen, tipo de jornada y contrato colectivo.

### Modelos de recomposición y límites de alcance

De R1, artículos 190–191: `Sr = Sn × Fsr`, `Fsr = (1 + Ps) × Tp/Tl`, `Mo = Sr/R`. Conservar bases de Ps y periodo común de Tp/Tl. En contratos de obra pública R1 fija tratamiento contractual del factor y de ajustes: diferenciar estimación nueva y ajuste contractual; no recalcular indiscriminadamente FSR ya convenido.

Para equipo propio, R1 arts. 194–206 separan depreciación, inversión, seguro, mantenimiento, combustibles, otras energías, lubricantes, llantas, piezas especiales y operador. Costos por hora se convierten por rendimiento a costo por unidad ejecutada. Combustible: consumo horario × precio compatible; operador: salario real del turno / horas efectivas. Alquiler se modela según alcance cotizado, no como matriz de propiedad. Horas efectivas y horas pagadas son parámetros diferentes (A09).

E1 sirve para localizar precio de combustible por estación/producto; no se obtuvo histórico completo. E2 requiere categoría, división, mes, kWh, demanda y asignación de cargos; no se obtuvo tabla completa CFE. E3 distingue series/fechas de divisas; no se obtuvo serie operativa completa. La conversión sólo se aplica al componente realmente en otra moneda. Evitar sumar flete, IVA, prestaciones o tipo de cambio ya contenidos en la base. Estas últimas son reglas de diseño derivadas de las condiciones de las fuentes.

### Scope filter / Object filter adicionales

Se excluyen cuotas IMSS presuntivas de mano de obra por m² como reemplazo de salarios de mercado. Estadísticas ENEC de remuneraciones reales/desestacionalizadas no son precios nominales de oficios. Blogs Slabsz/Opus se abrieron como localizadores; no acreditaron las primas Varela alegadas. La falta de tabla pública no prueba inexistencia de actualizaciones privadas.

La metodología no convierte proyecciones de septiembre en observaciones oficiales. Una base 100 normalizada debe señalar periodo, serie originaria y regla de normalización. Un índice por familia no acredita que bloque de concreto y tabique de arcilla tengan el mismo comportamiento. Pareto permite priorizar revisión, no ocultar ítems sin correspondencia.

### Conclusions y Next steps / Risks adicionales

Las fuentes permiten establecer reglas y algunos valores oficiales; no aportan por sí solas un conjunto completo de precios locales actualizados. A01/A02 impiden convertir tasas anuales en una trayectoria enero–septiembre. A03/A04/A07 requieren separar nominal, mínimo, FSR y productividad. A05/A08 requieren reglas con vigencia. A09 impide un factor diésel para el total de maquinaria. A10 impide activar porcentajes atribuidos al editor sin su evidencia.

Revisión puntual del repositorio: `ParametrosCosteoSnapshot` ya conserva evidencia de sobrecostos, pero no constituye una serie mensual de índices. `InsumoCatalogo` guarda precio y fuente; no modela por sí solo observaciones/vintages ni correspondencias revisadas. `ValidadorFactorSalarioReal` valida aritmética de Ps/Tp/Tl declarados; no calcula cuotas legales ni acredita sus bases. Sus límites globales de días en `constants.py` necesitan revisión con calendarios/vigencias antes de calificarlos como reglas legales universales. Esto es hallazgo de alcance, no certificación completa del módulo.

Migración propuesta, sin capa de compatibilidad que conserve inferencias erróneas:

1. **Fuente y versión**: original inmutable, huella, fecha publicada, periodo observado, metodología, base y condiciones de precio.
2. **Serie y observación**: identificador real, ámbito, unidad, clase `nivel/mensual/anual/pronóstico`, versión de publicación. Tasas anuales sólo informativas para este flujo.
3. **Correspondencia revisada**: insumo→serie con sustento y vigencia. Ausencia/conflicto bloquean actualización; cobertura por ítems y por valor visible.
4. **Precio original y derivado**: mes base y moneda explícitos; factor de la misma serie; precio derivado separado, nunca sobreescritura del original.
5. **Motor laboral versionado**: categoría/municipio, nominal, mínimos, SBC, UMA, tabla año, riesgo, prestaciones, calendario, rendimiento y tratamiento contractual.
6. **Matrices de equipo**: propiedad/alquiler, alcance, consumos y unidades, costos fijos, energía y operador; sin doble conteo.
7. **Presupuesto reproducible**: instantánea de fuentes/reglas/mapeos y política de redondeo. Proyecciones separadas de observaciones, con validación retrospectiva antes de habilitarlas.

Aún faltan series mensuales por insumo y mapeos completos; selector CEAV contrastado con SUA; mercadeo/consumos locales; migración con datos reales y pruebas integradas. No se implementó ni se declara listo un sistema de actualización automática con esta investigación. Esta ronda añade auditoría de evidencia y especificación; no modifica el estado GO de despliegue.
