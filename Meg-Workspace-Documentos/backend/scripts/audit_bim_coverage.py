"""Read-only IFC coverage and quantity audit; output contains private BIM identifiers.

Run: python -m scripts.audit_bim_coverage model.ifc --output-dir /private/report
No catalogue is selected and no economic quantity is approved by this command.
"""
import argparse
from collections import Counter
import csv
import hashlib
import json
from pathlib import Path

from app.engines.bim.coverage import auditar_volumen, conflictos_de_conjuntos, inventario_cobertura
from app.engines.bim.motor_bim import MotorBIM


def write_table(path, rows):
    if not rows:
        return
    with path.open('w', newline='', encoding='utf-8') as target:
        writer = csv.DictWriter(target, fieldnames=list(rows[0]))
        writer.writeheader()
        for row in rows:
            # Keep IFC names as data even when opened with spreadsheet software.
            cells = {}
            for key, value in row.items():
                cell = json.dumps(value, ensure_ascii=False) if isinstance(value, (list, dict)) else value
                if isinstance(cell, str) and cell.startswith(('=', '+', '-', '@', '\t', '\r')):
                    cell = "'" + cell
                cells[key] = cell
            writer.writerow(cells)


def audit(source, output):
    output.mkdir(parents=True, exist_ok=True)
    motor = MotorBIM()
    model = motor.cargar_ifc(str(source))
    result = motor.cuantificar()
    if result.errores:
        raise ValueError('; '.join(result.errores))
    rows = inventario_cobertura(model, result.elementos)
    remaining = [r for r in rows if not r['admitido']]
    conflicts = conflictos_de_conjuntos(result.elementos)
    volumes = []
    for element in result.elementos:
        if element.fuente_volumen != 'GEOMETRIA_CALCULADA':
            continue
        mesh = element.malla
        volumes.append({
            'global_id': element.global_id, 'tipo': element.tipo,
            'volumen_propuesto_m3': element.volumen,
            'fuente_cantidad': element.fuente_volumen,
            **auditar_volumen(mesh.vertices if mesh else [], mesh.caras if mesh else [], element.volumen),
        })
    with source.open('rb') as stream:
        source_hash = hashlib.file_digest(stream, 'sha256').hexdigest()
    summary = {
        'archivo_sha256': source_hash,
        'bytes': source.stat().st_size, 'schema': model.schema,
        'productos': len(rows), 'admitidos': len(result.elementos), 'restantes': len(remaining),
        'mallas_admitidas': sum(e.malla is not None for e in result.elementos),
        'fuentes_volumen_admitidos': dict(Counter(e.fuente_volumen for e in result.elementos)),
        'restantes_por_tipo': dict(Counter(r['tipo'] for r in remaining)),
        'restantes_por_cobertura': dict(Counter(r['estado_cobertura'] for r in remaining)),
        'restantes_con_representacion_propia': sum(r['representacion_propia'] for r in remaining),
        'relaciones_padre_hijo_admitidas': len(conflicts),
        'volumenes_geometricos': len(volumes),
        'diagnostico_volumenes': dict(Counter(r['estado'] for r in volumes)),
        'motivos_volumenes': dict(Counter(reason for r in volumes for reason in r['motivos'])),
        'partidas_contractuales_vinculadas': 0,
        'cantidades_economicas_aprobadas': 0,
        'catalogos_de_otras_obras_aplicados': False,
        'limites': ['Consistencia topológica y numérica no aprueba medición contractual.',
                    'No certifica ausencia de autointersecciones ni solapamientos de sólidos.',
                    'Parentesco IFC no demuestra cobertura gráfica; se exigen componentes de malla reales.'],
    }
    for filename, value in [('resumen.json', summary), ('inventario.json', rows),
                            ('restantes.json', remaining), ('volumenes_geometricos.json', volumes),
                            ('relaciones_admitidas.json', conflicts)]:
        (output / filename).write_text(json.dumps(value, indent=2, ensure_ascii=False) + '\n')
    write_table(output / 'restantes.csv', remaining)
    write_table(output / 'volumenes_geometricos.csv', volumes)
    print(json.dumps(summary, ensure_ascii=False))


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('ifc', type=Path)
    parser.add_argument('--output-dir', type=Path, required=True)
    args = parser.parse_args()
    audit(args.ifc, args.output_dir)
