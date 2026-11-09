import ast
from pathlib import Path


def test_orchestrator_materialize_call_passes_tenant_id_kwarg():
    root = Path(__file__).resolve().parents[2]
    source = (root / "app/engines/procurement/orchestrator.py").read_text(encoding="utf-8")
    tree = ast.parse(source)
    calls = []
    for node in ast.walk(tree):
        if isinstance(node, ast.Call) and isinstance(node.func, ast.Attribute) and node.func.attr == "materialize":
            calls.append(node)
    assert calls
    assert any(any(kw.arg == "tenant_id" for kw in call.keywords) for call in calls)
