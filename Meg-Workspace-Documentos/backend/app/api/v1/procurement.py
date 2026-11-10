from __future__ import annotations

from typing import Literal
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field

from fastapi import APIRouter, Depends, File, Form, Query, UploadFile, HTTPException, Header
from sqlalchemy.ext.asyncio import AsyncSession
from fastapi.responses import Response

from app.core.deps import get_current_user, get_db
from app.core.entitlements import requiere_rol
from app.models.user import UserRole
from app.models.procurement import TenderPackage
from app.models.user import User
from app.schemas.procurement.schemas import (
    ApprovalCreate, ArtifactCreate, EvidenceCreate, RequirementCreate, RevisionCreate, SemiAutoReviewPatch, TenderCreate,
    JurisdictionProfileCreate, LegalSourceCreate, LegalRuleCreate, JurisdictionPackCreate,
    RequirementCandidateConfirmation,
)
from app.services.procurement.service import ProcurementService
from app.services.procurement.artifact_policy import artifact_requires_signature, artifact_submission_eligible
from app.services.procurement.jobs import ProcurementJobService
from app.services.procurement.workspace import TenderWorkspaceService
from app.schemas.procurement.schemas import WorkspaceDocumentCreate, WorkspaceDocumentUpdate, WorkspaceDocumentRegenerate, WorkspaceLockPatch

router = APIRouter()

async def _read_upload_limited(file: UploadFile, max_bytes: int) -> bytes:
    if max_bytes <= 0:
        raise HTTPException(status_code=500, detail="Límite de archivo inválido.")
    if getattr(file, "size", None) is not None and file.size > max_bytes:
        raise HTTPException(status_code=413, detail="La fuente documental excede el límite configurado.")
    chunks: list[bytes] = []
    total = 0
    while True:
        chunk = await file.read(min(1024 * 1024, max_bytes - total + 1))
        if not chunk:
            break
        total += len(chunk)
        if total > max_bytes:
            raise HTTPException(status_code=413, detail="La fuente documental excede el límite configurado.")
        chunks.append(chunk)
    return b"".join(chunks)


@router.get("/catalog", response_model=dict)
async def procurement_catalog(db: AsyncSession = Depends(get_db), user: User = Depends(get_current_user)):
    return await ProcurementService(db, user).catalog()


@router.post("/jurisdiction-packs", response_model=dict, status_code=201, dependencies=[Depends(requiere_rol(UserRole.ADMIN, UserRole.SUPERADMIN))])
async def install_jurisdiction_pack(data: JurisdictionPackCreate, db: AsyncSession = Depends(get_db), user: User = Depends(get_current_user)):
    row = await ProcurementService(db, user).install_jurisdiction_pack(data)
    return {"id": str(row.id), "code": row.code, "authority": row.authority, "government_level": row.government_level, "version": row.profile_version}

@router.post("/jurisdiction-profiles", response_model=dict, status_code=201, dependencies=[Depends(requiere_rol(UserRole.ADMIN, UserRole.SUPERADMIN))])
async def create_jurisdiction_profile(data: JurisdictionProfileCreate, db: AsyncSession = Depends(get_db), user: User = Depends(get_current_user)):
    row = await ProcurementService(db, user).create_jurisdiction_profile(data)
    return {"id": str(row.id), "code": row.code, "authority": row.authority, "government_level": row.government_level, "version": row.profile_version}


@router.post("/legal-sources", response_model=dict, status_code=201, dependencies=[Depends(requiere_rol(UserRole.ADMIN, UserRole.SUPERADMIN))])
async def create_legal_source(data: LegalSourceCreate, db: AsyncSession = Depends(get_db), user: User = Depends(get_current_user)):
    row = await ProcurementService(db, user).create_legal_source(data)
    return {"id": str(row.id), "title": row.title, "version": row.version, "content_hash": row.content_hash}


@router.post("/legal-rules", response_model=dict, status_code=201, dependencies=[Depends(requiere_rol(UserRole.ADMIN, UserRole.SUPERADMIN))])
async def create_legal_rule(data: LegalRuleCreate, db: AsyncSession = Depends(get_db), user: User = Depends(get_current_user)):
    row = await ProcurementService(db, user).create_legal_rule(data)
    return {"id": str(row.id), "rule_id": row.rule_id, "version": row.rule_version, "jurisdiction_code": row.jurisdiction_code}
