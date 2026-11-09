"""Integrate financing and additional charges into price-unit totals.

Revision ID: 20261013_costeo_integral
Revises: 20261009_catalogo_importacion
"""
from alembic import op
import sqlalchemy as sa


revision = "20261013_costeo_integral"
down_revision = "20261009_catalogo_importacion"
branch_labels = None
depends_on = None


def upgrade():
    op.add_column(
        "presupuestos",
        sa.Column("monto_financiamiento", sa.Numeric(18, 2), nullable=False, server_default="0"),
    )
    op.add_column(
        "presupuestos",
        sa.Column("monto_cargos_adicionales", sa.Numeric(18, 2), nullable=False, server_default="0"),
    )
    op.add_column(
        "presupuestos",
        sa.Column("factor_financiamiento", sa.Numeric(8, 4), nullable=False, server_default="0"),
    )
    op.add_column(
        "presupuestos",
        sa.Column("factor_cargos_adicionales", sa.Numeric(8, 4), nullable=False, server_default="0"),
    )
    op.create_check_constraint(
        "ck_presupuesto_factor_financiamiento",
        "presupuestos",
        "factor_financiamiento BETWEEN 0 AND 1",
    )
    op.create_check_constraint(
        "ck_presupuesto_factor_cargos_adicionales",
        "presupuestos",
        "factor_cargos_adicionales BETWEEN 0 AND 1",
    )


def downgrade():
    op.drop_constraint(
        "ck_presupuesto_factor_cargos_adicionales",
        "presupuestos",
        type_="check",
    )
    op.drop_constraint(
        "ck_presupuesto_factor_financiamiento",
        "presupuestos",
        type_="check",
    )
    op.drop_column("presupuestos", "factor_cargos_adicionales")
    op.drop_column("presupuestos", "factor_financiamiento")
    op.drop_column("presupuestos", "monto_cargos_adicionales")
    op.drop_column("presupuestos", "monto_financiamiento")
