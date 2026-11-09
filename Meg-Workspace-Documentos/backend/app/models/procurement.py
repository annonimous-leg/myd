from __future__ import annotations

from enum import Enum
from uuid import UUID as UUIDType

from sqlalchemy import Boolean, CheckConstraint, ForeignKey, ForeignKeyConstraint, Index, Integer, Numeric, String, Text, UniqueConstraint, text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.types import UUID, JSONB
from app.models.base import Base, UUIDMixin, TenantMixin, AuditMixin


class TenderState(str, Enum):
    DISCOVERED = "DISCOVERED"
    INGESTED = "INGESTED"
    JURISDICTIONED = "JURISDICTIONED"
    REQUIREMENTS_MAPPED = "REQUIREMENTS_MAPPED"
    BIDDER_READY = "BIDDER_READY"
    TECHNICAL_MODEL_READY = "TECHNICAL_MODEL_READY"
    QUANTIFIED = "QUANTIFIED"
    ECONOMIC_MODEL_READY = "ECONOMIC_MODEL_READY"
    SCHEDULE_READY = "SCHEDULE_READY"
    DOCUMENTS_READY = "DOCUMENTS_READY"
    CROSS_VALIDATED = "CROSS_VALIDATED"
    QA_READY = "QA_READY"
    READY_FOR_HUMAN_REVIEW = "READY_FOR_HUMAN_REVIEW"
    HUMAN_APPROVAL = "HUMAN_APPROVAL"
    SIGNED = "SIGNED"
    SUBMISSION_READY = "SUBMISSION_READY"
    SUBMITTED = "SUBMITTED"
    ARCHIVED = "ARCHIVED"
    OBSERVED = "OBSERVED"
    BLOCKED = "BLOCKED"
    SUPERSEDED = "SUPERSEDED"
    CANCELLED = "CANCELLED"
    EXPIRED = "EXPIRED"


class RequirementCategory(str, Enum):
    LEGAL = "LEGAL"
    ADMINISTRATIVO = "ADMINISTRATIVO"
    TECNICO = "TECNICO"
    ECONOMICO = "ECONOMICO"
    CALENDARIO = "CALENDARIO"
    PRESENTACION = "PRESENTACION"
    GARANTIA = "GARANTIA"


class RequirementStatus(str, Enum):
    PENDING = "PENDING"
    PASS = "PASS"
    FAIL = "FAIL"
    UNKNOWN = "UNKNOWN"
    NOT_APPLICABLE = "NOT_APPLICABLE"
    OVERRIDE = "OVERRIDE"


class EvidenceKind(str, Enum):
    SOURCE_DOCUMENT = "SOURCE_DOCUMENT"
    COMPANY_RECORD = "COMPANY_RECORD"
    GENERATED_ARTIFACT = "GENERATED_ARTIFACT"
    CALCULATION = "CALCULATION"
    EXTERNAL_RECORD = "EXTERNAL_RECORD"
    USER_ASSERTION = "USER_ASSERTION"


class ArtifactStatus(str, Enum):
    DRAFT = "DRAFT"
    GENERATED = "GENERATED"
    VALIDATED = "VALIDATED"
    SIGNED = "SIGNED"
    SUBMITTED = "SUBMITTED"
    SUPERSEDED = "SUPERSEDED"


class ValidationSeverity(str, Enum):
    INFO = "INFO"
    WARNING = "WARNING"
    HIGH = "HIGH"
    BLOCKER = "BLOCKER"


class ValidationStatus(str, Enum):
    PASS = "PASS"
    FAIL = "FAIL"
    UNKNOWN = "UNKNOWN"


class TenderPackage(Base, UUIDMixin, TenantMixin, AuditMixin):
    __tablename__ = "tender_packages"
    expediente_id: Mapped[UUIDType] = mapped_column(
        UUID(as_uuid=True), ForeignKey("expedientes_obra.id", ondelete="CASCADE"), nullable=False, index=True
    )
    identifier: Mapped[str] = mapped_column(String(120), nullable=False)
    title: Mapped[str] = mapped_column(String(500), nullable=False)
    state: Mapped[str] = mapped_column(String(50), default=TenderState.DISCOVERED.value, index=True)
    jurisdiction_code: Mapped[str | None] = mapped_column(String(120), nullable=True, index=True)
    procedure_type: Mapped[str | None] = mapped_column(String(80), nullable=True)
    contract_type: Mapped[str | None] = mapped_column(String(80), nullable=True)
    evaluation_criterion: Mapped[str | None] = mapped_column(String(80), nullable=True)
    project_type: Mapped[str | None] = mapped_column(String(80), nullable=True)
    scope_scale: Mapped[str | None] = mapped_column(String(40), nullable=True)
    case_pack_code: Mapped[str | None] = mapped_column(String(120), nullable=True)
    funding_source: Mapped[str | None] = mapped_column(String(40), nullable=True)
    object_class: Mapped[str | None] = mapped_column(String(40), nullable=True)
    legal_regime: Mapped[str | None] = mapped_column(String(80), nullable=True)
    source_manifest: Mapped[dict] = mapped_column(JSONB, default=dict, nullable=False)
    canonical_model: Mapped[dict] = mapped_column(JSONB, default=dict, nullable=False)
    current_revision: Mapped[int] = mapped_column(Integer, default=1, nullable=False)
    frozen: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    review_state: Mapped[str | None] = mapped_column(String(50), nullable=True, index=True)
    row_version: Mapped[int] = mapped_column(Integer, default=1, nullable=False)

    __mapper_args__ = {"version_id_col": row_version, "version_id_generator": lambda v: (v or 0) + 1}

    revisions: Mapped[list["TenderRevision"]] = relationship(
        back_populates="tender", cascade="all, delete-orphan", order_by="TenderRevision.revision"
    )
    requirements: Mapped[list["TenderRequirement"]] = relationship(
        back_populates="tender", cascade="all, delete-orphan"
    )
    evidence: Mapped[list["TenderEvidence"]] = relationship(
        back_populates="tender", cascade="all, delete-orphan"
    )
    artifacts: Mapped[list["TenderArtifact"]] = relationship(
        back_populates="tender", cascade="all, delete-orphan"
    )
    validations: Mapped[list["TenderValidationRun"]] = relationship(
        back_populates="tender", cascade="all, delete-orphan"
    )
    dependencies: Mapped[list["TenderDependency"]] = relationship(
        back_populates="tender", cascade="all, delete-orphan"
    )

    __table_args__ = (
        UniqueConstraint("tenant_id", "identifier", name="uq_tender_package_tenant_identifier"),
        UniqueConstraint("tenant_id", "id", name="uq_tender_packages_tenant_id"),
        Index("idx_tender_package_tenant_state", "tenant_id", "state"),
    )


