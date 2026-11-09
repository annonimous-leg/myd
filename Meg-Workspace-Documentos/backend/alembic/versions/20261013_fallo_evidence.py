"""Persist the winning proposal and the precise evaluated evidence.

Historical free-text decisions are not converted into invented approvals.
"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import JSONB

revision = "20261013_fallo_evidence"
down_revision = "20261013_audit_ledger_hardening"
branch_labels = None
depends_on = None


def upgrade():
    if op.get_bind().execute(sa.text(
        "SELECT licitacion_id FROM contratos WHERE licitacion_id IS NOT NULL "
        "GROUP BY licitacion_id HAVING count(*) > 1 LIMIT 1"
    )).first():
        raise RuntimeError("Existen contratos múltiples por licitación; concilie la evidencia antes de migrar")
    op.add_column("licitaciones", sa.Column("fallo_snapshot", JSONB(), nullable=True))
    op.add_column("evaluaciones_licitacion", sa.Column("revision", sa.Integer(), nullable=False, server_default="0"))
    op.create_index("uq_evaluacion_revision", "evaluaciones_licitacion",
                    ["licitacion_id", "proposicion_id", "tipo", "revision"],
                    unique=True, postgresql_where=sa.text("revision > 0"))
    op.add_column("documentos", sa.Column("row_version", sa.Integer(), nullable=False, server_default="1"))
    op.create_unique_constraint("uq_contrato_licitacion", "contratos", ["licitacion_id"])


def downgrade():
    if op.get_bind().execute(sa.text("SELECT 1 FROM evaluaciones_licitacion WHERE revision > 0 LIMIT 1")).first():
        raise RuntimeError("Migración forward-only con evaluaciones versionadas: no borrar su orden de decisión")
    if op.get_bind().execute(sa.text("SELECT 1 FROM licitaciones WHERE fallo_snapshot IS NOT NULL LIMIT 1")).first():
        raise RuntimeError("Migración forward-only con evidencia de fallo: no borrar adjudicaciones")
    op.drop_column("licitaciones", "fallo_snapshot")
    op.drop_index("uq_evaluacion_revision", table_name="evaluaciones_licitacion")
    op.drop_column("evaluaciones_licitacion", "revision")
    op.drop_column("documentos", "row_version")
    op.drop_constraint("uq_contrato_licitacion", "contratos", type_="unique")
