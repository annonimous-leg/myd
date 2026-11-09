"""Add durable BIM technical drawing requests and private vector outputs."""
from alembic import op
import sqlalchemy as sa

revision = "20261102_bim_drawings"
down_revision = "20261028_audit_chain_guard"
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        "dibujos_bim",
        sa.Column("id", sa.Uuid(), primary_key=True),
        sa.Column("tenant_id", sa.Uuid(), sa.ForeignKey("tenants.id", ondelete="CASCADE"), nullable=False),
        sa.Column("modelo_id", sa.Uuid(), sa.ForeignKey("modelos_bim.id", ondelete="CASCADE"), nullable=False),
        sa.Column("expediente_id", sa.Uuid(), sa.ForeignKey("expedientes_obra.id", ondelete="CASCADE"), nullable=False),
        sa.Column("tipo", sa.String(20), nullable=False),
        sa.Column("titulo", sa.String(300), nullable=False),
        sa.Column("parametros", sa.JSON(), nullable=False),
        sa.Column("formatos", sa.JSON(), nullable=False),
        sa.Column("permitir_geometria_parcial", sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column("estado", sa.String(20), nullable=False, server_default="PENDIENTE"),
        sa.Column("error", sa.String(1000), nullable=True),
        sa.Column("source_model_updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("source_model_version", sa.String(50), nullable=True),
        sa.Column("source_num_elementos", sa.Integer(), nullable=False),
        sa.Column("source_geometry_sha256", sa.String(64), nullable=False),
        sa.Column("elementos_fuente", sa.Integer(), nullable=False),
        sa.Column("elementos_con_malla", sa.Integer(), nullable=True),
        sa.Column("elementos_sin_malla", sa.Integer(), nullable=True),
        sa.Column("ruta_svg", sa.String(1000), nullable=True),
        sa.Column("ruta_dxf", sa.String(1000), nullable=True),
        sa.Column("sha256_svg", sa.String(64), nullable=True),
        sa.Column("sha256_dxf", sa.String(64), nullable=True),
        sa.Column("metadatos", sa.JSON(), nullable=True),
        sa.Column("creado_por_id", sa.Uuid(), sa.ForeignKey("users.id", ondelete="SET NULL"), nullable=True),
        sa.Column("actualizado_por_id", sa.Uuid(), sa.ForeignKey("users.id", ondelete="SET NULL"), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.ForeignKeyConstraint(
            ["tenant_id", "expediente_id"],
            ["expedientes_obra.tenant_id", "expedientes_obra.id"],
            name="fk_dibujo_bim_tenant_expediente",
        ),
    )
    op.create_index("ix_dibujos_bim_tenant_id", "dibujos_bim", ["tenant_id"])
    op.create_index("ix_dibujos_bim_modelo_id", "dibujos_bim", ["modelo_id"])
    op.create_index("ix_dibujos_bim_expediente_id", "dibujos_bim", ["expediente_id"])
    op.create_index("ix_dibujos_bim_estado", "dibujos_bim", ["estado"])
    op.create_index("ix_dibujos_bim_modelo_created", "dibujos_bim", ["tenant_id", "modelo_id", "created_at"])


def downgrade():
    op.drop_index("ix_dibujos_bim_modelo_created", table_name="dibujos_bim")
    op.drop_index("ix_dibujos_bim_estado", table_name="dibujos_bim")
    op.drop_index("ix_dibujos_bim_expediente_id", table_name="dibujos_bim")
    op.drop_index("ix_dibujos_bim_modelo_id", table_name="dibujos_bim")
    op.drop_index("ix_dibujos_bim_tenant_id", table_name="dibujos_bim")
    op.drop_table("dibujos_bim")
