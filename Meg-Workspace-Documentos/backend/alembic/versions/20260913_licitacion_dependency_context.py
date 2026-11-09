"""Pin dependency context on legacy licitaciones.

Revision ID: 20260913_licitacion_dependency_context
Revises: 20260910_catalog_terms
"""
from alembic import op
import sqlalchemy as sa

revision = "20260913_licitacion_dependency_context"
down_revision = "20260910_catalog_terms"
branch_labels = None
depends_on = None

def upgrade() -> None:
    op.add_column("licitaciones", sa.Column("jurisdiction_code", sa.String(120), nullable=True))
    op.create_index("ix_licitaciones_jurisdiction_code", "licitaciones", ["jurisdiction_code"])
    op.execute(sa.text("""
        UPDATE licitaciones
        SET jurisdiction_code = COALESCE(
            reglas_participacion->>'jurisdiction_code',
            reglas_participacion->>'jurisdiction'
        )
        WHERE jurisdiction_code IS NULL AND reglas_participacion IS NOT NULL
    """))

def downgrade() -> None:
    op.drop_index("ix_licitaciones_jurisdiction_code", table_name="licitaciones")
    op.drop_column("licitaciones", "jurisdiction_code")