@router.post("/tenders", response_model=dict, status_code=201, dependencies=[Depends(requiere_rol(UserRole.TECNICO, UserRole.ADMIN, UserRole.SUPERADMIN))])
async def create_tender(data: TenderCreate, db: AsyncSession = Depends(get_db), user: User = Depends(get_current_user)):
    tender = await ProcurementService(db, user).create(data)
    return _tender(tender)


@router.get("/tenders/{tender_id}", response_model=dict)
async def get_tender(tender_id: UUID, db: AsyncSession = Depends(get_db), user: User = Depends(get_current_user)):
    tender = await ProcurementService(db, user)._get(tender_id)
    return _tender(tender)


@router.get("/tenders/{tender_id}/artifacts", response_model=list[dict])
async def list_tender_artifacts(tender_id: UUID, db: AsyncSession = Depends(get_db), user: User = Depends(get_current_user)):
    rows = await ProcurementService(db, user).list_artifacts(tender_id)
    return [{
        "id": str(row.id),
        "code": row.artifact_code,
        "artifact_code": row.artifact_code,
        "name": row.name,
        "media_type": row.media_type,
        "version": row.version,
        "status": row.status,
        "content_hash": row.content_hash,
        "signature": (row.artifact_metadata or {}).get("signature"),
        "submission_eligible": artifact_submission_eligible(row),
        "signature_required": artifact_requires_signature(row),
        "internal_workspace_artifact": bool((row.artifact_metadata or {}).get("internal_workspace_artifact")) or row.artifact_code == "QA-REPORT",
    } for row in rows]


@router.get("/tenders", response_model=list[dict])
async def list_tenders(
    state: str | None = Query(default=None),
    jurisdiction_code: str | None = Query(default=None),
    expediente_id: UUID | None = Query(default=None),
    offset: int = Query(default=0, ge=0),
    limit: int = Query(default=100, ge=1, le=500),
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
):
    return await ProcurementService(db, user).list_tenders(
        state=state, jurisdiction_code=jurisdiction_code, expediente_id=expediente_id, offset=offset, limit=limit
    )



@router.get("/tenders/{tender_id}/readiness", response_model=dict)
async def tender_readiness(tender_id: UUID, db: AsyncSession = Depends(get_db), user: User = Depends(get_current_user)):
    return await ProcurementService(db, user).readiness(tender_id)

@router.post("/tenders/{tender_id}/sources", response_model=dict, status_code=201, dependencies=[Depends(requiere_rol(UserRole.TECNICO, UserRole.ADMIN, UserRole.SUPERADMIN))])
async def ingest_source(tender_id: UUID, file: UploadFile = File(...), source_role: str = Form("CONVOCATORIA"), db: AsyncSession = Depends(get_db), user: User = Depends(get_current_user), _role: None = Depends(requiere_rol(UserRole.TECNICO, UserRole.ADMIN, UserRole.SUPERADMIN))):
    from app.config import get_settings
    content = await _read_upload_limited(file, get_settings().TENDER_SOURCE_MAX_FILE_SIZE_MB * 1024 * 1024)
    return await ProcurementService(db, user).ingest_source(tender_id, file.filename or "source", file.content_type or "application/octet-stream", content, source_role=source_role)

@router.get("/tenders/{tender_id}/requirements/candidates", response_model=list[dict])
async def requirement_candidates(tender_id: UUID, db: AsyncSession = Depends(get_db), user: User = Depends(get_current_user)):
    return await ProcurementService(db, user).requirement_candidates(tender_id)

@router.post("/tenders/{tender_id}/requirements/candidates/confirm", response_model=list[dict], dependencies=[Depends(requiere_rol(UserRole.TECNICO, UserRole.ADMIN, UserRole.SUPERADMIN))])
async def confirm_requirement_candidates(tender_id: UUID, data: list[RequirementCandidateConfirmation], db: AsyncSession = Depends(get_db), user: User = Depends(get_current_user)):
    return await ProcurementService(db, user).confirm_requirement_candidates(tender_id, data)

@router.post("/tenders/{tender_id}/requirements/derive", response_model=list[dict], dependencies=[Depends(requiere_rol(UserRole.TECNICO, UserRole.ADMIN, UserRole.SUPERADMIN))])
async def derive_requirements(tender_id: UUID, db: AsyncSession = Depends(get_db), user: User = Depends(get_current_user)):
    rows = await ProcurementService(db, user).derive_requirements(tender_id)
    return [{"id": str(r.id), "code": r.code, "category": r.category, "description": r.description, "mandatory": r.mandatory, "status": r.status, "source_reference": r.source_reference} for r in rows]