class TenderRevision(Base, UUIDMixin, TenantMixin):
    __tablename__ = "tender_revisions"

    tender_id: Mapped[UUIDType] = mapped_column(UUID(as_uuid=True), nullable=False, index=True)
    revision: Mapped[int] = mapped_column(Integer, nullable=False)
    reason: Mapped[str] = mapped_column(String(500), nullable=False)
    source_hash: Mapped[str | None] = mapped_column(String(64), nullable=True)
    model_snapshot: Mapped[dict] = mapped_column(JSONB, default=dict, nullable=False)
    impact_summary: Mapped[dict] = mapped_column(JSONB, default=dict, nullable=False)
    frozen: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)

    tender: Mapped[TenderPackage] = relationship(back_populates="revisions")

    __table_args__ = (
        UniqueConstraint("tender_id", "revision", name="uq_tender_revision"),
        ForeignKeyConstraint(["tenant_id", "tender_id"], ["tender_packages.tenant_id", "tender_packages.id"], ondelete="CASCADE"),
    )


class JurisdictionProfile(Base, UUIDMixin, TenantMixin, AuditMixin):
    tenant_id: Mapped[UUIDType | None] = mapped_column(UUID(as_uuid=True), ForeignKey("tenants.id", ondelete="CASCADE"), nullable=True, index=True)
    __tablename__ = "jurisdiction_profiles"

    code: Mapped[str] = mapped_column(String(120), nullable=False)
    authority: Mapped[str] = mapped_column(String(255), nullable=False)
    government_level: Mapped[str] = mapped_column(String(50), nullable=False)
    matter: Mapped[str] = mapped_column(String(120), nullable=False)
    portal_code: Mapped[str | None] = mapped_column(String(120), nullable=True)
    profile_version: Mapped[int] = mapped_column(Integer, default=1, nullable=False)
    ruleset: Mapped[dict] = mapped_column(JSONB, default=dict, nullable=False)
    templates: Mapped[dict] = mapped_column(JSONB, default=dict, nullable=False)
    active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)

    __table_args__ = (UniqueConstraint("tenant_id", "code", name="uq_jurisdiction_profile_tenant_code"),)


class LegalSource(Base, UUIDMixin, TenantMixin, AuditMixin):
    tenant_id: Mapped[UUIDType | None] = mapped_column(UUID(as_uuid=True), ForeignKey("tenants.id", ondelete="CASCADE"), nullable=True, index=True)
    __tablename__ = "legal_sources"

    authority: Mapped[str] = mapped_column(String(255), nullable=False)
    title: Mapped[str] = mapped_column(String(500), nullable=False)
    citation: Mapped[str | None] = mapped_column(String(500), nullable=True)
    source_uri: Mapped[str | None] = mapped_column(String(1000), nullable=True)
    publication_date: Mapped[str | None] = mapped_column(String(20), nullable=True)
    effective_from: Mapped[str | None] = mapped_column(String(20), nullable=True)
    effective_to: Mapped[str | None] = mapped_column(String(20), nullable=True)
    version: Mapped[str] = mapped_column(String(120), nullable=False)
    content_hash: Mapped[str | None] = mapped_column(String(64), nullable=True)
    jurisdiction_code: Mapped[str | None] = mapped_column(String(120), nullable=True)
    status: Mapped[str] = mapped_column(String(30), default="ACTIVE", nullable=False)


class LegalArticle(Base, UUIDMixin):
    __tablename__ = "legal_articles"
    source_id: Mapped[UUIDType] = mapped_column(UUID(as_uuid=True), ForeignKey("legal_sources.id", ondelete="CASCADE"), nullable=False, index=True)
    article_code: Mapped[str] = mapped_column(String(80), nullable=False)
    title: Mapped[str | None] = mapped_column(String(500), nullable=True)
    summary: Mapped[str] = mapped_column(Text, nullable=False)
    effective_from: Mapped[str | None] = mapped_column(String(20), nullable=True)
    effective_to: Mapped[str | None] = mapped_column(String(20), nullable=True)
    content_hash: Mapped[str | None] = mapped_column(String(64), nullable=True)
    status: Mapped[str] = mapped_column(String(30), default="ACTIVE", nullable=False)

    __table_args__ = (UniqueConstraint("source_id", "article_code", name="uq_legal_article_source_code"),)


