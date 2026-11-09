"""Megalodon is the bidder's proposal-preparation workspace, never the contracting authority's portal."""
import pytest
from pydantic import ValidationError
from sqlalchemy import select
from uuid import uuid4

from app.api.v1.procurement import RecommendProcedureBody
from app.schemas.procurement.schemas import EvidenceCreate
from app.main import app
from app.core.errors import MegalodonException
from app.engines.procurement.requirements import ProcurementRequirementMapper
from app.models.procurement import TenderEvidence, TenderPackage, TenderState
from app.services.procurement.service import ProcurementService
from app.services.procurement.workspace import TenderWorkspaceService
from tests.integration.test_closure_two_tenants import make_expediente


def test_authority_lifecycle_routers_are_not_exposed_by_megalodon():
    paths = set(app.openapi()["paths"])

    forbidden_prefixes = (
        "/api/v1/licitaciones",
        "/api/v1/contratos",
        "/api/v1/licitaciones-obra",
    )
    exposed = sorted(
        path for path in paths
        if any(path == prefix or path.startswith(prefix + "/") for prefix in forbidden_prefixes)
    )

    assert exposed == [], f"Official contracting-authority routes are still exposed: {exposed}"


def test_procurement_preparation_remains_available_for_bidder_workspace():
    paths = set(app.openapi()["paths"])

    assert "/api/v1/procurement/tenders" in paths
    assert "/api/v1/procurement/tenders/{tender_id}/compile" in paths
    assert "/api/v1/procurement/tenders/{tender_id}/submission" in paths
    assert "/api/v1/procurement/tenders/{tender_id}/submission/download" in paths


def test_procedure_recommendation_accepts_bidder_mode_only():
    body = RecommendProcedureBody.model_validate({
        "jurisdiction_code": "MX-FED-OBRA",
        "monto": 500000,
        "flow_mode": "LICITANTE",
        "procedure_type_declared": "LICITACION_PUBLICA",
    })

    assert body.flow_mode == "LICITANTE"

    with pytest.raises(ValidationError):
        RecommendProcedureBody.model_validate({
            "jurisdiction_code": "MX-FED-OBRA",
            "monto": 500000,
            "flow_mode": "CONVOCANTE",
        })



def test_bidder_workspace_service_has_no_authority_bridge_commands():
    assert not hasattr(TenderWorkspaceService, "bridge")
    assert not hasattr(TenderWorkspaceService, "sync_bridge")



def _source_requirement(code: str, description: str, source_hash: str, line: int) -> dict:
    return {
        "code": code,
        "description": description,
        "category": "LEGAL",
        "mandatory": None,
        "status": "REVIEW_REQUIRED",
        "source_reference": {
            "source_hash": source_hash,
            "text_original": description,
            "line_start": line,
            "line_end": line,
            "confirmation_required": True,
        },
    }


@pytest.mark.asyncio
async def test_confirming_repeated_official_code_changes_only_selected_source(db_session, tenant_a_user):
    tenant, user = tenant_a_user
    expediente = make_expediente(tenant, user)
    db_session.add(expediente)
    await db_session.flush()

    tender = TenderPackage(
        tenant_id=tenant.id,
        expediente_id=expediente.id,
        identifier=f"TP-{uuid4().hex[:8]}",
        title="Propuesta con bases y anexo",
        jurisdiction_code="MX-FED-OBRA",
        current_revision=1,
    )
    db_session.add(tender)
    await db_session.flush()

    base_hash, annex_hash = "a" * 64, "b" * 64
    base = TenderEvidence(
        tenant_id=tenant.id,
        tender_id=tender.id,
        kind="SOURCE_DOCUMENT",
        subject="bases.pdf",
        value={
            "source_role": "CONVOCATORIA",
            "requirement_candidates": [
                _source_requirement("REQ-001", "Presentar programa de obra", base_hash, 12),
            ],
        },
        source_uri="tenders/test/bases.pdf",
        source_hash=base_hash,
        source_revision=1,
        status="ACTIVE",
        creado_por_id=user.id,
        actualizado_por_id=user.id,
    )
    annex = TenderEvidence(
        tenant_id=tenant.id,
        tender_id=tender.id,
        kind="SOURCE_DOCUMENT",
        subject="anexo.pdf",
        value={
            "source_role": "ANEXO",
            "requirement_candidates": [
                _source_requirement("REQ-001", "Acreditar experiencia técnica", annex_hash, 4),
            ],
        },
        source_uri="tenders/test/anexo.pdf",
        source_hash=annex_hash,
        source_revision=1,
        status="ACTIVE",
        creado_por_id=user.id,
        actualizado_por_id=user.id,
    )
    db_session.add_all([base, annex])
    await db_session.commit()
    await db_session.refresh(base)
    await db_session.refresh(annex)

    service = ProcurementService(db_session, user)
    candidates = await service.requirement_candidates(tender.id)
    assert len(candidates) == 2
    assert candidates[0]["code"] == candidates[1]["code"] == "REQ-001"
    assert candidates[0]["candidate_id"] != candidates[1]["candidate_id"]

    selected = next(row for row in candidates if row["evidence_id"] == str(base.id))
    confirmed = await service.confirm_requirement_candidates(tender.id, [{
        "candidate_id": selected["candidate_id"],
        "evidence_id": str(base.id),
        "code": "REQ-001",
        "description": "Programa de obra revisado por el licitante",
        "category": "TECNICO",
        "mandatory": True,
    }])

    assert len(confirmed) == 1
    await db_session.refresh(base)
    await db_session.refresh(annex)
    base_candidate = base.value["requirement_candidates"][0]
    annex_candidate = annex.value["requirement_candidates"][0]
    assert base_candidate["status"] == "CONFIRMED"
    assert base_candidate["description"] == "Programa de obra revisado por el licitante"
    assert annex_candidate["status"] == "REVIEW_REQUIRED"
    assert annex_candidate["description"] == "Acreditar experiencia técnica"
    readiness = await service.readiness(tender.id)
    assert any(finding["code"] == "REQUIREMENT_REVIEW_REQUIRED" for finding in readiness["findings"])


