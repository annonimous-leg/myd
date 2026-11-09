# © 2026 Carl Own Megalodon
import hashlib
import json
from pathlib import Path
import openpyxl

source = Path("upload/Plantillas_Licitaciones_Obra_Publica_2026_REPLICAS_OFICIALES.xlsx")
book = openpyxl.load_workbook(source, data_only=False)
sheets = []
for sheet in book:
    cells = [{"cell": c.coordinate, "value": c.value, "type": c.data_type,
              "number_format": c.number_format, "locked": c.protection.locked}
             for row in sheet for c in row if c.value is not None]
    sheets.append({
        "name": sheet.title, "rows": sheet.max_row, "columns": sheet.max_column,
        "merged_ranges": [str(r) for r in sheet.merged_cells.ranges],
        "formulas": [c for c in cells if c["type"] == "f"],
        "capture_markers": [c for c in cells if isinstance(c["value"], str)
                            and any(t in c["value"].upper() for t in ("[CAPTURAR", "[CALCULAR", "_____"))],
        "print_area": str(sheet.print_area), "cells": cells,
    })
controls = []
sheet = book["CONTROL_PATRONES"]
headers = [c.value for c in sheet[1]]
for row in sheet.iter_rows(min_row=2, values_only=True):
    if row[0]:
        controls.append(dict(zip(headers, row)))
result = {"source_file": source.name, "source_sha256": hashlib.sha256(source.read_bytes()).hexdigest(),
          "source_claims_independently_verified": False, "submission_eligible": False,
          "sheets": sheets, "procedure_controls": controls}
Path("plantillas-review/inventario-plantillas.json").write_text(
    json.dumps(result, ensure_ascii=False, indent=2, default=str))
formula_count = sum(len(s["formulas"]) for s in sheets)
print(len(sheets), "hojas,", len(controls), "patrones,", formula_count, "fórmulas")
lines = ["# Plantillas aportadas · preparación de integración", "",
         "© 2026 Carl Own Megalodon", "",
         f"Se inspeccionaron {len(sheets)} hojas, {len(controls)} registros de CONTROL_PATRONES y {formula_count} fórmulas.",
         "El inventario incluye el contenido de las celdas, fórmulas, combinaciones, formatos numéricos, áreas de impresión y marcadores de captura.",
         "", "Los estados y referencias de CONTROL_PATRONES son declaraciones del archivo aportado. Su verificación externa queda pendiente.",
         "", "| Hoja | Fórmulas | Marcadores de captura o cálculo |", "|---|---:|---:|"]
lines += [f'| {s["name"]} | {len(s["formulas"])} | {len(s["capture_markers"])} |' for s in sheets]
lines += ["", "## Reglas para la integración", "",
          "Cada plantilla se vincula al procedimiento y a la huella del original. CONTROL_PATRONES exige resolver identificadores por convocatoria, incluyendo E-3/E-7, T-3, T-6 y variantes DE-2.",
          "Los textos [CALCULAR] requieren una fórmula o un resultado trazable del motor de costos antes de considerar completado el anexo. Los marcadores de captura identificados son candidatos a mapeo y requieren confirmar el destino dentro de la hoja.",
          "El adaptador XLSX debe autorizar celdas explícitas por versión y proteger fórmulas, textos de origen y celdas combinadas. Su prueba debe verificar la preservación del libro y la descarga del mismo binario guardado.",
          "Esta entrega incorpora la inspección y el inventario al paquete de código. El llenado XLSX desde Workspace queda pendiente de implementar y probar.",
          "", "## Referencias concretas del libro", ""]
for c in controls:
    lines.append(f'- {c[headers[0]]} — {c[headers[4]]}. {c[headers[6]]}')
Path("plantillas-review/REVISION-PLANTILLAS.md").write_text("\n".join(lines))