class LegalRule(Base, UUIDMixin, TenantMixin, AuditMixin):
    __tablename__ = "legal_rules"
    tenant_id: Mapped[UUIDType | None] = mapped_column(UUID(as_uuid=True), ForeignKey("tenants.id", ondelete="CASCADE"), nullable=True, index=True)

    rule_id: Mapped[str] = mapped_column(String(120), nullable=False)
    jurisdiction_code: Mapped[str | None] = mapped_column(String(120), nullable=True, index=True)
    domain: Mapped[str] = mapped_column(String(80), nullable=False)
    procedure_type: Mapped[str | None] = mapped_column(String(80), nullable=True)
    source_id: Mapped[UUIDType | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("legal_sources.id", ondelete="SET NULL"), nullable=True
    )
    article_id: Mapped[UUIDType | None] = mapped_column(UUID(as_uuid=True), ForeignKey("legal_articles.id", ondelete="SET NULL"), nullable=True, index=True)
    source_version: Mapped[str | None] = mapped_column(String(120), nullable=True)
    condition: Mapped[dict] = mapped_column(JSONB, default=dict, nullable=False)
    requirement: Mapped[dict] = mapped_column(JSONB, default=dict, nullable=False)
    validation: Mapped[dict] = mapped_column(JSONB, default=dict, nullable=False)
    severity: Mapped[str] = mapped_column(String(30), default="BLOCKER", nullable=False)
    effective_from: Mapped[str | None] = mapped_column(String(20), nullable=True)
    effective_to: Mapped[str | None] = mapped_column(String(20), nullable=True)
    rule_version: Mapped[int] = mapped_column(Integer, default=1, nullable=False)
    active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)

    __table_args__ = (
        UniqueConstraint("tenant_id", "rule_id", "rule_version", name="uq_legal_rule_version"),
    )



class ProcedureThreshold(Base, UUIDMixin, TenantMixin, AuditMixin):
    """Umbrales de procedimiento por jurisdicción y ejercicio fiscal.

    Los montos NO viven en código Python. Cada renglón representa un tramo
    presupuestal del Anexo 9 (o equivalente estatal) y se resuelve en runtime
    por JurisdictionProfile + herencia.
    """
    __tablename__ = "procedure_thresholds"

    tenant_id: Mapped[UUIDType | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("tenants.id", ondelete="CASCADE"), nullable=True, index=True
    )
    jurisdiction_code: Mapped[str] = mapped_column(String(120), nullable=False, index=True)
    government_level: Mapped[str] = mapped_column(String(50), nullable=False, default="FEDERAL")
    matter: Mapped[str] = mapped_column(String(120), nullable=False, default="PUBLIC_WORKS")
    tipo_contratacion: Mapped[str] = mapped_column(String(80), nullable=False, index=True)
    ejercicio_fiscal: Mapped[int] = mapped_column(Integer, nullable=False, index=True)
    presupuesto_min_miles: Mapped[float] = mapped_column(Numeric(18, 4), nullable=False, default=0)
    presupuesto_max_miles: Mapped[float | None] = mapped_column(Numeric(18, 4), nullable=True)
    adjudicacion_directa_miles: Mapped[float] = mapped_column(Numeric(18, 4), nullable=False)
    invitacion_restringida_miles: Mapped[float] = mapped_column(Numeric(18, 4), nullable=False)
    adjudicacion_directa_servicio_miles: Mapped[float | None] = mapped_column(Numeric(18, 4), nullable=True)
    invitacion_restringida_servicio_miles: Mapped[float | None] = mapped_column(Numeric(18, 4), nullable=True)
    ley: Mapped[str] = mapped_column(String(120), nullable=False)
    articulo_referencia: Mapped[str] = mapped_column(String(120), nullable=False)
    fuente: Mapped[str] = mapped_column(String(500), nullable=False)
    fuente_uri: Mapped[str | None] = mapped_column(String(1000), nullable=True)
    fecha_publicacion: Mapped[str | None] = mapped_column(String(20), nullable=True)
    estado_dato: Mapped[str] = mapped_column(String(30), nullable=False, default="PENDIENTE")
    notas: Mapped[str | None] = mapped_column(Text, nullable=True)
    active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)

    __table_args__ = (
        Index(
            "idx_procedure_threshold_lookup",
            "jurisdiction_code",
            "tipo_contratacion",
            "ejercicio_fiscal",
            "active",
        ),
        UniqueConstraint(
            "tenant_id",
            "jurisdiction_code",
            "tipo_contratacion",
            "ejercicio_fiscal",
            "presupuesto_min_miles",
            name="uq_procedure_threshold_tramo",
        ),
    )



class CatalogTerm(Base, UUIDMixin, TenantMixin, AuditMixin):
    """Vocabulario de catálogo de procurement (labels) — fuente de verdad en DB.

    domain: PROCEDURES | CONTRACT_TYPES | EVALUATION_CRITERIA | PROJECT_TYPES |
            FUNDING_SOURCES | OBJECT_CLASSES | LEGAL_REGIMES | SCOPE_SCALES
    """

    __tablename__ = "catalog_terms"

    domain: Mapped[str] = mapped_column(String(80), nullable=False, index=True)
    code: Mapped[str] = mapped_column(String(80), nullable=False, index=True)
    label: Mapped[str] = mapped_column(String(255), nullable=False)
    sort_order: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    active: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    meta: Mapped[dict] = mapped_column(JSONB, default=dict, nullable=False)

    __table_args__ = (
        UniqueConstraint("tenant_id", "domain", "code", name="uq_catalog_term_tenant_domain_code"),
        Index("idx_catalog_term_domain_active", "domain", "active"),
    )


class JurisdictionInheritance(Base, UUIDMixin, TenantMixin):

    __tablename__ = "jurisdiction_inheritance"

    child_profile_id: Mapped[UUIDType] = mapped_column(UUID(as_uuid=True), ForeignKey("jurisdiction_profiles.id", ondelete="CASCADE"), nullable=False, index=True)
    parent_profile_id: Mapped[UUIDType] = mapped_column(UUID(as_uuid=True), ForeignKey("jurisdiction_profiles.id", ondelete="CASCADE"), nullable=False, index=True)
    effective_from: Mapped[str | None] = mapped_column(String(20), nullable=True)
    effective_to: Mapped[str | None] = mapped_column(String(20), nullable=True)
    active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)

    __table_args__ = (UniqueConstraint("tenant_id", "child_profile_id", "parent_profile_id", name="uq_jurisdiction_inheritance"),)