@pytest.mark.asyncio
async def test_conflicting_duplicate_codes_are_rejected_without_partial_confirmation(db_session, tenant_a_user):
    tenant, user = tenant_a_user
    expediente = make_expediente(tenant, user)
    db_session.add(expediente)
    await db_session.flush()
    tender = TenderPackage(
        tenant_id=tenant.id,
        expediente_id=expediente.id,
        identifier=f"TP-{uuid4().hex[:8]}",
        title="Fuentes con requisito homónimo",
        jurisdiction_code="MX-FED-OBRA",
        current_revision=1,
    )
    db_session.add(tender)
    await db_session.flush()

    hashes = ("c" * 64, "d" * 64)
    evidence_rows = []
    for index, (source_hash, description) in enumerate(zip(
        hashes,
        ("Presentar programa de obra", "Acreditar experiencia técnica"),
    ), start=1):
        evidence_rows.append(TenderEvidence(
            tenant_id=tenant.id,
            tender_id=tender.id,
            kind="SOURCE_DOCUMENT",
            subject=f"fuente-{index}.pdf",
            value={
                "source_role": "CONVOCATORIA" if index == 1 else "ANEXO",
                "requirement_candidates": [
                    _source_requirement("REQ-009", description, source_hash, index),
                ],
            },
            source_uri=f"tenders/test/fuente-{index}.pdf",
            source_hash=source_hash,
            source_revision=1,
            status="ACTIVE",
            creado_por_id=user.id,
            actualizado_por_id=user.id,
        ))
    db_session.add_all(evidence_rows)
    await db_session.commit()
    for row in evidence_rows:
        await db_session.refresh(row)

    service = ProcurementService(db_session, user)
    candidates = await service.requirement_candidates(tender.id)
    patches = [
        {
            "candidate_id": candidate["candidate_id"],
            "evidence_id": candidate["evidence_id"],
            "code": candidate["code"],
            "description": candidate["description"],
            "category": candidate["category"],
            "mandatory": True,
        }
        for candidate in candidates
    ]
    with pytest.raises(MegalodonException) as exc:
        await service.confirm_requirement_candidates(tender.id, patches)
    assert exc.value.status_code == 409

    await db_session.rollback()
    for row in evidence_rows:
        await db_session.refresh(row)
        assert row.value["requirement_candidates"][0]["status"] == "REVIEW_REQUIRED"


