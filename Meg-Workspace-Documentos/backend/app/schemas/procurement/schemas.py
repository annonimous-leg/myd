from __future__ import annotations

from decimal import Decimal
from typing import Any, Literal
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, StrictBool, model_validator


class ProcurementFacts(BaseModel):
    model_config = ConfigDict(extra="allow")


class ProcurementEconomicModel(BaseModel):
    model_config = ConfigDict(extra="allow")
    partidas: list[dict[str, Any]] = Field(default_factory=list)
    factor_indirecto: Decimal | None = Field(default=None, ge=0, le=1, decimal_places=4)
    factor_utilidad: Decimal | None = Field(default=None, ge=0, le=1, decimal_places=4)
    factor_impuesto: Decimal | None = Field(default=None, ge=0, le=1, decimal_places=4)
    factor_riesgo: Decimal | None = Field(default=None, ge=0, le=1, decimal_places=4)
    source: str | None = Field(default=None, min_length=1, max_length=500)

    @model_validator(mode="after")
    def exigir_parametros_si_hay_partidas(self) -> "ProcurementEconomicModel":
        if not self.partidas:
            return self
        faltantes = [
            nombre for nombre in (
                "factor_indirecto", "factor_utilidad", "factor_impuesto", "factor_riesgo", "source",
            )
            if getattr(self, nombre) is None
            or (nombre == "source" and not str(getattr(self, nombre)).strip())
        ]
        if faltantes:
            raise ValueError("Las partidas requieren parámetros económicos explícitos: " + ", ".join(faltantes))
        self.source = self.source.strip() if self.source else self.source
        return self


class ProcurementScheduleModel(BaseModel):
    model_config = ConfigDict(extra="allow")
    start_date: str | None = None
    activities: list[dict[str, Any]] = Field(default_factory=list)


class ProcurementApprovalsModel(BaseModel):
    model_config = ConfigDict(extra="forbid")
    required_roles: list[str] = Field(default_factory=list, min_length=1)


class ProcurementCanonicalModel(BaseModel):
    model_config = ConfigDict(extra="forbid")
    facts: ProcurementFacts = Field(default_factory=ProcurementFacts)
    technical: dict[str, Any] = Field(default_factory=dict)
    economic: ProcurementEconomicModel = Field(default_factory=ProcurementEconomicModel)
    schedule: ProcurementScheduleModel = Field(default_factory=ProcurementScheduleModel)
    risk: dict[str, Any] = Field(default_factory=dict)
    bidder: dict[str, Any] = Field(default_factory=dict)
    approvals: ProcurementApprovalsModel
    submission: dict[str, Any] = Field(default_factory=dict)


class TenderFormatConfigurationCreate(BaseModel):
    model_config = ConfigDict(extra="forbid")
    version: str = Field(min_length=1, max_length=100)
    format_definitions: list[dict[str, Any]] = Field(default_factory=list)


class TenderCreate(BaseModel):
    model_config = ConfigDict(extra="forbid")
    expediente_id: UUID
    identifier: str = Field(min_length=1, max_length=120)
    title: str = Field(min_length=1, max_length=500)
    jurisdiction_code: str = Field(min_length=1, max_length=120)
    procedure_type: str | None = None
    contract_type: str | None = None
    evaluation_criterion: str | None = None
    project_type: str | None = None
    scope_scale: str | None = None
    case_pack_code: str | None = None
    funding_source: str | None = None
    object_class: str | None = None
    legal_regime: str | None = None
    source_manifest: dict[str, Any] = Field(default_factory=dict)
    format_configuration: TenderFormatConfigurationCreate | None = None
    canonical_model: ProcurementCanonicalModel


