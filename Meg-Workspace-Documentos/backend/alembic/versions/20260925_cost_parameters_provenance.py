"""presupuestos: factores explícitos, acotados y con procedencia

Revision ID: 20260925_cost_parameters
Revises: 20260914_clash_async_filtros
Create Date: 2026-09-25
"""
from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "20260925_cost_parameters"
down_revision: str | None = "20260914_clash_async_filtros"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    columns = {column["name"] for column in inspector.get_columns("presupuestos")}
    if "factor_riesgo" not in columns:
        op.add_column("presupuestos", sa.Column("factor_riesgo", sa.Numeric(8, 4), nullable=True))
    if "monto_riesgo" not in columns:
        op.add_column("presupuestos", sa.Column("monto_riesgo", sa.Numeric(18, 2), nullable=True))
    for column in ("factor_indirecto", "factor_utilidad", "factor_impuesto"):
        op.alter_column("presupuestos", column, server_default=None, existing_type=sa.Numeric(8, 4))
    constraint_names = {
        constraint["name"] for constraint in sa.inspect(bind).get_check_constraints("presupuestos")
        if constraint.get("name")
    }
    for column in ("factor_indirecto", "factor_utilidad", "factor_impuesto", "factor_riesgo"):
        name = f"ck_presupuesto_{column}"
        if name not in constraint_names:
            op.create_check_constraint(name, "presupuestos", f"{column} BETWEEN 0 AND 1")


def downgrade() -> None:
    bind = op.get_bind()
    constraint_names = {
        constraint["name"] for constraint in sa.inspect(bind).get_check_constraints("presupuestos")
        if constraint.get("name")
    }
    for column in ("factor_riesgo", "factor_impuesto", "factor_utilidad", "factor_indirecto"):
        name = f"ck_presupuesto_{column}"
        if name in constraint_names:
            op.drop_constraint(name, "presupuestos", type_="check")
    columns = {column["name"] for column in sa.inspect(bind).get_columns("presupuestos")}
    if "monto_riesgo" in columns:
        op.drop_column("presupuestos", "monto_riesgo")
    if "factor_riesgo" in columns:
        op.drop_column("presupuestos", "factor_riesgo")
    op.alter_column("presupuestos", "factor_indirecto", server_default="0.15", existing_type=sa.Numeric(8, 4))
    op.alter_column("presupuestos", "factor_utilidad", server_default="0.10", existing_type=sa.Numeric(8, 4))
    op.alter_column("presupuestos", "factor_impuesto", server_default="0.16", existing_type=sa.Numeric(8, 4))
