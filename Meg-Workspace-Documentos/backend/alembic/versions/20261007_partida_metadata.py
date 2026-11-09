"""Persist Partida provenance required by OCR and imported quantities.

Revision ID: 20261007_partida_metadata
Revises: 20261007_ocr_jobs
"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision = "20261007_partida_metadata"
down_revision = "20261007_ocr_jobs"
branch_labels = None
depends_on = None


def upgrade():
    op.add_column(
        "partidas",
        sa.Column(
            "metadatos",
            postgresql.JSONB(),
            nullable=False,
            server_default=sa.text("'{}'::jsonb"),
        ),
    )


def downgrade():
    op.drop_column("partidas", "metadatos")
