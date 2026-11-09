"""Store private PDF artifacts for IFC technical drawings."""
from alembic import op
import sqlalchemy as sa

revision = "20261105_bim_drawing_pdf"
down_revision = "20261102_bim_drawings"
branch_labels = None
depends_on = None


def upgrade():
    op.add_column("dibujos_bim", sa.Column("ruta_pdf", sa.String(1000), nullable=True))
    op.add_column("dibujos_bim", sa.Column("sha256_pdf", sa.String(64), nullable=True))


def downgrade():
    op.drop_column("dibujos_bim", "sha256_pdf")
    op.drop_column("dibujos_bim", "ruta_pdf")