class TenderRequirement(Base, UUIDMixin, TenantMixin, AuditMixin):
    __tablename__ = "tender_requirements"

    tender_id: Mapped[UUIDType] = mapped_column(
        UUID(as_uuid=True), nullable=False, index=True
    )
    code: Mapped[str] = mapped_column(String(120), nullable=False)
    category: Mapped[str] = mapped_column(String(40), nullable=False)
    description: Mapped[str] = mapped_column(Text, nullable=False)
    mandatory: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    condition: Mapped[dict] = mapped_column(JSONB, default=dict, nullable=False)
    source_reference: Mapped[dict] = mapped_column(JSONB, default=dict, nullable=False)
    legal_rule_id: Mapped[UUIDType | None] = mapped_column(UUID(as_uuid=True), ForeignKey("legal_rules.id", ondelete="SET NULL"), nullable=True, index=True)
    legal_article_id: Mapped[UUIDType | None] = mapped_column(UUID(as_uuid=True), ForeignKey("legal_articles.id", ondelete="SET NULL"), nullable=True, index=True)
    evidence_required: Mapped[list] = mapped_column(JSONB, default=list, nullable=False)
    artifact_required: Mapped[list] = mapped_column(JSONB, default=list, nullable=False)
    validator_code: Mapped[str | None] = mapped_column(String(120), nullable=True)
    approver_role: Mapped[str | None] = mapped_column(String(120), nullable=True)
    severity: Mapped[str] = mapped_column(String(30), default="BLOCKER", nullable=False)
    status: Mapped[str] = mapped_column(String(30), default=RequirementStatus.PENDING.value, nullable=False)
    evaluated_at: Mapped[str | None] = mapped_column(String(40), nullable=True)
    rule_definition_id: Mapped[UUIDType | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("tender_rule_definitions.id", ondelete="SET NULL"), nullable=True, index=True
    )

    tender: Mapped[TenderPackage] = relationship(back_populates="requirements")
    rule_definition: Mapped["TenderRuleDefinition | None"] = relationship(
        foreign_keys=[rule_definition_id]
    )

    __table_args__ = (
        UniqueConstraint("tenant_id", "id", name="uq_tender_requirements_tenant_id"),
        UniqueConstraint("tender_id", "code", name="uq_tender_requirement_code"),
        ForeignKeyConstraint(["tenant_id", "tender_id"], ["tender_packages.tenant_id", "tender_packages.id"], ondelete="CASCADE"),
    )


class TenderRuleDefinition(Base, UUIDMixin, TenantMixin, AuditMixin):
    """Versioned executable definition behind a tender requirement.

    The requirement remains the business-facing object; this table owns the
    immutable rule source/version and its deterministic test cases.
    """

    __tablename__ = "tender_rule_definitions"
    tender_id: Mapped[UUIDType] = mapped_column(UUID(as_uuid=True), nullable=False, index=True)
    requirement_id: Mapped[UUIDType] = mapped_column(UUID(as_uuid=True), nullable=False, index=True)
    code: Mapped[str] = mapped_column(String(120), nullable=False)
    version: Mapped[int] = mapped_column(Integer, nullable=False, default=1)
    status: Mapped[str] = mapped_column(String(30), nullable=False, default="ACTIVE")
    definition: Mapped[dict] = mapped_column(JSONB, default=dict, nullable=False)
    test_cases: Mapped[list] = mapped_column(JSONB, default=list, nullable=False)
    compiled_hash: Mapped[str | None] = mapped_column(String(64), nullable=True)
    source_reference: Mapped[dict] = mapped_column(JSONB, default=dict, nullable=False)
    activated_at: Mapped[str | None] = mapped_column(String(40), nullable=True)
    retired_at: Mapped[str | None] = mapped_column(String(40), nullable=True)

    requirement: Mapped[TenderRequirement] = relationship(
        foreign_keys=[requirement_id]
    )

    __table_args__ = (
        UniqueConstraint("tenant_id", "id", name="uq_tender_rule_definitions_tenant_id"),
        UniqueConstraint("tenant_id", "tender_id", "code", "version", name="uq_tender_rule_definition_version"),
        ForeignKeyConstraint(["tenant_id", "tender_id"], ["tender_packages.tenant_id", "tender_packages.id"], ondelete="CASCADE"),
        ForeignKeyConstraint(["tenant_id", "requirement_id"], ["tender_requirements.tenant_id", "tender_requirements.id"], ondelete="CASCADE"),
        CheckConstraint("status <> 'ACTIVE' OR COALESCE(jsonb_array_length(test_cases), 0) > 0", name="ck_tender_rule_active_requires_tests"),
        CheckConstraint("status <> 'ACTIVE' OR compiled_hash IS NOT NULL", name="ck_tender_rule_active_requires_hash"),
        Index("idx_tender_rule_definition_active", "tenant_id", "tender_id", "code", "status"),
    )