class RequirementCandidateConfirmation(BaseModel):
    """Strict human confirmation of one source-bound extracted requirement."""
    model_config = ConfigDict(extra="forbid")

    candidate_id: str = Field(min_length=64, max_length=64, pattern=r"^[0-9a-f]{64}$")
    evidence_id: UUID
    code: str = Field(min_length=1, max_length=120)
    description: str = Field(min_length=1, max_length=4000)
    category: Literal["LEGAL", "ADMINISTRATIVO", "TECNICO", "ECONOMICO", "CALENDARIO", "PRESENTACION", "GARANTIA"]
    mandatory: StrictBool


class RequirementCreate(BaseModel):
    code: str = Field(min_length=1, max_length=120)
    category: str
    description: str = Field(min_length=1)
    mandatory: bool = True
    condition: dict[str, Any] = Field(default_factory=dict)
    source_reference: dict[str, Any] = Field(default_factory=dict)
    evidence_required: list[Any] = Field(default_factory=list)
    artifact_required: list[Any] = Field(default_factory=list)
    validator_code: str | None = None
    approver_role: str | None = None
    severity: str = "BLOCKER"


class EvidenceCreate(BaseModel):
    # Only user-managed evidence kinds are accepted here. Uploaded sources,
    # generated artifacts and calculations have dedicated server-side flows.
    kind: Literal["COMPANY_RECORD", "EXTERNAL_RECORD", "USER_ASSERTION"]
    subject: str
    value: dict[str, Any] = Field(default_factory=dict)
    source_uri: str | None = None
    source_hash: str | None = None
    source_revision: int | None = None


class ArtifactCreate(BaseModel):
    artifact_code: str
    name: str
    media_type: str
    storage_path: str | None = None
    content_hash: str | None = None
    metadata: dict[str, Any] = Field(default_factory=dict)


class TenderFormatAmendment(TenderFormatConfigurationCreate):
    expected_revision: int = Field(ge=1)
    amendment_evidence_id: UUID
    base_evidence_id: UUID


class RevisionCreate(BaseModel):
    format_amendment: TenderFormatAmendment | None = None
    reason: str = Field(min_length=1, max_length=500)
    source_hash: str | None = None
    model_snapshot: dict[str, Any] | None = None


class SemiAutoReviewPatch(BaseModel):
    """Parche semi-automático: el usuario revisa/edita facts y checklist de formatos.

    No sustituye el presupuesto (partidas/APU vienen de hydrate).
    Solo materializa decisiones humanas sobre el borrador.
    """
    authority: str | None = Field(default=None, max_length=500)
    object: str | None = Field(default=None, max_length=2000)
    budget_total_reference: float | None = None
    format_checklist: list[dict[str, Any]] | None = None
    reason: str = Field(default="SEMI_AUTO_REVIEW", min_length=1, max_length=500)


class ApprovalCreate(BaseModel):
    role: str
    decision: str
    reason: str | None = None
    # Reviewer confirms the server-prepared ORIGINALS manifest observed beforehand.
    expected_artifact_manifest_sha256: str | None = Field(default=None, min_length=64, max_length=64)


class SubmissionResponse(BaseModel):
    id: UUID
    tender_id: UUID
    revision: int
    status: str
    package_hash: str | None
    manifest: dict[str, Any]


class IngestedSourceResponse(BaseModel):
    evidence_id: UUID
    storage_path: str
    sha256: str
    size_bytes: int
    media_type: str


class JurisdictionProfileCreate(BaseModel):
    model_config = ConfigDict(extra="forbid")
    code: str = Field(min_length=1, max_length=120)
    authority: str = Field(min_length=1, max_length=255)
    government_level: str = Field(min_length=1, max_length=50)
    matter: str = Field(min_length=1, max_length=120)
    portal_code: str | None = None
    profile_version: int = Field(default=1, ge=1)
    ruleset: dict[str, Any] = Field(default_factory=dict)
    templates: dict[str, Any] = Field(default_factory=dict)


