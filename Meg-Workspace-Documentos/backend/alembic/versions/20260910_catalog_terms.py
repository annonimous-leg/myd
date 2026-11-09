"""catalog_terms vocabulary for procurement UI/API

Revision ID: 20260910_catalog_terms
Revises: 20260909_procedure_thresholds
"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision = "20260910_catalog_terms"
down_revision = "20260909_procedure_thresholds"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "catalog_terms",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True, nullable=False),
        sa.Column("tenant_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("domain", sa.String(80), nullable=False),
        sa.Column("code", sa.String(80), nullable=False),
        sa.Column("label", sa.String(255), nullable=False),
        sa.Column("sort_order", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("active", sa.Boolean(), nullable=False, server_default=sa.text("true")),
        sa.Column("meta", postgresql.JSONB(astext_type=sa.Text()), nullable=False, server_default=sa.text("'{}'::jsonb")),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("created_by_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("updated_by_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.UniqueConstraint("tenant_id", "domain", "code", name="uq_catalog_term_tenant_domain_code"),
    )
    op.create_index("idx_catalog_term_domain_active", "catalog_terms", ["domain", "active"])
    op.create_index("ix_catalog_terms_domain", "catalog_terms", ["domain"])
    op.create_index("ix_catalog_terms_code", "catalog_terms", ["code"])


def downgrade() -> None:
    op.drop_index("ix_catalog_terms_code", table_name="catalog_terms")
    op.drop_index("ix_catalog_terms_domain", table_name="catalog_terms")
    op.drop_index("idx_catalog_term_domain_active", table_name="catalog_terms")
    op.drop_table("catalog_terms")
