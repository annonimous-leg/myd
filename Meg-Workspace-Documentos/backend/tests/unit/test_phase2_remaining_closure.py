from pathlib import Path
import ast

ROOT = Path(__file__).resolve().parents[2]


def _text(rel: str) -> str:
    return (ROOT / rel).read_text(encoding="utf-8")


def test_tez_requires_active_tenant_context():
    text = _text("tezcatlipoca/routers/auth.py")
    assert "tenant_id" in text
    assert "no tiene tenant activo" in text


def test_tez_capability_status_is_structured():
    text = _text("app/main.py")
    assert '"dependency_health"' in text
    assert '"last_success"' in text
    assert '/api/tezcatlipoca/status' in text


def test_pades_is_fail_closed():
    text = _text("app/modules/firma/pades_lt.py")
    assert "ValidationContext fallback" not in text
    assert "se rechaza" in text


def test_notification_results_are_explicit():
    text = _text("app/modules/notifications/service.py")
    assert '"estado": "SENT"' in text
    assert '"estado": "PERSISTED"' in text


def test_programacion_service_keeps_tenant_contract():
    path = ROOT / "app/services/programacion_service.py"
    tree = ast.parse(path.read_text(encoding="utf-8"))
    names = {
        n.name: {a.arg for a in n.args.args}
        for n in ast.walk(tree)
        if isinstance(n, (ast.FunctionDef, ast.AsyncFunctionDef))
        and n.name in {"calcular_cpm", "calcular_pert", "calcular_evm", "actualizar_avance", "obtener_gantt", "obtener_ruta_critica"}
    }
    assert all("tenant_id" in args for args in names.values())
