"""Selective-recovery regressions for procurement revision and format gates."""
import ast
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock

import pytest

from app.core.errors import MegalodonException
from app.models.procurement import TenderState
from app.services.procurement.service import (
    _approval_gate_ready,
    _ensure_tender_mutation_allowed,
    _merge_authoritative_format_checklist,
)
from app.services.procurement.artifact_policy import (
    artifact_requires_signature,
    artifact_submission_eligible,
)


def test_browser_cannot_downgrade_server_required_format():
    definitions = [{
        "format_code": "ECO.1",
        "title": "Análisis de precios unitarios",
        "category": "ECONOMICO",
        "required": True,
    }]
    submitted = [{
        "code": "ECO.1",
        "title": "Renamed by browser",
        "category": "ADMINISTRATIVO",
        "required": False,
        "status": "LISTO",
        "notes": "Reviewed",
    }]

    result = _merge_authoritative_format_checklist(definitions, submitted)

    assert result == [{
        "code": "ECO.1",
        "title": "Análisis de precios unitarios",
        "category": "ECONOMICO",
        "required": True,
        "status": "LISTO",
        "notes": "Reviewed",
    }]


def test_omitted_mandatory_format_is_restored_as_pending():
    result = _merge_authoritative_format_checklist(
        [
            {"code": "TEC-01", "title": "Memoria técnica", "category": "TECNICO", "required": True},
            {"code": "ECO-01", "title": "Presupuesto", "category": "ECONOMICO", "required": True},
        ],
        [{"code": "TEC-01", "status": "LISTO"}],
    )

    assert [row["code"] for row in result] == ["TEC-01", "ECO-01"]
    assert result[1]["required"] is True
    assert result[1]["status"] == "PENDIENTE"


@pytest.mark.parametrize("submitted", [
    [{"code": "UNKNOWN", "status": "LISTO"}],
    [{"code": "ECO.1", "status": "LISTO"}, {"code": "ECO.1", "status": "EDITADO"}],
    [{"code": "ECO.1", "status": "APPROVED"}],
])
def test_unknown_duplicate_or_invalid_format_rows_are_rejected(submitted):
    with pytest.raises(ValueError):
        _merge_authoritative_format_checklist(
            [{"format_code": "ECO.1", "required": True}],
            submitted,
        )


@pytest.mark.parametrize("state", [
    TenderState.CROSS_VALIDATED.value,
    TenderState.QA_READY.value,
    TenderState.READY_FOR_HUMAN_REVIEW.value,
    TenderState.HUMAN_APPROVAL.value,
    TenderState.SIGNED.value,
    TenderState.SUBMISSION_READY.value,
    TenderState.BLOCKED.value,
])
def test_post_qa_mutations_require_an_explicit_new_revision(state):
    tender = type("Tender", (), {"state": state, "frozen": False})()
    with pytest.raises(MegalodonException) as exc:
        _ensure_tender_mutation_allowed(tender, "edición")
    assert exc.value.status_code == 409


def test_pre_qa_mutation_is_allowed_and_frozen_tender_is_rejected():
    editable = type("Tender", (), {"state": TenderState.OBSERVED.value, "frozen": False})()
    _ensure_tender_mutation_allowed(editable, "edición")

    frozen = type("Tender", (), {"state": TenderState.OBSERVED.value, "frozen": True})()
    with pytest.raises(MegalodonException) as exc:
        _ensure_tender_mutation_allowed(frozen, "edición")
    assert exc.value.status_code == 400


def test_approval_gate_requires_readiness_and_reviewable_state():
    assert _approval_gate_ready(TenderState.QA_READY.value, {"ready": True})
    assert _approval_gate_ready(TenderState.READY_FOR_HUMAN_REVIEW.value, {"ready": True})
    assert not _approval_gate_ready(TenderState.QA_READY.value, {"ready": False})
    assert not _approval_gate_ready(TenderState.BLOCKED.value, {"ready": True})


def test_cross_validated_state_requires_explicit_compile_exception():
    tender = type("Tender", (), {"state": TenderState.CROSS_VALIDATED.value, "frozen": False})()
    with pytest.raises(MegalodonException):
        _ensure_tender_mutation_allowed(tender, "ingesta")

    _ensure_tender_mutation_allowed(
        tender,
        "compilación de artefactos",
        allow_cross_validated=True,
    )

    qa_ready = type("Tender", (), {"state": TenderState.QA_READY.value, "frozen": False})()
    with pytest.raises(MegalodonException):
        _ensure_tender_mutation_allowed(
            qa_ready,
            "compilación de artefactos",
            allow_cross_validated=True,
        )


def test_schedule_ready_remains_the_normal_compilation_entry_state():
    tender = type("Tender", (), {"state": TenderState.SCHEDULE_READY.value, "frozen": False})()
    _ensure_tender_mutation_allowed(tender, "compilación de artefactos")