@router.post("/tenders/{tender_id}/requirements", response_model=dict, status_code=201)
async def add_requirement(tender_id: UUID, data: RequirementCreate, db: AsyncSession = Depends(get_db), user: User = Depends(get_current_user), _role: None = Depends(requiere_rol(UserRole.TECNICO, UserRole.ADMIN, UserRole.SUPERADMIN))):
    row = await ProcurementService(db, user).add_requirement(tender_id, data)
    return {"id": str(row.id), "code": row.code, "status": row.status}


@router.post("/tenders/{tender_id}/requirements/{requirement_id}/rule/validate", response_model=dict, dependencies=[Depends(requiere_rol(UserRole.TECNICO, UserRole.ADMIN, UserRole.SUPERADMIN))])
async def validate_requirement_rule(tender_id: UUID, requirement_id: UUID, data: dict = {}, db: AsyncSession = Depends(get_db), user: User = Depends(get_current_user)):
    return await ProcurementService(db, user).validate_requirement_rule(
        tender_id, requirement_id, list(data.get("test_cases") or [])
    )


@router.post("/tenders/{tender_id}/requirements/{requirement_id}/rule/versions", response_model=dict, status_code=201, dependencies=[Depends(requiere_rol(UserRole.TECNICO, UserRole.ADMIN, UserRole.SUPERADMIN))])
async def create_requirement_rule_version(tender_id: UUID, requirement_id: UUID, data: dict, db: AsyncSession = Depends(get_db), user: User = Depends(get_current_user)):
    definition = dict(data.get("definition") or {})
    test_cases = list(data.get("test_cases") or [])
    return await ProcurementService(db, user).create_requirement_rule_version(tender_id, requirement_id, definition, test_cases)


@router.post("/tenders/{tender_id}/evidence", response_model=dict, status_code=201)
async def add_evidence(tender_id: UUID, data: EvidenceCreate, db: AsyncSession = Depends(get_db), user: User = Depends(get_current_user), _role: None = Depends(requiere_rol(UserRole.TECNICO, UserRole.ADMIN, UserRole.SUPERADMIN))):
    row = await ProcurementService(db, user).add_evidence(tender_id, data)
    return {"id": str(row.id), "kind": row.kind, "subject": row.subject}


@router.post("/tenders/{tender_id}/evidence/{evidence_id}/link", response_model=dict, status_code=201)
async def link_evidence(tender_id: UUID, evidence_id: UUID, requirement_id: UUID | None = None, artifact_id: UUID | None = None, relation: str = "SUPPORTS", db: AsyncSession = Depends(get_db), user: User = Depends(get_current_user), _role: None = Depends(requiere_rol(UserRole.TECNICO, UserRole.ADMIN, UserRole.SUPERADMIN))):
    row = await ProcurementService(db, user).link_evidence(tender_id, evidence_id, requirement_id, artifact_id, relation)
    return {"id": str(row.id), "relation": row.relation}


@router.post("/tenders/{tender_id}/artifacts", response_model=dict, status_code=201)
async def add_artifact(tender_id: UUID, data: ArtifactCreate, db: AsyncSession = Depends(get_db), user: User = Depends(get_current_user), _role: None = Depends(requiere_rol(UserRole.TECNICO, UserRole.ADMIN, UserRole.SUPERADMIN))):
    row = await ProcurementService(db, user).add_artifact(tender_id, data)
    return {"id": str(row.id), "artifact_code": row.artifact_code, "version": row.version}


@router.post("/tenders/{tender_id}/revisions", response_model=dict, status_code=201)
async def create_revision(tender_id: UUID, data: RevisionCreate, db: AsyncSession = Depends(get_db), user: User = Depends(get_current_user), _role: None = Depends(requiere_rol(UserRole.TECNICO, UserRole.ADMIN, UserRole.SUPERADMIN))):
    row = await ProcurementService(db, user).create_revision(tender_id, data)
    return {"id": str(row.id), "revision": row.revision, "reason": row.reason}



@router.post("/tenders/{tender_id}/jurisdiction", response_model=dict, dependencies=[Depends(requiere_rol(UserRole.TECNICO, UserRole.ADMIN, UserRole.SUPERADMIN))])
async def resolve_jurisdiction(tender_id: UUID, db: AsyncSession = Depends(get_db), user: User = Depends(get_current_user)):
    tender = await ProcurementService(db, user).resolve_jurisdiction(tender_id)
    return _tender(tender)