def test_requirement_mapper_preserves_all_sources_for_identical_repeated_code():
    mapper = ProcurementRequirementMapper()
    requirements = mapper.derive(
        tender_id=uuid4(),
        source_texts=[
            {
                "source_id": "evidence-a",
                "source_hash": "e" * 64,
                "uri": "tenders/test/bases.pdf",
                "document_id": "evidence-a",
                "revision": 1,
                "requirements": [{
                    "code": "REQ-014",
                    "description": "Presentar programa de obra vigente",
                    "category": "TECNICO",
                    "mandatory": True,
                    "source_reference": {
                        "source_id": "evidence-a",
                        "source_hash": "e" * 64,
                        "text_original": "Presentar programa de obra vigente",
                    },
                }],
            },
            {
                "source_id": "evidence-b",
                "source_hash": "f" * 64,
                "uri": "tenders/test/anexo.pdf",
                "document_id": "evidence-b",
                "revision": 1,
                "requirements": [{
                    "code": "REQ-014",
                    "description": "Presentar programa de obra vigente",
                    "category": "TECNICO",
                    "mandatory": True,
                    "source_reference": {
                        "source_id": "evidence-b",
                        "source_hash": "f" * 64,
                        "text_original": "Presentar programa de obra vigente",
                    },
                }],
            },
        ],
    )

    assert len(requirements) == 1
    supporting_sources = requirements[0].source_reference["supporting_sources"]
    assert {source["source_id"] for source in supporting_sources} == {"evidence-a", "evidence-b"}


def test_requirement_mapper_rejects_conflicting_definitions_for_same_official_code():
    mapper = ProcurementRequirementMapper()
    shared = {
        "code": "REQ-015",
        "category": "TECNICO",
        "mandatory": True,
    }
    with pytest.raises(ValueError, match="REQ-015"):
        mapper.derive(
            tender_id=uuid4(),
            source_texts=[
                {
                    "source_id": "evidence-a",
                    "source_hash": "1" * 64,
                    "uri": "tenders/test/bases.pdf",
                    "document_id": "evidence-a",
                    "revision": 1,
                    "requirements": [{
                        **shared,
                        "description": "Presentar programa de obra vigente",
                        "source_reference": {"source_id": "evidence-a", "source_hash": "1" * 64},
                    }],
                },
                {
                    "source_id": "evidence-b",
                    "source_hash": "2" * 64,
                    "uri": "tenders/test/anexo.pdf",
                    "document_id": "evidence-b",
                    "revision": 1,
                    "requirements": [{
                        **shared,
                        "description": "Acreditar experiencia técnica suficiente",
                        "source_reference": {"source_id": "evidence-b", "source_hash": "2" * 64},
                    }],
                },
            ],
        )



def test_requirement_confirmation_rejects_string_booleans_and_missing_source_identity():
    from app.schemas.procurement.schemas import RequirementCandidateConfirmation

    with pytest.raises(ValidationError):
        RequirementCandidateConfirmation.model_validate({
            "candidate_id": "a" * 64,
            "evidence_id": str(uuid4()),
            "code": "REQ-001",
            "description": "Requisito revisado",
            "category": "TECNICO",
            "mandatory": "false",
        })

    with pytest.raises(ValidationError):
        RequirementCandidateConfirmation.model_validate({
            "candidate_id": "a" * 64,
            "code": "REQ-001",
            "description": "Requisito revisado",
            "category": "TECNICO",
            "mandatory": False,
        })