class LegalSourceCreate(BaseModel):
    authority: str = Field(min_length=1, max_length=255)
    title: str = Field(min_length=1, max_length=500)
    citation: str | None = None
    source_uri: str | None = None
    publication_date: str | None = None
    effective_from: str | None = None
    effective_to: str | None = None
    version: str = Field(min_length=1, max_length=120)
    content_hash: str | None = None
    jurisdiction_code: str | None = None


class LegalRuleCreate(BaseModel):
    rule_id: str = Field(min_length=1, max_length=120)
    source_ref: str | None = Field(default=None, max_length=160)
    article_ref: str | None = Field(default=None, max_length=160)
    jurisdiction_code: str | None = None
    domain: str = Field(min_length=1, max_length=80)
    procedure_type: str | None = None
    source_id: UUID | None = None
    article_id: UUID | None = None
    source_version: str | None = None
    condition: dict[str, Any] = Field(default_factory=dict)
    requirement: dict[str, Any] = Field(default_factory=dict)
    validation: dict[str, Any] = Field(default_factory=dict)
    severity: str = "BLOCKER"
    effective_from: str | None = None
    effective_to: str | None = None
    rule_version: int = Field(default=1, ge=1)


class LegalArticleCreate(BaseModel):
    model_config = ConfigDict(extra="forbid")
    source_id: UUID | None = None
    source_ref: str | None = Field(default=None, max_length=160)
    article_code: str = Field(min_length=1, max_length=80)
    title: str | None = Field(default=None, max_length=500)
    summary: str = Field(min_length=1)
    effective_from: str | None = None
    effective_to: str | None = None
    content_hash: str | None = Field(default=None, max_length=64)


class JurisdictionPackCreate(BaseModel):
    model_config = ConfigDict(extra="forbid")
    profile: JurisdictionProfileCreate
    sources: list[LegalSourceCreate] = Field(min_length=1)
    articles: list[LegalArticleCreate] = Field(min_length=1)
    rules: list[LegalRuleCreate] = Field(min_length=1)

class WorkspaceDocumentCreate(BaseModel):
    artifact_code: str = Field(min_length=1, max_length=120)
    name: str = Field(min_length=1, max_length=500)
    media_type: str = Field(default="text/plain", max_length=120)

class WorkspaceDocumentUpdate(BaseModel):
    content_text: str = ""
    content_model: dict[str, Any] = Field(
        default_factory=dict,
        description=(
            "Edición humana del documento. Para que una edición realmente "
            "cambie el artefacto compilado (PDF/XLSX final) -- no solo el "
            "texto que se ve en el Workspace -- incluye la clave "
            "'field_overrides': un dict {ruta.canonica: valor} donde cada "
            "ruta debe ser una de las canonical_paths que el catálogo DB-driven "
            "ya declara para este formato (artifact_code). Rutas fuera de ese "
            "allow-list se ignoran silenciosamente en la siguiente compilación "
            "(ver ProcurementService.compile_artifacts -> _model_con_overrides_humanos). "
            "Sin 'field_overrides', la edición se guarda y se protege de "
            "sobreescritura (ver /regenerate), pero no afecta al binario."
        ),
    )
    expected_row_version: int = Field(ge=1)

class WorkspaceDocumentRegenerate(BaseModel):
    generated_text: str = ""
    generated_model: dict[str, Any] = Field(default_factory=dict)
    expected_row_version: int = Field(ge=1)

class WorkspaceLockPatch(BaseModel):
    locked: bool

class TenderLicitacionBridgeCreate(BaseModel):
    licitacion_id: UUID
    relationship_type: str = Field(default="PRIMARY", min_length=1, max_length=40)


class TenderLicitacionBridgeSync(BaseModel):
    direction: str = Field(default="TENDER_TO_LICITACION", pattern="^(TENDER_TO_LICITACION|LICITACION_TO_TENDER)$")
    expected_tender_revision: int = Field(ge=1)
    expected_licitacion_version: int = Field(ge=1)