@router.post(
    "/tenders/{tender_id}/semi-auto-review",
    response_model=dict,
    dependencies=[Depends(requiere_rol(UserRole.TECNICO, UserRole.ADMIN, UserRole.SUPERADMIN))],
)
async def apply_semi_auto_review(
    tender_id: UUID,
    body: SemiAutoReviewPatch,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
):
    """Persiste revisión humana del panel: authority/object/checklist de formatos.

    No modifica partidas del presupuesto. Habilita compile con criterio semi-auto.
    """
    return await ProcurementService(db, user).apply_semi_auto_review(tender_id, body)

@router.post(
    "/tenders/{tender_id}/hydrate-from-presupuesto",
    response_model=dict,
    dependencies=[Depends(requiere_rol(UserRole.TECNICO, UserRole.ADMIN, UserRole.SUPERADMIN))],
)
async def hydrate_from_presupuesto(
    tender_id: UUID,
    presupuesto_id: UUID | None = None,
    overwrite_economic: bool = True,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
):
    """Semi-auto: adjunta presupuesto programable del expediente al modelo canónico del tender.

    El catálogo/APU/montos salen de MotorCosteo vía Presupuesto; no se inventan.
    El usuario puede pasar presupuesto_id concreto o se toma el más usable del expediente.
    """
    return await ProcurementService(db, user).hydrate_from_presupuesto(
        tender_id,
        presupuesto_id=presupuesto_id,
        overwrite_economic=overwrite_economic,
    )


@router.post("/tenders/{tender_id}/compile", response_model=list[dict], dependencies=[Depends(requiere_rol(UserRole.TECNICO, UserRole.ADMIN, UserRole.SUPERADMIN))])
async def compile_artifacts(tender_id: UUID, db: AsyncSession = Depends(get_db), user: User = Depends(get_current_user)):
    rows = await ProcurementService(db, user).compile_artifacts(tender_id)
    return [{"id": str(r.id), "code": r.artifact_code, "version": r.version, "storage_path": r.storage_path, "content_hash": r.content_hash} for r in rows]

@router.post("/tenders/{tender_id}/jobs/run", response_model=dict, status_code=202, dependencies=[Depends(requiere_rol(UserRole.TECNICO, UserRole.ADMIN, UserRole.SUPERADMIN))])
async def enqueue_run_tender(
    tender_id: UUID,
    idempotency_key: str | None = Header(default=None, alias="Idempotency-Key", max_length=128),
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
):
    tender = await ProcurementService(db, user)._get(tender_id)
    job, replay = await ProcurementJobService(db, user).create_or_replay(tender, "RUN", idempotency_key)
    return {"job_id": str(job.id), "task_id": job.task_id, "status": job.status, "progress": job.progress, "idempotent_replay": replay}

@router.post("/tenders/{tender_id}/jobs/compile", response_model=dict, status_code=202, dependencies=[Depends(requiere_rol(UserRole.TECNICO, UserRole.ADMIN, UserRole.SUPERADMIN))])
async def enqueue_compile_tender(
    tender_id: UUID,
    idempotency_key: str | None = Header(default=None, alias="Idempotency-Key", max_length=128),
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
):
    tender = await ProcurementService(db, user)._get(tender_id)
    job, replay = await ProcurementJobService(db, user).create_or_replay(tender, "COMPILE", idempotency_key)
    return {"job_id": str(job.id), "task_id": job.task_id, "status": job.status, "progress": job.progress, "idempotent_replay": replay}

@router.get("/jobs/{job_id}", response_model=dict)
async def get_procurement_job(job_id: UUID, db: AsyncSession = Depends(get_db), user: User = Depends(get_current_user)):
    job = await ProcurementJobService(db, user).get(job_id)
    return {
        "job_id": str(job.id), "tender_id": str(job.tender_id), "kind": job.kind, "status": job.status,
        "task_id": job.task_id, "progress": job.progress, "result": job.result,
        "error_code": job.error_code, "error_message": job.error_message,
        "started_at": job.started_at.isoformat() if job.started_at else None,
        "finished_at": job.finished_at.isoformat() if job.finished_at else None,
    }

