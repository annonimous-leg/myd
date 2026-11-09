import ast
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
ORCH = (ROOT / "app/engines/procurement/orchestrator.py").read_text(encoding="utf-8")
TRACKER = (ROOT / "app/services/procurement/preparation_runs.py").read_text(encoding="utf-8")
SERVICE = (ROOT / "app/services/procurement/service.py").read_text(encoding="utf-8")
MODEL = (ROOT / "app/models/procurement.py").read_text(encoding="utf-8")
MATERIALIZER = (ROOT / "app/engines/procurement/materializer.py").read_text(encoding="utf-8")


def test_orchestrator_has_durable_stage_boundaries():
    for stage in (
        "CONTRACT_POLICY",
        "LOAD_RULE_INPUTS",
        "REQUIREMENT_EVALUATION",
        "MATERIALIZATION",
        "RISK_ANALYSIS",
        "CROSS_CONSISTENCY",
        "VALIDATION_EVIDENCE",
        "LIFECYCLE_GATE",
    ):
        assert f'"{stage}"' in ORCH


def test_stage_tracker_uses_independent_session_and_tenant_scope():
    assert "AsyncSessionLocal" in TRACKER
    assert "TenderPreparationRun.tenant_id == self.tenant_id" in TRACKER
    assert "TenderPreparationStageRun.tenant_id == self.tenant_id" in TRACKER


def test_validation_runs_have_normalized_evidence_link_entity():
    assert "class TenderValidationEvidenceLink" in MODEL
    assert "TenderValidationEvidenceLink(" in ORCH
    assert '"evidence_ids"' in ORCH


def test_materializer_requires_tenant_context():
    assert "tenant_id: UUID" in MATERIALIZER
    assert "ExpedienteObra.tenant_id == tenant_id" in MATERIALIZER
    assert "ModeloBIM.tenant_id == tenant_id" in MATERIALIZER


def test_orchestrator_passes_tenant_id_to_materialize():
    tree = ast.parse(ORCH)
    calls = [
        node
        for node in ast.walk(tree)
        if isinstance(node, ast.Call)
        and isinstance(node.func, ast.Attribute)
        and node.func.attr == "materialize"
    ]
    assert calls
    assert any(
        any(kw.arg == "tenant_id" and isinstance(kw.value, ast.Attribute) and kw.value.attr == "tenant_id" for kw in call.keywords)
        for call in calls
    )


def test_service_passes_tracker_into_orchestrator():
    assert "self.orchestrator.run(self.db, tender, tracker=tracker)" in SERVICE


def test_preparation_history_is_tenant_scoped():
    assert 'TenderPreparationRun.tender_id == tender.id' in SERVICE
    assert 'TenderPreparationRun.tenant_id == self.user.tenant_id' in SERVICE
    assert 'TenderPreparationStageRun.tenant_id == self.user.tenant_id' in SERVICE