def test_internal_qa_report_is_neither_submission_artifact_nor_signature_target():
    artifact = type("Artifact", (), {
        "artifact_code": "QA-REPORT",
        "media_type": "application/pdf",
        "artifact_metadata": {},
    })()

    assert artifact_submission_eligible(artifact) is False
    assert artifact_requires_signature(artifact) is False


def test_official_pdf_is_submission_eligible_and_requires_signature_by_default():
    artifact = type("Artifact", (), {
        "artifact_code": "TEC-01",
        "media_type": "application/pdf",
        "artifact_metadata": {"submission_eligible": True},
    })()

    assert artifact_submission_eligible(artifact) is True
    assert artifact_requires_signature(artifact) is True


def test_artifact_policy_is_server_metadata_driven():
    optional_pdf = type("Artifact", (), {
        "artifact_code": "ANNEX-OPTIONAL",
        "media_type": "application/pdf",
        "artifact_metadata": {"submission_eligible": True, "signature_required": False},
    })()
    internal_xlsx = type("Artifact", (), {
        "artifact_code": "INTERNAL-CALC",
        "media_type": "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        "artifact_metadata": {"submission_eligible": False, "signature_required": False},
    })()

    assert artifact_submission_eligible(optional_pdf) is True
    assert artifact_requires_signature(optional_pdf) is False
    assert artifact_submission_eligible(internal_xlsx) is False
    assert artifact_requires_signature(internal_xlsx) is False



def test_submission_manifest_is_built_before_signed_state_transition():
    source_path = Path(__file__).resolve().parents[2] / "app/services/procurement/service.py"
    module = ast.parse(source_path.read_text(encoding="utf-8"))
    service = next(
        node for node in module.body
        if isinstance(node, ast.ClassDef) and node.name == "ProcurementService"
    )
    submission = next(
        node for node in service.body
        if isinstance(node, ast.AsyncFunctionDef) and node.name == "submission"
    )

    build_lines = [
        node.lineno for node in ast.walk(submission)
        if isinstance(node, ast.Call)
        and isinstance(node.func, ast.Attribute)
        and node.func.attr == "build_submission"
    ]
    signed_transition_lines = [
        node.lineno for node in ast.walk(submission)
        if isinstance(node, ast.Call)
        and isinstance(node.func, ast.Attribute)
        and node.func.attr == "_transition"
        and len(node.args) >= 2
        and isinstance(node.args[1], ast.Attribute)
        and node.args[1].attr == "SIGNED"
    ]
    package_ready_lines = [
        node.lineno for node in ast.walk(submission)
        if isinstance(node, ast.Call)
        and isinstance(node.func, ast.Attribute)
        and node.func.attr == "_transition"
        and len(node.args) >= 2
        and isinstance(node.args[1], ast.Attribute)
        and node.args[1].attr == "SUBMISSION_READY"
    ]

    assert len(build_lines) == 1
    assert len(signed_transition_lines) == 1
    assert len(package_ready_lines) == 1
    assert build_lines[0] < signed_transition_lines[0] < package_ready_lines[0]



@pytest.mark.asyncio
async def test_workspace_client_draft_is_not_claimed_as_server_generated():
    from app.services.procurement.workspace import TenderWorkspaceService

    tenant_id = "tenant-1"
    user = SimpleNamespace(id="user-1", tenant_id=tenant_id)
    tender = SimpleNamespace(
        id="tender-1",
        current_revision=4,
        canonical_model={"facts": {"object": "Obra"}},
        frozen=False,
    )
    document = SimpleNamespace(
        id="document-1",
        row_version=2,
        version=2,
        locked=False,
        human_modified=False,
        tender_revision=3,
        generated_from_revision=3,
        generated_model_hash="old-model-hash",
        last_conflict=None,
        status="GENERATED",
        actualizado_por_id="previous-user",
    )
    db = SimpleNamespace(
        flush=AsyncMock(),
        add=MagicMock(),
        commit=AsyncMock(),
        refresh=AsyncMock(),
    )
    service = TenderWorkspaceService(db, user)
    service.tender = AsyncMock(return_value=tender)
    service.get_document = AsyncMock(return_value=document)

    result = await service.regenerate(
        "tender-1",
        "document-1",
        generated_text="Borrador elaborado fuera del servidor",
        generated_model={"body": "texto del cliente"},
        expected_row_version=2,
    )

    assert result.status == "DRAFT"
    assert result.human_modified is True
    assert result.generated_from_revision is None
    assert result.generated_model_hash is None
    revision = db.add.call_args.args[0]
    assert revision.operation == "CLIENT_DRAFT_IMPORT"
    assert revision.source_model_hash is None
    assert revision.human_modified is True
    assert revision.revision_metadata == {
        "content_origin": "client_supplied",
        "server_generation_verified": False,
    }



def test_legacy_artifacts_without_explicit_submission_policy_fail_closed():
    legacy_pdf = type("Artifact", (), {
        "artifact_code": "LEGACY-UNKNOWN",
        "media_type": "application/pdf",
        "artifact_metadata": {},
    })()

    assert artifact_submission_eligible(legacy_pdf) is False
    assert artifact_requires_signature(legacy_pdf) is False
