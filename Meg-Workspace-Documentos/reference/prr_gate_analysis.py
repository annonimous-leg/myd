import ast, json, re
from pathlib import Path
from datetime import datetime

ROOT=Path('/mnt/data/prr_runtime/backend')
REF=Path('/mnt/data/prr_runtime/reference/expediente_inbal_n3_2026.json')
fixture=json.loads(REF.read_text())
ref=fixture['reference']; data=fixture['synthetic_operational_input']

# Current code evidence
lic_path=ROOT/'app/api/v1/licitaciones_obra.py'
lic_text=lic_path.read_text()
tree=ast.parse(lic_text)
funcs={n.name:n for n in tree.body if isinstance(n, ast.AsyncFunctionDef)}

def const_strings(node):
    vals=[]
    for n in ast.walk(node):
        if isinstance(n, ast.Constant) and isinstance(n.value,(str,int,float)):
            vals.append(n.value)
    return vals

def uses_name(node,name):
    return any(isinstance(n,ast.Name) and n.id==name for n in ast.walk(node))

route_checks=[]
for name in ['crear_planeacion','obtener_planeacion','publicar_convocatoria','obtener_convocatoria','registrar_proposicion','listar_proposiciones','evaluar_proposiciones','emitir_fallo']:
    n=funcs[name]
    route_checks.append({
        'function':name,
        'line':n.lineno,
        'uses_db_name':uses_name(n,'db'),
        'uses_current_user_name':uses_name(n,'current_user'),
        'hardcoded_5000000':5000000.0 in const_strings(n),
        'hardcoded_180':180 in const_strings(n),
        'hardcoded_2026_dates':[x for x in const_strings(n) if isinstance(x,str) and x.startswith('2026-')],
        'hardcoded_plan_uuid': any(isinstance(x,str) and x.startswith('plan-') for x in const_strings(n)),
        'hardcoded_prop_uuid': any(isinstance(x,str) and x.startswith('prop-') for x in const_strings(n)),
    })

# Search-backed component integration presence
def refs(term):
    hits=[]
    for p in ROOT.rglob('*.py'):
        try:t=p.read_text(encoding='utf-8')
        except:continue
        if term in t:
            hits.append(str(p.relative_to(ROOT)))
    return sorted(set(hits))

integration={
 'PlaneacionExpediente':refs('PlaneacionExpediente'),
 'InvestigacionMercado':refs('InvestigacionMercado'),
 'SelectorProcedimiento':refs('SelectorProcedimiento'),
 'DocumentCompiler':refs('DocumentCompiler'),
 'CrossConsistency':refs('CrossConsistency'),
 'Outbox':refs('Outbox'),
 'Idempotency':refs('Idempotency'),
}

# Reference-vs-route exact contradictions obtained from the replay output.
replay=json.loads((Path('/mnt/data/prr_runtime/reference/route_replay_outputs.json')).read_text())
contradictions=[]
conv=replay['obtener_convocatoria']
if conv['monto_estimado'] != data['expediente']['monto_estimado']:
    contradictions.append(('monto_estimado',data['expediente']['monto_estimado'],conv['monto_estimado']))
if conv['plazo_ejecucion'] != data['expediente']['plazo_dias']:
    contradictions.append(('plazo_ejecucion',data['expediente']['plazo_dias'],conv['plazo_ejecucion']))
if conv['fecha_publicacion'] != ref['publication_date']:
    contradictions.append(('fecha_publicacion',ref['publication_date'],conv['fecha_publicacion']))
if conv['fecha_apertura'][:10] != ref['proposal_opening'][:10]:
    contradictions.append(('fecha_apertura',ref['proposal_opening'],conv['fecha_apertura']))
plane=replay['obtener_planeacion']
if plane['presupuesto_base']['monto'] != data['expediente']['monto_estimado']:
    contradictions.append(('planeacion.presupuesto_base',data['expediente']['monto_estimado'],plane['presupuesto_base']['monto']))
if plane['programa_obra']['duracion_dias'] != data['expediente']['plazo_dias']:
    contradictions.append(('planeacion.programa_obra.duracion',data['expediente']['plazo_dias'],plane['programa_obra']['duracion_dias']))

report={
 'reference':ref,
 'route_runtime_replay':'Current function bodies executed directly via AST harness; full FastAPI runtime blocked by missing declared dependencies.',
 'route_checks':route_checks,
 'contradictions_against_fixture_and_official_reference':contradictions,
 'integration_evidence':integration,
}
Path('/mnt/data/prr_runtime/reference/prr_gate_analysis.json').write_text(json.dumps(report,ensure_ascii=False,indent=2))
print(json.dumps(report,ensure_ascii=False,indent=2))
