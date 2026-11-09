from pathlib import Path
import ast

BACKEND = Path(__file__).resolve().parents[2]

def test_programacion_signatures_have_tenant_context():
    p=BACKEND/"app/services/programacion_service.py"
    tree=ast.parse(p.read_text())
    targets={"calcular_cpm","calcular_pert","calcular_evm","actualizar_avance","listar_actividades","actualizar_actividad","obtener_gantt","obtener_curva_s","obtener_ruta_critica","exportar_programa"}
    found={}
    for n in ast.walk(tree):
        if isinstance(n,(ast.FunctionDef,ast.AsyncFunctionDef)) and n.name in targets:
            found[n.name]={a.arg for a in n.args.args}
    assert targets == found.keys()
    assert all("tenant_id" in args for args in found.values())


def test_bim_worker_propagates_tenant():
    text=(BACKEND/"app/workers/bim_tasks.py").read_text()
    assert "tenant_id=generacion.tenant_id" in text


def test_tez_auth_rejects_missing_tenant():
    text=(BACKEND/"tezcatlipoca/routers/auth.py").read_text()
    assert "no tiene tenant activo" in text


def test_notification_log_is_tenant_scoped():
    model=(BACKEND/"app/models/notifications.py").read_text()
    service=(BACKEND/"app/modules/notifications/service.py").read_text()
    assert "tenant_id" in model and 'ForeignKey("tenants.id"' in model
    assert "class NotificationLog(Base, UUIDMixin):" in model
    assert "tenant_id == tenant_id" in service


def test_tez_status_endpoint_exists():
    text=(BACKEND/"app/main.py").read_text()
    assert '/api/tezcatlipoca/status' in text
    assert 'dependency_health' in text
    assert 'CONFIG_REQUIRED' in text
