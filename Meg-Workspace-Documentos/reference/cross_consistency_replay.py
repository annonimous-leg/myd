import json
from pathlib import Path
ROOT=Path(__file__).parent

def check_case(path):
    d=json.loads(Path(path).read_text())['synthetic_operational_input']
    e=d['expediente']; p=d['presupuesto']; m=d['investigacion_mercado']; pr=d['proposicion']; pl=d['planeacion']
    findings=[]
    def eq(a,b,code,desc):
        if a!=b:
            findings.append({'code':code,'severity':'P0','expected':b,'actual':a,'description':desc})
    eq(p['total_sin_iva'],e['monto_estimado'],'CONS-MONTO','Presupuesto total vs monto estimado del expediente')
    if 'plazo_dias' in pl:
        eq(pl['plazo_dias'],e['plazo_dias'],'CONS-PLAZO','Plazo de planeacion vs plazo del expediente')
    if abs(m['precio_referencia']-e['monto_estimado']) > 0.02:
        findings.append({'code':'CONS-MARKET','severity':'P0','expected':e['monto_estimado'],'actual':m['precio_referencia'],'description':'Precio de referencia de investigación de mercado vs monto del expediente'})
    if pr['monto_total'] > m['precio_referencia']:
        findings.append({'code':'CONS-BID','severity':'WARNING','expected':f'<= {m["precio_referencia"]}','actual':pr['monto_total'],'description':'Oferta de ejemplo por encima de referencia'})
    return findings
for f in ['expediente_inbal_n3_2026_CONTROL.json','expediente_inbal_n3_2026_INCONSISTENTE.json']:
    print('\nCASE',f)
    xs=check_case(ROOT/f)
    if not xs: print('PASS')
    else:
        for x in xs: print(x)
