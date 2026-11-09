"""Store measured TIN coverage and source evidence without inventing history."""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision = "20261008_topografia_evidencia"
down_revision = "20261008_topografia_crs"
branch_labels = None
depends_on = None


def upgrade():
    op.add_column("calculos_volumen", sa.Column("evidencia", postgresql.JSONB(), nullable=True))


def downgrade():
    op.drop_column("calculos_volumen", "evidencia")
