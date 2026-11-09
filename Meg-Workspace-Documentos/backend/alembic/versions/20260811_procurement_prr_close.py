"""PRR closure infrastructure: durable jobs, idempotency and storage intents."""
from alembic import op
import sqlalchemy as sa
from app.db.types import UUID

revision = "20260811_procurement_prr_close"
down_revision = "20260811_procurement_saas_v7"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("tender_artifacts", sa.Column("signature_idempotency_key", sa.String(128), nullable=True))
    op.add_column("submission_packages", sa.Column("idempotency_key", sa.String(128), nullable=True))
    op.create_unique_constraint("uq_tender_artifact_signature_idempotency", "tender_artifacts", ["tenant_id", "signature_idempotency_key"])
    op.create_unique_constraint("uq_submission_package_idempotency", "submission_packages", ["tenant_id", "idempotency_key"])

    op.add_column("tender_requirements", sa.Column("legal_rule_id", UUID(), nullable=True))
    op.add_column("tender_requirements", sa.Column("legal_article_id", UUID(), nullable=True))
    op.create_foreign_key("fk_tender_requirements_legal_rule", "tender_requirements", "legal_rules", ["legal_rule_id"], ["id"], ondelete="SET NULL")
    op.create_foreign_key("fk_tender_requirements_legal_article", "tender_requirements", "legal_articles", ["legal_article_id"], ["id"], ondelete="SET NULL")
    op.create_index("ix_tender_requirements_legal_rule_id", "tender_requirements", ["legal_rule_id"])
    op.create_index("ix_tender_requirements_legal_article_id", "tender_requirements", ["legal_article_id"])

    op.create_table(
        "jurisdiction_inheritance",
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("id", UUID(), nullable=False),
        sa.Column("tenant_id", UUID(), nullable=False),
        sa.Column("child_profile_id", UUID(), nullable=False),
        sa.Column("parent_profile_id", UUID(), nullable=False),
        sa.Column("effective_from", sa.String(20), nullable=True),
        sa.Column("effective_to", sa.String(20), nullable=True),
        sa.Column("active", sa.Boolean(), nullable=False, server_default=sa.true()),
        sa.PrimaryKeyConstraint("id"),
        sa.ForeignKeyConstraint(["tenant_id"], ["tenants.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["child_profile_id"], ["jurisdiction_profiles.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["parent_profile_id"], ["jurisdiction_profiles.id"], ondelete="CASCADE"),
        sa.UniqueConstraint("tenant_id", "child_profile_id", "parent_profile_id", name="uq_jurisdiction_inheritance"),
    )
    op.create_index("ix_jurisdiction_inheritance_child_profile_id", "jurisdiction_inheritance", ["child_profile_id"])
    op.create_index("ix_jurisdiction_inheritance_parent_profile_id", "jurisdiction_inheritance", ["parent_profile_id"])

    op.create_table(
        "procurement_jobs",
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("id", UUID(), nullable=False),
        sa.Column("tenant_id", UUID(), nullable=False),
        sa.Column("creado_por_id", UUID(), nullable=True),
        sa.Column("actualizado_por_id", UUID(), nullable=True),
        sa.Column("tender_id", UUID(), nullable=False),
        sa.Column("kind", sa.String(40), nullable=False),
        sa.Column("status", sa.String(30), nullable=False, server_default="PENDING"),
        sa.Column("task_id", sa.String(128), nullable=True),
        sa.Column("idempotency_key", sa.String(128), nullable=True),
        sa.Column("request_hash", sa.String(64), nullable=False),
        sa.Column("progress", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("result", sa.JSON(), nullable=False, server_default=sa.text("'{}'")),
        sa.Column("error_code", sa.String(80), nullable=True),
        sa.Column("error_message", sa.Text(), nullable=True),
        sa.Column("started_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("finished_at", sa.DateTime(timezone=True), nullable=True),
        sa.PrimaryKeyConstraint("id"),
        sa.ForeignKeyConstraint(["tenant_id"], ["tenants.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["creado_por_id"], ["users.id"], ondelete="SET NULL"),
        sa.ForeignKeyConstraint(["actualizado_por_id"], ["users.id"], ondelete="SET NULL"),
        sa.ForeignKeyConstraint(["tender_id"], ["tender_packages.id"], ondelete="CASCADE"),
        sa.UniqueConstraint("task_id", name="uq_procurement_job_task"),
        sa.UniqueConstraint("tenant_id", "tender_id", "kind", "idempotency_key", name="uq_procurement_job_idempotency"),
    )
    op.create_index("idx_procurement_job_tenant_status", "procurement_jobs", ["tenant_id", "status"])
    op.create_index("ix_procurement_jobs_tender_id", "procurement_jobs", ["tender_id"])

    op.create_table(
        "procurement_idempotency",
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("id", UUID(), nullable=False),
        sa.Column("tenant_id", UUID(), nullable=False),
        sa.Column("key", sa.String(128), nullable=False),
        sa.Column("request_hash", sa.String(64), nullable=False),
        sa.Column("job_id", UUID(), nullable=False),
        sa.PrimaryKeyConstraint("id"),
        sa.ForeignKeyConstraint(["tenant_id"], ["tenants.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["job_id"], ["procurement_jobs.id"], ondelete="CASCADE"),
        sa.UniqueConstraint("tenant_id", "key", name="uq_procurement_idempotency_tenant_key"),
    )
    op.create_index("ix_procurement_idempotency_job_id", "procurement_idempotency", ["job_id"])

    op.create_table(
        "procurement_storage_intents",
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("id", UUID(), nullable=False),
        sa.Column("tenant_id", UUID(), nullable=False),
        sa.Column("job_id", UUID(), nullable=True),
        sa.Column("bucket", sa.String(120), nullable=False),
        sa.Column("storage_path", sa.String(1000), nullable=False),
        sa.Column("content_hash", sa.String(64), nullable=False),
        sa.Column("content_type", sa.String(160), nullable=False),
        sa.Column("size_bytes", sa.Integer(), nullable=False),
        sa.Column("state", sa.String(30), nullable=False, server_default="PENDING"),
        sa.Column("entity_type", sa.String(80), nullable=False),
        sa.Column("entity_id", UUID(), nullable=True),
        sa.Column("verified", sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column("error_message", sa.Text(), nullable=True),
        sa.PrimaryKeyConstraint("id"),
        sa.ForeignKeyConstraint(["tenant_id"], ["tenants.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["job_id"], ["procurement_jobs.id"], ondelete="SET NULL"),
        sa.UniqueConstraint("tenant_id", "bucket", "storage_path", "content_hash", name="uq_procurement_storage_intent"),
    )
    op.create_index("ix_procurement_storage_intents_job_id", "procurement_storage_intents", ["job_id"])
    op.create_index("ix_procurement_storage_intents_state", "procurement_storage_intents", ["state"])


def downgrade() -> None:
    op.drop_constraint("uq_submission_package_idempotency", "submission_packages", type_="unique")
    op.drop_constraint("uq_tender_artifact_signature_idempotency", "tender_artifacts", type_="unique")
    op.drop_column("submission_packages", "idempotency_key")
    op.drop_column("tender_artifacts", "signature_idempotency_key")
    op.drop_index("ix_tender_requirements_legal_article_id", table_name="tender_requirements")
    op.drop_index("ix_tender_requirements_legal_rule_id", table_name="tender_requirements")
    op.drop_constraint("fk_tender_requirements_legal_article", "tender_requirements", type_="foreignkey")
    op.drop_constraint("fk_tender_requirements_legal_rule", "tender_requirements", type_="foreignkey")
    op.drop_column("tender_requirements", "legal_article_id")
    op.drop_column("tender_requirements", "legal_rule_id")
    op.drop_index("ix_jurisdiction_inheritance_parent_profile_id", table_name="jurisdiction_inheritance")
    op.drop_index("ix_jurisdiction_inheritance_child_profile_id", table_name="jurisdiction_inheritance")
    op.drop_table("jurisdiction_inheritance")
    op.drop_index("ix_procurement_storage_intents_state", table_name="procurement_storage_intents")
    op.drop_index("ix_procurement_storage_intents_job_id", table_name="procurement_storage_intents")
    op.drop_table("procurement_storage_intents")
    op.drop_index("ix_procurement_idempotency_job_id", table_name="procurement_idempotency")
    op.drop_table("procurement_idempotency")
    op.drop_index("ix_procurement_jobs_tender_id", table_name="procurement_jobs")
    op.drop_index("idx_procurement_job_tenant_status", table_name="procurement_jobs")
    op.drop_table("procurement_jobs")
