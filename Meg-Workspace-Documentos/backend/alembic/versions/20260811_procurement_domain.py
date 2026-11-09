"""Create Tender Automation Domain tables explicitly.

This migration is intentionally explicit; it does not invoke SQLAlchemy
metadata.create_all(), so production schema changes remain visible to Alembic
and can be reviewed, ordered and rolled back.
"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision = "20260811_procurement"
down_revision = "ff2a1b3c4d5e"
branch_labels = None
depends_on = None

UUID = postgresql.UUID(as_uuid=True)
JSONB = postgresql.JSONB


def _common(audit: bool = False, tenant: bool = True):
    cols = [
        sa.Column("id", UUID, primary_key=True, nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
    ]
    if tenant:
        cols.append(sa.Column("tenant_id", UUID, sa.ForeignKey("tenants.id", ondelete="CASCADE"), nullable=False))
    if audit:
        cols.extend([
            sa.Column("creado_por_id", UUID, sa.ForeignKey("users.id", ondelete="SET NULL"), nullable=True),
            sa.Column("actualizado_por_id", UUID, sa.ForeignKey("users.id", ondelete="SET NULL"), nullable=True),
        ])
    return cols


def upgrade() -> None:
    op.create_table(
        "tender_packages",
        *_common(audit=True),
        sa.Column("expediente_id", UUID, sa.ForeignKey("expedientes_obra.id", ondelete="CASCADE"), nullable=False),
        sa.Column("identifier", sa.String(120), nullable=False),
        sa.Column("title", sa.String(500), nullable=False),
        sa.Column("state", sa.String(50), nullable=False, server_default="DISCOVERED"),
        sa.Column("jurisdiction_code", sa.String(120), nullable=True),
        sa.Column("procedure_type", sa.String(80), nullable=True),
        sa.Column("contract_type", sa.String(80), nullable=True),
        sa.Column("source_manifest", JSONB, nullable=False, server_default=sa.text("'{}'::jsonb")),
        sa.Column("canonical_model", JSONB, nullable=False, server_default=sa.text("'{}'::jsonb")),
        sa.Column("current_revision", sa.Integer, nullable=False, server_default="1"),
        sa.Column("frozen", sa.Boolean, nullable=False, server_default=sa.false()),
        sa.UniqueConstraint("tenant_id", "identifier", name="uq_tender_package_tenant_identifier"),
    )
    op.create_index("idx_tender_packages_tenant", "tender_packages", ["tenant_id"])
    op.create_index("idx_tender_packages_tenant_state", "tender_packages", ["tenant_id", "state"])
    op.create_index("idx_tender_packages_expediente", "tender_packages", ["expediente_id"])
    op.create_index("idx_tender_packages_jurisdiction", "tender_packages", ["jurisdiction_code"])

    op.create_table(
        "tender_revisions",
        *_common(tenant=False),
        sa.Column("tenant_id", UUID, sa.ForeignKey("tenants.id", ondelete="CASCADE"), nullable=False),
        sa.Column("tender_id", UUID, sa.ForeignKey("tender_packages.id", ondelete="CASCADE"), nullable=False),
        sa.Column("revision", sa.Integer, nullable=False),
        sa.Column("reason", sa.String(500), nullable=False),
        sa.Column("source_hash", sa.String(64), nullable=True),
        sa.Column("model_snapshot", JSONB, nullable=False, server_default=sa.text("'{}'::jsonb")),
        sa.Column("impact_summary", JSONB, nullable=False, server_default=sa.text("'{}'::jsonb")),
        sa.Column("frozen", sa.Boolean, nullable=False, server_default=sa.false()),
        sa.UniqueConstraint("tender_id", "revision", name="uq_tender_revision"),
    )
    op.create_index("idx_tender_revisions_tender", "tender_revisions", ["tender_id"])
    op.create_index("idx_tender_revisions_tenant", "tender_revisions", ["tenant_id"])

    op.create_table(
        "jurisdiction_profiles",
        *_common(audit=True),
        sa.Column("code", sa.String(120), nullable=False),
        sa.Column("authority", sa.String(255), nullable=False),
        sa.Column("government_level", sa.String(50), nullable=False),
        sa.Column("matter", sa.String(120), nullable=False),
        sa.Column("portal_code", sa.String(120), nullable=True),
        sa.Column("profile_version", sa.Integer, nullable=False, server_default="1"),
        sa.Column("ruleset", JSONB, nullable=False, server_default=sa.text("'{}'::jsonb")),
        sa.Column("templates", JSONB, nullable=False, server_default=sa.text("'{}'::jsonb")),
        sa.Column("active", sa.Boolean, nullable=False, server_default=sa.true()),
        sa.UniqueConstraint("tenant_id", "code", name="uq_jurisdiction_profile_tenant_code"),
    )
    op.create_index("idx_jurisdiction_profiles_tenant", "jurisdiction_profiles", ["tenant_id"])

    op.create_table(
        "legal_sources",
        *_common(audit=True),
        sa.Column("authority", sa.String(255), nullable=False),
        sa.Column("title", sa.String(500), nullable=False),
        sa.Column("citation", sa.String(500), nullable=True),
        sa.Column("source_uri", sa.String(1000), nullable=True),
        sa.Column("publication_date", sa.String(20), nullable=True),
        sa.Column("effective_from", sa.String(20), nullable=True),
        sa.Column("effective_to", sa.String(20), nullable=True),
        sa.Column("version", sa.String(120), nullable=False),
        sa.Column("content_hash", sa.String(64), nullable=True),
        sa.Column("jurisdiction_code", sa.String(120), nullable=True),
    )
    op.create_index("idx_legal_sources_tenant", "legal_sources", ["tenant_id"])
    op.create_index("idx_legal_sources_jurisdiction", "legal_sources", ["jurisdiction_code"])

    op.create_table(
        "legal_rules",
        *_common(audit=True),
        sa.Column("rule_id", sa.String(120), nullable=False),
        sa.Column("jurisdiction_code", sa.String(120), nullable=True),
        sa.Column("domain", sa.String(80), nullable=False),
        sa.Column("procedure_type", sa.String(80), nullable=True),
        sa.Column("source_id", UUID, sa.ForeignKey("legal_sources.id", ondelete="SET NULL"), nullable=True),
        sa.Column("source_version", sa.String(120), nullable=True),
        sa.Column("condition", JSONB, nullable=False, server_default=sa.text("'{}'::jsonb")),
        sa.Column("requirement", JSONB, nullable=False, server_default=sa.text("'{}'::jsonb")),
        sa.Column("validation", JSONB, nullable=False, server_default=sa.text("'{}'::jsonb")),
        sa.Column("severity", sa.String(30), nullable=False, server_default="BLOCKER"),
        sa.Column("effective_from", sa.String(20), nullable=True),
        sa.Column("effective_to", sa.String(20), nullable=True),
        sa.Column("rule_version", sa.Integer, nullable=False, server_default="1"),
        sa.Column("active", sa.Boolean, nullable=False, server_default=sa.true()),
        sa.UniqueConstraint("tenant_id", "rule_id", "rule_version", name="uq_legal_rule_version"),
    )
    op.create_index("idx_legal_rules_tenant", "legal_rules", ["tenant_id"])
    op.create_index("idx_legal_rules_jurisdiction", "legal_rules", ["jurisdiction_code"])

    op.create_table(
        "tender_requirements",
        *_common(audit=True),
        sa.Column("tender_id", UUID, sa.ForeignKey("tender_packages.id", ondelete="CASCADE"), nullable=False),
        sa.Column("code", sa.String(120), nullable=False),
        sa.Column("category", sa.String(40), nullable=False),
        sa.Column("description", sa.Text, nullable=False),
        sa.Column("mandatory", sa.Boolean, nullable=False, server_default=sa.true()),
        sa.Column("condition", JSONB, nullable=False, server_default=sa.text("'{}'::jsonb")),
        sa.Column("source_reference", JSONB, nullable=False, server_default=sa.text("'{}'::jsonb")),
        sa.Column("evidence_required", JSONB, nullable=False, server_default=sa.text("'[]'::jsonb")),
        sa.Column("artifact_required", JSONB, nullable=False, server_default=sa.text("'[]'::jsonb")),
        sa.Column("validator_code", sa.String(120), nullable=True),
        sa.Column("approver_role", sa.String(120), nullable=True),
        sa.Column("severity", sa.String(30), nullable=False, server_default="BLOCKER"),
        sa.Column("status", sa.String(30), nullable=False, server_default="PENDING"),
        sa.Column("evaluated_at", sa.String(40), nullable=True),
        sa.UniqueConstraint("tender_id", "code", name="uq_tender_requirement_code"),
    )
    op.create_index("idx_tender_requirements_tenant", "tender_requirements", ["tenant_id"])
    op.create_index("idx_tender_requirements_tender", "tender_requirements", ["tender_id"])

    op.create_table(
        "tender_evidence",
        *_common(audit=True),
        sa.Column("tender_id", UUID, sa.ForeignKey("tender_packages.id", ondelete="CASCADE"), nullable=False),
        sa.Column("kind", sa.String(40), nullable=False),
        sa.Column("subject", sa.String(255), nullable=False),
        sa.Column("value", JSONB, nullable=False, server_default=sa.text("'{}'::jsonb")),
        sa.Column("source_uri", sa.String(1000), nullable=True),
        sa.Column("extraction_uri", sa.String(1000), nullable=True),
        sa.Column("source_hash", sa.String(64), nullable=True),
        sa.Column("source_revision", sa.Integer, nullable=True),
        sa.Column("valid_from", sa.String(40), nullable=True),
        sa.Column("valid_to", sa.String(40), nullable=True),
        sa.Column("status", sa.String(30), nullable=False, server_default="ACTIVE"),
    )
    op.create_index("idx_tender_evidence_tenant", "tender_evidence", ["tenant_id"])
    op.create_index("idx_tender_evidence_tender", "tender_evidence", ["tender_id"])
    op.create_index(
        "uq_tender_evidence_source_hash", "tender_evidence", ["tender_id", "source_hash"],
        unique=True, postgresql_where=sa.text("source_hash IS NOT NULL AND kind = 'SOURCE_DOCUMENT'")
    )

    op.create_table(
        "tender_artifacts",
        *_common(audit=True),
        sa.Column("tender_id", UUID, sa.ForeignKey("tender_packages.id", ondelete="CASCADE"), nullable=False),
        sa.Column("artifact_code", sa.String(120), nullable=False),
        sa.Column("name", sa.String(500), nullable=False),
        sa.Column("media_type", sa.String(120), nullable=False),
        sa.Column("version", sa.Integer, nullable=False, server_default="1"),
        sa.Column("status", sa.String(30), nullable=False, server_default="DRAFT"),
        sa.Column("source_model_hash", sa.String(64), nullable=True),
        sa.Column("storage_path", sa.String(1000), nullable=True),
        sa.Column("content_hash", sa.String(64), nullable=True),
        sa.Column("metadata", JSONB, nullable=False, server_default=sa.text("'{}'::jsonb")),
        sa.UniqueConstraint("tender_id", "artifact_code", "version", name="uq_tender_artifact_version"),
    )
    op.create_index("idx_tender_artifacts_tenant", "tender_artifacts", ["tenant_id"])
    op.create_index("idx_tender_artifacts_tender", "tender_artifacts", ["tender_id"])

    op.create_table(
        "tender_evidence_links",
        *_common(audit=False),
        sa.Column("evidence_id", UUID, sa.ForeignKey("tender_evidence.id", ondelete="CASCADE"), nullable=False),
        sa.Column("requirement_id", UUID, sa.ForeignKey("tender_requirements.id", ondelete="CASCADE"), nullable=True),
        sa.Column("artifact_id", UUID, sa.ForeignKey("tender_artifacts.id", ondelete="CASCADE"), nullable=True),
        sa.Column("relation", sa.String(80), nullable=False),
        sa.UniqueConstraint("evidence_id", "requirement_id", "artifact_id", "relation", name="uq_tender_evidence_link"),
    )
    op.create_index("idx_tender_evidence_links_tenant", "tender_evidence_links", ["tenant_id"])
    op.create_index("idx_tender_evidence_links_evidence", "tender_evidence_links", ["evidence_id"])
    op.create_index("idx_tender_evidence_links_requirement", "tender_evidence_links", ["requirement_id"])
    op.create_index("idx_tender_evidence_links_artifact", "tender_evidence_links", ["artifact_id"])

    op.create_table(
        "tender_dependencies",
        *_common(audit=False),
        sa.Column("tender_id", UUID, sa.ForeignKey("tender_packages.id", ondelete="CASCADE"), nullable=False),
        sa.Column("source_type", sa.String(80), nullable=False),
        sa.Column("source_key", sa.String(255), nullable=False),
        sa.Column("target_type", sa.String(80), nullable=False),
        sa.Column("target_key", sa.String(255), nullable=False),
        sa.Column("relation", sa.String(80), nullable=False),
        sa.Column("invalidates_signed", sa.Boolean, nullable=False, server_default=sa.true()),
        sa.Column("metadata", JSONB, nullable=False, server_default=sa.text("'{}'::jsonb")),
    )
    op.create_index("idx_tender_dependencies_tenant", "tender_dependencies", ["tenant_id"])
    op.create_index("idx_tender_dependencies_tender", "tender_dependencies", ["tender_id"])

    op.create_table(
        "tender_validation_runs",
        *_common(audit=True),
        sa.Column("tender_id", UUID, sa.ForeignKey("tender_packages.id", ondelete="CASCADE"), nullable=False),
        sa.Column("engine", sa.String(120), nullable=False),
        sa.Column("status", sa.String(30), nullable=False),
        sa.Column("severity", sa.String(30), nullable=False),
        sa.Column("rule_id", sa.String(120), nullable=True),
        sa.Column("message", sa.Text, nullable=False),
        sa.Column("evidence", JSONB, nullable=False, server_default=sa.text("'{}'::jsonb")),
        sa.Column("revision", sa.Integer, nullable=False),
    )
    op.create_index("idx_tender_validation_runs_tenant", "tender_validation_runs", ["tenant_id"])
    op.create_index("idx_tender_validation_runs_tender", "tender_validation_runs", ["tender_id"])

    op.create_table(
        "tender_approvals",
        *_common(audit=True),
        sa.Column("tender_id", UUID, sa.ForeignKey("tender_packages.id", ondelete="CASCADE"), nullable=False),
        sa.Column("role", sa.String(120), nullable=False),
        sa.Column("decision", sa.String(40), nullable=False),
        sa.Column("reason", sa.Text, nullable=True),
        sa.Column("revision", sa.Integer, nullable=False),
    )
    op.create_index("idx_tender_approvals_tenant", "tender_approvals", ["tenant_id"])
    op.create_index("idx_tender_approvals_tender", "tender_approvals", ["tender_id"])

    op.create_table(
        "submission_packages",
        *_common(audit=True),
        sa.Column("tender_id", UUID, sa.ForeignKey("tender_packages.id", ondelete="CASCADE"), nullable=False),
        sa.Column("revision", sa.Integer, nullable=False),
        sa.Column("manifest", JSONB, nullable=False, server_default=sa.text("'{}'::jsonb")),
        sa.Column("package_hash", sa.String(64), nullable=True),
        sa.Column("signed_hash", sa.String(64), nullable=True),
        sa.Column("status", sa.String(40), nullable=False, server_default="DRAFT"),
        sa.Column("portal_code", sa.String(120), nullable=True),
        sa.Column("receipt", JSONB, nullable=True),
        sa.UniqueConstraint("tender_id", "revision", name="uq_submission_package_revision"),
    )
    op.create_index("idx_submission_packages_tenant", "submission_packages", ["tenant_id"])
    op.create_index("idx_submission_packages_tender", "submission_packages", ["tender_id"])


def downgrade() -> None:
    op.drop_table("submission_packages")
    op.drop_table("tender_approvals")
    op.drop_table("tender_validation_runs")
    op.drop_table("tender_dependencies")
    op.drop_table("tender_evidence_links")
    op.drop_table("tender_artifacts")
    op.drop_index("uq_tender_evidence_source_hash", table_name="tender_evidence")
    op.drop_table("tender_evidence")
    op.drop_table("tender_requirements")
    op.drop_table("legal_rules")
    op.drop_table("legal_sources")
    op.drop_table("jurisdiction_profiles")
    op.drop_table("tender_revisions")
    op.drop_table("tender_packages")
