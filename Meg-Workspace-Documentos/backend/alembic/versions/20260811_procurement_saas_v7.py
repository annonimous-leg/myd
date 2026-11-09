"""Procurement SaaS hardening: optimistic locking, approval race constraint and indexes."""
from alembic import op
import sqlalchemy as sa

revision = "20260811_procurement_saas_v7"
down_revision = "20260811_procurement_v6_jurisdiction_funding"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("tender_packages", sa.Column("row_version", sa.Integer(), nullable=False, server_default="1"))
    op.create_unique_constraint("uq_tender_approval_role_revision", "tender_approvals", ["tender_id", "revision", "role"])
    op.create_index("idx_tender_evidence_tenant_hash_kind", "tender_evidence", ["tenant_id", "source_hash", "kind"])


def downgrade() -> None:
    op.drop_index("idx_tender_evidence_tenant_hash_kind", table_name="tender_evidence")
    op.drop_constraint("uq_tender_approval_role_revision", "tender_approvals", type_="unique")
    op.drop_column("tender_packages", "row_version")
