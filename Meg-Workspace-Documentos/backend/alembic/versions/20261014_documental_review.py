"""Require a documented reviewer attestation instead of declared form flags."""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import JSONB

revision = "20261014_documental_review"
down_revision = "20261013_fallo_evidence"
branch_labels = None
depends_on = None


def upgrade():
    op.add_column("proposiciones", sa.Column("verificacion_documental", JSONB(), nullable=True))


def downgrade():
    if op.get_bind().execute(sa.text(
        "SELECT 1 FROM proposiciones WHERE verificacion_documental IS NOT NULL LIMIT 1"
    )).first():
        raise RuntimeError("Migración forward-only con revisión documental: no borrar la evidencia del revisor")
    op.drop_column("proposiciones", "verificacion_documental")
