from __future__ import annotations

import ast
from pathlib import Path
from unittest.mock import AsyncMock

import pytest

from app.engines.juridico.motor_juridico import MotorJuridico, TipoContratacion
from app.engines.procurement.requirements import ProcurementRequirementMapper
from app.engines.procurement.rules import DeterministicRuleCompiler, DeterministicRuleRuntime
from app.engines.procurement.threshold_resolver import ThresholdBand, ThresholdDecision


def test_requirement_mapper_fails_closed_for_malformed_condition():
    assert ProcurementRequirementMapper._matches({}, {"x": 1}) is False
    assert ProcurementRequirementMapper._matches({"field": "missing", "op": "eq", "val": 1}, {"x": 1}) is False


def test_decision_table_no_match_is_a_testable_outcome():
    compiler = DeterministicRuleCompiler()
    runtime = DeterministicRuleRuntime()
    definition = {
        "id": "UNIQUE-NO-MATCH",
        "hit_policy": "UNIQUE",
        "rows": [
            {
                "id": "R1",
                "conditions": [{"field": "amount", "op": "gte", "val": 10}],
                "action": {"procedure": "DIRECT"},
            }
        ],
    }
    compiled = compiler.compile_decision_table(definition)
    result = runtime.evaluate_decision_table(compiled, {"amount": 1})
    assert result.matched is False
    assert result.error == "DECISION_MISS: ninguna fila coincide."
    cases = compiler.test_decision_table(compiled, [{"facts": {"amount": 1}, "expected": None}])
    assert cases[0]["passed"] is True


@pytest.mark.asyncio
async def test_candidate_legal_threshold_is_not_authoritative():
    engine = MotorJuridico()
    engine._thresholds.resolve = AsyncMock(return_value=ThresholdDecision(
        found=True,
        jurisdiction_code="MX-FED-OBRA",
        tipo_contratacion="OBRA_PUBLICA",
        ejercicio_fiscal=2026,
        band=ThresholdBand(0, None, 499, 3776, 223, 2868),
        ley="LOPSRM",
        articulo_referencia="Art. 43",
        fuente="Fuente secundaria pendiente de verificación",
        fuente_uri=None,
        estado_dato="CANDIDATO",
        datos_verificados=False,
        es_candidato=True,
        notes="No confirmado contra fuente primaria.",
        inherited_from=("MX-FED-OBRA",),
    ))
    result = await engine.determinar_procedimiento(
        object(),
        tenant_id="00000000-0000-0000-0000-000000000001",
        jurisdiction_code="MX-FED-OBRA",
        monto=1_000_000,
        tipo_contratacion=TipoContratacion.OBRA_PUBLICA,
        ejercicio_fiscal=2026,
        presupuesto_dependencia_miles=1_000,
    )
    assert result.procedimiento.value == "SIN_DETERMINAR"
    assert result.valido is False
    assert result.datos_verificados is False
    assert result.es_candidato is True


def test_rule_activation_requires_executed_tests_and_orchestrator_uses_draft():
    root = Path(__file__).parents[2] / "app"
    service = (root / "services/procurement/service.py").read_text()
    orchestrator = (root / "engines/procurement/orchestrator.py").read_text()
    assert 'if not cases:' in service
    assert 'if any(not result["passed"] for result in results):' in service
    assert 'status="ACTIVE"' in service
    assert 'status="DRAFT"' in orchestrator
    assert 'test_cases=[]' in orchestrator


def test_orchestrator_has_durable_execution_provenance_model():
    model = (Path(__file__).parents[2] / "app/models/procurement.py").read_text()
    versions = Path(__file__).parents[2] / "alembic/versions"
    provenance = (versions / "20260826_tender_rule_execution_provenance.py").read_text()
    hardening = (versions / "20260826_rule_execution_tenant_hardening.py").read_text()
    for token in ("TenderRuleExecution", "input_facts_hash", "compiled_hash", "selected_row_ids", "evaluated_conditions", "validation_run_id"):
        assert token in model
    assert 'revision = "20260826_tender_rule_execution_provenance"' in provenance
    assert 'down_revision = "20260826_tender_rule_lifecycle"' in provenance
    assert 'revision = "20260826_rule_execution_tenant_hardening"' in hardening
    assert 'down_revision = "20260826_tender_rule_execution_provenance"' in hardening
    assert 'op.create_table(' not in hardening
    for token in ("fk_rule_execution_tenant_tender", "fk_rule_execution_tenant_requirement", "fk_rule_execution_tenant_definition", "fk_rule_execution_tenant_validation"):
        assert token in hardening


def test_release_root_layout_and_human_gate_are_operationally_consistent():
    repo = Path(__file__).parents[3]
    git_root = repo.parent
    workflow = (git_root / ".github/workflows/security-hardening.yml").read_text()
    frontend = (repo / "frontend/app/src/apps/licitaciones-obra/components/TenderAutomationPanel.tsx").read_text()
    assert (git_root / ".github/workflows/security-hardening.yml").exists()
    assert "working-directory: Meg-Workspace-Documentos/backend" in workflow
    assert "working-directory: Meg-Workspace-Documentos/frontend/app" in workflow
    assert "readiness?.ready !== true" in frontend
    assert "'QA_READY', 'READY_FOR_HUMAN_REVIEW'" in frontend
