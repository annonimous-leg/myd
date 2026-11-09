from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql
revision = "20260914_workspace_bridge_versioning"
down_revision = "20260914_db_driven_formats_structure"
branch_labels = None
depends_on = None

def upgrade():
    op.add_column("licitaciones", sa.Column("row_version", sa.Integer(), nullable=False, server_default="1"))
    op.create_unique_constraint("uq_licitaciones_tenant_id", "licitaciones", ["tenant_id", "id"])

def downgrade():
    op.drop_constraint("uq_licitaciones_tenant_id", "licitaciones", type_="unique")
    op.drop_column("licitaciones", "row_version")
