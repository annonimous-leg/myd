import ast
from pathlib import Path
root=Path('/tmp/auditB/backend/app')
checks=[]
# ProgramacionService production class restored
p=root/'services/programacion_service.py'; t=ast.parse(p.read_text())
classes={n.name:n for n in t.body if isinstance(n,ast.ClassDef)}
svc=classes.get('ProgramacionService'); methods={n.name for n in svc.body if isinstance(n,(ast.FunctionDef,ast.AsyncFunctionDef))} if svc else set()
checks.append(('ProgramacionService class', svc is not None))
checks.append(('ProgramacionService core methods', {'crear_programa','calcular_cpm','calcular_pert','calcular_evm','actualizar_avance','listar_actividades','actualizar_actividad'}.issubset(methods)))
checks.append(('ProgramacionService tenant constructor', 'tenant_id' in ast.get_source_segment(p.read_text(), next(n for n in svc.body if isinstance(n,ast.FunctionDef) and n.name=='__init__'))))
# No accidental unparameterized PresupuestoService in app
for path in root.rglob('*.py'):
    if '__pycache__' in path.parts: continue
    text=path.read_text(errors='ignore')
    if 'PresupuestoService(db)' in text:
        checks.append((f'no bare PresupuestoService: {path.relative_to(root)}',False))
# restored endpoint
lp=root/'api/v1/licitaciones.py'; lt=ast.parse(lp.read_text()); fn={n.name for n in lt.body if isinstance(n,(ast.FunctionDef,ast.AsyncFunctionDef))}; checks.append(('create junta endpoint restored', 'crear_junta_aclaraciones' in fn))
# module constructors tenant-aware
for f,c in [('modules/expedientes/service.py','ExpedienteModuleService'),('modules/presupuestos/service.py','PresupuestoModuleService')]:
 p=root/f; t=ast.parse(p.read_text()); cls=next(cn for cn in t.body if isinstance(cn,ast.ClassDef) and cn.name==c); init=next(m for m in cls.body if isinstance(m,(ast.FunctionDef,ast.AsyncFunctionDef)) and m.name=='__init__'); checks.append((f'{c} accepts tenant', any(a.arg=='tenant_id' for a in init.args.args)))
for name,ok in checks:
 print(('PASS' if ok else 'FAIL'), name)
if not all(ok for _,ok in checks): raise SystemExit(1)
