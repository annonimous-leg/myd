from pathlib import Path
import ast


def test_notification_panel_passes_tenant_id():
    root = Path(__file__).parents[2]
    tree = ast.parse((root / "app/modules/notifications/service.py").read_text())
    fn = next(n for n in ast.walk(tree) if isinstance(n, ast.AsyncFunctionDef) and n.name == "_guardar_panel")
    assert "tenant_id" in {a.arg for a in fn.args.args}
    src = (root / "app/modules/notifications/service.py").read_text()
    assert "tenant_id=tenant_id" in src


def test_notification_legacy_rows_are_not_assigned_to_unknown_tenant():
    root = Path(__file__).parents[2]
    model = (root / "app/models/notifications.py").read_text()
    migration = (root / "alembic/versions/ff2a1b3c4d5e_notification_tenant_scope.py").read_text()
    assert "nullable=True" in model
    assert "LEGACY_UNSCOPED" in model
    assert "LEGACY_UNSCOPED" in migration
    assert "tenant_id IS NULL" in migration