@router.post("/tenders/{tender_id}/run", response_model=dict, dependencies=[Depends(requiere_rol(UserRole.TECNICO, UserRole.ADMIN, UserRole.SUPERADMIN))])
async def run_tender(tender_id: UUID, db: AsyncSession = Depends(get_db), user: User = Depends(get_current_user)):
    return await ProcurementService(db, user).run(tender_id)


@router.get("/tenders/{tender_id}/preparation-runs", response_model=dict)
async def preparation_history(tender_id: UUID, db: AsyncSession = Depends(get_db), user: User = Depends(get_current_user)):
    return await ProcurementService(db, user).preparation_history(tender_id)


@router.get("/tenders/{tender_id}/approvals/manifest", response_model=dict, dependencies=[Depends(requiere_rol(UserRole.REVISOR, UserRole.ADMIN, UserRole.SUPERADMIN))])
async def preview_approval_manifest(tender_id: UUID, db: AsyncSession = Depends(get_db), user: User = Depends(get_current_user)):
    return await ProcurementService(db, user).approval_manifest_preview(tender_id)


@router.get("/tenders/{tender_id}/artifacts/{artifact_id}/original", response_model=dict, dependencies=[Depends(requiere_rol(UserRole.REVISOR, UserRole.ADMIN, UserRole.SUPERADMIN))])
async def download_original_artifact(tender_id: UUID, artifact_id: UUID, db: AsyncSession = Depends(get_db), user: User = Depends(get_current_user)):
    return await ProcurementService(db, user).original_download_url(tender_id, artifact_id)


@router.post("/tenders/{tender_id}/approvals", response_model=dict, status_code=201, dependencies=[Depends(requiere_rol(UserRole.REVISOR, UserRole.ADMIN, UserRole.SUPERADMIN))])
async def approve_tender(tender_id: UUID, data: ApprovalCreate, db: AsyncSession = Depends(get_db), user: User = Depends(get_current_user)):
    row = await ProcurementService(db, user).approval(tender_id, data)
    return {"id": str(row.id), "decision": row.decision, "revision": row.revision,
            "artifact_manifest_sha256": row.artifact_manifest_hash}


@router.post("/tenders/{tender_id}/artifacts/{artifact_id}/sign", response_model=dict, dependencies=[Depends(requiere_rol(UserRole.REVISOR, UserRole.ADMIN, UserRole.SUPERADMIN))])
async def sign_artifact(
    tender_id: UUID, artifact_id: UUID,
    certificado_cer: UploadFile = File(...), certificado_key: UploadFile = File(...),
    password: str = Form(...), razon: str = Form("Firma de artefacto de proposición"),
    ubicacion: str = Form("México"), usar_tsa: bool = Form(True), tsa_url: str | None = Form(None),
    db: AsyncSession = Depends(get_db), user: User = Depends(get_current_user),
    idempotency_key: str = Header(..., alias="Idempotency-Key", min_length=16, max_length=128),
    _role: None = Depends(requiere_rol(UserRole.REVISOR, UserRole.ADMIN, UserRole.SUPERADMIN)),
):
    from app.config import get_settings
    service = ProcurementService(db, user)
    max_bytes = 2 * 1024 * 1024  # FIEL certificate/key files are small; do not reuse document upload limits.
    certificado_cer_bytes = await _read_upload_limited(certificado_cer, max_bytes)
    certificado_key_bytes = await _read_upload_limited(certificado_key, max_bytes)
    return await service.sign_artifact(
        tender_id=tender_id, artifact_id=artifact_id,
        certificado_cer=certificado_cer_bytes, certificado_key=certificado_key_bytes,
        password=password, razon=razon, ubicacion=ubicacion, usar_tsa=usar_tsa, tsa_url=tsa_url, idempotency_key=idempotency_key,
    )


@router.post("/tenders/{tender_id}/submission", response_model=dict, dependencies=[Depends(requiere_rol(UserRole.REVISOR, UserRole.ADMIN, UserRole.SUPERADMIN))])
async def build_submission(tender_id: UUID, idempotency_key: str | None = Header(default=None, alias="Idempotency-Key", max_length=128), db: AsyncSession = Depends(get_db), user: User = Depends(get_current_user)):
    row = await ProcurementService(db, user).submission(tender_id, idempotency_key=idempotency_key)
    return {"id": str(row.id), "status": row.status, "package_hash": row.package_hash, "manifest": row.manifest}