class TenderEvidence(Base, UUIDMixin, TenantMixin, AuditMixin):
    __tablename__ = "tender_evidence"

    tender_id: Mapped[UUIDType] = mapped_column(
        UUID(as_uuid=True), nullable=False, index=True
    )
    kind: Mapped[str] = mapped_column(String(40), nullable=False)
    subject: Mapped[str] = mapped_column(String(255), nullable=False)
    value: Mapped[dict] = mapped_column(JSONB, default=dict, nullable=False)
    source_uri: Mapped[str | None] = mapped_column(String(1000), nullable=True)
    extraction_uri: Mapped[str | None] = mapped_column(String(1000), nullable=True)
    source_hash: Mapped[str | None] = mapped_column(String(64), nullable=True)
    source_revision: Mapped[int | None] = mapped_column(Integer, nullable=True)
    valid_from: Mapped[str | None] = mapped_column(String(40), nullable=True)
    valid_to: Mapped[str | None] = mapped_column(String(40), nullable=True)
    status: Mapped[str] = mapped_column(String(30), default="ACTIVE", nullable=False)

    tender: Mapped[TenderPackage] = relationship(back_populates="evidence")

    __table_args__ = (
        UniqueConstraint("tenant_id", "id", name="uq_tender_evidence_tenant_id"),
        Index(
            "uq_tender_evidence_source_hash", "tender_id", "source_hash",
            unique=True, postgresql_where=text("source_hash IS NOT NULL AND kind = 'SOURCE_DOCUMENT'")
        ),
        ForeignKeyConstraint(["tenant_id", "tender_id"], ["tender_packages.tenant_id", "tender_packages.id"], ondelete="CASCADE"),
    )


class TenderEvidenceLink(Base, UUIDMixin, TenantMixin):
    __tablename__ = "tender_evidence_links"

    tender_id: Mapped[UUIDType] = mapped_column(
        UUID(as_uuid=True), nullable=False, index=True
    )
    evidence_id: Mapped[UUIDType] = mapped_column(
        UUID(as_uuid=True), nullable=False, index=True
    )
    requirement_id: Mapped[UUIDType | None] = mapped_column(
        UUID(as_uuid=True), nullable=True, index=True
    )
    artifact_id: Mapped[UUIDType | None] = mapped_column(
        UUID(as_uuid=True), nullable=True, index=True
    )
    relation: Mapped[str] = mapped_column(String(80), nullable=False)

    __table_args__ = (
        ForeignKeyConstraint(["tenant_id", "tender_id"], ["tender_packages.tenant_id", "tender_packages.id"], ondelete="CASCADE"),
        ForeignKeyConstraint(["tenant_id", "evidence_id"], ["tender_evidence.tenant_id", "tender_evidence.id"], ondelete="CASCADE"),
        ForeignKeyConstraint(["tenant_id", "requirement_id"], ["tender_requirements.tenant_id", "tender_requirements.id"], ondelete="CASCADE"),
        ForeignKeyConstraint(["tenant_id", "artifact_id"], ["tender_artifacts.tenant_id", "tender_artifacts.id"], ondelete="CASCADE"),
    )


class TenderArtifact(Base, UUIDMixin, TenantMixin, AuditMixin):
    __tablename__ = "tender_artifacts"

    tender_id: Mapped[UUIDType] = mapped_column(
        UUID(as_uuid=True), nullable=False, index=True
    )
    artifact_code: Mapped[str] = mapped_column(String(120), nullable=False)
    name: Mapped[str] = mapped_column(String(500), nullable=False)
    media_type: Mapped[str] = mapped_column(String(120), nullable=False)
    version: Mapped[int] = mapped_column(Integer, default=1, nullable=False)
    status: Mapped[str] = mapped_column(String(30), default=ArtifactStatus.DRAFT.value, nullable=False)
    source_model_hash: Mapped[str | None] = mapped_column(String(64), nullable=True)
    storage_path: Mapped[str | None] = mapped_column(String(1000), nullable=True)
    content_hash: Mapped[str | None] = mapped_column(String(64), nullable=True)
    artifact_metadata: Mapped[dict] = mapped_column("metadata", JSONB, default=dict, nullable=False)
    signature_idempotency_key: Mapped[str | None] = mapped_column(String(128), nullable=True)

    tender: Mapped[TenderPackage] = relationship(back_populates="artifacts")

    __table_args__ = (
        UniqueConstraint("tenant_id", "id", name="uq_tender_artifacts_tenant_id"),
        UniqueConstraint("tender_id", "artifact_code", "version", name="uq_tender_artifact_version"),
        UniqueConstraint("tenant_id", "signature_idempotency_key", name="uq_tender_artifact_signature_idempotency"),
        ForeignKeyConstraint(["tenant_id", "tender_id"], ["tender_packages.tenant_id", "tender_packages.id"], ondelete="CASCADE"),
    )




class TenderLicitacionBridge(Base, UUIDMixin, TenantMixin, AuditMixin):
    """Explicit ownership bridge between proposal preparation and formal procurement lifecycle."""
    __tablename__ = "tender_licitacion_bridges"

    tender_package_id: Mapped[UUIDType] = mapped_column(UUID(as_uuid=True), nullable=False, index=True)
    licitacion_id: Mapped[UUIDType] = mapped_column(UUID(as_uuid=True), nullable=False, index=True)
    expediente_id: Mapped[UUIDType] = mapped_column(UUID(as_uuid=True), nullable=False, index=True)
    relationship_type: Mapped[str] = mapped_column(String(40), nullable=False, default="PRIMARY")
    active: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True, index=True)
    contract_version: Mapped[int] = mapped_column(Integer, nullable=False, default=1)
    field_mapping: Mapped[dict] = mapped_column(JSONB, default=dict, nullable=False)
    last_tender_revision: Mapped[int | None] = mapped_column(Integer, nullable=True)
    last_licitacion_version: Mapped[int | None] = mapped_column(Integer, nullable=True)
    conflict_policy: Mapped[str] = mapped_column(String(40), nullable=False, default="FAIL_CLOSED")

    __table_args__ = (
        UniqueConstraint("tenant_id", "tender_package_id", "licitacion_id", name="uq_tender_licitacion_bridge"),
        Index("idx_tender_bridge_tenant_active", "tenant_id", "active"),
        ForeignKeyConstraint(["tenant_id", "tender_package_id"], ["tender_packages.tenant_id", "tender_packages.id"], ondelete="CASCADE"),
        ForeignKeyConstraint(["tenant_id", "licitacion_id"], ["licitaciones.tenant_id", "licitaciones.id"], ondelete="CASCADE"),
        ForeignKeyConstraint(["tenant_id", "expediente_id"], ["expedientes_obra.tenant_id", "expedientes_obra.id"], ondelete="CASCADE"),
    )


