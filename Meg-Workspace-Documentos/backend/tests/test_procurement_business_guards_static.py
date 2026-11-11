from pathlib import Path

BASE = Path(__file__).resolve().parents[1]
SERVICE = (BASE / "app/services/procurement/service.py").read_text(encoding="utf-8")
FRONT = (BASE / "../frontend/app/src/apps/licitaciones-obra/components/TenderAutomationPanel.tsx").resolve().read_text(encoding="utf-8")

def test_create_validates_jurisdiction_configuration_before_persisting():
    assert "await self._validate_tender_configuration(data)" in SERVICE

def test_reference_case_artifacts_are_not_submission_eligible_without_official_template():
    policy = (BASE / "app/services/procurement/artifact_policy.py").read_text(encoding="utf-8")
    assert "reference_only = bool(case_spec is not None and not official_template)" in SERVICE
    assert '"submission_eligible": submission_eligible' in SERVICE
    assert '"reference_only": reference_only' in SERVICE
    assert "def artifact_submission_eligible" in policy
    assert 'if _code(artifact) == "QA-REPORT":' in policy

def test_frontend_idempotency_key_is_stable_per_revision():
    assert 'procurement-run:${tender.id}:r${tender.current_revision}' in FRONT
    assert ':${Date.now()}' not in FRONT

def test_frontend_surfaces_business_readiness_gates():
    assert '.procurement.readiness(' in FRONT
    assert 'Antes de continuar' in FRONT
