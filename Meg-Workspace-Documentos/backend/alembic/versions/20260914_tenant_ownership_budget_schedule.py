from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision = "20260914_tenant_ownership_budget_schedule"
down_revision = "20260914_workspace_bridge_tenant"
branch_labels = None
depends_on = None


def _uuid():
    return postgresql.UUID(as_uuid=True)


def _assert_no_nulls(bind, table):
    remaining = bind.execute(sa.text(f"SELECT count(*) FROM {table} WHERE tenant_id IS NULL")).scalar_one()
    if remaining:
        raise RuntimeError(f"No se pudo poblar tenant_id en {table}: {remaining} filas quedaron NULL")


def upgrade():
    uuid = _uuid()

    # Add nullable first so existing installations can be backfilled from
    # the ownership graph before the columns become NOT NULL.
    for table in (
        "presupuestos", "partidas", "conceptos", "insumos",
        "programas_obra", "actividades_programa",
    ):
        op.add_column(table, sa.Column("tenant_id", uuid, nullable=True))

    # Backfill from the existing ownership chain. No tenant is guessed and
    # no global/default tenant is invented. A missing parent is a migration
    # invariant failure and aborts the transaction.
    op.execute(sa.text("""
        UPDATE presupuestos p
        SET tenant_id = e.tenant_id
        FROM expedientes_obra e
        WHERE p.expediente_id = e.id
    """))
    op.execute(sa.text("""
        UPDATE partidas p
        SET tenant_id = b.tenant_id
        FROM presupuestos b
        WHERE p.presupuesto_id = b.id
    """))
    op.execute(sa.text("""
        UPDATE conceptos c
        SET tenant_id = p.tenant_id
        FROM partidas p
        WHERE c.partida_id = p.id
    """))
    op.execute(sa.text("""
        UPDATE insumos i
        SET tenant_id = c.tenant_id
        FROM conceptos c
        WHERE i.concepto_id = c.id
    """))
    op.execute(sa.text("""
        UPDATE programas_obra p
        SET tenant_id = e.tenant_id
        FROM expedientes_obra e
        WHERE p.expediente_id = e.id
    """))
    op.execute(sa.text("""
        UPDATE actividades_programa a
        SET tenant_id = p.tenant_id
        FROM programas_obra p
        WHERE a.programa_id = p.id
    """))

    bind = op.get_bind()
    for table in (
        "presupuestos", "partidas", "conceptos", "insumos",
        "programas_obra", "actividades_programa",
    ):
        _assert_no_nulls(bind, table)
        op.alter_column(table, "tenant_id", nullable=False)

    # Parent unique keys are required targets for the composite ownership FKs.
    for table, name in (
        ("presupuestos", "uq_presupuesto_tenant_id"),
        ("partidas", "uq_partida_tenant_id"),
        ("conceptos", "uq_concepto_tenant_id"),
        ("programas_obra", "uq_programa_tenant_id"),
    ):
        op.create_unique_constraint(name, table, ["tenant_id", "id"])

    for table, name in (
        ("presupuestos", "idx_presupuesto_tenant"),
        ("partidas", "idx_partida_tenant"),
        ("conceptos", "idx_concepto_tenant"),
        ("insumos", "idx_insumo_tenant"),
        ("programas_obra", "idx_programa_tenant"),
        ("actividades_programa", "idx_actividad_tenant"),
    ):
        op.create_index(name, table, ["tenant_id"])

    op.create_foreign_key(
        "fk_presupuesto_tenant_expediente", "presupuestos", "expedientes_obra",
        ["tenant_id", "expediente_id"], ["tenant_id", "id"], ondelete="CASCADE"
    )
    op.create_foreign_key(
        "fk_partida_tenant_presupuesto", "partidas", "presupuestos",
        ["tenant_id", "presupuesto_id"], ["tenant_id", "id"], ondelete="CASCADE"
    )
    op.create_foreign_key(
        "fk_concepto_tenant_partida", "conceptos", "partidas",
        ["tenant_id", "partida_id"], ["tenant_id", "id"], ondelete="CASCADE"
    )
    op.create_foreign_key(
        "fk_insumo_tenant_concepto", "insumos", "conceptos",
        ["tenant_id", "concepto_id"], ["tenant_id", "id"], ondelete="CASCADE"
    )
    op.create_foreign_key(
        "fk_programa_tenant_expediente", "programas_obra", "expedientes_obra",
        ["tenant_id", "expediente_id"], ["tenant_id", "id"], ondelete="CASCADE"
    )
    op.create_foreign_key(
        "fk_actividad_tenant_programa", "actividades_programa", "programas_obra",
        ["tenant_id", "programa_id"], ["tenant_id", "id"], ondelete="CASCADE"
    )


def downgrade():
    for name, table in (
        ("fk_actividad_tenant_programa", "actividades_programa"),
        ("fk_programa_tenant_expediente", "programas_obra"),
        ("fk_insumo_tenant_concepto", "insumos"),
        ("fk_concepto_tenant_partida", "conceptos"),
        ("fk_partida_tenant_presupuesto", "partidas"),
        ("fk_presupuesto_tenant_expediente", "presupuestos"),
    ):
        op.drop_constraint(name, table, type_="foreignkey")

    for name, table in (
        ("idx_actividad_tenant", "actividades_programa"),
        ("idx_programa_tenant", "programas_obra"),
        ("idx_insumo_tenant", "insumos"),
        ("idx_concepto_tenant", "conceptos"),
        ("idx_partida_tenant", "partidas"),
        ("idx_presupuesto_tenant", "presupuestos"),
    ):
        op.drop_index(name, table_name=table)

    for name, table in (
        ("uq_programa_tenant_id", "programas_obra"),
        ("uq_concepto_tenant_id", "conceptos"),
        ("uq_partida_tenant_id", "partidas"),
        ("uq_presupuesto_tenant_id", "presupuestos"),
    ):
        op.drop_constraint(name, table, type_="unique")

    for table in (
        "actividades_programa", "programas_obra", "insumos",
        "conceptos", "partidas", "presupuestos",
    ):
        op.drop_column(table, "tenant_id")
