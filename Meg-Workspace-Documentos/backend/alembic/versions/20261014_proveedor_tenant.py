"""Scope supplier RFC uniqueness to its owning organization."""
from alembic import op
import sqlalchemy as sa

revision = "20261014_proveedor_tenant"
down_revision = "20261014_documental_review"
branch_labels = None
depends_on = None


def upgrade():
    op.drop_index("ix_proveedores_rfc", table_name="proveedores")
    op.create_index("uq_proveedores_tenant_rfc", "proveedores", ["tenant_id", "rfc"], unique=True)


def downgrade():
    if op.get_bind().execute(sa.text(
        "SELECT rfc FROM proveedores GROUP BY rfc HAVING count(*) > 1 LIMIT 1"
    )).first():
        raise RuntimeError("No se puede restaurar RFC global: proveedores de distintas organizaciones comparten RFC")
    op.drop_index("uq_proveedores_tenant_rfc", table_name="proveedores")
    op.create_index("ix_proveedores_rfc", "proveedores", ["rfc"], unique=True)