class BridgeFieldContract(Base, UUIDMixin, AuditMixin):
    """Contrato versionado de campos para TenderLicitacionBridge.

    FIX P1 auditoría 2026-09-14: antes el mapping de campos vivía como un
    dict literal escrito en Python dentro de TenderWorkspaceService.bridge()
    -- cualquier cambio de reglas exigía un deploy de código, y no existía
    ningún registro versionado externo. Ahora es una tabla: se puede tener
    más de una versión, activar/desactivar sin tocar código, y -- lo que
    resolvía el hallazgo de "no es realmente bidireccional por defecto" --
    un operador puede agregar reglas LICITACION_TO_TENDER sin deploy.

    tenant_id es NULLABLE a propósito: NULL = contrato global (aplica a
    todos los tenants salvo que tengan uno propio). Si un tenant necesita
    un contrato distinto, se le crea una fila con su tenant_id -- consulta
    en TenderWorkspaceService.bridge() prioriza el contrato del tenant
    sobre el global.
    """
    __tablename__ = "bridge_field_contracts"

    tenant_id: Mapped[UUIDType | None] = mapped_column(UUID(as_uuid=True), ForeignKey("tenants.id", ondelete="CASCADE"), nullable=True, index=True)
    version: Mapped[int] = mapped_column(Integer, nullable=False)
    is_active: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True, index=True)
    fields: Mapped[list] = mapped_column(JSONB, default=list, nullable=False)
    notes: Mapped[str | None] = mapped_column(Text, nullable=True)

    __table_args__ = (
        UniqueConstraint("tenant_id", "version", name="uq_bridge_contract_tenant_version"),
        Index("idx_bridge_contract_active", "tenant_id", "is_active"),
    )


class TenderDocument(Base, UUIDMixin, TenantMixin, AuditMixin):
    """Editable document owned by a TenderPackage workspace."""
    __tablename__ = "tender_documents"

    tender_id: Mapped[UUIDType] = mapped_column(UUID(as_uuid=True), nullable=False, index=True)
    artifact_code: Mapped[str] = mapped_column(String(120), nullable=False)
    name: Mapped[str] = mapped_column(String(500), nullable=False)
    media_type: Mapped[str] = mapped_column(String(120), nullable=False, default="text/plain")
    content_text: Mapped[str] = mapped_column(Text, nullable=False, default="")
    content_model: Mapped[dict] = mapped_column(JSONB, default=dict, nullable=False)
    status: Mapped[str] = mapped_column(String(30), nullable=False, default="DRAFT")
    version: Mapped[int] = mapped_column(Integer, nullable=False, default=1)
    tender_revision: Mapped[int] = mapped_column(Integer, nullable=False)
    generated_from_revision: Mapped[int | None] = mapped_column(Integer, nullable=True)
    generated_model_hash: Mapped[str | None] = mapped_column(String(64), nullable=True)
    human_modified: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    locked: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    source_evidence_ids: Mapped[list] = mapped_column(JSONB, default=list, nullable=False)
    requirement_ids: Mapped[list] = mapped_column(JSONB, default=list, nullable=False)
    data_dependencies: Mapped[list] = mapped_column(JSONB, default=list, nullable=False)
    warnings: Mapped[list] = mapped_column(JSONB, default=list, nullable=False)
    last_conflict: Mapped[dict | None] = mapped_column(JSONB, nullable=True)
    row_version: Mapped[int] = mapped_column(Integer, default=1, nullable=False)

    __mapper_args__ = {"version_id_col": row_version, "version_id_generator": lambda v: (v or 0) + 1}

    __table_args__ = (
        UniqueConstraint("tenant_id", "id", name="uq_tender_document_tenant_id"),
        UniqueConstraint("tenant_id", "tender_id", "artifact_code", "version", name="uq_tender_document_version"),
        ForeignKeyConstraint(["tenant_id", "tender_id"], ["tender_packages.tenant_id", "tender_packages.id"], ondelete="CASCADE"),
    )


class TenderDocumentRevision(Base, UUIDMixin, TenantMixin):
    """Immutable document history; every persisted edit/regeneration gets a revision."""
    __tablename__ = "tender_document_revisions"

    document_id: Mapped[UUIDType] = mapped_column(UUID(as_uuid=True), nullable=False, index=True)
    version: Mapped[int] = mapped_column(Integer, nullable=False)
    operation: Mapped[str] = mapped_column(String(40), nullable=False)
    content_text: Mapped[str] = mapped_column(Text, nullable=False, default="")
    content_model: Mapped[dict] = mapped_column(JSONB, default=dict, nullable=False)
    tender_revision: Mapped[int] = mapped_column(Integer, nullable=False)
    source_model_hash: Mapped[str | None] = mapped_column(String(64), nullable=True)
    human_modified: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    revision_metadata: Mapped[dict] = mapped_column("metadata", JSONB, default=dict, nullable=False)

    __table_args__ = (
        UniqueConstraint("tenant_id", "document_id", "version", name="uq_tender_document_revision"),
        ForeignKeyConstraint(["tenant_id", "document_id"], ["tender_documents.tenant_id", "tender_documents.id"], ondelete="CASCADE"),
    )