@pytest.mark.asyncio
async def test_run_blocks_when_only_some_extracted_requirements_are_human_confirmed(
    db_session, tenant_a_user, monkeypatch,
):
    tenant, user = tenant_a_user
    expediente = make_expediente(tenant, user)
    db_session.add(expediente)
    await db_session.flush()

    tender = TenderPackage(
        tenant_id=tenant.id,
        expediente_id=expediente.id,
        identifier=f"TP-{uuid4().hex[:8]}",
        title="Revisión parcial de requisitos",
        jurisdiction_code="MX-FED-OBRA",
        state=TenderState.JURISDICTIONED.value,
        current_revision=1,
    )
    db_session.add(tender)
    await db_session.flush()

    evidence_rows = []
    for index, status in enumerate(("CONFIRMED", "REVIEW_REQUIRED"), start=1):
        source_hash = f"{index:064x}"
        description = f"Requisito de prueba {index}"
        candidate = {
            "code": f"REQ-{index:03d}",
            "description": description,
            "category": "TECNICO",
            "mandatory": True if status == "CONFIRMED" else None,
            "status": status,
            "source_reference": {
                "source_hash": source_hash,
                "text_original": description,
                "line_start": index,
                "line_end": index,
                "confirmation_required": status != "CONFIRMED",
                **({"confirmed_by_user_id": str(user.id)} if status == "CONFIRMED" else {}),
            },
        }
        evidence_rows.append(TenderEvidence(
            tenant_id=tenant.id,
            tender_id=tender.id,
            kind="SOURCE_DOCUMENT",
            subject=f"fuente-{index}.pdf",
            value={
                "source_role": "CONVOCATORIA",
                "requirement_candidates": [candidate],
            },
            source_uri=f"tenders/test/fuente-{index}.pdf",
            source_hash=source_hash,
            source_revision=1,
            status="ACTIVE",
            creado_por_id=user.id,
            actualizado_por_id=user.id,
        ))
    db_session.add_all(evidence_rows)
    await db_session.commit()

    class FakeTracker:
        def __init__(self, *_args, **_kwargs):
            self.stage_results = []
            self.final_result = None

        async def start(self, **_kwargs):
            return None

        async def begin_stage(self, *_args, **_kwargs):
            return None

        async def finish_stage(self, **kwargs):
            self.stage_results.append(kwargs)

        async def finish(self, status, **kwargs):
            self.final_result = {"status": status, **kwargs}

    trackers = []

    def make_tracker(*args, **kwargs):
        tracker = FakeTracker(*args, **kwargs)
        trackers.append(tracker)
        return tracker

    monkeypatch.setattr("app.services.procurement.service.PreparationRunTracker", make_tracker)
    service = ProcurementService(db_session, user)
    orchestrator_called = False

    async def fake_orchestrator_run(*_args, **_kwargs):
        nonlocal orchestrator_called
        orchestrator_called = True
        return {"findings": []}

    async def no_commit():
        return None

    service.orchestrator.run = fake_orchestrator_run
    service._commit = no_commit

    with pytest.raises(MegalodonException) as exc:
        await service.run(tender.id)

    assert exc.value.status_code == 409
    assert "sin confirmación humana" in str(exc.value).lower()
    assert trackers and trackers[0].final_result is not None
    assert trackers[0].final_result["status"] == "BLOCKED"
    assert trackers[0].final_result["failure_code"] == "REQUIREMENT_REVIEW_REQUIRED"
    assert not orchestrator_called, "The deterministic orchestrator must not run with a partially reviewed requirement set."



def test_requirement_confirmation_rejects_categories_outside_the_canonical_domain():
    from app.schemas.procurement.schemas import RequirementCandidateConfirmation

    base = {
        "candidate_id": "a" * 64,
        "evidence_id": str(uuid4()),
        "code": "REQ-016",
        "description": "Requisito revisado",
        "mandatory": True,
    }
    for unsupported in ("PROGRAMACION", "OTRO", "INVENTADA"):
        with pytest.raises(ValidationError):
            RequirementCandidateConfirmation.model_validate({**base, "category": unsupported})

    accepted = RequirementCandidateConfirmation.model_validate({**base, "category": "CALENDARIO"})
    assert accepted.category == "CALENDARIO"

@pytest.mark.asyncio
async def test_generic_evidence_write_cannot_forge_a_source_or_confirm_extracted_requirements(
    db_session, tenant_a_user,
):
    tenant, user = tenant_a_user
    expediente = make_expediente(tenant, user)
    db_session.add(expediente)
    await db_session.flush()

    tender = TenderPackage(
        tenant_id=tenant.id,
        expediente_id=expediente.id,
        identifier=f"TP-{uuid4().hex[:8]}",
        title="Guardia de fuente documental",
        jurisdiction_code="MX-FED-OBRA",
        current_revision=1,
    )
    db_session.add(tender)
    await db_session.commit()

    forged = EvidenceCreate.model_construct(
        kind="SOURCE_DOCUMENT",
        subject="bases-falsificadas.pdf",
        value={
            "source_role": "CONVOCATORIA",
            "requirement_candidates": [{
                "code": "REQ-FORGED",
                "description": "Candidato sin archivo fuente",
                "category": "TECNICO",
                "mandatory": True,
                "status": "CONFIRMED",
                "source_reference": {
                    "confirmation_required": False,
                    "confirmed_by_user_id": str(user.id),
                },
            }],
        },
        source_uri="tenders/fake/bases-falsificadas.pdf",
        source_hash="a" * 64,
        source_revision=1,
    )

    with pytest.raises(MegalodonException) as exc:
        await ProcurementService(db_session, user).add_evidence(tender.id, forged)

    assert exc.value.status_code == 422
    stored = await db_session.scalar(
        select(TenderEvidence).where(
            TenderEvidence.tender_id == tender.id,
            TenderEvidence.tenant_id == tenant.id,
            TenderEvidence.subject == "bases-falsificadas.pdf",
        )
    )
    assert stored is None

