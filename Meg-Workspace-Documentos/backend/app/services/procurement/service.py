from __future__ import annotations

import copy
from datetime import datetime, timezone
from hashlib import sha256
import json
import structlog
from typing import Any
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.orm import selectinload
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm.exc import StaleDataError
from sqlalchemy.exc import IntegrityError
from pydantic import ValidationError

from app.core.errors import ErrorCode, MegalodonException
from app.config import get_settings
from app.models.expediente import Documento, ExpedienteObra
from app.models.presupuesto import Presupuesto, Partida, Concepto
from app.models.programacion import ProgramaObra
from app.models.procurement import (
    PreparationRunStatus,
    ArtifactStatus,
    EvidenceKind,
    RequirementStatus,
    SubmissionPackage,
    TenderApproval,
    TenderArtifact,
    TenderEvidence,
    TenderRuleDefinition,
    TenderEvidenceLink,
    TenderPackage,
    JurisdictionProfile, LegalSource, LegalRule, LegalArticle,
    TenderRequirement,
    TenderRevision,
    TenderState,
    TenderValidationRun, JurisdictionInheritance, TenderDocument, TenderDocumentRevision,
    TenderDependency,
)
from app.models.user import User
from app.schemas.procurement.schemas import (
    ApprovalCreate,
    ArtifactCreate,
    EvidenceCreate,
    RequirementCreate,
    RevisionCreate,
    SemiAutoReviewPatch,
    TenderCreate, JurisdictionPackCreate, JurisdictionProfileCreate, LegalSourceCreate, LegalRuleCreate,
    RequirementCandidateConfirmation,
)
from app.engines.procurement.orchestrator import TenderOrchestrator
from app.engines.procurement.compiler import ProcurementArtifactCompiler
from app.engines.procurement.jurisdiction import JurisdictionResolver
from app.integrations.supabase_storage import storage_documentos, storage_exportaciones
from app.services.firma_service import FirmaService
from app.engines.procurement.source_extract import TenderSourceExtractor
from app.engines.procurement.lifecycle import TenderLifecycle, InvalidTenderTransition
from app.engines.procurement.requirements import ProcurementRequirementMapper
from app.engines.procurement.catalog import case_packs_for_jurisdiction, get_case_pack, get_configured_case_pack, load_case_packs, load_domain_map, build_catalog_payload
from app.engines.procurement.contract_policy import ContractPolicyError
from app.engines.procurement.rules import DeterministicRuleCompiler, RuleCompilationError
from app.services.procurement.storage_guard import ProcurementStorageGuard
from app.services.procurement.artifact_policy import artifact_requires_signature, artifact_submission_eligible
from app.services.procurement.preparation_runs import PreparationRunTracker, PIPELINE_VERSION
from app.engines.procurement.domain_contracts import snapshot_source_is_current, source_revision_token
from app.engines.procurement.proposition_bridge import build_economic_block, hydrate_canonical_from_presupuesto
from app.engines.procurement.format_field_map import load_format_catalog, normalize_format_code
from app.engines.procurement.workspace_overrides import model_with_workspace_overrides
from app.models.bim import ModeloBIM
from app.models.topografia import CalculoVolumen


logger = structlog.get_logger()


def _requirement_candidate_identity(evidence_id: UUID | str, evidence_hash: str | None, candidate: dict[str, Any]) -> str:
    """Stable, source-bound identity that does not change when a human edits the description."""
    reference = candidate.get("source_reference")
    if not isinstance(reference, dict):
        reference = {}
    anchor_fields = (
        "source_hash", "document", "page", "section", "table", "row", "cell",
        "field", "line_start", "line_end", "text_original",
    )
    identity = {
        "evidence_id": str(evidence_id),
        "evidence_hash": str(evidence_hash or ""),
        "code": str(candidate.get("code") or "").strip(),
        "source_anchor": {field: reference.get(field) for field in anchor_fields},
    }
    return sha256(json.dumps(identity, sort_keys=True, separators=(",", ":"), default=str).encode()).hexdigest()


def _requirement_definition_signature(value: Any) -> str:
    def read(name: str, default: Any = None) -> Any:
        return value.get(name, default) if isinstance(value, dict) else getattr(value, name, default)
    return json.dumps({
        "category": str(read("category") or "").strip().upper(),
        "description": str(read("description") or "").strip(),
        "mandatory": read("mandatory"),
        "condition": read("condition") or {},
        "evidence_required": read("evidence_required") or [],
        "artifact_required": read("artifact_required") or [],
        "severity": str(read("severity") or "BLOCKER").strip().upper(),
        "validator_code": read("validator_code"),
        "approver_role": read("approver_role"),
    }, sort_keys=True, separators=(",", ":"), default=str)


def _merge_requirement_provenance(current: dict[str, Any] | None, incoming: dict[str, Any] | None) -> dict[str, Any]:
    current_ref = dict(current) if isinstance(current, dict) else {}
    incoming_ref = dict(incoming) if isinstance(incoming, dict) else {}

    def records(reference: dict[str, Any]) -> list[dict[str, Any]]:
        supporting = reference.get("supporting_sources")
        if isinstance(supporting, list):
            return [dict(item) for item in supporting if isinstance(item, dict)]
        return [{key: value for key, value in reference.items() if key != "supporting_sources"}] if reference else []

    unique: dict[str, dict[str, Any]] = {}
    for source in records(current_ref) + records(incoming_ref):
        key = json.dumps(source, sort_keys=True, separators=(",", ":"), default=str)
        unique.setdefault(key, source)
    if not unique:
        return current_ref or incoming_ref
    base = current_ref or incoming_ref
    return {**base, "supporting_sources": list(unique.values())}


_TENDER_STATES_REQUIRING_NEW_REVISION = frozenset({
    TenderState.CROSS_VALIDATED.value,
    TenderState.QA_READY.value,
    TenderState.READY_FOR_HUMAN_REVIEW.value,
    TenderState.HUMAN_APPROVAL.value,
    TenderState.SIGNED.value,
    TenderState.SUBMISSION_READY.value,
    TenderState.SUBMITTED.value,
    TenderState.ARCHIVED.value,
    TenderState.BLOCKED.value,
    TenderState.SUPERSEDED.value,
    TenderState.CANCELLED.value,
    TenderState.EXPIRED.value,
})


def _ensure_tender_mutation_allowed(
    tender: TenderPackage,
    operation: str,
    *,
    allow_cross_validated: bool = False,
) -> None:
    if tender.frozen:
        raise MegalodonException(ErrorCode.BAD_REQUEST, "El expediente está congelado.", 400)
    state = getattr(tender.state, "value", tender.state)
    if state in _TENDER_STATES_REQUIRING_NEW_REVISION and not (
        allow_cross_validated and state == TenderState.CROSS_VALIDATED.value
    ):
        raise MegalodonException(
            ErrorCode.CONFLICT,
            f"No se puede ejecutar {operation} después de QA/aprobación. Crea una nueva revisión explícita para invalidar los artefactos y aprobaciones anteriores.",
            409,
        )


def _approval_gate_ready(state: str, readiness: dict[str, Any]) -> bool:
    state_value = getattr(state, "value", state)
    return state_value in {
        TenderState.QA_READY.value,
        TenderState.READY_FOR_HUMAN_REVIEW.value,
    } and readiness.get("ready") is True