@router.get("/tenders/{tender_id}/submission/download", response_model=dict, dependencies=[Depends(requiere_rol(UserRole.TECNICO, UserRole.REVISOR, UserRole.ADMIN, UserRole.SUPERADMIN))])
async def download_submission(tender_id: UUID, db: AsyncSession = Depends(get_db), user: User = Depends(get_current_user)):
    return await ProcurementService(db, user).submission_download_url(tender_id)


@router.post("/tenders/{tender_id}/submission/receipt", response_model=dict)
async def register_submission_receipt(
    tender_id: UUID, portal_code: str, receipt_reference: str, receipt_file: UploadFile = File(...),
    db: AsyncSession = Depends(get_db), user: User = Depends(get_current_user),
    _role: None = Depends(requiere_rol(UserRole.REVISOR, UserRole.ADMIN, UserRole.SUPERADMIN)),
):
    from app.config import get_settings
    service = ProcurementService(db, user)
    receipt_content = await _read_upload_limited(receipt_file, get_settings().TENDER_SOURCE_MAX_FILE_SIZE_MB * 1024 * 1024)
    return await service.register_submission_receipt(
        tender_id=tender_id, portal_code=portal_code, receipt_reference=receipt_reference,
        filename=receipt_file.filename or "receipt", content_type=receipt_file.content_type or "application/octet-stream",
        content=receipt_content,
    )



class RecommendProcedureBody(BaseModel):
    """Validates the procedure declared in a published solicitation for a bidder."""
    model_config = ConfigDict(extra="forbid")

    jurisdiction_code: str
    monto: float = Field(..., gt=0)
    es_obra_publica: bool = True
    ejercicio_fiscal: int = 2026
    excepcion_legal: str | None = None
    justificacion_excepcion: str | None = None
    investigacion_mercado_realizada: bool = False
    flow_mode: Literal["LICITANTE"] = "LICITANTE"
    procedure_type_declared: str | None = None


@router.post("/recommend-procedure")
async def recommend_procedure(
    body: RecommendProcedureBody,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
    _role: None = Depends(requiere_rol(UserRole.REVISOR, UserRole.ADMIN, UserRole.SUPERADMIN)),
):
    return await ProcurementService(db, user).recommend_procedure(
        jurisdiction_code=body.jurisdiction_code,
        monto=body.monto,
        es_obra_publica=body.es_obra_publica,
        presupuesto_dependencia_miles=None,
        ejercicio_fiscal=body.ejercicio_fiscal,
        excepcion_legal=body.excepcion_legal,
        justificacion_excepcion=body.justificacion_excepcion,
        investigacion_mercado_realizada=body.investigacion_mercado_realizada,
        tender_id=None,
        flow_mode="LICITANTE",
        procedure_type_declared=body.procedure_type_declared,
    )


class DerivePropositionStructureBody(BaseModel):
    jurisdiction_code: str | None = None
    procedure_type: str | None = None
    evaluation_criterion: str | None = None
    legal_regime: str | None = "LOPSRM"
    case_pack_code: str | None = None
    include_optional: bool = True


class CongruenceCheckBody(BaseModel):
    carta_monto: float | None = None
    catalogo_total: float | None = None
    programa_montos_total: float | None = None
    explosion_cd_total: float | None = None
    tolerance: float = 0.01


@router.post("/derive-proposition-structure")
async def derive_proposition_structure(
    body: DerivePropositionStructureBody,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
    _role: None = Depends(requiere_rol(UserRole.TECNICO, UserRole.REVISOR, UserRole.ADMIN, UserRole.SUPERADMIN)),
):
    """Checklist configurado en DB para la dependencia seleccionada."""
    if not body.jurisdiction_code:
        raise HTTPException(status_code=422, detail="jurisdiction_code es obligatorio para cargar la estructura de la dependencia.")
    from app.engines.procurement.proposition_structure import derive_proposition_structure as derive
    return await derive(
        db, tenant_id=user.tenant_id, jurisdiction_code=body.jurisdiction_code,
        procedure_type=body.procedure_type,
        evaluation_criterion=body.evaluation_criterion,
        legal_regime=body.legal_regime,
        case_pack_code=body.case_pack_code,
        include_optional=body.include_optional,
    )


