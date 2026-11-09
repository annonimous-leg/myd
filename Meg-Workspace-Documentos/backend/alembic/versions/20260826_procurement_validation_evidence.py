"""Link every validation finding to concrete tenant-scoped evidence."""
from alembic import op
import sqlalchemy as sa
from app.db.types import UUID

revision = "20260826_procurement_validation_evidence"
down_revision = "20260826_procurement_preparation_runs"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "tender_validation_evidence_links",
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("id", UUID(), nullable=False),
        sa.Column("tenant_id", UUID(), nullable=False),
        sa.Column("validation_run_id", UUID(), nullable=False),
        sa.Column("evidence_id", UUID(), nullable=False),
        sa.Column("relation", sa.String(80), nullable=False, server_default="SUPPORTS"),
        sa.PrimaryKeyConstraint("id"),
        sa.ForeignKeyConstraint(["tenant_id"], ["tenants.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["validation_run_id"], ["tender_validation_runs.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["evidence_id"], ["tender_evidence.id"], ondelete="CASCADE"),
        sa.UniqueConstraint(
            "tenant_id", "validation_run_id", "evidence_id", "relation",
            name="uq_tender_validation_evidence_link",
        ),
    )
    op.create_index(
        "idx_tender_validation_evidence_tenant_validation",
        "tender_validation_evidence_links",
        ["tenant_id", "validation_run_id"],
    )
    op.create_index(
        "idx_tender_validation_evidence_tenant_evidence",
        "tender_validation_evidence_links",
        ["tenant_id", "evidence_id"],
    )


def downgrade() -> None:
    op.drop_index("idx_tender_validation_evidence_tenant_evidence", table_name="tender_validation_evidence_links")
    op.drop_index("idx_tender_validation_evidence_tenant_validation", table_name="tender_validation_evidence_links")
    op.drop_table("tender_validation_evidence_links")