def _merge_authoritative_format_checklist(
    definitions: list[dict[str, Any]],
    submitted: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    """Merge human status/notes into the server-owned format catalogue."""
    authoritative: dict[str, dict[str, Any]] = {}
    for definition in definitions:
        if not isinstance(definition, dict):
            raise ValueError("El catálogo contiene una definición de formato inválida.")
        raw_code = definition.get("code") or definition.get("format_code")
        code = normalize_format_code(str(raw_code or ""))
        if not code:
            raise ValueError("El catálogo contiene un formato sin código.")
        if code in authoritative:
            raise ValueError(f"El catálogo contiene el formato duplicado {code}.")
        authoritative[code] = definition

    submitted_by_code: dict[str, dict[str, Any]] = {}
    for item in submitted:
        if not isinstance(item, dict):
            raise ValueError("Cada elemento del checklist debe ser un objeto.")
        code = normalize_format_code(str(item.get("code") or ""))
        if not code:
            raise ValueError("Cada formato revisado debe incluir un código.")
        if code not in authoritative:
            raise ValueError(f"El formato {code} no pertenece al catálogo autorizado del expediente.")
        if code in submitted_by_code:
            raise ValueError(f"El formato {code} aparece duplicado en la solicitud.")
        submitted_by_code[code] = item

    allowed_statuses = {"PENDIENTE", "REVISADO", "EDITADO", "LISTO"}
    merged: list[dict[str, Any]] = []
    for code, definition in authoritative.items():
        item = submitted_by_code.get(code, {})
        status = str(item.get("status") or "PENDIENTE").upper()
        if status not in allowed_statuses:
            raise ValueError(f"Estado inválido para el formato {code}.")
        merged.append({
            "code": code,
            "title": str(definition.get("title") or definition.get("name") or code),
            "category": str(definition.get("category") or "TECNICO").upper(),
            "required": bool(definition.get("required", True)),
            "status": status,
            "notes": str(item.get("notes") or "")[:2000],
        })
    return merged


class ProcurementService:
    async def _commit(self) -> None:
        try:
            await self.db.commit()
        except (StaleDataError, IntegrityError) as exc:
            await self.db.rollback()
            raise MegalodonException(
                ErrorCode.CONFLICT,
                "La operación colisionó con otra modificación concurrente. Recarga la revisión e inténtalo nuevamente.",
                409,
            ) from exc

    def __init__(self, db: AsyncSession, user: User, *, independent_sessions=None, preparation_correlation_id=None) -> None:
        self.db = db
        self.user = user
        self.independent_sessions = independent_sessions
        self.preparation_correlation_id = preparation_correlation_id
        self.orchestrator = TenderOrchestrator()
        self.compiler = ProcurementArtifactCompiler()
        self.jurisdiction = JurisdictionResolver()
        self.extractor = TenderSourceExtractor()
        self.requirement_mapper = ProcurementRequirementMapper()
        self.rule_compiler = DeterministicRuleCompiler()
        self.storage_guard = ProcurementStorageGuard(session_factory=independent_sessions)



    async def _effective_profile(self, code: str | None) -> JurisdictionProfile | None:
        if not code:
            return None
        return await self.db.scalar(
            select(JurisdictionProfile).where(
                JurisdictionProfile.code == code.upper(),
                JurisdictionProfile.active.is_(True),
                (JurisdictionProfile.tenant_id == self.user.tenant_id) | (JurisdictionProfile.tenant_id.is_(None)),
            ).order_by(JurisdictionProfile.tenant_id.desc().nullslast())
        )

    async def _validate_tender_configuration(self, data: TenderCreate) -> JurisdictionProfile:
        from sqlalchemy import or_
        profile = await self.db.scalar(select(JurisdictionProfile).where(
            JurisdictionProfile.code == data.jurisdiction_code.upper(),
            JurisdictionProfile.active.is_(True),
            or_(JurisdictionProfile.tenant_id == self.user.tenant_id, JurisdictionProfile.tenant_id.is_(None)),
        ).order_by(JurisdictionProfile.tenant_id.desc().nullslast()))
        if profile is None:
            raise MegalodonException(ErrorCode.PARAMETRO_INVALIDO, "La jurisdicción seleccionada no está registrada para este tenant.", 422)
        ruleset = profile.ruleset or {}
        inherited = set(await self.jurisdiction.inheritance_codes(self.db, self.user.tenant_id, profile.code))
        applicable_rules = (await self.db.execute(select(LegalRule).where(
            LegalRule.active.is_(True), LegalRule.jurisdiction_code.in_(sorted(inherited)),
            or_(LegalRule.tenant_id == self.user.tenant_id, LegalRule.tenant_id.is_(None)),
        ))).scalars().all()
        applicable_sources = (await self.db.execute(select(LegalSource).where(
            LegalSource.status == "ACTIVE", LegalSource.jurisdiction_code.in_(sorted(inherited)),
            or_(LegalSource.tenant_id == self.user.tenant_id, LegalSource.tenant_id.is_(None)),
        ))).scalars().all()
        linked_articles = (await self.db.execute(select(LegalArticle).join(LegalSource).where(
            LegalArticle.status == "ACTIVE", LegalSource.jurisdiction_code.in_(sorted(inherited)),
            or_(LegalSource.tenant_id == self.user.tenant_id, LegalSource.tenant_id.is_(None)),
        ))).scalars().all()
        if not ruleset.get("allowed_procedures") or not ruleset.get("allowed_contract_types"):
            raise MegalodonException(ErrorCode.VALIDACION_FALLIDA, f"El perfil {profile.code} no tiene procedimientos/tipos de contrato configurados.", 409)
        if not applicable_rules or not applicable_sources or not linked_articles or not any(r.article_id for r in applicable_rules):
            raise MegalodonException(ErrorCode.VALIDACION_FALLIDA, f"El perfil {profile.code} no tiene RuleSet, fuentes, artículos y bindings artículo-regla completos.", 409)

        def required_allowed(key: str, value: str | None) -> None:
            values = {str(v).upper() for v in (ruleset.get(key) or [])}
            if value is None:
                raise MegalodonException(ErrorCode.PARAMETRO_INVALIDO, f"{key} es obligatorio para {profile.code}.", 422)
            if values and str(value).upper() not in values:
                raise MegalodonException(ErrorCode.PARAMETRO_INVALIDO, f"{value} no está habilitado para {profile.code}: {key}.", 422)

        required_allowed("allowed_procedures", data.procedure_type)
        required_allowed("allowed_contract_types", data.contract_type)
        required_allowed("allowed_evaluation_criteria", data.evaluation_criterion)
        for key, value in (("allowed_funding_sources", data.funding_source), ("allowed_legal_regimes", data.legal_regime)):
            if value is not None and ruleset.get(key) and str(value).upper() not in {str(v).upper() for v in ruleset[key]}:
                raise MegalodonException(ErrorCode.PARAMETRO_INVALIDO, f"{value} no está habilitado para {profile.code}: {key}.", 422)
        for key, value in (("allowed_project_types", data.project_type), ("allowed_scope_scales", data.scope_scale), ("allowed_object_classes", data.object_class)):
            if value is not None and ruleset.get(key) and value not in ruleset[key]:
                raise MegalodonException(ErrorCode.PARAMETRO_INVALIDO, f"{value} no está habilitado para {profile.code}: {key}.", 422)
        # Validación contra vocabulario en catalog_terms (DB). Si el dominio
        # aún no está sembrado, no se inventa whitelist: se acepta el valor
        # y se deja traza — la UI solo ofrece opciones del catálogo cargado.
        async def _reject_if_known_domain(domain: str, value: str | None, label: str) -> None:
            if not value:
                return
            m = await load_domain_map(self.db, tenant_id=self.user.tenant_id, domain=domain)
            if m and value not in m:
                raise MegalodonException(
                    ErrorCode.PARAMETRO_INVALIDO,
                    f"{label} no soportado: {value}.",
                    422,
                )

        await _reject_if_known_domain("PROJECT_TYPES", data.project_type, "Tipo de proyecto")
        await _reject_if_known_domain("SCOPE_SCALES", data.scope_scale, "Escala de alcance")
        await _reject_if_known_domain("FUNDING_SOURCES", data.funding_source, "Fuente de recursos")
        await _reject_if_known_domain("OBJECT_CLASSES", data.object_class, "Clase de objeto")
        await _reject_if_known_domain("LEGAL_REGIMES", data.legal_regime, "Régimen jurídico")
        case_pack = await get_case_pack(self.db, tenant_id=self.user.tenant_id, code=data.case_pack_code)
        if data.case_pack_code and (case_pack is None or case_pack.get("jurisdiction_code") != profile.code):
            raise MegalodonException(ErrorCode.PARAMETRO_INVALIDO, "El paquete documental seleccionado no corresponde al perfil jurídico.", 422)
        if data.case_pack_code and ruleset.get("case_packs") and data.case_pack_code not in set(ruleset["case_packs"]):
            raise MegalodonException(ErrorCode.PARAMETRO_INVALIDO, f"El paquete {data.case_pack_code} no está habilitado para {profile.code}.", 422)
        return profile

    async def readiness(self, tender_id: UUID) -> dict:
        tender = await self._get(tender_id)
        profile = await self._effective_profile(tender.jurisdiction_code)
        findings: list[dict] = []
        if profile is None:
            findings.append({"code":"JURISDICTION_NOT_FOUND","severity":"BLOCKER","message":"La jurisdicción seleccionada no está disponible."})
        else:
            rs = profile.ruleset or {}
            for key in ("allowed_procedures", "allowed_contract_types", "allowed_evaluation_criteria"):
                if not rs.get(key):
                    findings.append({"code":f"JURISDICTION_{key.upper()}","severity":"BLOCKER","message":f"{key} no está configurado para {profile.code}."})
            if not rs.get("ready_for_execution", False):
                findings.append({"code":"JURISDICTION_NOT_READY","severity":"BLOCKER","message":f"{profile.code} no está marcado como listo para ejecución."})
        source_readiness = await self.requirement_source_readiness(tender.id)
        if source_readiness["missing_source_roles"]:
            missing = ", ".join(source_readiness["missing_source_roles"])
            findings.append({"code":"OFFICIAL_SOURCE_REQUIRED","severity":"BLOCKER","message":f"Faltan fuentes oficiales requeridas por el flujo/dependencia: {missing}."})
        reqs = (await self.db.execute(select(TenderRequirement).where(TenderRequirement.tender_id == tender.id, TenderRequirement.tenant_id == self.user.tenant_id))).scalars().all()
        candidate_count = 0
        for ev in (await self.db.execute(select(TenderEvidence).where(
            TenderEvidence.tender_id == tender.id,
            TenderEvidence.tenant_id == self.user.tenant_id,
            TenderEvidence.kind == "SOURCE_DOCUMENT", TenderEvidence.status == "ACTIVE"
        ))).scalars().all():
            candidate_count += sum(1 for c in ((ev.value or {}).get("requirement_candidates") or []) if isinstance(c, dict) and c.get("status") != "CONFIRMED")
        if candidate_count:
            findings.append({"code":"REQUIREMENT_REVIEW_REQUIRED","severity":"BLOCKER","message":f"Existen {candidate_count} candidatos extraídos de fuentes oficiales que requieren revisión y confirmación humana."})
        missing_requirements = [r.code for r in reqs if r.mandatory and r.status not in {RequirementStatus.PASS.value, RequirementStatus.NOT_APPLICABLE.value, RequirementStatus.OVERRIDE.value}]
        if missing_requirements:
            findings.append({"code":"REQUIREMENTS_UNSATISFIED","severity":"BLOCKER","message":"Requisitos obligatorios pendientes: " + ", ".join(sorted(missing_requirements))})

        # A snapshot técnico sólo es confiable para el gate si podemos demostrar
        # que la fuente actual conserva la misma revisión que tenía al congelarse.
        technical = (tender.canonical_model or {}).get("technical", {})
        snapshots = technical.get("snapshots", []) if isinstance(technical, dict) else []
        for snapshot in snapshots:
            if not isinstance(snapshot, dict):
                findings.append({"code":"TECHNICAL_SNAPSHOT_INVALID","severity":"BLOCKER","message":"Existe un snapshot técnico con formato inválido."})
                continue
            source = snapshot.get("source") if isinstance(snapshot.get("source"), dict) else {}
            resource_type = source.get("resource_type")
            resource_id = source.get("resource_id")
            stored_revision = source.get("revision")
            current_revision = None
            if resource_type == "BIM_MODEL":
                try:
                    source_row = await self.db.scalar(select(ModeloBIM).where(
                        ModeloBIM.id == UUID(str(resource_id)),
                        ModeloBIM.tenant_id == self.user.tenant_id,
                        ModeloBIM.expediente_id == tender.expediente_id,
                    ))
                except (ValueError, TypeError):
                    source_row = None
                if source_row is not None:
                    current_revision = source_revision_token(source_row.updated_at, source_row.version_ifc)
            elif resource_type == "TOPOGRAFIA_VOLUMEN":
                try:
                    source_row = await self.db.scalar(
                        select(CalculoVolumen)
                        .join(ExpedienteObra, CalculoVolumen.expediente_id == ExpedienteObra.id)
                        .where(
                            CalculoVolumen.id == UUID(str(resource_id)),
                            CalculoVolumen.expediente_id == tender.expediente_id,
                            ExpedienteObra.tenant_id == self.user.tenant_id,
                        )
                    )
                except (ValueError, TypeError):
                    source_row = None
                if source_row is not None:
                    current_revision = source_revision_token(source_row.updated_at)
            else:
                findings.append({"code":"TECHNICAL_SNAPSHOT_SOURCE_UNKNOWN","severity":"BLOCKER","message":f"Fuente de snapshot técnico no soportada/verificable: {resource_type!r}."})
                continue
            if source_row is None:
                findings.append({"code":"TECHNICAL_SNAPSHOT_SOURCE_MISSING","severity":"BLOCKER","message":f"La fuente del snapshot técnico ya no existe o no pertenece al tenant/expediente: {resource_type}:{resource_id}."})
            elif not snapshot_source_is_current(stored_revision, current_revision):
                findings.append({"code":"TECHNICAL_SNAPSHOT_STALE","severity":"BLOCKER","message":f"El snapshot técnico quedó obsoleto respecto de la fuente: {resource_type}:{resource_id}. Rematerializa antes de continuar."})
        blocker = any(f.get("severity") in {"BLOCKER", "P0"} for f in findings)
        gate_state = TenderState.READY_FOR_HUMAN_REVIEW.value if tender.state in {TenderState.QA_READY.value, TenderState.READY_FOR_HUMAN_REVIEW.value} and not blocker else tender.state
        ready = gate_state == TenderState.READY_FOR_HUMAN_REVIEW.value
        return {
            "tender_id": str(tender.id),
            "state": tender.state,
            "review_state": gate_state,
            "ready": ready,
            "findings": findings,
            "mandatory_requirements": len([r for r in reqs if r.mandatory]),
            "satisfied_requirements": len([r for r in reqs if r.mandatory and r.status in {RequirementStatus.PASS.value, RequirementStatus.NOT_APPLICABLE.value, RequirementStatus.OVERRIDE.value}]),
            "source_readiness": source_readiness,
            "pipeline_version": PIPELINE_VERSION,
            "engine": "MECHANICAL_DETERMINISTIC",
            "ai": False,
        }

    async def catalog(self) -> dict:
        from sqlalchemy import or_, func
        profiles_raw = (await self.db.execute(select(JurisdictionProfile).where(JurisdictionProfile.active.is_(True), or_(JurisdictionProfile.tenant_id == self.user.tenant_id, JurisdictionProfile.tenant_id.is_(None))).order_by(JurisdictionProfile.government_level, JurisdictionProfile.authority, JurisdictionProfile.code, JurisdictionProfile.tenant_id.desc().nullslast()))).scalars().all()
        profiles=[]; seen_codes=set()
        for profile in profiles_raw:
            if profile.code in seen_codes:
                continue
            seen_codes.add(profile.code); profiles.append(profile)
        rules = (await self.db.execute(select(LegalRule).where(LegalRule.active.is_(True), or_(LegalRule.tenant_id == self.user.tenant_id, LegalRule.tenant_id.is_(None))))).scalars().all()
        sources = (await self.db.execute(select(LegalSource).where(or_(LegalSource.tenant_id == self.user.tenant_id, LegalSource.tenant_id.is_(None)), LegalSource.status == "ACTIVE"))).scalars().all()
        articles = (await self.db.execute(select(LegalArticle).join(LegalSource).where(or_(LegalSource.tenant_id == self.user.tenant_id, LegalSource.tenant_id.is_(None)), LegalArticle.status == "ACTIVE"))).scalars().all()
        rules_by_code = {}
        for r in rules:
            rules_by_code[r.jurisdiction_code or "__GLOBAL__"] = rules_by_code.get(r.jurisdiction_code or "__GLOBAL__", 0) + 1
        article_by_source = {}
        for a in articles:
            article_by_source[str(a.source_id)] = article_by_source.get(str(a.source_id), 0) + 1
        source_by_j = {}
        for src in sources:
            source_by_j[src.jurisdiction_code or "__GLOBAL__"] = source_by_j.get(src.jurisdiction_code or "__GLOBAL__", 0) + 1
        items=[]
        for p in profiles:
            rs = p.ruleset or {}
            inherited = set(await self.jurisdiction.inheritance_codes(self.db, self.user.tenant_id, p.code))
            applicable_rule_rows = [r for r in rules if r.jurisdiction_code in inherited or r.jurisdiction_code is None]
            count_rules = len(applicable_rule_rows)
            count_sources = sum(1 for src in sources if src.jurisdiction_code in inherited or src.jurisdiction_code is None)
            count_articles = sum(article_by_source.get(str(src.id), 0) for src in sources if src.jurisdiction_code in inherited or src.jurisdiction_code is None)
            bound_articles = sum(1 for r in applicable_rule_rows if r.article_id is not None)
            ready = bool(count_rules and count_sources and count_articles and bound_articles and rs.get("allowed_procedures") and rs.get("allowed_contract_types"))
            reasons=[]
            if not count_sources: reasons.append("NO_ACTIVE_LEGAL_SOURCES")
            if not count_rules: reasons.append("NO_ACTIVE_RULESET")
            if not count_articles: reasons.append("NO_LINKED_ARTICLES")
            if not bound_articles: reasons.append("NO_RULE_ARTICLE_BINDINGS")
            if rs.get("requires_official_entity_pack"): reasons.append("ENTITY_SPECIFIC_SOURCE_PACK_REQUIRED")
            format_catalog = await load_format_catalog(
                self.db, tenant_id=self.user.tenant_id, jurisdiction_code=p.code
            )
            items.append({"code":p.code,"authority":p.authority,"government_level":p.government_level,"matter":p.matter,"portal_code":p.portal_code,"version":p.profile_version,"tenant_scope":"GLOBAL" if p.tenant_id is None else "TENANT","ready_for_execution":ready,"readiness_reasons":reasons,"rule_count":count_rules,"source_count":count_sources,"article_count":count_articles,"bound_rule_article_count":bound_articles,"allowed_procedures":rs.get("allowed_procedures",[]),"allowed_contract_types":rs.get("allowed_contract_types",[]),"allowed_evaluation_criteria":rs.get("allowed_evaluation_criteria",[]),"allowed_funding_sources":rs.get("allowed_funding_sources", []),"allowed_legal_regimes":rs.get("allowed_legal_regimes", []),"regime_family":rs.get("regime_family"),"selection_label":rs.get("selection_label",p.authority),"case_packs": await case_packs_for_jurisdiction(self.db, tenant_id=self.user.tenant_id, jurisdiction_code=p.code),"format_definitions": list(format_catalog.values()),"required_approval_roles":rs.get("required_approval_roles") or ["revisor"]})
        vocab = await build_catalog_payload(self.db, tenant_id=self.user.tenant_id)
        return {
            "profiles": items,
            **{k: v for k, v in vocab.items() if k not in ("vocabulary_complete", "vocabulary_missing_domains")},
            "vocabulary_complete": vocab["vocabulary_complete"],
            "vocabulary_missing_domains": vocab["vocabulary_missing_domains"],
            "case_packs": await load_case_packs(self.db, tenant_id=self.user.tenant_id),
            "legal_sources": [{"id":str(s.id),"jurisdiction_code":s.jurisdiction_code,"title":s.title,"citation":s.citation,"version":s.version,"source_uri":s.source_uri,"status":s.status} for s in sources],
            "articles": [{"id":str(a.id),"source_id":str(a.source_id),"article":a.article_code,"title":a.title,"summary":a.summary} for a in articles],
        }

    async def install_jurisdiction_pack(self, data: JurisdictionPackCreate) -> JurisdictionProfile:
        profile_data = data.profile
        existing = await self.db.scalar(select(JurisdictionProfile).where(
            JurisdictionProfile.code == profile_data.code.upper(),
            JurisdictionProfile.tenant_id == self.user.tenant_id,
        ))
        if existing is not None:
            raise MegalodonException(ErrorCode.CONFLICT, "El perfil de jurisdicción ya existe para este tenant.", 409)
        profile = JurisdictionProfile(
            code=profile_data.code.upper(), authority=profile_data.authority,
            government_level=profile_data.government_level, matter=profile_data.matter,
            portal_code=profile_data.portal_code, profile_version=profile_data.profile_version,
            ruleset=profile_data.ruleset, templates=profile_data.templates,
            tenant_id=self.user.tenant_id, creado_por_id=self.user.id, actualizado_por_id=self.user.id,
        )
        self.db.add(profile)
        await self.db.flush()
        for parent_code in [str(x).upper() for x in (profile_data.ruleset or {}).get("inherits_from", [])]:
            parent = await self.db.scalar(select(JurisdictionProfile).where(
                JurisdictionProfile.code == parent_code,
                JurisdictionProfile.active.is_(True),
                (JurisdictionProfile.tenant_id == self.user.tenant_id) | (JurisdictionProfile.tenant_id.is_(None)),
            ).order_by(JurisdictionProfile.tenant_id.desc().nullslast()))
            if parent is None:
                raise MegalodonException(ErrorCode.DOCUMENTO_NO_ENCONTRADO, f"La jurisdicción padre {parent_code} no existe.", 404)
            self.db.add(JurisdictionInheritance(
                tenant_id=self.user.tenant_id, child_profile_id=profile.id, parent_profile_id=parent.id,
                effective_from=str(profile_data.ruleset.get("effective_from")) if profile_data.ruleset.get("effective_from") else None,
                active=True,
            ))
        source_map: dict[str, LegalSource] = {}
        for source_data in data.sources:
            source = LegalSource(
                authority=source_data.authority, title=source_data.title, citation=source_data.citation,
                source_uri=source_data.source_uri, publication_date=source_data.publication_date,
                effective_from=source_data.effective_from, effective_to=source_data.effective_to,
                version=source_data.version, content_hash=source_data.content_hash,
                jurisdiction_code=profile.code, status="ACTIVE", tenant_id=self.user.tenant_id,
                creado_por_id=self.user.id, actualizado_por_id=self.user.id,
            )
            self.db.add(source)
            await self.db.flush()
            source_key = f"{source_data.citation or source_data.title}|{source_data.version}"
            source_map[source_key] = source
            source_map[source_data.citation or source_data.title] = source
        article_map: dict[str, LegalArticle] = {}
        for article_data in data.articles:
            source = source_map.get(article_data.source_ref or "") if article_data.source_ref else None
            if source is None and article_data.source_id is not None:
                source = await self.db.scalar(select(LegalSource).where(
                    LegalSource.id == article_data.source_id,
                    LegalSource.tenant_id == self.user.tenant_id,
                ))
            if source is None:
                raise MegalodonException(ErrorCode.DOCUMENTO_NO_ENCONTRADO, f"La fuente del artículo {article_data.article_code} no pertenece al tenant o no coincide con el paquete.", 404)
            article = LegalArticle(
                source_id=source.id, article_code=article_data.article_code, title=article_data.title,
                summary=article_data.summary, effective_from=article_data.effective_from,
                effective_to=article_data.effective_to, content_hash=article_data.content_hash, status="ACTIVE",
            )
            self.db.add(article)
            await self.db.flush()
            article_map[f"{source.id}:{article.article_code}"] = article
            article_map[article.article_code] = article
        for rule_data in data.rules:
            if rule_data.jurisdiction_code and rule_data.jurisdiction_code.upper() != profile.code:
                raise MegalodonException(ErrorCode.PARAMETRO_INVALIDO, f"La regla {rule_data.rule_id} apunta a otra jurisdicción.", 422)
            source = source_map.get(rule_data.source_ref or "") if rule_data.source_ref else None
            article = article_map.get(rule_data.article_ref or "") if rule_data.article_ref else None
            if article is None and rule_data.article_id is not None:
                article = await self.db.scalar(select(LegalArticle).join(LegalSource).where(
                    LegalArticle.id == rule_data.article_id,
                    (LegalSource.tenant_id == self.user.tenant_id) | (LegalSource.tenant_id.is_(None)),
                ))
                if article is None:
                    raise MegalodonException(ErrorCode.DOCUMENTO_NO_ENCONTRADO, f"Artículo jurídico no encontrado para {rule_data.rule_id} dentro del tenant/fuente permitidos.", 404)
            if article is not None and source is None:
                source = source_map.get(str(article.source_id))
                if source is None:
                    source = await self.db.scalar(select(LegalSource).where(LegalSource.id == article.source_id, LegalSource.tenant_id == self.user.tenant_id))
            if source is None and rule_data.source_id is not None:
                source = await self.db.scalar(select(LegalSource).where(LegalSource.id == rule_data.source_id, LegalSource.tenant_id == self.user.tenant_id))
            if rule_data.article_id is not None and article is None:
                raise MegalodonException(ErrorCode.DOCUMENTO_NO_ENCONTRADO, f"Artículo jurídico no encontrado para {rule_data.rule_id}.", 404)
            if rule_data.source_id is not None and source is None:
                raise MegalodonException(ErrorCode.DOCUMENTO_NO_ENCONTRADO, f"Fuente jurídica no encontrada para {rule_data.rule_id}.", 404)
            rule = LegalRule(
                rule_id=rule_data.rule_id, jurisdiction_code=profile.code, domain=rule_data.domain,
                procedure_type=rule_data.procedure_type, source_id=source.id if source else None,
                article_id=article.id if article else None, source_version=rule_data.source_version,
                condition=rule_data.condition, requirement=rule_data.requirement, validation=rule_data.validation,
                severity=rule_data.severity, effective_from=rule_data.effective_from, effective_to=rule_data.effective_to,
                rule_version=rule_data.rule_version, active=True, tenant_id=self.user.tenant_id,
                creado_por_id=self.user.id, actualizado_por_id=self.user.id,
            )
            self.db.add(rule)
        await self._commit()
        await self.db.refresh(profile)
        return profile

    async def create_jurisdiction_profile(self, data: JurisdictionProfileCreate) -> JurisdictionProfile:
        exists = await self.db.scalar(select(JurisdictionProfile).where(
            JurisdictionProfile.code == data.code.upper(),
            JurisdictionProfile.tenant_id == self.user.tenant_id,
        ))
        if exists:
            raise MegalodonException(ErrorCode.CONFLICT, "El perfil de jurisdicción ya existe.", 409)
        row = JurisdictionProfile(
            code=data.code.upper(), authority=data.authority, government_level=data.government_level, matter=data.matter,
            portal_code=data.portal_code, profile_version=data.profile_version, ruleset=data.ruleset, templates=data.templates,
            tenant_id=self.user.tenant_id, creado_por_id=self.user.id, actualizado_por_id=self.user.id,
        )
        self.db.add(row)
        await self.db.flush()
        for parent_code in [str(x).upper() for x in (data.ruleset or {}).get("inherits_from", [])]:
            parent = await self.db.scalar(select(JurisdictionProfile).where(
                JurisdictionProfile.code == parent_code,
                JurisdictionProfile.active.is_(True),
                (JurisdictionProfile.tenant_id == self.user.tenant_id) | (JurisdictionProfile.tenant_id.is_(None)),
            ).order_by(JurisdictionProfile.tenant_id.desc().nullslast()))
            if parent is None:
                raise MegalodonException(ErrorCode.DOCUMENTO_NO_ENCONTRADO, f"La jurisdicción padre {parent_code} no existe.", 404)
            self.db.add(JurisdictionInheritance(tenant_id=self.user.tenant_id, child_profile_id=row.id, parent_profile_id=parent.id, active=True))
        await self._commit(); await self.db.refresh(row)
        return row

    async def create_legal_source(self, data: LegalSourceCreate) -> LegalSource:
        row = LegalSource(
            authority=data.authority, title=data.title, citation=data.citation, source_uri=data.source_uri,
            publication_date=data.publication_date, effective_from=data.effective_from, effective_to=data.effective_to,
            version=data.version, content_hash=data.content_hash, jurisdiction_code=data.jurisdiction_code, status="ACTIVE",
            tenant_id=self.user.tenant_id, creado_por_id=self.user.id, actualizado_por_id=self.user.id,
        )
        self.db.add(row)
        await self._commit(); await self.db.refresh(row)
        return row

    async def create_legal_rule(self, data: LegalRuleCreate) -> LegalRule:
        from sqlalchemy import or_
        source = None
        if not data.jurisdiction_code:
            raise MegalodonException(ErrorCode.PARAMETRO_INVALIDO, "Una regla jurídica requiere jurisdiction_code explícito.", 422)
        if data.source_id is None and not data.source_ref:
            raise MegalodonException(ErrorCode.VALIDACION_FALLIDA, "Una regla jurídica requiere una fuente jurídica vinculada.", 422)
        if data.article_id is None and not data.article_ref:
            raise MegalodonException(ErrorCode.VALIDACION_FALLIDA, "Una regla jurídica requiere un artículo jurídico vinculado.", 422)
        if data.source_id is not None:
            from sqlalchemy import or_
            source = await self.db.scalar(select(LegalSource).where(
                LegalSource.id == data.source_id, or_(LegalSource.tenant_id == self.user.tenant_id, LegalSource.tenant_id.is_(None))
            ))
            if source is None:
                raise MegalodonException(ErrorCode.DOCUMENTO_NO_ENCONTRADO, "Fuente jurídica no encontrada.", 404)
        if data.article_id is not None:
            article = await self.db.scalar(select(LegalArticle).join(LegalSource).where(
                LegalArticle.id == data.article_id,
                (LegalSource.tenant_id == self.user.tenant_id) | (LegalSource.tenant_id.is_(None)),
            ))
            if article is None:
                raise MegalodonException(ErrorCode.DOCUMENTO_NO_ENCONTRADO, "Artículo jurídico no encontrado para este tenant.", 404)
            if data.source_id is not None and article.source_id != data.source_id:
                raise MegalodonException(ErrorCode.PARAMETRO_INVALIDO, "El artículo jurídico no pertenece a la fuente seleccionada.", 422)
            if source is None:
                source = await self.db.scalar(select(LegalSource).where(
                    LegalSource.id == article.source_id,
                    (LegalSource.tenant_id == self.user.tenant_id) | (LegalSource.tenant_id.is_(None)),
                ))
                if source is None:
                    raise MegalodonException(ErrorCode.DOCUMENTO_NO_ENCONTRADO, "Fuente del artículo jurídico no encontrada para este tenant.", 404)
        if source is None and data.source_ref:
            ref = data.source_ref.strip()
            source = await self.db.scalar(select(LegalSource).where(
                or_(LegalSource.citation == ref, LegalSource.title == ref),
                or_(LegalSource.tenant_id == self.user.tenant_id, LegalSource.tenant_id.is_(None)),
                LegalSource.jurisdiction_code == data.jurisdiction_code,
                LegalSource.status == "ACTIVE",
            ).order_by(LegalSource.tenant_id.desc().nullslast(), LegalSource.version.desc()))
            if source is None:
                raise MegalodonException(ErrorCode.DOCUMENTO_NO_ENCONTRADO, "source_ref no pudo resolverse dentro de la jurisdicción seleccionada.", 404)
        if article is None and data.article_ref:
            article = await self.db.scalar(select(LegalArticle).where(
                LegalArticle.article_code == data.article_ref.strip(),
                LegalArticle.source_id == source.id,
                LegalArticle.status == "ACTIVE",
            ))
            if article is None:
                raise MegalodonException(ErrorCode.DOCUMENTO_NO_ENCONTRADO, "article_ref no pudo resolverse dentro de la fuente seleccionada.", 404)
        if source is None or article is None or article.source_id != source.id:
            raise MegalodonException(ErrorCode.VALIDACION_FALLIDA, "La regla jurídica debe quedar vinculada a fuente y artículo de la misma jurisdicción.", 422)
        exists = await self.db.scalar(select(LegalRule).where(
            LegalRule.rule_id == data.rule_id, LegalRule.rule_version == data.rule_version, or_(LegalRule.tenant_id == self.user.tenant_id, LegalRule.tenant_id.is_(None))
        ))
        if exists:
            raise MegalodonException(ErrorCode.CONFLICT, "La versión de regla jurídica ya existe.", 409)
        row = LegalRule(
            rule_id=data.rule_id, jurisdiction_code=data.jurisdiction_code, domain=data.domain, procedure_type=data.procedure_type,
            source_id=source.id, article_id=article.id, source_version=data.source_version, condition=data.condition, requirement=data.requirement,
            validation=data.validation, severity=data.severity, effective_from=data.effective_from, effective_to=data.effective_to,
            rule_version=data.rule_version, active=True, tenant_id=self.user.tenant_id, creado_por_id=self.user.id, actualizado_por_id=self.user.id,
        )
        self.db.add(row)
        await self._commit(); await self.db.refresh(row)
        return row

    async def _get(self, tender_id: UUID, *, for_update: bool = False) -> TenderPackage:
        stmt = select(TenderPackage).where(
            TenderPackage.id == tender_id,
            TenderPackage.tenant_id == self.user.tenant_id,
        )
        if for_update:
            # IDs/tenant ownership remain immutable. Serialize writers with
            # NO KEY UPDATE so the independently committed preparation trace
            # can acquire its FK KEY SHARE lock on this same tender. FOR UPDATE
            # caused run() to wait forever on its own trace transaction.
            stmt = stmt.with_for_update(key_share=True).execution_options(populate_existing=True)
        tender = await self.db.scalar(stmt)
        if tender is None:
            raise MegalodonException(ErrorCode.DOCUMENTO_NO_ENCONTRADO, "TenderPackage no encontrado.", 404)
        return tender

    @staticmethod
    def _transition(tender: TenderPackage, target: TenderState) -> None:
        try:
            tender.state = TenderLifecycle.transition(tender.state, target.value)
        except InvalidTenderTransition as exc:
            raise MegalodonException(ErrorCode.VALIDACION_FALLIDA, str(exc), 409) from exc

    async def list_tenders(
        self, *, state: str | None = None, jurisdiction_code: str | None = None, expediente_id: UUID | None = None, offset: int = 0, limit: int = 100
    ) -> list[dict]:
        query = select(TenderPackage).where(TenderPackage.tenant_id == self.user.tenant_id)
        if state:
            query = query.where(TenderPackage.state == state)
        if jurisdiction_code:
            query = query.where(TenderPackage.jurisdiction_code == jurisdiction_code)
        if expediente_id:
            query = query.where(TenderPackage.expediente_id == expediente_id)
        rows = (await self.db.execute(query.order_by(TenderPackage.updated_at.desc()).offset(max(0, offset)).limit(min(max(1, limit), 500)))).scalars().all()
        return [
            {
                "id": str(row.id),
                "expediente_id": str(row.expediente_id),
                "identifier": row.identifier,
                "title": row.title,
                "state": row.state,
                "jurisdiction_code": row.jurisdiction_code,
                "procedure_type": row.procedure_type,
                "contract_type": row.contract_type,
                "evaluation_criterion": row.evaluation_criterion, "project_type": row.project_type, "scope_scale": row.scope_scale, "case_pack_code": row.case_pack_code,
                "revision": row.current_revision,
                "frozen": row.frozen,
                "updated_at": row.updated_at.isoformat() if row.updated_at else None,
            }
            for row in rows
        ]

    async def create(self, data: TenderCreate) -> TenderPackage:
        await self._validate_tender_configuration(data)
        expediente = await self.db.scalar(
            select(ExpedienteObra).where(
                ExpedienteObra.id == data.expediente_id,
                ExpedienteObra.tenant_id == self.user.tenant_id,
            )
        )
        if expediente is None:
            raise MegalodonException(ErrorCode.DOCUMENTO_NO_ENCONTRADO, "Expediente no encontrado.", 404)
        duplicate = await self.db.scalar(
            select(TenderPackage).where(
                TenderPackage.identifier == data.identifier,
                TenderPackage.tenant_id == self.user.tenant_id,
            )
        )
        if duplicate:
            raise MegalodonException(ErrorCode.CONFLICT, "Ya existe un TenderPackage con ese identificador.", 409)

        canonical = data.canonical_model.model_dump(mode="json")
        canonical.update({"identifier": data.identifier, "title": data.title})
        canonical["facts"].update({"jurisdiction_code": data.jurisdiction_code.upper(), "procedure_type": data.procedure_type, "contract_type": data.contract_type, "evaluation_criterion": data.evaluation_criterion, "project_type": data.project_type, "scope_scale": data.scope_scale, "case_pack_code": data.case_pack_code, "funding_source": data.funding_source, "object_class": data.object_class, "legal_regime": data.legal_regime})
        if not canonical.get("facts", {}).get("object"):
            canonical["facts"]["object"] = expediente.proyecto_nombre or expediente.titulo
        if not canonical.get("facts", {}).get("description"):
            canonical["facts"]["description"] = expediente.descripcion or ""
        if not canonical.get("facts", {}).get("authority"):
            canonical["facts"]["authority"] = expediente.organo
        if not canonical.get("facts", {}).get("location"):
            canonical["facts"]["location"] = expediente.ubicacion_obra

        # Reuse real engineering/economic state already persisted in Megalodon.
        # This is a projection, not a copy of defaults: empty procurement sections
        # are hydrated only from actual expediente-owned records.
        if not canonical.get("economic", {}).get("partidas"):
            budget = await self.db.scalar(
                select(Presupuesto)
                .join(ExpedienteObra, ExpedienteObra.id == Presupuesto.expediente_id)
                .where(Presupuesto.expediente_id == expediente.id, ExpedienteObra.tenant_id == self.user.tenant_id)
                .options(selectinload(Presupuesto.partidas).selectinload(Partida.conceptos).selectinload(Concepto.insumos))
                .order_by(Presupuesto.id.desc())
                .limit(1)
            )
            if budget is not None and budget.partidas:
                canonical["economic"] = {
                    **canonical.get("economic", {}),
                    **build_economic_block(budget),
                }

        if not canonical.get("schedule", {}).get("activities"):
            program = await self.db.scalar(
                select(ProgramaObra)
                .join(ExpedienteObra, ExpedienteObra.id == ProgramaObra.expediente_id)
                .where(ProgramaObra.expediente_id == expediente.id, ExpedienteObra.tenant_id == self.user.tenant_id)
                .options(selectinload(ProgramaObra.actividades))
                .order_by(ProgramaObra.id.desc())
                .limit(1)
            )
            if program is not None and program.actividades:
                canonical["schedule"] = {
                    **canonical.get("schedule", {}),
                    "start_date": program.fecha_inicio_plan.isoformat(),
                    "activities": [
                        {
                            "id": activity.identificador, "name": activity.nombre,
                            "description": activity.descripcion or "", "wbs_code": activity.wbs_codigo,
                            "wbs_level": int(activity.wbs_nivel), "duration_days": float(activity.duracion),
                            "budget": float(activity.costo_presupuestado),
                            "predecessors": list(activity.predecesoras or []), "type": activity.tipo,
                        } for activity in program.actividades
                    ],
                }
        tender = TenderPackage(
            expediente_id=data.expediente_id,
            identifier=data.identifier,
            title=data.title,
            jurisdiction_code=data.jurisdiction_code,
            procedure_type=data.procedure_type,
            contract_type=data.contract_type,
            evaluation_criterion=data.evaluation_criterion, project_type=data.project_type, scope_scale=data.scope_scale, case_pack_code=data.case_pack_code,
            source_manifest=data.source_manifest,
            canonical_model=canonical,
            tenant_id=self.user.tenant_id,
            creado_por_id=self.user.id,
            actualizado_por_id=self.user.id,
        )
        self.db.add(tender)
        await self.db.flush()
        revision = TenderRevision(
            tender_id=tender.id, revision=1, reason="INITIAL",
            source_hash=self._hash(data.source_manifest),
            model_snapshot=tender.canonical_model,
            tenant_id=self.user.tenant_id,
        )
        self.db.add(revision)
        await self._commit()
        await self.db.refresh(tender)
        return tender

    @staticmethod
    def _format_detection_candidates(format_catalog: dict[str, dict], *, filename: str, text: str) -> list[dict[str, Any]]:
        """Conservative deterministic format detection from supplied tender sources.

        This is only a suggestion layer: it never changes requirements or legal
        meaning. A candidate must be matched by an explicit DB-configured format
        code or alias; the user still confirms the checklist before compilation.
        """
        haystack = f"{filename}\n{text}".casefold()
        candidates: list[dict[str, Any]] = []
        for code, binding in format_catalog.items():
            matches: list[str] = []
            terms = [str(code), str(binding.get("title") or ""), str(binding.get("megalodon_code") or "")]
            terms += [str(x) for x in (binding.get("aliases") or []) if str(x).strip()]
            for term in terms:
                if term.casefold() in haystack:
                    matches.append(term)
            if matches:
                candidates.append({
                    "code": code,
                    "title": str(binding.get("title") or code),
                    "required": bool(binding.get("required", False)),
                    "matched_terms": sorted(set(matches), key=str.casefold),
                    "source": "DB_FORMAT_CATALOG_EXACT_MATCH",
                })
        candidates.sort(key=lambda x: (not x["required"], x["code"]))
        return candidates

    async def ingest_source(self, tender_id: UUID, filename: str, content_type: str, content: bytes, source_role: str = "CONVOCATORIA") -> dict:
        tender = await self._get(tender_id, for_update=True)
        _ensure_tender_mutation_allowed(tender, "ingesta de fuentes")
        if not content:
            raise MegalodonException(ErrorCode.ARCHIVO_ERROR, "La fuente documental está vacía.", 422)
        max_bytes = get_settings().TENDER_SOURCE_MAX_FILE_SIZE_MB * 1024 * 1024
        if len(content) > max_bytes:
            raise MegalodonException(
                ErrorCode.ARCHIVO_ERROR,
                f"La fuente excede el límite configurado de {get_settings().TENDER_SOURCE_MAX_FILE_SIZE_MB} MB.",
                413,
            )
        digest = sha256(content).hexdigest()
        duplicate = await self.db.scalar(select(TenderEvidence).where(
            TenderEvidence.tender_id == tender.id,
            TenderEvidence.tenant_id == self.user.tenant_id,
            TenderEvidence.source_hash == digest,
            TenderEvidence.kind == "SOURCE_DOCUMENT",
            TenderEvidence.status == "ACTIVE",
        ))
        if duplicate is not None:
            return {
                "evidence_id": str(duplicate.id),
                "storage_path": duplicate.source_uri,
                "sha256": digest,
                "size_bytes": int((duplicate.value or {}).get("size_bytes", 0)),
                "media_type": str((duplicate.value or {}).get("media_type", content_type)),
                "idempotent": True,
            }
        safe_name = filename.replace("/", "_").replace("\\", "_")
        extracted = self.extractor.extract(filename, content_type or "application/octet-stream", content)
        format_catalog = await load_format_catalog(
            self.db, tenant_id=self.user.tenant_id, jurisdiction_code=tender.jurisdiction_code
        )
        detected_formats = self._format_detection_candidates(
            format_catalog, filename=filename, text=extracted.text or ""
        )
        profile = await self._effective_profile(tender.jurisdiction_code)
        extraction_config = ((profile.templates or {}).get("requirement_extraction") if profile else None) or {}
        source_role = str(source_role or "CONVOCATORIA").upper().strip()
        flow_code = str(tender.project_type or (tender.canonical_model or {}).get("facts", {}).get("project_type") or "OBRA_PUBLICA").upper()
        document_version = self.extractor.detect_document_version(
            extracted, extraction_config.get("document_version_pattern")
        )
        physical_format = str(extracted.metadata.get("format") or "UNKNOWN").upper()
        detected_format_codes = [str(x.get("code") or "").upper() for x in detected_formats if isinstance(x, dict) and x.get("code")]
        selected_format = detected_format_codes[0] if detected_format_codes else physical_format
        if selected_format not in {"PDF", "DOCX", "XLSX"} and selected_format not in {str(k).upper() for k in (extraction_config.get("format_codes") or [])}:
            # The extractor receives the official format code when configured;
            # otherwise it falls back to the physical document format.
            selected_format = physical_format
        allowed_roles = set(extraction_config.get("source_roles") or {})
        if allowed_roles and source_role not in allowed_roles:
            raise MegalodonException(
                ErrorCode.PARAMETRO_INVALIDO,
                f"El tipo de fuente {source_role} no está configurado para la dependencia seleccionada.",
                422,
            )
        path = f"tenders/{self.user.tenant_id}/{tender.id}/sources/r{tender.current_revision}/{digest[:16]}-{safe_name}"
        stored = await storage_documentos().subir(path, content, content_type or "application/octet-stream")
        extraction_uri = None
        if extracted.text:
            extraction_payload = extracted.text.encode("utf-8")
            extraction_hash = sha256(extraction_payload).hexdigest()
            extraction_uri = f"tenders/{self.user.tenant_id}/{tender.id}/sources/r{tender.current_revision}/{digest[:16]}-{safe_name}.txt"
            await storage_documentos().subir(extraction_uri, extraction_payload, "text/plain; charset=utf-8")
        evidence = TenderEvidence(
            tender_id=tender.id, kind="SOURCE_DOCUMENT", subject=filename,
            value={
                "media_type": content_type, "size_bytes": len(content),
                "extraction": extracted.metadata, "pages": extracted.pages,
                "extraction_sha256": extraction_hash if extracted.text else None,
                "format_detection": detected_formats,
                "source_role": source_role,
                "flow_code": flow_code,
                "document_version": document_version,
                "requirement_candidates": self.extractor.extract_requirement_candidates(
                    extracted, source_id=digest, source_hash=digest, source_role=source_role,
                    extraction_config=extraction_config, format_code=selected_format, physical_format=physical_format,
                    flow_code=flow_code, dependency_code=tender.jurisdiction_code, document_version=document_version, source_revision=tender.current_revision,
                ),
                "source_relations": self.extractor.extract_source_relations(
                    extracted, source_id=digest, source_hash=digest, source_role=source_role,
                    dependency_code=tender.jurisdiction_code, flow_code=flow_code, format_code=selected_format,
                    document_version=document_version, source_revision=tender.current_revision,
                ),
            },
            source_uri=stored, extraction_uri=extraction_uri, source_hash=digest, source_revision=tender.current_revision,
            tenant_id=self.user.tenant_id, creado_por_id=self.user.id, actualizado_por_id=self.user.id,
        )
        self.db.add(evidence)
        tender.source_manifest = {**(tender.source_manifest or {}), "sources": [
            *((tender.source_manifest or {}).get("sources", [])),
            {"filename": filename, "storage_path": stored, "sha256": digest, "media_type": content_type, "size_bytes": len(content), "revision": tender.current_revision, "source_role": source_role, "detected_formats": detected_formats},
        ]}
        canonical = dict(tender.canonical_model or {})
        detection = dict(canonical.get("format_detection") or {})
        by_code = {str(x.get("code")): x for x in detection.get("candidates") or [] if isinstance(x, dict) and x.get("code")}
        for candidate in detected_formats:
            by_code[str(candidate["code"])] = candidate
        detection["candidates"] = list(by_code.values())
        detection["last_source_hash"] = digest
        canonical["format_detection"] = detection
        tender.canonical_model = canonical
        if tender.state == TenderState.DISCOVERED.value:
            self._transition(tender, TenderState.INGESTED)
        await self._commit()
        await self.db.refresh(evidence)
        return {"evidence_id": str(evidence.id), "storage_path": stored, "sha256": digest, "size_bytes": len(content), "media_type": content_type, "source_role": source_role, "detected_formats": detected_formats, "requirement_candidates": (evidence.value or {}).get("requirement_candidates", [])}

    async def requirement_candidates(self, tender_id: UUID) -> list[dict[str, Any]]:
        tender = await self._get(tender_id)
        evidence = (await self.db.execute(select(TenderEvidence).where(
            TenderEvidence.tender_id == tender.id,
            TenderEvidence.tenant_id == self.user.tenant_id,
            TenderEvidence.kind == "SOURCE_DOCUMENT",
            TenderEvidence.status == "ACTIVE",
        ))).scalars().all()
        result: list[dict[str, Any]] = []
        for item in evidence:
            value = item.value or {}
            for candidate in value.get("requirement_candidates") or []:
                if isinstance(candidate, dict):
                    result.append({
                        **candidate,
                        "candidate_id": _requirement_candidate_identity(item.id, item.source_hash, candidate),
                        "evidence_id": str(item.id),
                        "source_role": value.get("source_role"),
                    })
        return result

    async def confirm_requirement_candidates(
        self,
        tender_id: UUID,
        candidates: list[RequirementCandidateConfirmation | dict[str, Any]],
    ) -> list[dict[str, Any]]:
        tender = await self._get(tender_id, for_update=True)
        _ensure_tender_mutation_allowed(tender, "confirmación de requisitos")

        requested: list[RequirementCandidateConfirmation] = []
        for raw_candidate in candidates:
            if isinstance(raw_candidate, RequirementCandidateConfirmation):
                patch = raw_candidate
            else:
                try:
                    patch = RequirementCandidateConfirmation.model_validate(raw_candidate)
                except ValidationError as exc:
                    raise MegalodonException(
                        ErrorCode.PARAMETRO_INVALIDO,
                        "La confirmación requiere candidate_id, evidence_id, código, descripción, categoría y obligatoriedad booleana.",
                        422,
                    ) from exc
            if not patch.description.strip() or not patch.category.strip() or not patch.code.strip():
                raise MegalodonException(
                    ErrorCode.PARAMETRO_INVALIDO,
                    "La confirmación requiere código, descripción y categoría no vacíos.",
                    422,
                )
            requested.append(patch.model_copy(update={
                "code": patch.code.strip(),
                "description": patch.description.strip(),
                "category": patch.category.strip().upper(),
            }))

        if not requested:
            raise MegalodonException(ErrorCode.PARAMETRO_INVALIDO, "No se proporcionaron candidatos para confirmar.", 422)
        requested_ids = [candidate.candidate_id for candidate in requested]
        if len(set(requested_ids)) != len(requested_ids):
            raise MegalodonException(ErrorCode.PARAMETRO_INVALIDO, "La solicitud contiene candidatos duplicados.", 422)

        evidence = (await self.db.execute(select(TenderEvidence).where(
            TenderEvidence.tender_id == tender.id,
            TenderEvidence.tenant_id == self.user.tenant_id,
            TenderEvidence.kind == "SOURCE_DOCUMENT",
            TenderEvidence.status == "ACTIVE",
        ))).scalars().all()

        candidate_index: dict[str, tuple[TenderEvidence, dict[str, Any], dict[str, Any]]] = {}
        values_by_evidence: dict[str, dict[str, Any]] = {}
        for item in evidence:
            value = item.value or {}
            values_by_evidence[str(item.id)] = copy.deepcopy(value)
            for candidate in value.get("requirement_candidates") or []:
                if isinstance(candidate, dict):
                    identity = _requirement_candidate_identity(item.id, item.source_hash, candidate)
                    candidate_index[identity] = (item, candidate, value)

        resolved: list[tuple[RequirementCandidateConfirmation, TenderEvidence, dict[str, Any]]] = []
        for patch in requested:
            match = candidate_index.get(patch.candidate_id)
            if match is None:
                raise MegalodonException(
                    ErrorCode.CONFLICT,
                    "El candidato cambió, ya no existe o dejó de pertenecer a una fuente activa. Recarga y revisa de nuevo.",
                    409,
                )
            item, stored_candidate, source_value = match
            if str(item.id) != str(patch.evidence_id) or str(stored_candidate.get("code") or "").strip() != patch.code:
                raise MegalodonException(
                    ErrorCode.CONFLICT,
                    "La identidad del candidato no coincide con la fuente y el código actuales.",
                    409,
                )
            resolved.append((patch, item, stored_candidate))

        # Repeated official codes are scoped to sources for editing, but they must
        # not silently produce two contradictory effective requirements.
        definitions_by_code: dict[str, tuple[str, str, bool]] = {}
        for _, stored_candidate, _ in candidate_index.values():
            if str(stored_candidate.get("status") or "") != "CONFIRMED":
                continue
            code = str(stored_candidate.get("code") or "").strip()
            mandatory = stored_candidate.get("mandatory")
            if not isinstance(mandatory, bool):
                raise MegalodonException(
                    ErrorCode.CONFLICT,
                    f"El requisito {code} aparece confirmado sin obligatoriedad booleana válida.",
                    409,
                )
            definition = (
                str(stored_candidate.get("description") or "").strip(),
                str(stored_candidate.get("category") or "ADMINISTRATIVO").strip().upper(),
                mandatory,
            )
            previous = definitions_by_code.get(code)
            if previous is not None and previous != definition:
                raise MegalodonException(
                    ErrorCode.CONFLICT,
                    f"El código {code} tiene definiciones confirmadas distintas entre fuentes. Debe conciliarse antes de continuar.",
                    409,
                )
            definitions_by_code[code] = definition

        for patch, _, _ in resolved:
            definition = (patch.description, patch.category, patch.mandatory)
            previous = definitions_by_code.get(patch.code)
            if previous is not None and previous != definition:
                raise MegalodonException(
                    ErrorCode.CONFLICT,
                    f"El código {patch.code} aparece en varias fuentes con definiciones diferentes. La confirmación se bloqueó sin cambios para evitar perder una obligación.",
                    409,
                )
            definitions_by_code[patch.code] = definition

        changed: list[dict[str, Any]] = []
        touched_evidence: set[str] = set()
        for patch, item, stored_candidate in resolved:
            evidence_id = str(item.id)
            value = values_by_evidence[evidence_id]
            source_candidates = list(value.get("requirement_candidates") or [])
            target = next(
                (
                    candidate for candidate in source_candidates
                    if isinstance(candidate, dict)
                    and _requirement_candidate_identity(item.id, item.source_hash, candidate) == patch.candidate_id
                ),
                None,
            )
            if target is None:
                raise MegalodonException(
                    ErrorCode.CONFLICT,
                    "El candidato cambió durante la confirmación. Recarga el expediente y vuelve a revisar.",
                    409,
                )

            if str(target.get("status") or "") != "CONFIRMED":
                target["description"] = patch.description
                target["category"] = patch.category
                target["mandatory"] = patch.mandatory
                target["status"] = "CONFIRMED"
                source_reference = target.get("source_reference")
                if not isinstance(source_reference, dict):
                    source_reference = {}
                source_reference["confirmation_required"] = False
                source_reference["confirmed_by_user_id"] = str(self.user.id)
                target["source_reference"] = source_reference
                value["requirement_candidates"] = source_candidates
                touched_evidence.add(evidence_id)
            changed.append({
                **target,
                "candidate_id": patch.candidate_id,
                "evidence_id": evidence_id,
                "source_role": value.get("source_role"),
            })

        for item in evidence:
            evidence_id = str(item.id)
            if evidence_id in touched_evidence:
                item.value = values_by_evidence[evidence_id]

        if touched_evidence:
            try:
                await self.derive_requirements(tender.id)
            except Exception:
                await self.db.rollback()
                raise
        return changed

    async def requirement_source_readiness(self, tender_id: UUID) -> dict[str, Any]:
        """Report whether the user has supplied the official source set needed to work.

        This check is deliberately separate from extraction capability. Missing sources
        are a user/input blocker; sources present but not successfully mapped are an
        engine defect/review state and must never be reported as user omission.
        """
        tender = await self._get(tender_id)
        profile = await self._effective_profile(tender.jurisdiction_code)
        cfg = ((profile.templates or {}).get("requirement_extraction") if profile else None) or {}
        required = [str(x).upper() for x in (cfg.get("required_source_roles") or ["CONVOCATORIA"]) ]
        evidence = (await self.db.execute(select(TenderEvidence).where(
            TenderEvidence.tender_id == tender.id,
            TenderEvidence.tenant_id == self.user.tenant_id,
            TenderEvidence.kind == "SOURCE_DOCUMENT",
            TenderEvidence.status == "ACTIVE",
        ))).scalars().all()
        uploaded = {str((e.value or {}).get("source_role") or "").upper() for e in evidence}
        missing = [role for role in required if role not in uploaded]
        candidate_count = sum(len((e.value or {}).get("requirement_candidates") or []) for e in evidence)
        confirmed_count = sum(
            sum(1 for c in ((e.value or {}).get("requirement_candidates") or [])
                if isinstance(c, dict) and c.get("status") == "CONFIRMED")
            for e in evidence
        )
        return {
            "ready": not missing,
            "required_source_roles": required,
            "uploaded_source_roles": sorted(x for x in uploaded if x),
            "missing_source_roles": missing,
            "candidate_count": candidate_count,
            "confirmed_candidate_count": confirmed_count,
            "engine": "MECHANICAL_DETERMINISTIC",
            "ai": False,
        }

    async def derive_requirements(self, tender_id: UUID) -> list[TenderRequirement]:
        tender = await self._get(tender_id, for_update=True)
        _ensure_tender_mutation_allowed(tender, "derivación de requisitos")
        evidence = (await self.db.execute(select(TenderEvidence).where(
            TenderEvidence.tender_id == tender.id,
            TenderEvidence.tenant_id == self.user.tenant_id,
            TenderEvidence.kind == "SOURCE_DOCUMENT",
            TenderEvidence.status == "ACTIVE",
        ))).scalars().all()
        source_texts = []
        for item in evidence:
            value = item.value or {}
            candidates = [c for c in (value.get("requirement_candidates") or []) if isinstance(c, dict)]
            # Only candidates explicitly confirmed by the user can become effective requirements.
            confirmed = [c for c in candidates if c.get("status") == "CONFIRMED" and c.get("description")]
            source_texts.append({
                "source_id": str(item.id),
                "source_hash": item.source_hash,
                "uri": item.source_uri,
                "document_id": str(item.id),
                "revision": item.source_revision,
                "source_role": value.get("source_role"),
                "requirements": confirmed,
            })
        try:
            mined = self.requirement_mapper.derive(
                tender_id=tender.id,
                source_texts=source_texts,
                facts=tender.canonical_model.get("facts", {}),
            )
        except ValueError as exc:
            raise MegalodonException(
                ErrorCode.CONFLICT,
                str(exc),
                409,
            ) from exc

        existing = (await self.db.execute(select(TenderRequirement).where(
            TenderRequirement.tender_id == tender.id,
            TenderRequirement.tenant_id == self.user.tenant_id,
        ))).scalars().all()
        existing_by_code = {row.code: row for row in existing}

        # Validate all collisions before mutating requirements or provenance. This
        # prevents a conflicting source from leaving a partial derivation behind.
        for req in mined:
            row = existing_by_code.get(req.code)
            if row is not None and _requirement_definition_signature(row) != _requirement_definition_signature(req):
                raise MegalodonException(
                    ErrorCode.CONFLICT,
                    f"El código {req.code} ya existe con una definición distinta. La derivación se bloqueó para conservar la obligación vigente.",
                    409,
                )

        rows = list(existing)
        for req in mined:
            existing_row = existing_by_code.get(req.code)
            if existing_row is not None:
                merged_reference = _merge_requirement_provenance(
                    existing_row.source_reference or {},
                    req.source_reference or {},
                )
                if merged_reference != (existing_row.source_reference or {}):
                    existing_row.source_reference = merged_reference
                continue

            source_reference = dict(req.source_reference)
            source_reference["authority"] = "TENDER_SOURCE"
            row = TenderRequirement(
                tender_id=tender.id, tenant_id=self.user.tenant_id,
                creado_por_id=self.user.id, actualizado_por_id=self.user.id,
                code=req.code, category=req.category, description=req.description, mandatory=req.mandatory,
                condition=req.condition, source_reference=source_reference, legal_rule_id=None, legal_article_id=None,
                evidence_required=req.evidence_required, artifact_required=req.artifact_required,
                validator_code=req.validator_code, approver_role=req.approver_role, severity=req.severity,
                status=RequirementStatus.PENDING.value,
            )
            self.db.add(row)
            rows.append(row)
            existing_by_code[row.code] = row
        if mined:
            if tender.state == TenderState.INGESTED.value:
                self._transition(tender, TenderState.JURISDICTIONED)
            if tender.state == TenderState.JURISDICTIONED.value:
                self._transition(tender, TenderState.REQUIREMENTS_MAPPED)
        await self._commit()
        for row in rows:
            await self.db.refresh(row)
        return rows

    async def add_requirement(self, tender_id: UUID, data: RequirementCreate) -> TenderRequirement:
        tender = await self._get(tender_id, for_update=True)
        _ensure_tender_mutation_allowed(tender, "alta de requisitos")
        exists = await self.db.scalar(
            select(TenderRequirement).where(
                TenderRequirement.tender_id == tender.id,
                TenderRequirement.tenant_id == self.user.tenant_id,
                TenderRequirement.code == data.code,
            )
        )
        if exists:
            raise MegalodonException(ErrorCode.CONFLICT, "El requisito ya existe.", 409)
        data_dict = data.model_dump()
        source_ref = dict(data_dict.get("source_reference") or {})
        # Manual creation is valid in the client's editable Workspace. The workspace
        # is an explicit human-authorized proposal layer; it is not a normative source.
        workspace_document_id = source_ref.get("workspace_document_id") or source_ref.get("document_id")
        if workspace_document_id and str(source_ref.get("authority") or "").upper() == "WORKSPACE_EDIT":
            try:
                workspace_row = await self.db.scalar(select(TenderDocument).where(
                    TenderDocument.id == UUID(str(workspace_document_id)),
                    TenderDocument.tender_id == tender.id,
                    TenderDocument.tenant_id == self.user.tenant_id,
                ))
            except (ValueError, TypeError):
                workspace_row = None
            if workspace_row is None:
                raise MegalodonException(ErrorCode.DOCUMENTO_NO_ENCONTRADO, "Documento de Workspace no encontrado para este expediente/tenant.", 404)
            if not workspace_row.human_modified or workspace_row.locked:
                raise MegalodonException(ErrorCode.VALIDACION_FALLIDA, "El requisito manual solo puede incorporarse desde una edición vigente y editable del Workspace.", 422)
            expected_version = source_ref.get("document_version") or source_ref.get("version")
            if expected_version is not None and int(expected_version) != int(workspace_row.version):
                raise MegalodonException(ErrorCode.CONFLICT, "La versión del Workspace indicada ya no es la vigente.", 409)
            data_dict["source_reference"] = {
                **source_ref,
                "authority": "WORKSPACE_EDIT",
                "workspace_document_id": str(workspace_row.id),
                "document": workspace_row.name,
                "document_version": workspace_row.version,
                "tender_revision": workspace_row.tender_revision,
                "workspace_human_modified": True,
            }
            legal_rule_id = None
            legal_article_id = None
            # Workspace editing is already an explicit user action. Normative references
            # may be attached later for validation, but never supply the proposal text.
            source_ref = data_dict["source_reference"]
            evidence_id = None
        else:
            evidence_id = source_ref.get("evidence_id") or source_ref.get("source_id")
            if not evidence_id:
                raise MegalodonException(
                    ErrorCode.VALIDACION_FALLIDA,
                    "Un requisito de propuesta debe provenir de una fuente oficial cargada o de una edición explícita del Workspace. Indique evidence_id/source_id o workspace_document_id con authority=WORKSPACE_EDIT.",
                    422,
                )
        if evidence_id is not None:
            try:
                evidence_row = await self.db.scalar(select(TenderEvidence).where(
                    TenderEvidence.id == UUID(str(evidence_id)),
                    TenderEvidence.tender_id == tender.id,
                    TenderEvidence.tenant_id == self.user.tenant_id,
                    TenderEvidence.kind == "SOURCE_DOCUMENT",
                    TenderEvidence.status == "ACTIVE",
                ))
            except (ValueError, TypeError):
                evidence_row = None
            if evidence_row is None:
                raise MegalodonException(ErrorCode.VALIDACION_FALLIDA, "La fuente oficial indicada no pertenece a este expediente/tenant.", 422)
            candidates = list((evidence_row.value or {}).get("requirement_candidates") or [])
            matched = next((c for c in candidates if isinstance(c, dict) and str(c.get("code")) == str(data.code)), None)
            if not matched or matched.get("status") != "CONFIRMED":
                raise MegalodonException(
                    ErrorCode.VALIDACION_FALLIDA,
                    "El requisito debe existir como candidato extraído de la fuente oficial y estar confirmado por el usuario antes de materializarse.",
                    422,
                )
            data_dict["source_reference"] = {**dict(matched.get("source_reference") or {}), **source_ref, "authority": "TENDER_SOURCE"}
            legal_rule_id = None
            legal_article_id = None
        # A normative reference may be attached as a cross-check, but it is never
        # required to create the proposal requirement and never supplies its text.
        ref = data_dict.get("source_reference") or {}
        if ref.get("legal_rule_id") and ref.get("article_id"):
            legal_rule = await self.db.scalar(select(LegalRule).where(
                LegalRule.rule_id == ref["legal_rule_id"],
                (LegalRule.tenant_id == self.user.tenant_id) | (LegalRule.tenant_id.is_(None)),
            ))
            if legal_rule is not None:
                try:
                    article = await self.db.scalar(select(LegalArticle).join(LegalSource).where(
                        LegalArticle.id == UUID(str(ref["article_id"])),
                        LegalSource.id == LegalArticle.source_id,
                        (LegalSource.tenant_id == self.user.tenant_id) | (LegalSource.tenant_id.is_(None)),
                    ))
                except (ValueError, TypeError):
                    article = None
                if article is not None and article.source_id == legal_rule.source_id:
                    legal_rule_id = legal_rule.id
                    legal_article_id = article.id
        row = TenderRequirement(
            tender_id=tender.id, tenant_id=self.user.tenant_id, creado_por_id=self.user.id, actualizado_por_id=self.user.id,
            legal_rule_id=legal_rule_id, legal_article_id=legal_article_id,
            **{("artifact_metadata" if k == "metadata" else k): v for k, v in data_dict.items()},
        )
        self.db.add(row)
        await self.db.flush()
        if data.condition.get("conditions"):
            rule_definition = {
                "id": data.code,
                "message": data.condition.get("message", data.description),
                "severity": data.severity,
                "logic": data.condition.get("logic", "ALL"),
                "conditions": data.condition.get("conditions") or [],
            }
            try:
                compiled = self.rule_compiler.compile(rule_definition, version=1)
            except RuleCompilationError as exc:
                raise MegalodonException(ErrorCode.PARAMETRO_INVALIDO, str(exc), 422) from exc
            definition_row = TenderRuleDefinition(
                tender_id=tender.id, tenant_id=self.user.tenant_id, requirement_id=row.id,
                code=data.code, version=compiled.version, status="DRAFT", definition=compiled.definition,
                test_cases=[], compiled_hash=compiled.compiled_hash, source_reference=data.source_reference,
                creado_por_id=self.user.id, actualizado_por_id=self.user.id,
            )
            self.db.add(definition_row)
            await self.db.flush()
            row.rule_definition_id = definition_row.id
        if tender.state in {TenderState.INGESTED.value, TenderState.JURISDICTIONED.value}:
            self._transition(tender, TenderState.REQUIREMENTS_MAPPED)
        tender.updated_at = datetime.now(timezone.utc)
        await self._commit()
        await self.db.refresh(row)
        return row

    async def validate_requirement_rule(self, tender_id: UUID, requirement_id: UUID, test_cases: list[dict] | None = None) -> dict:
        tender = await self._get(tender_id, for_update=True)
        _ensure_tender_mutation_allowed(tender, "activación de reglas")
        requirement = await self.db.scalar(select(TenderRequirement).where(
            TenderRequirement.id == requirement_id,
            TenderRequirement.tender_id == tender.id,
            TenderRequirement.tenant_id == self.user.tenant_id,
        ))
        if requirement is None:
            raise MegalodonException(ErrorCode.DOCUMENTO_NO_ENCONTRADO, "Requisito no encontrado.", 404)
        definition = await self.db.scalar(select(TenderRuleDefinition).where(
            TenderRuleDefinition.id == requirement.rule_definition_id,
            TenderRuleDefinition.tender_id == tender.id,
            TenderRuleDefinition.tenant_id == self.user.tenant_id,
        ))
        if definition is None:
            raise MegalodonException(ErrorCode.VALIDACION_FALLIDA, "El requisito no tiene una definición de regla versionada.", 409)
        if definition.status != "DRAFT":
            raise MegalodonException(ErrorCode.CONFLICT, "Las versiones activas/retiradas son inmutables; crea una nueva versión para modificar la regla.", 409)
        compiled = (
            self.rule_compiler.compile_decision_table(definition.definition, version=definition.version)
            if definition.definition.get("rows") is not None
            else self.rule_compiler.compile(definition.definition, version=definition.version)
        )
        cases = test_cases if test_cases is not None else list(definition.test_cases or [])
        if not cases:
            raise MegalodonException(ErrorCode.VALIDACION_FALLIDA, "Una regla no puede activarse sin casos de prueba ejecutados.", 422)
        results = (
            self.rule_compiler.test_decision_table(compiled, cases)
            if hasattr(compiled, "rows")
            else self.rule_compiler.test(compiled, cases)
        )
        if any(not result["passed"] for result in results):
            definition.compiled_hash = compiled.compiled_hash
            definition.test_cases = cases
            await self._commit()
            return {"status": "DRAFT", "rule_id": definition.code, "version": definition.version, "tests": results}
        definition.status = "ACTIVE"
        definition.compiled_hash = compiled.compiled_hash
        definition.test_cases = cases
        definition.activated_at = datetime.now(timezone.utc).isoformat()
        requirement.status = RequirementStatus.PENDING.value
        requirement.evaluated_at = None
        requirement.actualizado_por_id = self.user.id
        await self._commit()
        return {"status": "ACTIVE", "rule_id": definition.code, "version": definition.version, "compiled_hash": compiled.compiled_hash, "tests": results}

    async def create_requirement_rule_version(self, tender_id: UUID, requirement_id: UUID, definition: dict, test_cases: list[dict] | None = None) -> dict:
        tender = await self._get(tender_id, for_update=True)
        _ensure_tender_mutation_allowed(tender, "nueva versión de regla")
        requirement = await self.db.scalar(select(TenderRequirement).where(
            TenderRequirement.id == requirement_id,
            TenderRequirement.tender_id == tender.id,
            TenderRequirement.tenant_id == self.user.tenant_id,
        ))
        if requirement is None:
            raise MegalodonException(ErrorCode.DOCUMENTO_NO_ENCONTRADO, "Requisito no encontrado.", 404)
        previous = await self.db.scalar(select(TenderRuleDefinition).where(
            TenderRuleDefinition.requirement_id == requirement.id,
            TenderRuleDefinition.tenant_id == self.user.tenant_id,
        ).order_by(TenderRuleDefinition.version.desc()))
        version = (previous.version + 1) if previous else 1
        source = dict(definition)
        source["id"] = requirement.code
        compiled = (
            self.rule_compiler.compile_decision_table(source, version=version)
            if source.get("rows") is not None
            else self.rule_compiler.compile(source, version=version)
        )
        cases = list(test_cases or [])
        if not cases:
            raise MegalodonException(ErrorCode.VALIDACION_FALLIDA, "La nueva versión requiere casos de prueba antes de activarse.", 422)
        results = (
            self.rule_compiler.test_decision_table(compiled, cases)
            if hasattr(compiled, "rows")
            else self.rule_compiler.test(compiled, cases)
        )
        if any(not result["passed"] for result in results):
            raise MegalodonException(ErrorCode.VALIDACION_FALLIDA, "La nueva versión de regla no pasa sus casos de prueba.", 422)
        if previous is not None:
            previous.status = "RETIRED"
            previous.retired_at = datetime.now(timezone.utc).isoformat()
        normalized_definition = compiled.source_definition if hasattr(compiled, "source_definition") else compiled.definition
        row = TenderRuleDefinition(
            tender_id=tender.id, tenant_id=self.user.tenant_id, requirement_id=requirement.id,
            code=requirement.code, version=version, status="ACTIVE", definition=normalized_definition,
            test_cases=cases, compiled_hash=compiled.compiled_hash, source_reference=requirement.source_reference or {},
            activated_at=datetime.now(timezone.utc).isoformat(), creado_por_id=self.user.id, actualizado_por_id=self.user.id,
        )
        self.db.add(row)
        await self.db.flush()
        requirement.rule_definition_id = row.id
        requirement.condition = normalized_definition
        requirement.status = RequirementStatus.PENDING.value
        requirement.evaluated_at = None
        requirement.actualizado_por_id = self.user.id
        await self._commit()
        return {"id": str(row.id), "rule_id": row.code, "version": version, "status": row.status, "compiled_hash": row.compiled_hash, "tests": results}

    async def add_evidence(self, tender_id: UUID, data: EvidenceCreate) -> TenderEvidence:
        tender = await self._get(tender_id, for_update=True)
        _ensure_tender_mutation_allowed(tender, "alta de evidencia")
        allowed_kinds = {
            EvidenceKind.COMPANY_RECORD.value,
            EvidenceKind.EXTERNAL_RECORD.value,
            EvidenceKind.USER_ASSERTION.value,
        }
        if data.kind not in allowed_kinds:
            # Defense in depth for internal calls that bypass Pydantic validation.
            # SOURCE_DOCUMENT must pass through ingest_source(), which hashes and
            # extracts the actual bytes before making it eligible for review gates.
            raise MegalodonException(
                ErrorCode.PARAMETRO_INVALIDO,
                "Este tipo de evidencia sólo puede crearse mediante el flujo interno autorizado.",
                422,
            )
        row = TenderEvidence(
            tender_id=tender.id, tenant_id=self.user.tenant_id, creado_por_id=self.user.id, actualizado_por_id=self.user.id,
            **{("artifact_metadata" if k == "metadata" else k): v for k, v in data.model_dump().items()},
        )
        self.db.add(row)
        await self._commit()
        await self.db.refresh(row)
        return row

    async def link_evidence(self, tender_id: UUID, evidence_id: UUID, requirement_id: UUID | None = None, artifact_id: UUID | None = None, relation: str = "SUPPORTS") -> TenderEvidenceLink:
        tender = await self._get(tender_id, for_update=True)
        _ensure_tender_mutation_allowed(tender, "vinculación de evidencia")
        evidence = await self.db.scalar(select(TenderEvidence).where(
            TenderEvidence.id == evidence_id,
            TenderEvidence.tender_id == tender.id,
            TenderEvidence.tenant_id == self.user.tenant_id,
        ))
        if evidence is None:
            raise MegalodonException(ErrorCode.DOCUMENTO_NO_ENCONTRADO, "Evidencia no encontrada.", 404)
        if requirement_id is not None:
            req = await self.db.scalar(select(TenderRequirement).where(
                TenderRequirement.id == requirement_id,
                TenderRequirement.tender_id == tender.id,
                TenderRequirement.tenant_id == self.user.tenant_id,
            ))
            if req is None:
                raise MegalodonException(ErrorCode.DOCUMENTO_NO_ENCONTRADO, "Requisito no encontrado.", 404)
        if artifact_id is not None:
            art = await self.db.scalar(select(TenderArtifact).where(
                TenderArtifact.id == artifact_id,
                TenderArtifact.tender_id == tender.id,
                TenderArtifact.tenant_id == self.user.tenant_id,
            ))
            if art is None:
                raise MegalodonException(ErrorCode.DOCUMENTO_NO_ENCONTRADO, "Artefacto no encontrado.", 404)
        link = TenderEvidenceLink(
            tender_id=tender.id, evidence_id=evidence.id, requirement_id=requirement_id, artifact_id=artifact_id,
            relation=relation, tenant_id=self.user.tenant_id,
        )
        self.db.add(link)
        await self._commit()
        return link

    async def add_artifact(self, tender_id: UUID, data: ArtifactCreate) -> TenderArtifact:
        tender = await self._get(tender_id, for_update=True)
        _ensure_tender_mutation_allowed(tender, "alta de artefacto")
        if not data.storage_path or not data.content_hash:
            raise MegalodonException(ErrorCode.VALIDACION_FALLIDA, "Un artefacto persistido debe apuntar a un objeto real y declarar su SHA-256.", 422)
        expected_prefix = f"tenders/{self.user.tenant_id}/{tender.id}/"
        if not data.storage_path.startswith(expected_prefix):
            raise MegalodonException(ErrorCode.ARCHIVO_ERROR, "El storage_path del artefacto no pertenece al tenant/tender actual.", 403)
        required_codes = {str(x) for r in (await self.db.execute(select(TenderRequirement).where(
            TenderRequirement.tender_id == tender.id,
            TenderRequirement.tenant_id == self.user.tenant_id,
            TenderRequirement.status != "NOT_APPLICABLE",
        ))).scalars().all() for x in (r.artifact_required or [])}
        if required_codes and data.artifact_code not in required_codes:
            logger.info(
                "procurement_artifact_uploaded_nonrequired_code",
                tender_id=str(tender.id),
                artifact_code=data.artifact_code,
            )
        bucket = storage_exportaciones()
        try:
            content = await bucket.descargar(data.storage_path)
        except Exception as exc:
            raise MegalodonException(ErrorCode.ARCHIVO_ERROR, "No fue posible recuperar el artefacto desde storage.", 409) from exc
        actual_hash = self.compiler.sha256(content)
        if actual_hash != data.content_hash:
            raise MegalodonException(ErrorCode.ARCHIVO_ERROR, "El SHA-256 declarado no coincide con el contenido almacenado.", 409)
        version = (await self.db.scalar(
            select(TenderArtifact.version).where(
                TenderArtifact.tender_id == tender.id,
                TenderArtifact.tenant_id == self.user.tenant_id,
                TenderArtifact.artifact_code == data.artifact_code
            ).order_by(TenderArtifact.version.desc()).limit(1)
        ) or 0) + 1
        row = TenderArtifact(
            tender_id=tender.id, version=version, status=ArtifactStatus.GENERATED.value,
            tenant_id=self.user.tenant_id, creado_por_id=self.user.id, actualizado_por_id=self.user.id,
            source_model_hash=self.orchestrator.canonical_hash(tender.canonical_model),
            **{("artifact_metadata" if k == "metadata" else k): v for k, v in data.model_dump().items()},
        )
        self.db.add(row)
        self.db.add(TenderEvidence(
            tender_id=tender.id, kind="GENERATED_ARTIFACT", subject=data.name,
            value={"artifact_code": data.artifact_code, "version": version, "media_type": data.media_type},
            source_uri=data.storage_path, source_hash=actual_hash, source_revision=tender.current_revision,
            tenant_id=self.user.tenant_id, creado_por_id=self.user.id, actualizado_por_id=self.user.id,
        ))
        await self._commit()
        await self.db.refresh(row)
        return row

    async def create_revision(self, tender_id: UUID, data: RevisionCreate) -> TenderRevision:
        tender = await self._get(tender_id, for_update=True)
        if tender.frozen:
            raise MegalodonException(ErrorCode.BAD_REQUEST, "El expediente ya está congelado.", 400)
        terminal_states = {
            TenderState.SUBMITTED.value,
            TenderState.ARCHIVED.value,
            TenderState.CANCELLED.value,
            TenderState.EXPIRED.value,
            TenderState.SUPERSEDED.value,
        }
        if tender.state in terminal_states:
            raise MegalodonException(
                ErrorCode.CONFLICT,
                "Un expediente enviado o terminal no puede reabrirse mediante una nueva revisión.",
                409,
            )
        previous = tender.canonical_model or {}
        snapshot = data.model_snapshot if data.model_snapshot is not None else previous
        revision_number = tender.current_revision + 1

        def changed_paths(a: object, b: object, prefix: str = "") -> list[str]:
            if isinstance(a, dict) and isinstance(b, dict):
                keys = set(a) | set(b)
                result: list[str] = []
                for key in sorted(keys):
                    path = f"{prefix}.{key}" if prefix else str(key)
                    result.extend(changed_paths(a.get(key), b.get(key), path))
                return result
            if isinstance(a, list) and isinstance(b, list):
                if a == b:
                    return []
                return [prefix or "*"]
            return [] if a == b else [prefix or "*"]

        changed = changed_paths(previous, snapshot)
        impacted = sorted(set(path.split(".", 1)[0] for path in changed))
        impact_summary = {
            "changed_paths": changed,
            "impacted_domains": impacted,
            "invalidates_signed": bool(changed),
            "previous_revision": tender.current_revision,
        }
        row = TenderRevision(
            tender_id=tender.id, revision=revision_number, reason=data.reason,
            source_hash=data.source_hash or self._hash(snapshot), model_snapshot=snapshot,
            impact_summary=impact_summary, tenant_id=self.user.tenant_id,
        )
        tender.current_revision = revision_number
        tender.canonical_model = snapshot
        tender.frozen = False
        tender.state = TenderState.OBSERVED.value
        tender.review_state = None
        requirements = (await self.db.execute(
            select(TenderRequirement).where(
                TenderRequirement.tender_id == tender.id,
                TenderRequirement.tenant_id == self.user.tenant_id,
            ).with_for_update()
        )).scalars().all()
        for requirement in requirements:
            requirement.status = RequirementStatus.PENDING.value
            requirement.evaluated_at = None
            requirement.actualizado_por_id = self.user.id

        artifacts = (await self.db.execute(select(TenderArtifact).where(
            TenderArtifact.tender_id == tender.id,
            TenderArtifact.tenant_id == self.user.tenant_id,
            TenderArtifact.status != ArtifactStatus.SUPERSEDED.value,
        ))).scalars().all()
        for artifact in artifacts:
            artifact.status = ArtifactStatus.SUPERSEDED.value
        submissions = (await self.db.execute(select(SubmissionPackage).where(
            SubmissionPackage.tender_id == tender.id,
            SubmissionPackage.tenant_id == self.user.tenant_id,
            SubmissionPackage.status != "SUPERSEDED",
        ))).scalars().all()
        for submission in submissions:
            submission.status = "SUPERSEDED"

        dependencies = (await self.db.execute(select(TenderDependency).where(
            TenderDependency.tender_id == tender.id,
            TenderDependency.tenant_id == self.user.tenant_id,
            TenderDependency.invalidates_signed.is_(True),
        ))).scalars().all()
        for dep in dependencies:
            if dep.source_key.split('.', 1)[0] in impacted:
                dep.artifact_metadata = {**(dep.artifact_metadata or {}), "invalidated_revision": revision_number}

        self.db.add(row)
        await self._commit()
        await self.db.refresh(row)
        return row

    async def resolve_jurisdiction(self, tender_id: UUID) -> TenderPackage:
        tender = await self._get(tender_id)
        metadata = dict(tender.source_manifest or {})
        decision = await self.jurisdiction.resolve_db(self.db, self.user.tenant_id, {
            **metadata, "jurisdiction_code": tender.jurisdiction_code,
        })
        tender.jurisdiction_code = decision.code
        tender.canonical_model = {
            **tender.canonical_model,
            "jurisdiction": decision.__dict__,
            "jurisdiction_code": decision.code,
        }
        if tender.state in {TenderState.INGESTED.value, TenderState.OBSERVED.value}:
            self._transition(tender, TenderState.JURISDICTIONED)
        await self._commit()
        await self.db.refresh(tender)
        return tender

    async def recommend_procedure(
        self,
        *,
        jurisdiction_code: str,
        monto: float,
        es_obra_publica: bool = True,
        presupuesto_dependencia_miles: float | None = None,
        ejercicio_fiscal: int = 2026,
        excepcion_legal: str | None = None,
        justificacion_excepcion: str | None = None,
        investigacion_mercado_realizada: bool = False,
        tender_id: UUID | None = None,
        flow_mode: str = "LICITANTE",
        procedure_type_declared: str | None = None,
    ) -> dict:
        """Recomienda procedimiento desde umbrales DB + excepciones LegalRule.

        flow_mode:
          CONVOCANTE — planeación previa a publicar convocatoria; puede exigir
            presupuesto_dependencia_miles (Anexo 9) y materializar en tender.
          LICITANTE — respuesta a convocatoria ya publicada; el procedimiento
            suele venir declarado. No exige presupuesto de dependencia y
            NUNCA materializa procedure_type desde umbrales (solo orienta).
        """
        from app.services.juridico_service import JuridicoService

        mode = (flow_mode or "LICITANTE").strip().upper()
        if mode not in {"LICITANTE", "CONVOCANTE"}:
            mode = "LICITANTE"

        # --- Modo LICITANTE con procedimiento ya declarado en convocatoria ---
        declared = (procedure_type_declared or "").strip().upper() or None
        if tender_id is not None and not declared:
            try:
                tender_existing = await self._get(tender_id)
                declared = (tender_existing.procedure_type or "").strip().upper() or None
            except Exception:
                declared = None

        if mode == "LICITANTE" and declared in {"LICITACION_PUBLICA", "INVITACION", "ADJUDICACION"}:
            return {
                "valido": True,
                "flow_mode": mode,
                "procedimiento": declared,
                "procedure_type": declared,
                "fuente": "CONVOCATORIA_DECLARADA",
                "datos_verificados": True,
                "es_candidato": False,
                "materialized": False,
                "materialize_blocked_reason": "MODO_LICITANTE_PROCEDIMIENTO_YA_DECLARADO",
                "observaciones": [
                    "Modo LICITANTE: el procedimiento proviene de la convocatoria publicada; "
                    "no se recalcula ni se materializa desde umbrales Anexo 9."
                ],
                "umbrales": None,
                "justificacion": {
                    "fundamento": "Procedimiento declarado por la convocante en la convocatoria.",
                    "ley": None,
                    "articulo": None,
                },
                "garantias_hint": {
                    "cumplimiento": "Resolver desde LegalRule GARANTIAS al adjudicar.",
                    "seriedad": "Solo si la convocatoria/case_pack exige garantía de seriedad.",
                },
            }

        # --- CONVOCANTE: presupuesto dependencia obligatorio si hay tabla escalonada federal ---
        if mode == "CONVOCANTE" and presupuesto_dependencia_miles is None:
            # Solo bloquear si el código es federal o hereda umbrales federales escalonados.
            # El motor igual puede fallar closed; aquí damos error de dominio claro.
            code_u = str(jurisdiction_code).upper()
            if code_u.startswith("MX-FED") or code_u in {"MX-FED-OBRA", "MX-FED-ADQ"}:
                return {
                    "valido": False,
                    "flow_mode": mode,
                    "procedimiento": None,
                    "procedure_type": None,
                    "datos_verificados": False,
                    "es_candidato": False,
                    "materialized": False,
                    "materialize_blocked_reason": "FALTA_PRESUPUESTO_DEPENDENCIA_ANEXO9",
                    "observaciones": [
                        "Modo CONVOCANTE federal: se requiere presupuesto autorizado de la "
                        "dependencia en miles de pesos (Anexo 9 PEF) para elegir el tramo de umbrales."
                    ],
                    "umbrales": None,
                }

        service = JuridicoService(self.db, tenant_id=self.user.tenant_id)
        result = await service.determinar_procedimiento(
            monto=monto,
            tipo_contratacion="OBRA_PUBLICA" if es_obra_publica else "ADQUISICION",
            es_obra_publica=es_obra_publica,
            jurisdiction_code=jurisdiction_code,
            ejercicio_fiscal=ejercicio_fiscal,
            presupuesto_dependencia_miles=presupuesto_dependencia_miles,
            excepcion_legal=excepcion_legal,
            justificacion_excepcion=justificacion_excepcion,
            investigacion_mercado_realizada=investigacion_mercado_realizada,
            tenant_id=self.user.tenant_id,
        )

        map_proc = {
            "LICITACION_PUBLICA": "LICITACION_PUBLICA",
            "INVITACION_TRES": "INVITACION",
            "ADJUDICACION_DIRECTA": "ADJUDICACION",
        }
        recommended = map_proc.get(result.get("procedimiento"), result.get("procedimiento"))
        result["procedure_type"] = recommended
        result["flow_mode"] = mode

        # Materialización: solo CONVOCANTE + verificado + no candidato
        can_materialize = (
            mode == "CONVOCANTE"
            and bool(result.get("valido"))
            and not bool(result.get("es_candidato"))
            and bool(result.get("datos_verificados"))
        )
        if mode == "LICITANTE":
            result["materialized"] = False
            result["materialize_blocked_reason"] = "MODO_LICITANTE_NO_MATERIALIZA"
            result.setdefault("observaciones", []).append(
                "Modo LICITANTE: la recomendación es orientativa; el procedimiento de la "
                "convocatoria prevalece. No se escribe procedure_type en el tender."
            )
        elif result.get("es_candidato"):
            result.setdefault("observaciones", []).append(
                "Umbral en estado CANDIDATO: recomendación orientativa; no se materializa."
            )
            result["materialized"] = False
            result["materialize_blocked_reason"] = "ESTADO_DATO_CANDIDATO"

        if (
            tender_id is not None
            and can_materialize
            and recommended in {"LICITACION_PUBLICA", "INVITACION", "ADJUDICACION"}
        ):
            tender = await self._get(tender_id, for_update=True)
            profile = await self._effective_profile(tender.jurisdiction_code or jurisdiction_code)
            allowed = set((profile.ruleset or {}).get("allowed_procedures") or []) if profile else set()
            if allowed and recommended not in allowed:
                result["valido"] = False
                result["materialized"] = False
                result.setdefault("observaciones", []).append(
                    f"El procedimiento {recommended} no está en allowed_procedures del perfil {profile.code}."
                )
            else:
                tender.procedure_type = recommended
                model = dict(tender.canonical_model or {})
                facts = dict(model.get("facts") or {})
                facts["procedure_type"] = recommended
                facts["procedure_recommendation"] = {
                    "umbrales": result.get("umbrales"),
                    "fuente_umbral": result.get("fuente_umbral"),
                    "datos_verificados": result.get("datos_verificados"),
                    "es_candidato": result.get("es_candidato"),
                    "justificacion": result.get("justificacion"),
                    "flow_mode": mode,
                }
                model["facts"] = facts
                tender.canonical_model = model
                await self._commit()
                await self.db.refresh(tender)
                result["tender_id"] = str(tender.id)
                result["tender_procedure_type"] = tender.procedure_type
                result["materialized"] = True
        elif tender_id is not None and not can_materialize:
            result["materialized"] = False
            result["tender_id"] = str(tender_id)
        return result





    async def apply_semi_auto_review(self, tender_id: UUID, data: SemiAutoReviewPatch) -> dict:
        """Persist human edits while enforcing revision and server-owned format rules."""
        tender = await self._get(tender_id, for_update=True)
        _ensure_tender_mutation_allowed(tender, "revisión semiautomática")
        model = dict(tender.canonical_model or {})
        facts = dict(model.get("facts") or {})
        if data.authority is not None and str(data.authority).strip():
            facts["authority"] = str(data.authority).strip()
        if data.object is not None and str(data.object).strip():
            facts["object"] = str(data.object).strip()
        model["facts"] = facts

        if data.format_checklist is not None:
            try:
                if tender.case_pack_code:
                    configured_pack = await get_configured_case_pack(
                        self.db,
                        tenant_id=self.user.tenant_id,
                        jurisdiction_code=tender.jurisdiction_code,
                        code=tender.case_pack_code,
                    )
                    if configured_pack is None:
                        raise ValueError(
                            f"El case pack {tender.case_pack_code} no está configurado para la jurisdicción."
                        )
                    authoritative_formats = list(configured_pack.get("artifacts") or [])
                else:
                    format_catalog = await load_format_catalog(
                        self.db,
                        tenant_id=self.user.tenant_id,
                        jurisdiction_code=tender.jurisdiction_code,
                    )
                    authoritative_formats = list(format_catalog.values())
                cleaned = _merge_authoritative_format_checklist(
                    authoritative_formats,
                    data.format_checklist,
                )
            except ValueError as exc:
                raise MegalodonException(
                    ErrorCode.PARAMETRO_INVALIDO,
                    str(exc),
                    422,
                ) from exc
            model["format_checklist"] = cleaned
            required_pending = [
                c["code"] for c in cleaned
                if c.get("required") and c.get("status") not in {"LISTO", "EDITADO"}
            ]
            model["semi_auto"] = {
                "review_reason": data.reason,
                "required_pending": required_pending,
                "ready_to_compile": len(required_pending) == 0,
            }

        if data.budget_total_reference is not None:
            eco = dict(model.get("economic") or {})
            eco["budget_total_reference"] = float(data.budget_total_reference)
            model["economic"] = eco

        previous = tender.canonical_model or {}
        revision_number = int(tender.current_revision or 1) + 1
        row = TenderRevision(
            tender_id=tender.id,
            revision=revision_number,
            reason=data.reason,
            source_hash=self._hash(model),
            model_snapshot=model,
            impact_summary={
                "changed_paths": ["facts", "format_checklist", "semi_auto"],
                "impacted_domains": ["FACTS", "SEMI_AUTO"],
                "invalidates_signed": False,
                "previous_revision": tender.current_revision,
                "soft_patch": True,
            },
            tenant_id=self.user.tenant_id,
        )
        tender.current_revision = revision_number
        tender.canonical_model = model
        # Preserve pipeline state — soft review must not reset to OBSERVED
        self.db.add(row)
        await self._commit()
        return {
            "tender_id": str(tender.id),
            "revision": revision_number,
            "state": tender.state,
            "facts": model.get("facts"),
            "semi_auto": model.get("semi_auto"),
            "format_checklist": model.get("format_checklist"),
            "economic_summary": {
                "budget_total": (model.get("economic") or {}).get("budget_total"),
                "budget_total_reference": (model.get("economic") or {}).get("budget_total_reference"),
                "partidas": len((model.get("economic") or {}).get("partidas") or []),
            },
        }

    async def hydrate_from_presupuesto(
        self,
        tender_id: UUID,
        *,
        presupuesto_id: UUID | None = None,
        overwrite_economic: bool = True,
    ) -> dict:
        """Adjunta el presupuesto programable del expediente al canonical_model del tender.

        Endpoint de semi-automatización: el usuario elige/corrige presupuesto;
        Megalodon no inventa el catálogo — lo toma de MotorCosteo/DB.
        """
        tender = await self._get(tender_id, for_update=True)
        _ensure_tender_mutation_allowed(tender, "rehidratación de presupuesto")
        model = await hydrate_canonical_from_presupuesto(
            self.db,
            tender,
            presupuesto_id=presupuesto_id,
            overwrite_economic=overwrite_economic,
        )
        tender.canonical_model = model
        await self._commit()
        return {
            "tender_id": str(tender.id),
            "bridge": model.get("_bridge"),
            "economic_summary": {
                "budget_total": (model.get("economic") or {}).get("budget_total"),
                "partidas": len((model.get("economic") or {}).get("partidas") or []),
                "monto_directo": (model.get("economic") or {}).get("monto_directo"),
            },
            "facts": model.get("facts") or {},
        }

    async def compile_artifacts(self, tender_id: UUID) -> list[TenderArtifact]:
        tender = await self._get(tender_id, for_update=True)
        _ensure_tender_mutation_allowed(
            tender,
            "compilación de artefactos",
            allow_cross_validated=True,
        )
        # Preserve human review facts/checklist before economic hydrate
        prior = dict(tender.canonical_model or {})
        prior_facts = dict(prior.get("facts") or {})
        prior_checklist = prior.get("format_checklist")
        prior_semi = prior.get("semi_auto")
        # Soft gate: required formats must be LISTO/EDITADO when checklist exists
        if isinstance(prior_checklist, list) and prior_checklist:
            pending = [
                str(i.get("code"))
                for i in prior_checklist
                if isinstance(i, dict)
                and i.get("required", True)
                and str(i.get("status") or "").upper() not in {"LISTO", "EDITADO"}
            ]
            if pending:
                raise MegalodonException(
                    ErrorCode.VALIDACION_FALLIDA,
                    f"Semi-automatización: formatos obligatorios sin LISTO/EDITADO: {', '.join(pending)}",
                    409,
                )
        # Puente real: hidratar economic desde presupuesto programable del expediente
        # (MotorCosteo / PresupuestoService). No inventa montos.
        model = await hydrate_canonical_from_presupuesto(self.db, tender, overwrite_economic=True)
        # Re-apply human facts (authority/object) so hydrate does not erase panel edits
        facts = dict(model.get("facts") or {})
        for key in ("authority", "object", "proposal_validity_days", "duration_days"):
            val = prior_facts.get(key)
            if val not in (None, ""):
                facts[key] = val
        model["facts"] = facts
        if prior_checklist is not None:
            model["format_checklist"] = prior_checklist
        if prior_semi is not None:
            model["semi_auto"] = prior_semi
        tender.canonical_model = model
        await self.db.flush()
        result = await self.orchestrator.run(self.db, tender)
        if result["findings"]:
            await self._commit()
            raise MegalodonException(ErrorCode.VALIDACION_FALLIDA, "No se pueden compilar artefactos con hallazgos bloqueantes o no resueltos.", 409)
        model = tender.canonical_model
        findings = result["findings"]
        artifact_specs: list[tuple[str, str, str, bytes, list[str]]] = []

        # External format selection is DB-driven.  The profile selected at tender
        # creation is the root context; no compiler can cross into another profile.
        jurisdiction_code = (tender.jurisdiction_code or "").strip().upper()
        if not jurisdiction_code:
            raise MegalodonException(ErrorCode.VALIDACION_FALLIDA, "No existe dependencia convocante en el expediente; no se puede seleccionar catálogo de formatos.", 409)
        try:
            format_catalog = await load_format_catalog(
                self.db, tenant_id=self.user.tenant_id, jurisdiction_code=jurisdiction_code
            )
        except ValueError as exc:
            raise MegalodonException(ErrorCode.VALIDACION_FALLIDA, str(exc), 409) from exc

        detected = [str(x).strip() for x in (model.get("detected_formats") or []) if str(x).strip()]
        checklist_codes = [str(x.get("code") or "").strip() for x in (model.get("format_checklist") or []) if isinstance(x, dict) and str(x.get("code") or "").strip()]
        selected_codes = detected or [c for c in checklist_codes if normalize_format_code(c) in format_catalog]
        if not selected_codes:
            # Backward-compatible mode: use the selected dependency's configured
            # formats, but only compile artifacts whose canonical inputs exist.
            selected_codes = list(format_catalog)

        def _get_path(path: str, values: dict) -> Any:
            cur: Any = values
            for part in path.split("."):
                if isinstance(cur, dict): cur = cur.get(part)
                else: return None
            return cur

        def _path_present(path: str, values: dict) -> bool:
            if path.endswith(".conceptos"):
                partidas = _get_path("economic.partidas", values) or []
                return bool(partidas) and any((p or {}).get("conceptos") for p in partidas)
            value = _get_path(path, values)
            return value not in (None, "", [], {})

        workspace_docs_by_code: dict[str, TenderDocument] = {
            d.artifact_code: d
            for d in (await self.db.execute(select(TenderDocument).where(
                TenderDocument.tender_id == tender.id,
                TenderDocument.tenant_id == self.user.tenant_id,
            ).order_by(TenderDocument.version, TenderDocument.id))).scalars().all()
        }

        # Los formatos con plantilla guardan ediciones en claves específicas.
        # Se validan contra el mapa del formato y la revisión de la licitación.
        def _model_con_overrides_humanos(code: str, binding: dict) -> tuple[dict, list[str]]:
            doc = workspace_docs_by_code.get(code)
            if doc is None:
                return model, []
            try:
                return model_with_workspace_overrides(
                    model, binding, doc.content_model,
                    human_modified=doc.human_modified,
                    document_tender_revision=doc.tender_revision,
                    current_tender_revision=tender.current_revision,
                )
            except ValueError as exc:
                raise MegalodonException(
                    ErrorCode.VALIDACION_FALLIDA,
                    f"El anexo {code} requiere revisión de sus campos: {exc}",
                    409,
                ) from exc

        seen_codes: set[str] = set()
        for external_code in selected_codes:
            code = normalize_format_code(external_code)
            if code in seen_codes: continue
            binding = format_catalog.get(code)
            if binding is None:
                raise MegalodonException(ErrorCode.VALIDACION_FALLIDA, f"El formato {external_code} no está configurado para la dependencia {jurisdiction_code}.", 409)
            paths = binding.get("canonical_paths") or []
            modelo_para_compilar, overrides_aplicados = _model_con_overrides_humanos(code, binding)
            missing = [p for p in paths if not _path_present(str(p), modelo_para_compilar)]
            required = bool(binding.get("required", False)) or code in {normalize_format_code(x) for x in detected}
            if missing:
                if required:
                    raise MegalodonException(ErrorCode.VALIDACION_FALLIDA, f"El formato {code} requiere datos canónicos ausentes: {', '.join(map(str, missing))}.", 409)
                continue
            try:
                content = self.compiler.compile_from_binding(binding, modelo_para_compilar)
            except (ValueError, TypeError, KeyError) as exc:
                raise MegalodonException(ErrorCode.VALIDACION_FALLIDA, f"No se pudo compilar {code}: {exc}", 409) from exc
            media = "application/pdf" if str(binding.get("compiler", "")).endswith("pdf") else "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
            artifact_specs.append((code, str(binding.get("title") or code), media, content, overrides_aplicados))
            seen_codes.add(code)

        if not artifact_specs:
            raise MegalodonException(ErrorCode.VALIDACION_FALLIDA, f"La dependencia {jurisdiction_code} no tiene formatos compilables con los datos actuales; configure formatos en DB o complete las fuentes del expediente.", 409)

        case_pack = await get_configured_case_pack(self.db, tenant_id=self.user.tenant_id, jurisdiction_code=jurisdiction_code, code=tender.case_pack_code)
        if case_pack is not None:
            source_templates = (model.get("technical", {}) or {}).get("official_templates", {})
            existing_codes = {code for code, *_ in artifact_specs}
            for spec in case_pack.get("artifacts") or []:
                code = spec.get("code")
                title = spec.get("title") or code
                if code in existing_codes:
                    continue
                if spec.get("requires_uploaded_template") and not source_templates.get(code):
                    raise MegalodonException(ErrorCode.VALIDACION_FALLIDA, f"El paquete {case_pack.get('code')} exige la plantilla oficial {code}; ingrésala como fuente/plantilla antes de compilar.", 409)
                annex_content = self.compiler.compile_annex_pdf(code, title, {**model, "revision": tender.current_revision}, requirement=spec)
                artifact_specs.append((code, title, "application/pdf", annex_content, []))

        artifact_specs.append(("QA-REPORT", "Reporte de QA", "application/pdf", self.compiler.compile_summary_pdf({**model, "revision": tender.current_revision}, findings), []))
        bucket = storage_exportaciones()
        artifacts: list[TenderArtifact] = []
        source_hash = self.orchestrator.canonical_hash(model)

        existing = (await self.db.execute(select(TenderArtifact).where(
            TenderArtifact.tender_id == tender.id,
            TenderArtifact.tenant_id == self.user.tenant_id,
            TenderArtifact.source_model_hash == source_hash,
            TenderArtifact.status != ArtifactStatus.SUPERSEDED.value,
        ))).scalars().all()
        existing_by_code = {a.artifact_code: a for a in existing}

        for code, name, media, content, overrides_aplicados in artifact_specs:
            content_hash = self.compiler.sha256(content)
            case_spec = next(
                (spec for spec in (case_pack.get("artifacts") or []) if spec.get("code") == code),
                None,
            ) if case_pack is not None else None
            source_binding = format_catalog.get(code) or case_spec or {}
            source_templates = (model.get("technical", {}) or {}).get("official_templates", {})
            official_template = bool(source_templates.get(code)) if case_pack is not None else False
            reference_only = bool(case_spec is not None and not official_template)
            internal_qa_report = code.strip().upper() == "QA-REPORT"
            configured_submission = source_binding.get("submission_eligible")
            submission_eligible = (
                configured_submission if isinstance(configured_submission, bool)
                else (not reference_only and not internal_qa_report)
            )
            configured_signature = source_binding.get("signature_required")
            signature_required = (
                False if internal_qa_report else (
                    configured_signature if isinstance(configured_signature, bool)
                    else media == "application/pdf"
                )
            )
            current = existing_by_code.get(code)
            if current and current.content_hash == content_hash and current.storage_path:
                stored = await bucket.descargar(current.storage_path)
                if self.compiler.sha256(stored) == content_hash:
                    current.artifact_metadata = {
                        **(current.artifact_metadata or {}),
                        "submission_eligible": submission_eligible,
                        "signature_required": signature_required,
                        "reference_only": reference_only,
                        "internal_workspace_artifact": internal_qa_report,
                    }
                    artifacts.append(current)
                    continue

            prior = (await self.db.scalar(select(TenderArtifact.version).where(
                TenderArtifact.tender_id == tender.id,
                TenderArtifact.tenant_id == self.user.tenant_id,
                TenderArtifact.artifact_code == code,
            ).order_by(TenderArtifact.version.desc()).limit(1)) or 0)
            version = prior + 1
            extension = ".xlsx" if media.endswith("spreadsheetml.sheet") else ".pdf"
            path = f"tenders/{tender.tenant_id}/{tender.id}/r{tender.current_revision}/{code}-v{version}-{content_hash}{extension}"
            await self.storage_guard.upload_verified(tenant_id=self.user.tenant_id, job_id=None, bucket_name=get_settings().SUPABASE_BUCKET_EXPORTS, path=path, content=content, content_type=media, entity_type="TenderArtifact")
            # Submission and signature eligibility are server-owned format policy.
            artifact = TenderArtifact(
                tender_id=tender.id, artifact_code=code, name=name, media_type=media, version=version,
                status=ArtifactStatus.GENERATED.value, source_model_hash=source_hash, storage_path=path,
                content_hash=content_hash, tenant_id=self.user.tenant_id, creado_por_id=self.user.id, actualizado_por_id=self.user.id,
                artifact_metadata={
                    "revision": tender.current_revision,
                    "canonical_model_hash": source_hash,
                    "submission_eligible": submission_eligible,
                    "signature_required": signature_required,
                    "reference_only": reference_only,
                    "internal_workspace_artifact": internal_qa_report,
                    "human_field_overrides_applied": overrides_aplicados,
                },
            )
            self.db.add(artifact)
            artifacts.append(artifact)
            # Materialize an editable workspace projection alongside the binary artifact.
            # FIX P0 auditoría 2026-09-14: esto ya NO es solo una vitrina de
            # solo-lectura. Si el usuario había guardado content_model.field_overrides
            # human_modified=True para este code, esos valores SÍ se inyectaron
            # en compile_from_binding() (ver _model_con_overrides_humanos arriba)
            # y por tanto SÍ están reflejados en el binario que se acaba de subir.
            # Cuando no hay override humano, este doc sigue siendo la proyección
            # generada libremente reescribible en cada compilación.
            existing_doc = await self.db.scalar(select(TenderDocument).where(
                TenderDocument.tender_id == tender.id, TenderDocument.tenant_id == self.user.tenant_id,
                TenderDocument.artifact_code == code,
            ).order_by(TenderDocument.version.desc(), TenderDocument.id).limit(1))
            # Nota: cuando existing_doc.human_modified es True (justo el caso en
            # que overrides_aplicados puede venir no-vacío), las ramas de abajo
            # NO reescriben content_text/content_model -- se deja intacto el
            # field_overrides que el usuario guardó, que es la fuente real. El
            # rastro verificable de que ese override sí llegó al binario vive en
            # TenderArtifact.artifact_metadata["human_field_overrides_applied"]
            # (siempre se escribe, arriba), no aquí.
            generated_text = f"Artefacto compilado: {code}\nRuta: {path}\nSHA-256: {content_hash}\nRevisión del TenderPackage: {tender.current_revision}"
            generated_model = {"artifact_storage_path": path, "artifact_id": str(artifact.id), "compiled": True}
            if existing_doc is None:
                doc = TenderDocument(
                    tenant_id=self.user.tenant_id, creado_por_id=self.user.id, actualizado_por_id=self.user.id,
                    tender_id=tender.id, artifact_code=code, name=name, media_type=media, content_text=generated_text,
                    content_model=generated_model, status="GENERATED", version=1, tender_revision=tender.current_revision,
                    generated_from_revision=tender.current_revision, generated_model_hash=source_hash, human_modified=False, locked=False,
                    source_evidence_ids=[], requirement_ids=[], data_dependencies=["canonical_model.facts", "canonical_model.technical", "canonical_model.economic", "canonical_model.schedule"], warnings=[],
                )
                self.db.add(doc); await self.db.flush()
                self.db.add(TenderDocumentRevision(tenant_id=self.user.tenant_id, document_id=doc.id, version=1, operation="GENERATE", content_text=generated_text, content_model=generated_model, tender_revision=tender.current_revision, source_model_hash=source_hash, human_modified=False, revision_metadata={"artifact_id": str(artifact.id), "storage_path": path}))
            elif not existing_doc.human_modified and not existing_doc.locked:
                existing_doc.version += 1; existing_doc.content_text = generated_text; existing_doc.content_model = generated_model; existing_doc.tender_revision = tender.current_revision; existing_doc.generated_from_revision = tender.current_revision; existing_doc.generated_model_hash = source_hash; existing_doc.status = "GENERATED"; existing_doc.actualizado_por_id = self.user.id
                await self.db.flush()
                self.db.add(TenderDocumentRevision(tenant_id=self.user.tenant_id, document_id=existing_doc.id, version=existing_doc.version, operation="REGENERATE", content_text=generated_text, content_model=generated_model, tender_revision=tender.current_revision, source_model_hash=source_hash, human_modified=False, revision_metadata={"artifact_id": str(artifact.id), "storage_path": path}))
            elif existing_doc.human_modified and (existing_doc.generated_model_hash != source_hash or existing_doc.tender_revision != tender.current_revision):
                existing_doc.last_conflict = {"kind":"NEW_COMPILED_ARTIFACT_WITH_HUMAN_EDIT","document_version":existing_doc.version,"document_tender_revision":existing_doc.tender_revision,"new_tender_revision":tender.current_revision,"new_model_hash":source_hash,"artifact_id":str(artifact.id)}
            evidence = TenderEvidence(
                tender_id=tender.id, kind="CALCULATION", subject=f"{code}@r{tender.current_revision}",
                value={"engine": "ProcurementArtifactCompiler", "artifact_code": code, "canonical_model_hash": source_hash},
                source_hash=content_hash, source_revision=tender.current_revision,
                tenant_id=self.user.tenant_id, creado_por_id=self.user.id, actualizado_por_id=self.user.id,
            )
            self.db.add(evidence)
            await self.db.flush()
            self.db.add(TenderEvidenceLink(
                tender_id=tender.id, evidence_id=evidence.id, artifact_id=artifact.id,
                relation="GENERATES", tenant_id=self.user.tenant_id,
            ))
            domain = str(binding.get("category") or "OTHER").upper()
            self.db.add(TenderDependency(
                tender_id=tender.id, source_type="CANONICAL_MODEL", source_key=domain,
                target_type="ARTIFACT", target_key=code, relation="GENERATES",
                invalidates_signed=True, tenant_id=self.user.tenant_id,
                artifact_metadata={"revision": tender.current_revision, "canonical_model_hash": source_hash},
            ))

        # Any older artifact not generated by this exact canonical revision is no longer active.
        all_active = (await self.db.execute(select(TenderArtifact).where(
            TenderArtifact.tender_id == tender.id,
            TenderArtifact.tenant_id == self.user.tenant_id,
            TenderArtifact.status != ArtifactStatus.SUPERSEDED.value,
        ))).scalars().all()
        active_codes = {a.artifact_code for a in artifacts}
        for old in all_active:
            if old.artifact_code in active_codes and old.source_model_hash != source_hash:
                old.status = ArtifactStatus.SUPERSEDED.value

        current_state = str(tender.state)
        if current_state == TenderState.SCHEDULE_READY.value:
            self._transition(tender, TenderState.DOCUMENTS_READY)
        elif current_state not in {TenderState.DOCUMENTS_READY.value, TenderState.CROSS_VALIDATED.value, TenderState.QA_READY.value, TenderState.HUMAN_APPROVAL.value}:
            raise MegalodonException(
                ErrorCode.VALIDACION_FALLIDA,
                f"No se pueden cerrar documentos desde el estado {current_state}; complete primero los gates del dominio.",
                409,
            )
        if tender.state == TenderState.DOCUMENTS_READY.value:
            final_result = await self.orchestrator.run(self.db, tender)
            if final_result["findings"]:
                await self._commit()
                raise MegalodonException(ErrorCode.VALIDACION_FALLIDA, "Los artefactos generados no superaron la validación cruzada.", 409)
            self._transition(tender, TenderState.QA_READY)
        await self._commit()
        return artifacts

    async def run(self, tender_id: UUID) -> dict:
        tender = await self._get(tender_id, for_update=True)
        _ensure_tender_mutation_allowed(tender, "ejecución del pipeline")
        tracker = PreparationRunTracker(self.db, tender, self.user.id, session_factory=self.independent_sessions)
        await tracker.start(correlation_id=self.preparation_correlation_id)
        tracker_terminal = False

        try:
            # This gate applies to every run state, not only first-time requirement derivation.
            # A partial review must never allow the orchestrator to continue with a subset of obligations.
            await tracker.begin_stage("REQUIREMENT_CONFIRMATION_GUARD", input_refs={
                "tender_id": str(tender.id),
                "tenant_id": str(tender.tenant_id),
                "revision": tender.current_revision,
            }, engine_version=PIPELINE_VERSION)
            candidate_readiness = await self.requirement_source_readiness(tender.id)
            candidate_count = candidate_readiness.get("candidate_count")
            confirmed_candidate_count = candidate_readiness.get("confirmed_candidate_count")
            counts_are_valid = (
                isinstance(candidate_count, int) and not isinstance(candidate_count, bool)
                and isinstance(confirmed_candidate_count, int) and not isinstance(confirmed_candidate_count, bool)
                and candidate_count >= 0 and confirmed_candidate_count >= 0
            )
            if not counts_are_valid or confirmed_candidate_count > candidate_count:
                code = "REQUIREMENT_REVIEW_INTEGRITY"
                detail = "No se pudo demostrar la integridad del conteo de requisitos confirmados; la ejecución se bloqueó por seguridad."
                await tracker.finish_stage(status="BLOCKED", error_code=code, error_detail=detail)
                await tracker.finish(PreparationRunStatus.BLOCKED.value, failure_code=code, failure_detail=detail)
                tracker_terminal = True
                raise MegalodonException(ErrorCode.VALIDACION_FALLIDA, detail, 409)
            if confirmed_candidate_count != candidate_count:
                pending = candidate_count - confirmed_candidate_count
                code = "REQUIREMENT_REVIEW_REQUIRED"
                detail = (
                    f"Hay {pending} de {candidate_count} requisitos candidatos sin confirmación humana. "
                    "Deben revisarse todos antes de continuar con la elaboración."
                )
                await tracker.finish_stage(status="BLOCKED", error_code=code, error_detail=detail)
                await tracker.finish(PreparationRunStatus.BLOCKED.value, failure_code=code, failure_detail=detail)
                tracker_terminal = True
                raise MegalodonException(ErrorCode.VALIDACION_FALLIDA, detail, 409)
            await tracker.finish_stage(status="PASS", output_refs={
                "candidate_count": candidate_count,
                "confirmed_candidate_count": confirmed_candidate_count,
            })

            await tracker.begin_stage("INPUT_GUARD", input_refs={
                "tender_id": str(tender.id),
                "tenant_id": str(tender.tenant_id),
                "revision": tender.current_revision,
                "state": tender.state,
            }, engine_version=PIPELINE_VERSION)
            if tender.state == TenderState.DISCOVERED.value:
                source_count = await self.db.scalar(select(TenderEvidence.id).where(
                    TenderEvidence.tender_id == tender.id,
                    TenderEvidence.tenant_id == self.user.tenant_id,
                    TenderEvidence.kind == "SOURCE_DOCUMENT",
                    TenderEvidence.status == "ACTIVE",
                ).limit(1))
                if source_count is None:
                    await tracker.finish_stage(
                        status="BLOCKED",
                        error_code="SOURCE_REQUIRED",
                        error_detail="El expediente requiere al menos una fuente documental antes de iniciar la automatización.",
                    )
                    await tracker.finish(PreparationRunStatus.BLOCKED.value, failure_code="SOURCE_REQUIRED", failure_detail="Fuente documental requerida")
                    tracker_terminal = True
                    raise MegalodonException(ErrorCode.VALIDACION_FALLIDA, "El expediente requiere al menos una fuente documental antes de iniciar la automatización.", 409)
                self._transition(tender, TenderState.INGESTED)
                await self.db.flush()
            await tracker.finish_stage(status="PASS", output_refs={"state": tender.state, "has_source": True})

            await tracker.begin_stage("JURISDICTION_RESOLUTION", input_refs={"state": tender.state, "jurisdiction_code": tender.jurisdiction_code})
            before_jurisdiction = tender.jurisdiction_code
            if tender.state in {TenderState.INGESTED.value, TenderState.OBSERVED.value} or not tender.jurisdiction_code:
                tender = await self.resolve_jurisdiction(tender.id)
                await self.db.refresh(tender)
            await tracker.finish_stage(status="PASS", output_refs={"jurisdiction_code": tender.jurisdiction_code, "changed": before_jurisdiction != tender.jurisdiction_code})

            await tracker.begin_stage("REQUIREMENT_DERIVATION", input_refs={
                "jurisdiction_code": tender.jurisdiction_code,
                "procedure_type": tender.procedure_type,
                "revision": tender.current_revision,
            }, engine_version=PIPELINE_VERSION)
            if tender.state in {TenderState.JURISDICTIONED.value, TenderState.OBSERVED.value}:
                readiness = await self.requirement_source_readiness(tender.id)
                if not readiness["ready"]:
                    missing = ", ".join(readiness["missing_source_roles"])
                    detail = (
                        "Faltan fuentes oficiales que el usuario debe proporcionar para este flujo: " + missing + ". "
                        "Megalodon no puede completar la elaboración hasta recibirlas."
                    )
                    await tracker.finish_stage(status="BLOCKED", error_code="OFFICIAL_SOURCE_REQUIRED", error_detail=detail)
                    await tracker.finish(PreparationRunStatus.BLOCKED.value, failure_code="OFFICIAL_SOURCE_REQUIRED", failure_detail=detail)
                    tracker_terminal = True
                    raise MegalodonException(ErrorCode.VALIDACION_FALLIDA, detail, 409)

                rows = await self.derive_requirements(tender.id)
                if not rows and readiness["candidate_count"] == 0:
                    detail = (
                        "Las fuentes oficiales requeridas ya fueron cargadas, pero el extractor mecánico no produjo candidatos estructurados. "
                        "Esto no se atribuye al usuario: corresponde corregir la extracción específica de la dependencia, formato o flujo."
                    )
                    await tracker.finish_stage(status="BLOCKED", error_code="EXTRACTION_INCOMPLETE", error_detail=detail)
                    await tracker.finish(PreparationRunStatus.BLOCKED.value, failure_code="EXTRACTION_INCOMPLETE", failure_detail=detail)
                    tracker_terminal = True
                    raise MegalodonException(ErrorCode.VALIDACION_FALLIDA, detail, 409)
                if not rows and readiness["candidate_count"] > 0:
                    detail = (
                        "Las fuentes contienen candidatos confirmados, pero el mapeador no produjo requisitos efectivos. "
                        "La ejecución se bloquea por extracción o mapeo incompleto; debe corregirse el procesamiento antes de continuar."
                    )
                    await tracker.finish_stage(status="BLOCKED", error_code="REQUIREMENT_DERIVATION_INCOMPLETE", error_detail=detail)
                    await tracker.finish(PreparationRunStatus.BLOCKED.value, failure_code="REQUIREMENT_DERIVATION_INCOMPLETE", failure_detail=detail)
                    tracker_terminal = True
                    raise MegalodonException(ErrorCode.VALIDACION_FALLIDA, detail, 409)
                await self.db.refresh(tender)
                await tracker.finish_stage(status="PASS", output_refs={"requirement_count": len(rows), "state": tender.state, "source_readiness": readiness})
            else:
                await tracker.finish_stage(status="PASS", output_refs={"requirement_count": 0, "state": tender.state, "skipped": True})

            result = await self.orchestrator.run(self.db, tender, tracker=tracker)
            if result["findings"]:
                tender.review_state = TenderState.BLOCKED.value
                result['state'] = tender.state
                result['review_state'] = tender.review_state
                await self._commit()
                await tracker.finish(
                    PreparationRunStatus.BLOCKED.value,
                    failure_code="VALIDATION_BLOCKED",
                    failure_detail="; ".join(f.get("code", "") for f in result["findings"]),
                )
                tracker_terminal = True
                return result

            model = tender.canonical_model or {}
            progression = [
                (TenderState.REQUIREMENTS_MAPPED.value, TenderState.BIDDER_READY, lambda m: bool(m.get("bidder"))),
                (TenderState.BIDDER_READY.value, TenderState.TECHNICAL_MODEL_READY, lambda m: bool(m.get("technical"))),
                (TenderState.TECHNICAL_MODEL_READY.value, TenderState.QUANTIFIED, lambda m: bool((m.get("technical") or {}).get("quantities")) or bool((m.get("economic") or {}).get("partidas"))),
                (TenderState.QUANTIFIED.value, TenderState.ECONOMIC_MODEL_READY, lambda m: bool((m.get("economic") or {}).get("budget_total"))),
                (TenderState.ECONOMIC_MODEL_READY.value, TenderState.SCHEDULE_READY, lambda m: bool((m.get("schedule") or {}).get("activities"))),
            ]
            await tracker.begin_stage("LIFECYCLE_PROGRESSION", input_refs={"state": tender.state, "revision": tender.current_revision})
            advanced_states: list[str] = []
            advanced = True
            while advanced:
                advanced = False
                for src, target, ready in progression:
                    if tender.state != src:
                        continue
                    if not ready(model):
                        break
                    self._transition(tender, target)
                    advanced_states.append(tender.state)
                    advanced = True
                    break
            result["state"] = tender.state
            result["next_gate"] = {
                TenderState.REQUIREMENTS_MAPPED.value: "BIDDER_READY",
                TenderState.BIDDER_READY.value: "TECHNICAL_MODEL_READY",
                TenderState.TECHNICAL_MODEL_READY.value: "QUANTIFIED",
                TenderState.QUANTIFIED.value: "ECONOMIC_MODEL_READY",
                TenderState.ECONOMIC_MODEL_READY.value: "SCHEDULE_READY",
                TenderState.SCHEDULE_READY.value: "DOCUMENTS_READY",
                TenderState.DOCUMENTS_READY.value: "CROSS_VALIDATED",
                TenderState.CROSS_VALIDATED.value: "QA_READY",
                TenderState.QA_READY.value: "READY_FOR_HUMAN_REVIEW",
                TenderState.READY_FOR_HUMAN_REVIEW.value: "HUMAN_APPROVAL",
            }.get(tender.state)
            if tender.state == TenderState.QA_READY.value:
                self._transition(tender, TenderState.READY_FOR_HUMAN_REVIEW)
            tender.review_state = tender.state if tender.state == TenderState.READY_FOR_HUMAN_REVIEW.value else None
            result["state"] = tender.state
            result["review_state"] = tender.review_state
            await tracker.finish_stage(status="PASS", output_refs={"advanced_states": advanced_states, "state": tender.state, "review_state": tender.review_state})
            final_status = PreparationRunStatus.READY_FOR_HUMAN_REVIEW.value if tender.state == TenderState.READY_FOR_HUMAN_REVIEW.value else PreparationRunStatus.RUNNING.value
            await tracker.finish(final_status, atomic=True)
            tracker_terminal = True
            await self._commit()
            return result
        except MegalodonException as exc:
            if not tracker_terminal:
                await tracker.finish(PreparationRunStatus.FAILED.value, failure_code=type(exc).__name__, failure_detail=str(exc)[:4000])
            await self.db.rollback()
            raise
        except Exception as exc:
            if not tracker_terminal:
                await tracker.finish(PreparationRunStatus.FAILED.value, failure_code=type(exc).__name__, failure_detail=str(exc)[:4000])
            await self.db.rollback()
            raise

    async def list_artifacts(self, tender_id: UUID) -> list[TenderArtifact]:
        tender = await self._get(tender_id)
        rows = (await self.db.execute(
            select(TenderArtifact)
            .where(
                TenderArtifact.tender_id == tender.id,
                TenderArtifact.tenant_id == self.user.tenant_id,
            )
            .order_by(TenderArtifact.artifact_code, TenderArtifact.version.desc())
        )).scalars().all()
        return list(rows)

    async def preparation_history(self, tender_id: UUID) -> dict:
        tender = await self._get(tender_id)
        from app.models.procurement import TenderPreparationRun, TenderPreparationStageRun
        runs = (await self.db.execute(select(TenderPreparationRun).where(
            TenderPreparationRun.tender_id == tender.id,
            TenderPreparationRun.tenant_id == self.user.tenant_id,
        ).order_by(TenderPreparationRun.created_at.desc()))).scalars().all()
        result = []
        for run in runs:
            stages = (await self.db.execute(select(TenderPreparationStageRun).where(
                TenderPreparationStageRun.preparation_run_id == run.id,
                TenderPreparationStageRun.tenant_id == self.user.tenant_id,
            ).order_by(TenderPreparationStageRun.created_at.asc()))).scalars().all()
            result.append({
                "id": str(run.id),
                "tenant_id": str(run.tenant_id),
                "correlation_id": run.correlation_id,
                "pipeline_version": run.pipeline_version,
                "status": run.status,
                "current_stage": run.current_stage,
                "failure_code": run.failure_code,
                "failure_detail": run.failure_detail,
                "started_at": run.started_at,
                "finished_at": run.finished_at,
                "stages": [{
                    "id": str(stage.id),
                    "stage": stage.stage,
                    "status": stage.status,
                    "input_refs": stage.input_refs,
                    "output_refs": stage.output_refs,
                    "rule_version": stage.rule_version,
                    "engine_version": stage.engine_version,
                    "error_code": stage.error_code,
                    "error_detail": stage.error_detail,
                    "started_at": stage.started_at,
                    "finished_at": stage.finished_at,
                } for stage in stages],
            })
        return {"tender_id": str(tender.id), "tenant_id": str(tender.tenant_id), "runs": result}

    async def submission_download_url(self, tender_id: UUID, *, expires_seconds: int = 900) -> dict:
        """Returns a short-lived signed URL for the verified submission package.

        The lookup is tenant-scoped and the package must belong to the current
        revision. The endpoint never accepts an arbitrary storage path from the
        client, preventing cross-tenant/path traversal through object storage.
        """
        tender = await self._get(tender_id)
        if tender.state != TenderState.SUBMISSION_READY.value:
            raise MegalodonException(
                ErrorCode.VALIDACION_FALLIDA,
                "La descarga solo está disponible cuando la presentación está SUBMISSION_READY.",
                409,
            )
        submission = await self.db.scalar(select(SubmissionPackage).where(
            SubmissionPackage.tender_id == tender.id,
            SubmissionPackage.revision == tender.current_revision,
            SubmissionPackage.tenant_id == self.user.tenant_id,
        ))
        if submission is None:
            raise MegalodonException(ErrorCode.DOCUMENTO_NO_ENCONTRADO, "Paquete de presentación no encontrado.", 404)
        path = str((submission.manifest or {}).get("submission_storage_path") or "")
        expected_prefix = f"tenders/{self.user.tenant_id}/{tender.id}/r{tender.current_revision}/"
        if not path or not path.startswith(expected_prefix) or ".." in path.split("/"):
            raise MegalodonException(ErrorCode.ARCHIVO_ERROR, "La ruta del paquete no pertenece al tenant/revisión actual.", 409)
        url = await storage_exportaciones().url_firmada(path, expires_seconds)
        return {
            "submission_id": str(submission.id),
            "tender_id": str(tender.id),
            "revision": tender.current_revision,
            "url": url,
            "expira_en_segundos": expires_seconds,
            "sha256": submission.package_hash,
        }

    async def register_submission_receipt(
        self, tender_id: UUID, portal_code: str, receipt_reference: str,
        filename: str, content_type: str, content: bytes,
    ) -> dict:
        tender = await self._get(tender_id)
        if not content:
            raise MegalodonException(ErrorCode.ARCHIVO_ERROR, "El comprobante está vacío.", 422)
        if tender.state != TenderState.SUBMISSION_READY.value:
            raise MegalodonException(ErrorCode.VALIDACION_FALLIDA, "El expediente sólo acepta comprobante cuando el paquete está SUBMISSION_READY.", 409)
        submission = await self.db.scalar(select(SubmissionPackage).where(
            SubmissionPackage.tender_id == tender.id,
            SubmissionPackage.revision == tender.current_revision,
            SubmissionPackage.tenant_id == self.user.tenant_id,
        ))
        if submission is None or not submission.package_hash:
            raise MegalodonException(ErrorCode.VALIDACION_FALLIDA, "No existe un paquete de presentación generado para esta revisión.", 409)
        digest = self.compiler.sha256(content)
        safe_name = filename.replace("/", "_").replace("\\", "_")
        path = f"tenders/{self.user.tenant_id}/{tender.id}/r{tender.current_revision}/receipt-{digest[:16]}-{safe_name}"
        stored = await self.storage_guard.upload_verified(tenant_id=self.user.tenant_id, job_id=None, bucket_name=get_settings().SUPABASE_BUCKET_DOCUMENTOS, path=path, content=content, content_type=content_type, entity_type="SubmissionReceipt", entity_id=submission.id)
        submission.portal_code = portal_code
        submission.receipt = {
            "reference": receipt_reference,
            "portal_code": portal_code,
            "storage_path": stored,
            "sha256": digest,
            "package_hash": submission.package_hash,
            "recorded_at": datetime.now(timezone.utc).isoformat(),
        }
        submission.status = "SUBMITTED"
        self._transition(tender, TenderState.SUBMITTED)
        await self._commit()
        return {"submission_id": str(submission.id), "status": submission.status, "portal_code": portal_code, "receipt_reference": receipt_reference, "receipt_sha256": digest}

    async def freeze(self, tender_id: UUID) -> TenderPackage:
        tender = await self._get(tender_id)
        if tender.state != TenderState.SUBMISSION_READY.value:
            raise MegalodonException(ErrorCode.VALIDACION_FALLIDA, "Solo se puede congelar un expediente listo para presentación.", 400)
        tender.frozen = True
        await self._commit()
        await self.db.refresh(tender)
        return tender

    async def approval(self, tender_id: UUID, data: ApprovalCreate) -> TenderApproval:
        tender = await self._get(tender_id, for_update=True)
        if data.decision not in {"APPROVED", "REJECTED"}:
            raise MegalodonException(ErrorCode.PARAMETRO_INVALIDO, "Decision debe ser APPROVED o REJECTED.", 422)
        required_roles = set((tender.canonical_model.get("approvals") or {}).get("required_roles", []))
        if not required_roles:
            raise MegalodonException(ErrorCode.VALIDACION_FALLIDA, "El expediente no define roles de aprobación; no puede avanzar a presentación.", 409)
        if data.role not in required_roles:
            raise MegalodonException(ErrorCode.PERMISO_DENEGADO, f"El rol {data.role} no está autorizado para este expediente.", 403)
        if tender.creado_por_id == self.user.id and data.decision == "APPROVED":
            raise MegalodonException(ErrorCode.PERMISO_DENEGADO, "Separación de funciones: el creador del expediente no puede aprobar su propia presentación.", 403)
        if tender.state not in {TenderState.QA_READY.value, TenderState.READY_FOR_HUMAN_REVIEW.value}:
            raise MegalodonException(ErrorCode.VALIDACION_FALLIDA, f"No se puede aprobar en estado {tender.state}; se requiere READY_FOR_HUMAN_REVIEW.", 409)
        if data.decision == "APPROVED":
            readiness = await self.readiness(tender.id)
            if not _approval_gate_ready(tender.state, readiness):
                blockers = [
                    str(item.get("code") or item.get("message") or "BLOCKER")
                    for item in readiness.get("findings", [])
                    if item.get("severity") in {"BLOCKER", "P0"}
                ]
                raise MegalodonException(
                    ErrorCode.VALIDACION_FALLIDA,
                    "La aprobación está bloqueada por readiness: " + (", ".join(blockers) or "QA no está listo."),
                    409,
                )
            if tender.state == TenderState.QA_READY.value:
                self._transition(tender, TenderState.READY_FOR_HUMAN_REVIEW)
            tender.review_state = TenderState.READY_FOR_HUMAN_REVIEW.value
        existing = await self.db.scalar(select(TenderApproval).where(
            TenderApproval.tender_id == tender.id,
            TenderApproval.revision == tender.current_revision,
            TenderApproval.role == data.role,
            TenderApproval.tenant_id == self.user.tenant_id,
        ).with_for_update())
        if existing:
            raise MegalodonException(ErrorCode.CONFLICT, f"El rol {data.role} ya emitió una decisión para esta revisión.", 409)
        if data.decision == "APPROVED":
            previous_actor_approval = await self.db.scalar(
                select(TenderApproval).where(
                    TenderApproval.tender_id == tender.id,
                    TenderApproval.revision == tender.current_revision,
                    TenderApproval.tenant_id == self.user.tenant_id,
                    TenderApproval.decision == "APPROVED",
                    TenderApproval.creado_por_id == self.user.id,
                ).with_for_update()
            )
            if (
                previous_actor_approval is not None
                and previous_actor_approval.role != data.role
            ):
                raise MegalodonException(
                    ErrorCode.PERMISO_DENEGADO,
                    "Separación de funciones: una misma persona no puede cubrir más de un rol de aprobación en la misma revisión.",
                    403,
                )
        row = TenderApproval(
            tender_id=tender.id, role=data.role, decision=data.decision, reason=data.reason, revision=tender.current_revision,
            tenant_id=self.user.tenant_id, creado_por_id=self.user.id, actualizado_por_id=self.user.id,
        )
        self.db.add(row)
        if data.decision == "REJECTED":
            tender.state = TenderState.BLOCKED.value
        else:
            current_approved = (await self.db.execute(select(TenderApproval).where(
                TenderApproval.tender_id == tender.id,
                TenderApproval.revision == tender.current_revision,
                TenderApproval.tenant_id == self.user.tenant_id,
                TenderApproval.decision == "APPROVED",
            ))).scalars().all()
            roles = {r.role for r in current_approved} | {data.role}
            if required_roles.issubset(roles):
                if tender.state in {TenderState.QA_READY.value, TenderState.READY_FOR_HUMAN_REVIEW.value}:
                    if tender.state == TenderState.QA_READY.value:
                        self._transition(tender, TenderState.READY_FOR_HUMAN_REVIEW)
                    self._transition(tender, TenderState.HUMAN_APPROVAL)
                elif tender.state != TenderState.HUMAN_APPROVAL.value:
                    raise MegalodonException(ErrorCode.VALIDACION_FALLIDA, f"El expediente no puede alcanzar aprobación humana desde {tender.state}.", 409)
            else:
                if tender.state == TenderState.BLOCKED.value:
                    raise MegalodonException(ErrorCode.VALIDACION_FALLIDA, "Un expediente bloqueado requiere una nueva ejecución de QA antes de continuar.", 409)
        await self._commit()
        await self.db.refresh(row)
        return row

    async def _cleanup_uncommitted_signature_outputs(
        self,
        documento_id: UUID,
        artifact_id: UUID,
        signed_path: str | None,
        signed_export_path: str | None,
    ) -> None:
        """Delete signature renditions only when the committed DB does not reference them."""
        try:
            document = await self.db.scalar(
                select(Documento)
                .where(Documento.id == documento_id)
                .execution_options(populate_existing=True)
            )
            artifact = await self.db.scalar(
                select(TenderArtifact)
                .where(
                    TenderArtifact.id == artifact_id,
                    TenderArtifact.tenant_id == self.user.tenant_id,
                )
                .execution_options(populate_existing=True)
            )
            document_paths = {
                item.get("storage_path_firmado")
                for item in ((document.metadatos or {}).get("firmas", []) if document else [])
                if isinstance(item, dict)
            }
            artifact_signature = (
                (artifact.artifact_metadata or {}).get("signature", {})
                if artifact else {}
            )
            to_delete = []
            if signed_path and signed_path not in document_paths:
                to_delete.append(signed_path)
            if signed_export_path and artifact_signature.get("signed_storage_path") != signed_export_path:
                to_delete.append(signed_export_path)
            if to_delete:
                await storage_exportaciones().eliminar(list(dict.fromkeys(to_delete)))
        except Exception as cleanup_exc:
            # When DB reference state is uncertain, retain the storage objects.
            logger.warning(
                "No se pudieron reconciliar salidas de firma no confirmadas para artefacto %s: %s",
                artifact_id,
                cleanup_exc,
            )

    async def sign_artifact(
        self,
        tender_id: UUID,
        artifact_id: UUID,
        certificado_cer: bytes,
        certificado_key: bytes,
        password: str,
        razon: str = "Firma de artefacto de proposición",
        ubicacion: str = "México",
        usar_tsa: bool = True,
        tsa_url: str | None = None,
        idempotency_key: str | None = None,
    ) -> dict:
        tender = await self._get(tender_id, for_update=True)
        if tender.state not in {TenderState.HUMAN_APPROVAL.value, TenderState.SIGNED.value}:
            raise MegalodonException(ErrorCode.VALIDACION_FALLIDA, "La firma sólo puede ejecutarse después de la aprobación humana.", 409)
        if tender.frozen:
            raise MegalodonException(ErrorCode.BAD_REQUEST, "El expediente está congelado.", 400)
        artifact = await self.db.scalar(select(TenderArtifact).where(
            TenderArtifact.id == artifact_id,
            TenderArtifact.tender_id == tender.id,
            TenderArtifact.tenant_id == self.user.tenant_id,
        ).with_for_update())
        if artifact is None:
            raise MegalodonException(ErrorCode.DOCUMENTO_NO_ENCONTRADO, "Artefacto no encontrado.", 404)
        if not artifact_requires_signature(artifact):
            raise MegalodonException(
                ErrorCode.VALIDACION_FALLIDA,
                "El artefacto no está configurado como documento que requiera firma electrónica.",
                409,
            )
        if not isinstance(idempotency_key, str) or not idempotency_key.strip():
            raise MegalodonException(ErrorCode.PARAMETRO_INVALIDO, "La firma PAdES requiere Idempotency-Key.", 422)
        existing_key = artifact.signature_idempotency_key
        if existing_key and existing_key != idempotency_key:
            raise MegalodonException(ErrorCode.CONFLICT, "El artefacto ya fue firmado con otra Idempotency-Key.", 409)
        if existing_key == idempotency_key and artifact.status == ArtifactStatus.SIGNED.value:
            return {**(artifact.artifact_metadata or {}).get("signature", {}), "artifact_id": str(artifact.id), "artifact_code": artifact.artifact_code, "status": artifact.status, "idempotent_replay": True}
        if artifact.media_type != "application/pdf":
            raise MegalodonException(ErrorCode.PARAMETRO_INVALIDO, "La firma PAdES sólo admite artefactos PDF.", 422)
        if artifact.status not in {ArtifactStatus.GENERATED.value, ArtifactStatus.VALIDATED.value}:
            raise MegalodonException(
                ErrorCode.VALIDACION_FALLIDA,
                f"No se puede firmar un artefacto en estado {artifact.status}.",
                409,
            )
        bucket = storage_exportaciones()
        original = await bucket.descargar(artifact.storage_path or "")
        if self.compiler.sha256(original) != artifact.content_hash:
            raise MegalodonException(ErrorCode.ARCHIVO_ERROR, "El hash del artefacto no coincide con storage.", 409)

        document = Documento(
            identificador=f"TENDER-{tender.identifier}-{artifact.artifact_code}-R{tender.current_revision}",
            nombre=artifact.name,
            tipo_documental="PROCUREMENT_ARTIFACT",
            formato="pdf",
            storage_path=artifact.storage_path or "",
            storage_bucket=get_settings().SUPABASE_BUCKET_EXPORTS,
            size_bytes=len(original),
            hash_sha256=artifact.content_hash or self.compiler.sha256(original),
            expediente_id=tender.expediente_id,
            metadatos={"tender_id": str(tender.id), "artifact_id": str(artifact.id), "revision": tender.current_revision},
        )
        self.db.add(document)
        await self.db.flush()

        signed_path = None
        signed_export_path = None
        try:
            result = await FirmaService(self.db).firmar_documento(
                documento_id=document.id,
                certificado_cer=certificado_cer,
                certificado_key=certificado_key,
                password=password,
                razon=razon,
                ubicacion=ubicacion,
                usuario_id=self.user.id,
                usar_tsa=usar_tsa,
                tsa_url=tsa_url,
                commit=False,
            )
            signed_path = result["storage_path_firmado"]
            signed_content = await storage_exportaciones().descargar(signed_path)
            signed_hash = self.compiler.sha256(signed_content)
            signed_export_path = f"tenders/{self.user.tenant_id}/{tender.id}/r{tender.current_revision}/{artifact.artifact_code}-v{artifact.version}.firmado.pdf"
            await self.storage_guard.upload_verified(
                tenant_id=self.user.tenant_id,
                job_id=None,
                bucket_name=get_settings().SUPABASE_BUCKET_EXPORTS,
                path=signed_export_path,
                content=signed_content,
                content_type="application/pdf",
                entity_type="SignedTenderArtifact",
                entity_id=artifact.id,
            )
            artifact.status = ArtifactStatus.SIGNED.value
            artifact.signature_idempotency_key = idempotency_key
            artifact.artifact_metadata = {
                **(artifact.artifact_metadata or {}),
                "signature": {
                    **result,
                    "signed_storage_path": signed_export_path,
                    "signed_sha256": signed_hash,
                    "original_sha256": artifact.content_hash,
                },
            }
            if tender.canonical_model.get("submission") is not None:
                tender.canonical_model = {
                    **tender.canonical_model,
                    "submission": {
                        **tender.canonical_model.get("submission", {}),
                        "signed_artifacts": [
                            *(tender.canonical_model.get("submission", {}).get("signed_artifacts", [])),
                            {"artifact_id": str(artifact.id), "artifact_code": artifact.artifact_code, "sha256": signed_hash},
                        ],
                    },
                }
            await self._commit()
            return {
                "artifact_id": str(artifact.id),
                "artifact_code": artifact.artifact_code,
                "status": artifact.status,
                "original_sha256": artifact.content_hash,
                "signed_sha256": signed_hash,
                "signed_storage_path": signed_export_path,
                "signature": result,
            }
        except BaseException:
            await self.db.rollback()
            await self._cleanup_uncommitted_signature_outputs(
                document.id,
                artifact.id,
                signed_path,
                signed_export_path,
            )
            raise

    async def submission(self, tender_id: UUID, idempotency_key: str | None = None) -> SubmissionPackage:
        # Serialize package creation against concurrent approvals, revisions and retries.
        tender = await self._get(tender_id, for_update=True)
        if tender.state != TenderState.HUMAN_APPROVAL.value:
            raise MegalodonException(ErrorCode.VALIDACION_FALLIDA, "La presentación requiere validación cruzada y aprobación humana completa.", 409)
        required_roles = set((tender.canonical_model.get("approvals") or {}).get("required_roles", []))
        approvals = (await self.db.execute(
            select(TenderApproval).where(
                TenderApproval.tender_id == tender.id,
                TenderApproval.revision == tender.current_revision,
                TenderApproval.tenant_id == self.user.tenant_id,
                TenderApproval.decision == "APPROVED",
            )
        )).scalars().all()
        approved_roles = {row.role for row in approvals}
        missing_roles = sorted(required_roles - approved_roles)
        if missing_roles:
            raise MegalodonException(
                ErrorCode.VALIDACION_FALLIDA,
                f"Faltan aprobaciones requeridas: {', '.join(missing_roles)}",
                409,
            )

        active_artifacts = (await self.db.execute(select(TenderArtifact).where(
            TenderArtifact.tender_id == tender.id,
            TenderArtifact.tenant_id == self.user.tenant_id,
            TenderArtifact.status != ArtifactStatus.SUPERSEDED.value,
        ))).scalars().all()
        reference_only = [a.artifact_code for a in active_artifacts if bool((a.artifact_metadata or {}).get("reference_only"))]
        if reference_only:
            raise MegalodonException(ErrorCode.VALIDACION_FALLIDA, f"Existen artefactos de referencia que no pueden presentarse como oficiales: {', '.join(sorted(reference_only))}", 409)
        submission_artifacts = [a for a in active_artifacts if artifact_submission_eligible(a)]
        unsigned_pdfs = [
            a.artifact_code for a in submission_artifacts
            if artifact_requires_signature(a) and a.status != ArtifactStatus.SIGNED.value
        ]
        if unsigned_pdfs:
            raise MegalodonException(
                ErrorCode.VALIDACION_FALLIDA,
                f"Existen artefactos PDF sin firma: {', '.join(sorted(unsigned_pdfs))}",
                409,
            )

        existing_submission = await self.db.scalar(select(SubmissionPackage).where(
            SubmissionPackage.tender_id == tender.id,
            SubmissionPackage.revision == tender.current_revision,
            SubmissionPackage.tenant_id == self.user.tenant_id,
        ))
        if existing_submission is not None and existing_submission.idempotency_key:
            if idempotency_key and existing_submission.idempotency_key != idempotency_key:
                raise MegalodonException(ErrorCode.CONFLICT, "La revisión ya tiene un submission asociado a otra Idempotency-Key.", 409)
            if not idempotency_key or existing_submission.idempotency_key == idempotency_key:
                return existing_submission
        # Build the package manifest while the aggregate is still HUMAN_APPROVAL;
        # TenderOrchestrator validates that state as the precondition for submission.
        submission = await self.orchestrator.build_submission(self.db, tender)
        submission.idempotency_key = idempotency_key
        artifacts_all = (await self.db.execute(
            select(TenderArtifact).where(
                TenderArtifact.tender_id == tender.id,
                TenderArtifact.tenant_id == self.user.tenant_id,
                TenderArtifact.status != ArtifactStatus.SUPERSEDED.value,
            )
        )).scalars().all()
        artifacts = [a for a in artifacts_all if artifact_submission_eligible(a)]
        if not artifacts:
            raise MegalodonException(ErrorCode.VALIDACION_FALLIDA, "No existen artefactos elegibles para el paquete de presentación.", 409)
        stored_artifacts: list[dict] = []
        packaged_files: list[dict] = []
        bucket = storage_exportaciones()
        for artifact in artifacts:
            if not artifact.storage_path or not artifact.content_hash:
                raise MegalodonException(ErrorCode.ARCHIVO_ERROR, f"Artefacto {artifact.artifact_code} sin contenido inmutable.", 409)
            signature = (artifact.artifact_metadata or {}).get("signature") or {}
            package_path = signature.get("signed_storage_path") or artifact.storage_path
            expected_hash = signature.get("signed_sha256") if signature.get("signed_storage_path") else artifact.content_hash
            content = await bucket.descargar(package_path)
            actual_hash = self.compiler.sha256(content)
            if actual_hash != expected_hash:
                raise MegalodonException(ErrorCode.ARCHIVO_ERROR, f"Hash inválido del artefacto {artifact.artifact_code}.", 409)
            zip_path = f"{artifact.artifact_code}/v{artifact.version}-{artifact.name}".replace("\\", "/")
            stored_artifacts.append({"path": zip_path, "content": content})
            packaged_files.append({
                "path": zip_path, "code": artifact.artifact_code, "version": artifact.version,
                "sha256": actual_hash, "size_bytes": len(content),
            })
        manifest = {
            **submission.manifest,
            "submission_revision": tender.current_revision,
            "artifact_count": len(stored_artifacts),
            "artifacts_verified": True,
            "packaged_files": sorted(packaged_files, key=lambda entry: entry["path"]),
            "canonical_model_hash": self.orchestrator.canonical_hash(tender.canonical_model),
        }
        package_content = self.compiler.compile_submission_zip(stored_artifacts, manifest)
        package_hash = self.compiler.sha256(package_content)
        package_path = f"tenders/{self.user.tenant_id}/{tender.id}/r{tender.current_revision}/SUBMISSION-v{tender.current_revision}.zip"
        await self.storage_guard.upload_verified(tenant_id=self.user.tenant_id, job_id=None, bucket_name=get_settings().SUPABASE_BUCKET_EXPORTS, path=package_path, content=package_content, content_type="application/zip", entity_type="SubmissionPackage", entity_id=submission.id)
        submission.package_hash = package_hash
        submission.manifest = {
            **manifest,
            "submission_storage_path": package_path,
            "submission_content_sha256": package_hash,
        }
        self._transition(tender, TenderState.SIGNED)
        self._transition(tender, TenderState.SUBMISSION_READY)
        await self._commit()
        await self.db.refresh(submission)
        return submission

    @staticmethod
    def _hash(value: object) -> str:
        return sha256(json.dumps(value, sort_keys=True, default=str).encode()).hexdigest()