@router.post("/economic-congruence-check")
async def economic_congruence_check(
    body: CongruenceCheckBody,
    user: User = Depends(get_current_user),
    _role: None = Depends(requiere_rol(UserRole.TECNICO, UserRole.REVISOR, UserRole.ADMIN, UserRole.SUPERADMIN)),
):
    """Congruencia de montos económicos (carta/catálogo/programas/explosión). Sin APU."""
    from app.engines.procurement.proposition_structure import congruence_check
    return congruence_check(
        carta_monto=body.carta_monto,
        catalogo_total=body.catalogo_total,
        programa_montos_total=body.programa_montos_total,
        explosion_cd_total=body.explosion_cd_total,
        tolerance=body.tolerance,
    )


@router.get("/tenders/{tender_id}/workspace/documents", response_model=list[dict])
async def workspace_documents(tender_id: UUID, db: AsyncSession = Depends(get_db), user: User = Depends(get_current_user)):
    rows = await TenderWorkspaceService(db, user).list_documents(tender_id)
    return [_document(row) for row in rows]

@router.post("/tenders/{tender_id}/workspace/documents", response_model=dict, status_code=201, dependencies=[Depends(requiere_rol(UserRole.TECNICO, UserRole.ADMIN, UserRole.SUPERADMIN))])
async def workspace_create_document(tender_id: UUID, data: WorkspaceDocumentCreate, db: AsyncSession = Depends(get_db), user: User = Depends(get_current_user)):
    row = await TenderWorkspaceService(db, user).open_or_create(tender_id, data.artifact_code, data.name, data.media_type)
    return _document(row)

@router.get("/tenders/{tender_id}/workspace/document-templates")
async def workspace_document_templates(tender_id: UUID, db: AsyncSession = Depends(get_db),
                                       user: User = Depends(get_current_user)):
    return await TenderWorkspaceService(db, user).document_templates(tender_id)


@router.get("/tenders/{tender_id}/workspace/documents/{document_id}", response_model=dict)
async def workspace_get_document(tender_id: UUID, document_id: UUID, db: AsyncSession = Depends(get_db), user: User = Depends(get_current_user)):
    return _document(await TenderWorkspaceService(db, user).get_document(tender_id, document_id))

@router.put("/tenders/{tender_id}/workspace/documents/{document_id}", response_model=dict, dependencies=[Depends(requiere_rol(UserRole.TECNICO, UserRole.ADMIN, UserRole.SUPERADMIN))])
async def workspace_update_document(tender_id: UUID, document_id: UUID, data: WorkspaceDocumentUpdate, db: AsyncSession = Depends(get_db), user: User = Depends(get_current_user)):
    return _document(await TenderWorkspaceService(db, user).update_document(tender_id, document_id, content_text=data.content_text, content_model=data.content_model, expected_row_version=data.expected_row_version))

class WorkspaceRenderRequest(BaseModel):
    expected_row_version: int = Field(ge=1)
    values: dict[str, str] = Field(max_length=10)
    template_token: str | None = Field(default=None, min_length=64, max_length=64)


@router.get("/tenders/{tender_id}/workspace/documents/{document_id}/editor")
async def workspace_editor(tender_id: UUID, document_id: UUID, db: AsyncSession = Depends(get_db),
                           user: User = Depends(get_current_user)):
    return await TenderWorkspaceService(db, user).editor(tender_id, document_id)


@router.post("/tenders/{tender_id}/workspace/documents/{document_id}/render",
             dependencies=[Depends(requiere_rol(UserRole.TECNICO, UserRole.ADMIN, UserRole.SUPERADMIN))])
async def workspace_render(tender_id: UUID, document_id: UUID, data: WorkspaceRenderRequest,
                           db: AsyncSession = Depends(get_db), user: User = Depends(get_current_user)):
    return await TenderWorkspaceService(db, user).save_rendered(
        tender_id, document_id, values=data.values, expected_row_version=data.expected_row_version,
        template_token=data.template_token,
    )


@router.get("/tenders/{tender_id}/workspace/documents/{document_id}/versions/{version}/file")
async def workspace_revision_file(tender_id: UUID, document_id: UUID, version: int, download: bool = False,
                                  db: AsyncSession = Depends(get_db), user: User = Depends(get_current_user)):
    content, media = await TenderWorkspaceService(db, user).revision_file(tender_id, document_id, version)
    extension = {
        "application/pdf": "pdf",
        "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet": "xlsx",
        "application/vnd.openxmlformats-officedocument.wordprocessingml.document": "docx",
    }[media]
    disposition = "attachment" if download or extension != "pdf" else "inline"
    return Response(content, media_type=media, headers={
        "Content-Disposition": f'{disposition}; filename="anexo-{document_id}-v{version}.{extension}"',
        "Cache-Control": "private, no-store", "X-Content-Type-Options": "nosniff",
    })


