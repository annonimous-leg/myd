# Plantillas aportadas · preparación de integración

© 2026 Carl Own Megalodon

Se inspeccionaron 29 hojas, 26 registros de CONTROL_PATRONES y 0 fórmulas.
El inventario incluye el contenido de las celdas, fórmulas, combinaciones, formatos numéricos, áreas de impresión y marcadores de captura.

Los estados y referencias de CONTROL_PATRONES son declaraciones del archivo aportado. Su verificación externa queda pendiente.

| Hoja | Fórmulas | Marcadores de captura o cálculo |
|---|---:|---:|
| SICT_E-3_Propuesta_Eco | 0 | 8 |
| SICT_E-5_APU | 0 | 0 |
| SICT_E-15_FASAR | 0 | 0 |
| SICT_E-16_Indirectos | 0 | 3 |
| SICT_E-17_Financiamiento | 0 | 3 |
| SICT_T-1_Manifestacion | 0 | 8 |
| SICT_T-3_Personal | 0 | 0 |
| SICT_T-6_Financiera | 0 | 0 |
| IMSS_AnexoXVIII_Eco | 0 | 2 |
| IMSS_AnexoV_Integridad | 0 | 3 |
| IMSS_AnexoXIV_NoConflicto | 0 | 3 |
| IMSS_AnexoVII_MIPYMES | 0 | 3 |
| ISIFE_Doc21_FASAR | 0 | 1 |
| ISIFE_Doc23_Indirectos | 0 | 3 |
| ISIFE_Doc24_Financiamiento | 0 | 2 |
| PEMEX_DE-2_Catalogo | 0 | 0 |
| PEMEX_SSPA_Obligaciones | 0 | 0 |
| PEMEX_PACMA | 0 | 0 |
| CFE_VolC_Economica | 0 | 0 |
| CONAGUA_F-8_Fianza | 0 | 3 |
| CONAGUA_Anexo_Economico | 0 | 0 |
| ComprasMX_Anexo2_Eco | 0 | 0 |
| Gen_Fianza_Seriedad | 0 | 3 |
| Gen_Fianza_Cumplimiento | 0 | 3 |
| Gen_Decl_Integridad | 0 | 3 |
| Gen_No_Conflicto | 0 | 3 |
| INDICE_Tabla_Comparativa | 0 | 0 |
| FUENTES_Y_VALIDACION | 0 | 0 |
| CONTROL_PATRONES | 0 | 0 |

## Reglas para la integración

Cada plantilla se vincula al procedimiento y a la huella del original. CONTROL_PATRONES exige resolver identificadores por convocatoria, incluyendo E-3/E-7, T-3, T-6 y variantes DE-2.
Los textos [CALCULAR] requieren una fórmula o un resultado trazable del motor de costos antes de considerar completado el anexo. Los marcadores de captura identificados son candidatos a mapeo y requieren confirmar el destino dentro de la hoja.
El adaptador XLSX debe autorizar celdas explícitas por versión y proteger fórmulas, textos de origen y celdas combinadas. Su prueba debe verificar la preservación del libro y la descarga del mismo binario guardado.
Esta entrega incorpora la inspección y el inventario al paquete de código. El llenado XLSX desde Workspace queda pendiente de implementar y probar.

## Referencias concretas del libro

- TPL-SICT-E3 — REMAPEAR. No llamar E-3 universal; usar el ID que indique la convocatoria.
- TPL-SICT-E5 — RÉPLICA ESTRUCTURAL. Mantener materiales, mano de obra y equipo; integrar indirectos/financiamiento/utilidad según convocatoria.
- TPL-SICT-E15 — RÉPLICA ESTRUCTURAL. No fijar tasas; calcular con variables laborales vigentes y guía de llenado.
- TPL-SICT-E16 — RÉPLICA ESTRUCTURAL. Separar oficina central y campo, con porcentajes e importes.
- TPL-SICT-E17 — RÉPLICA ESTRUCTURAL. La tasa y flujo deben salir del procedimiento, no de un valor fijo.
- TPL-SICT-T1 — RÉPLICA CONDICIONAL. No asumir T-1 universal; usar el anexo que la convocatoria enumere.
- TPL-SICT-T3 — CORREGIDO. En esta convocatoria T-3 se refiere a experiencia/capacidad técnica.
- TPL-SICT-T6 — CORREGIDO. No confundir T-6 con capacidad financiera; eso es T-4 en el patrón consultado.
- TPL-IMSS-XVIII — RÉPLICA CONDICIONAL. El anexo se publica en Compras MX y sus columnas cambian por contratación.
- TPL-IMSS-V — CONDICIONAL. Usar numeración de la convocatoria concreta.
- TPL-IMSS-XIV — CONDICIONAL. No asumir que XIV siempre significa el mismo documento.
- TPL-IMSS-VII — RÉPLICA CONDICIONAL. Usar el anexo/número que la convocatoria concreta indique.
- TPL-ISIFE-21 — RÉPLICA ESTRUCTURAL. Incluye datos de obra, proceso, contrato, categorías, salario tabulado, FSR y salario real.
- TPL-ISIFE-23 — RÉPLICA ESTRUCTURAL. Separar oficina central/campo y justificar rubros.
- TPL-ISIFE-24 — RÉPLICA ESTRUCTURAL. Usar flujo y tasa del expediente concreto.
- TPL-PEMEX-DE2 — VERSIONADO. Nunca seleccionar DE-2 solo por nombre; resolver por convocatoria/procedimiento.
- TPL-PEMEX-SSPA — CONDICIONAL. Depende del régimen, contrato y anexo SSPA.
- TPL-PEMEX-PACMA — CONDICIONAL. Aplicar solo cuando las bases lo incorporen.
- TPL-CFE-AE — RÉPLICA ESTRUCTURAL. AE-1 a AE-16 deben venir del pliego concreto; no usar Volumen C universal.
- TPL-CONAGUA-F8 — CONDICIONAL. Reproducir texto de póliza que venga en convocatoria/modelo de contrato; no inventar porcentajes.
- TPL-CONAGUA-AE — RÉPLICA ESTRUCTURAL. Descripción, unidad, cantidad, precio unitario número/letra e importes; sin IVA.
- TPL-CMX-ECO — CONDICIONAL. Compras MX es plataforma; el formato pertenece a la convocante.
- TPL-GEN-FIANZA-S — NO OFICIAL. No presentar como formato oficial; usar únicamente como generador preliminar.
- TPL-GEN-FIANZA-C — NO OFICIAL. Sustituir por texto de la póliza/anexo oficial del contrato.
- TPL-GEN-INTEGRIDAD — NO OFICIAL. Debe mapear al artículo/anexo de la convocatoria concreta.
- TPL-GEN-CONFLICTO — NO OFICIAL. Debe mapear al formato/anexo de la convocatoria concreta.