# Anexo 9 PEF 2026 + estrategia semi-automatización (evidencia real)

## 1. Fuente oficial de umbrales

| Dato | Valor |
|------|--------|
| Instrumento | **Anexo 9** del PEF para el Ejercicio Fiscal **2026** |
| Publicación | DOF **21 de noviembre de 2025** |
| Fundamento PEF | Art. 3 fracc. X PEF 2026 |
| Fundamento leyes | LOPSRM **Art. 43** (obra) · LAASSP **Art. 55** (adquisiciones) |
| Unidad | **Miles de pesos**, **sin IVA** |
| PDF Cámara | https://www.diputados.gob.mx/LeyesBiblio/pdf/PEF_2026.pdf |

Los tramos **no son un monto fijo nacional**: dependen del **presupuesto autorizado** de la dependencia/entidad para esa categoría de gasto en el ejercicio.

Ejemplo tramo más bajo (obra, presupuesto ≤ 15,000 miles):

- AD obra: **499** miles → $499,000
- INV obra: **3,776** miles → $3,776,000
- AD servicio rel.: 223 · INV servicio rel.: 2,868

Tramo abierto (presupuesto > 2,700,000 miles):

- AD obra: **3,893** · INV obra: **28,913**

Seeds: `backend/app/data/seeds/procedure_thresholds.csv` → `estado_dato=VERIFICADO`.

---

## 2. Qué piden las convocatorias reales (muestra 2025–2026)

Revisión de convocatorias federales publicadas (CompraNet / gob.mx):

| Requisito | ¿Quién lo pide? | ¿Entra en propuesta del licitante? | Estrategia en Megalodon |
|-----------|-----------------|--------------------------------------|-------------------------|
| **Procedimiento ya declarado** (LP / I3P / AD) | Todas las convocatorias publicadas | No: lo fija la convocante | UI: si el tender ya trae `procedure_type`, **no recalcular** salvo modo “convocante / planeación” |
| **Presupuesto autorizado dependencia (Anexo 9)** | Uso **interno** de la convocante (Art. 43) | **No** aparece como dato que el licitante capture en la propuesta | Campo `presupuesto_dependencia_miles` solo en flujo **planeación/recomendación de procedimiento**; oculto/opcional en flujo “responder convocatoria” |
| **Garantía de cumplimiento ≥ 10%** | Casi todas (SECTUR, CENACE, Banobras, CNSNS, modelos DOF 15-abr-2022) | Sí (adjudicado) | LegalRule `GARANTIA-CUMPLIMIENTO-OBRA-MIN10` — obligatorio en validación de póliza |
| **Garantía de anticipo 100%** | Cuando hay anticipo | Sí | LegalRule anticipo |
| **Garantía de seriedad** | **Variable**: FONATUR publica formatos propios; muchas LP federales de servicios **no** fijan 5% genérico en convocatoria | Solo si la convocatoria lo exige | **No hardcodear 5%**. Estado `PENDIENTE_REGLA` / flag por case_pack o `requirement` de la convocatoria |
| **Opinión IMSS / INFONAVIT / 32-D SAT** | Muy frecuente en federales | Sí | Artefactos de compliance (ya hay carpeta de opiniones en repo) |
| **Penas convencionales** | Casi todas; tope ligado a garantía de cumplimiento (LOPSRM 46 Bis) | Cláusula contractual | Tope desde LegalRule PENALIZACIONES |
| **Umbrales estatales** | Congresos locales (ej. SLP 2026: AD obra $1.51M, INV $4.26M) | Régimen local | Perfiles estatales + `inherits_from` federal solo si no hay tabla local VERIFICADA |

### Conclusión operativa

1. **Semi-automatización “licitante”** (armar propuesta ante convocatoria publicada):  
   - El procedimiento **ya viene** en la convocatoria.  
   - No exigir presupuesto Anexo 9 al usuario.  
   - Garantías/seriedad/checklist: desde **perfil + LegalRule + case_pack** de esa dependencia/convocatoria.

2. **Semi-automatización “convocante / planeación”** (decidir procedimiento antes de publicar):  
   - Sí exigir `presupuesto_dependencia_miles` para federales (tabla escalonada).  
   - Recomendar AD / INV / LP con umbrales VERIFICADOS.  
   - No materializar si faltan datos.

3. **Seriedad**: solo si el case_pack o la regla de la convocatoria la declara; no inventar porcentaje.

---

## 3. Documentación vigente a mantener en corpus

| Documento | Uso |
|-----------|-----|
| PEF 2026 Anexo 9 | Umbrales federales anuales |
| LOPSRM Art. 42, 43, 46 Bis, 48 | Excepciones, umbrales, penas, garantías |
| RLOPSRM Art. 91 | Piso 10% cumplimiento |
| LAASSP Art. 54, 55, 69, 75 | Equivalente adquisiciones |
| Modelos de fianza DOF 15-abr-2022 | Texto pólizas |
| Políticas estatales de montos (cuando existan) | Perfiles no federales |

Cada ejercicio fiscal: re-seed `procedure_thresholds` desde el Anexo 9 del PEF del año y marcar `ejercicio_fiscal`.