@router.get("/tenders/{tender_id}/workspace/documents/{document_id}/history", response_model=list[dict])
async def workspace_document_history(tender_id: UUID, document_id: UUID, db: AsyncSession = Depends(get_db), user: User = Depends(get_current_user)):
    rows = await TenderWorkspaceService(db, user).history(tender_id, document_id)
    return [{"id":str(r.id),"version":r.version,"operation":r.operation,"tender_revision":r.tender_revision,"human_modified":r.human_modified,"content_text":r.content_text,"content_model":r.content_model,"metadata":{k: v for k, v in (r.revision_metadata or {}).items() if k not in {"workspace_pdf", "workspace_docx", "workspace_xlsx"}},"created_at":r.created_at.isoformat()} for r in rows]

@router.post("/tenders/{tender_id}/workspace/documents/{document_id}/regenerate", response_model=dict, dependencies=[Depends(requiere_rol(UserRole.TECNICO, UserRole.ADMIN, UserRole.SUPERADMIN))])
async def workspace_regenerate_document(tender_id: UUID, document_id: UUID, data: WorkspaceDocumentRegenerate, db: AsyncSession = Depends(get_db), user: User = Depends(get_current_user)):
    return _document(await TenderWorkspaceService(db, user).regenerate(tender_id, document_id, generated_text=data.generated_text, generated_model=data.generated_model, expected_row_version=data.expected_row_version))

@router.patch("/tenders/{tender_id}/workspace/documents/{document_id}/lock", response_model=dict, dependencies=[Depends(requiere_rol(UserRole.REVISOR, UserRole.ADMIN, UserRole.SUPERADMIN))])
async def workspace_lock_document(tender_id: UUID, document_id: UUID, data: WorkspaceLockPatch, db: AsyncSession = Depends(get_db), user: User = Depends(get_current_user)):
    return _document(await TenderWorkspaceService(db, user).lock_document(tender_id, document_id, data.locked))

@router.post("/tenders/{tender_id}/freeze", response_model=dict, dependencies=[Depends(requiere_rol(UserRole.REVISOR, UserRole.ADMIN, UserRole.SUPERADMIN))])
async def freeze_tender(tender_id: UUID, db: AsyncSession = Depends(get_db), user: User = Depends(get_current_user)):
    tender = await ProcurementService(db, user).freeze(tender_id)
    return _tender(tender)


def _document(row) -> dict:
    return {"id":str(row.id),"tender_id":str(row.tender_id),"artifact_code":row.artifact_code,"name":row.name,"media_type":row.media_type,"content_text":row.content_text,"content_model":row.content_model,"status":row.status,"version":row.version,"tender_revision":row.tender_revision,"generated_from_revision":row.generated_from_revision,"generated_model_hash":row.generated_model_hash,"human_modified":row.human_modified,"locked":row.locked,"source_evidence_ids":row.source_evidence_ids,"requirement_ids":row.requirement_ids,"data_dependencies":row.data_dependencies,"warnings":row.warnings,"last_conflict":row.last_conflict,"row_version":row.row_version}

def _tender(tender: TenderPackage) -> dict:
    return {
        "id": str(tender.id), "expediente_id": str(tender.expediente_id), "identifier": tender.identifier,
        "title": tender.title, "state": tender.state, "review_state": tender.review_state, "jurisdiction_code": tender.jurisdiction_code,
        "procedure_type": tender.procedure_type, "contract_type": tender.contract_type,
        "evaluation_criterion": tender.evaluation_criterion, "project_type": tender.project_type,
        "scope_scale": tender.scope_scale, "case_pack_code": tender.case_pack_code,
        "funding_source": tender.funding_source, "object_class": tender.object_class, "legal_regime": tender.legal_regime,
        "current_revision": tender.current_revision, "frozen": tender.frozen,
        # The canonical model is the procurement workspace state. It is safe to
        # expose here because _get() has already enforced tenant ownership.
        "canonical_model": tender.canonical_model or {},
        "source_manifest": tender.source_manifest or {},
        "model_hash": __import__("hashlib").sha256(__import__("json").dumps(tender.canonical_model, sort_keys=True, default=str).encode()).hexdigest(),
    }