class TenderDependency(Base, UUIDMixin, TenantMixin):
    __tablename__ = "tender_dependencies"

    tender_id: Mapped[UUIDType] = mapped_column(
        UUID(as_uuid=True), nullable=False, index=True
    )
    source_type: Mapped[str] = mapped_column(String(80), nullable=False)
    source_key: Mapped[str] = mapped_column(String(255), nullable=False)
    target_type: Mapped[str] = mapped_column(String(80), nullable=False)
    target_key: Mapped[str] = mapped_column(String(255), nullable=False)
    relation: Mapped[str] = mapped_column(String(80), nullable=False)
    invalidates_signed: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    artifact_metadata: Mapped[dict] = mapped_column("metadata", JSONB, default=dict, nullable=False)

    tender: Mapped[TenderPackage] = relationship(back_populates="dependencies")

    __table_args__ = (
        ForeignKeyConstraint(["tenant_id", "tender_id"], ["tender_packages.tenant_id", "tender_packages.id"], ondelete="CASCADE"),
    )


class TenderValidationRun(Base, UUIDMixin, TenantMixin, AuditMixin):
    __tablename__ = "tender_validation_runs"

    tender_id: Mapped[UUIDType] = mapped_column(
        UUID(as_uuid=True), nullable=False, index=True
    )
    engine: Mapped[str] = mapped_column(String(120), nullable=False)
    status: Mapped[str] = mapped_column(String(30), nullable=False)
    severity: Mapped[str] = mapped_column(String(30), nullable=False)
    rule_id: Mapped[str | None] = mapped_column(String(120), nullable=True)
    message: Mapped[str] = mapped_column(Text, nullable=False)
    evidence: Mapped[dict] = mapped_column(JSONB, default=dict, nullable=False)
    revision: Mapped[int] = mapped_column(Integer, nullable=False)

    tender: Mapped[TenderPackage] = relationship(back_populates="validations")

    __table_args__ = (
        UniqueConstraint("tenant_id", "id", name="uq_tender_validation_runs_tenant_id"),
        ForeignKeyConstraint(["tenant_id", "tender_id"], ["tender_packages.tenant_id", "tender_packages.id"], ondelete="CASCADE"),
    )


class TenderRuleExecution(Base, UUIDMixin, TenantMixin, AuditMixin):
    """Durable forensic record of one deterministic rule execution.

    The execution stores the exact rule artifact, input snapshot/hash and
    DecisionTable diagnostics needed to reproduce or explain a result later.
    """

    __tablename__ = "tender_rule_executions"

    tender_id: Mapped[UUIDType] = mapped_column(UUID(as_uuid=True), nullable=False, index=True)
    requirement_id: Mapped[UUIDType] = mapped_column(UUID(as_uuid=True), nullable=False, index=True)
    rule_definition_id: Mapped[UUIDType | None] = mapped_column(UUID(as_uuid=True), nullable=True, index=True)
    validation_run_id: Mapped[UUIDType | None] = mapped_column(UUID(as_uuid=True), nullable=True, index=True)
    rule_code: Mapped[str] = mapped_column(String(120), nullable=False)
    rule_version: Mapped[int | None] = mapped_column(Integer, nullable=True)
    compiled_hash: Mapped[str | None] = mapped_column(String(64), nullable=True)
    source_reference: Mapped[dict] = mapped_column(JSONB, default=dict, nullable=False)
    engine_version: Mapped[str] = mapped_column(String(120), nullable=False)
    execution_status: Mapped[str] = mapped_column(String(30), nullable=False)
    matched: Mapped[bool | None] = mapped_column(Boolean, nullable=True)
    input_facts_hash: Mapped[str] = mapped_column(String(64), nullable=False)
    input_facts: Mapped[dict] = mapped_column(JSONB, default=dict, nullable=False)
    hit_policy: Mapped[str | None] = mapped_column(String(20), nullable=True)
    selected_row_ids: Mapped[list] = mapped_column(JSONB, default=list, nullable=False)
    evaluated_conditions: Mapped[list] = mapped_column(JSONB, default=list, nullable=False)
    actions: Mapped[list] = mapped_column(JSONB, default=list, nullable=False)
    result_payload: Mapped[dict] = mapped_column(JSONB, default=dict, nullable=False)
    error_code: Mapped[str | None] = mapped_column(String(120), nullable=True)
    revision: Mapped[int] = mapped_column(Integer, nullable=False)
    executed_at: Mapped[str] = mapped_column(String(40), nullable=False)

    __table_args__ = (
        ForeignKeyConstraint(["tenant_id", "tender_id"], ["tender_packages.tenant_id", "tender_packages.id"], ondelete="CASCADE"),
        ForeignKeyConstraint(["tenant_id", "requirement_id"], ["tender_requirements.tenant_id", "tender_requirements.id"], ondelete="CASCADE"),
        ForeignKeyConstraint(["tenant_id", "rule_definition_id"], ["tender_rule_definitions.tenant_id", "tender_rule_definitions.id"], ondelete="RESTRICT"),
        ForeignKeyConstraint(["tenant_id", "validation_run_id"], ["tender_validation_runs.tenant_id", "tender_validation_runs.id"], ondelete="RESTRICT"),
        Index("idx_tender_rule_execution_tenant_requirement_revision", "tenant_id", "requirement_id", "revision"),
        Index("idx_tender_rule_execution_tenant_hash", "tenant_id", "compiled_hash"),
    )


class TenderValidationEvidenceLink(Base, UUIDMixin, TenantMixin):
    __tablename__ = "tender_validation_evidence_links"

    validation_run_id: Mapped[UUIDType] = mapped_column(UUID(as_uuid=True), nullable=False, index=True)
    evidence_id: Mapped[UUIDType] = mapped_column(UUID(as_uuid=True), nullable=False, index=True)
    relation: Mapped[str] = mapped_column(String(80), nullable=False, default="SUPPORTS")

    __table_args__ = (
        ForeignKeyConstraint(["tenant_id", "validation_run_id"], ["tender_validation_runs.tenant_id", "tender_validation_runs.id"], ondelete="CASCADE"),
        ForeignKeyConstraint(["tenant_id", "evidence_id"], ["tender_evidence.tenant_id", "tender_evidence.id"], ondelete="CASCADE"),
        UniqueConstraint("tenant_id", "validation_run_id", "evidence_id", "relation", name="uq_tender_validation_evidence_link"),
    )


class TenderApproval(Base, UUIDMixin, TenantMixin, AuditMixin):
    __tablename__ = "tender_approvals"

    tender_id: Mapped[UUIDType] = mapped_column(
        UUID(as_uuid=True), nullable=False, index=True
    )
    role: Mapped[str] = mapped_column(String(120), nullable=False)
    decision: Mapped[str] = mapped_column(String(40), nullable=False)
    reason: Mapped[str | None] = mapped_column(Text, nullable=True)
    revision: Mapped[int] = mapped_column(Integer, nullable=False)

    __table_args__ = (
        UniqueConstraint("tender_id", "revision", "role", name="uq_tender_approval_role_revision"),
        ForeignKeyConstraint(["tenant_id", "tender_id"], ["tender_packages.tenant_id", "tender_packages.id"], ondelete="CASCADE"),
    )


class SubmissionPackage(Base, UUIDMixin, TenantMixin, AuditMixin):
    __tablename__ = "submission_packages"

    tender_id: Mapped[UUIDType] = mapped_column(
        UUID(as_uuid=True), nullable=False, index=True
    )
    revision: Mapped[int] = mapped_column(Integer, nullable=False)
    manifest: Mapped[dict] = mapped_column(JSONB, default=dict, nullable=False)
    package_hash: Mapped[str | None] = mapped_column(String(64), nullable=True)
    signed_hash: Mapped[str | None] = mapped_column(String(64), nullable=True)
    status: Mapped[str] = mapped_column(String(40), default="DRAFT", nullable=False)
    portal_code: Mapped[str | None] = mapped_column(String(120), nullable=True)
    receipt: Mapped[dict | None] = mapped_column(JSONB, nullable=True)
    idempotency_key: Mapped[str | None] = mapped_column(String(128), nullable=True)

    __table_args__ = (
        UniqueConstraint("tender_id", "revision", name="uq_submission_package_revision"),
        UniqueConstraint("tenant_id", "idempotency_key", name="uq_submission_package_idempotency"),
        ForeignKeyConstraint(["tenant_id", "tender_id"], ["tender_packages.tenant_id", "tender_packages.id"], ondelete="CASCADE"),
    )


class PreparationRunStatus(str, Enum):
    RUNNING = "RUNNING"
    BLOCKED = "BLOCKED"
    FAILED = "FAILED"
    READY_FOR_HUMAN_REVIEW = "READY_FOR_HUMAN_REVIEW"
    CANCELLED = "CANCELLED"


class PreparationStageStatus(str, Enum):
    RUNNING = "RUNNING"
    PASS = "PASS"
    BLOCKED = "BLOCKED"
    FAILED = "FAILED"
    SKIPPED = "SKIPPED"


class TenderPreparationRun(Base, UUIDMixin, TenantMixin, AuditMixin):
    __tablename__ = "tender_preparation_runs"

    tender_id: Mapped[UUIDType] = mapped_column(
        UUID(as_uuid=True), nullable=False, index=True
    )
    correlation_id: Mapped[str] = mapped_column(String(120), nullable=False, index=True)
    pipeline_version: Mapped[str] = mapped_column(String(80), nullable=False)
    status: Mapped[str] = mapped_column(String(40), nullable=False, default=PreparationRunStatus.RUNNING.value, index=True)
    current_stage: Mapped[str | None] = mapped_column(String(80), nullable=True)
    failure_code: Mapped[str | None] = mapped_column(String(120), nullable=True)
    failure_detail: Mapped[str | None] = mapped_column(Text, nullable=True)
    started_at: Mapped[str | None] = mapped_column(String(40), nullable=True)
    finished_at: Mapped[str | None] = mapped_column(String(40), nullable=True)

    __table_args__ = (
        UniqueConstraint("tenant_id", "id", name="uq_tender_preparation_runs_tenant_id"),
        Index("idx_tender_preparation_run_tenant_tender", "tenant_id", "tender_id", "created_at"),
        ForeignKeyConstraint(["tenant_id", "tender_id"], ["tender_packages.tenant_id", "tender_packages.id"], ondelete="CASCADE"),
    )


class TenderPreparationStageRun(Base, UUIDMixin, TenantMixin):
    __tablename__ = "tender_preparation_stage_runs"

    preparation_run_id: Mapped[UUIDType] = mapped_column(
        UUID(as_uuid=True), nullable=False, index=True
    )
    stage: Mapped[str] = mapped_column(String(80), nullable=False)
    status: Mapped[str] = mapped_column(String(30), nullable=False)
    input_refs: Mapped[dict] = mapped_column(JSONB, default=dict, nullable=False)
    output_refs: Mapped[dict] = mapped_column(JSONB, default=dict, nullable=False)
    rule_version: Mapped[str | None] = mapped_column(String(120), nullable=True)
    engine_version: Mapped[str | None] = mapped_column(String(120), nullable=True)
    error_code: Mapped[str | None] = mapped_column(String(120), nullable=True)
    error_detail: Mapped[str | None] = mapped_column(Text, nullable=True)
    started_at: Mapped[str | None] = mapped_column(String(40), nullable=True)
    finished_at: Mapped[str | None] = mapped_column(String(40), nullable=True)

    __table_args__ = (
        Index("idx_tender_stage_run_tenant_run_stage", "tenant_id", "preparation_run_id", "stage"),
        ForeignKeyConstraint(["tenant_id", "preparation_run_id"], ["tender_preparation_runs.tenant_id", "tender_preparation_runs.id"], ondelete="CASCADE"),
    )
