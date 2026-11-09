"""procedure_thresholds table for DB-driven umbrales

Revision ID: 20260909_procedure_thresholds
Revises: 20260902_webhook_idempotency_suscripcion
Create Date: 2026-09-09
"""
from __future__ import annotations

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision = "20260909_procedure_thresholds"
down_revision = "20260902_webhook_idempotency_suscripcion"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "procedure_thresholds",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True, nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("tenant_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("tenants.id", ondelete="CASCADE"), nullable=True),
        sa.Column("creado_por_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("actualizado_por_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("jurisdiction_code", sa.String(120), nullable=False),
        sa.Column("government_level", sa.String(50), nullable=False, server_default="FEDERAL"),
        sa.Column("matter", sa.String(120), nullable=False, server_default="PUBLIC_WORKS"),
        sa.Column("tipo_contratacion", sa.String(80), nullable=False),
        sa.Column("ejercicio_fiscal", sa.Integer(), nullable=False),
        sa.Column("presupuesto_min_miles", sa.Numeric(18, 4), nullable=False, server_default="0"),
        sa.Column("presupuesto_max_miles", sa.Numeric(18, 4), nullable=True),
        sa.Column("adjudicacion_directa_miles", sa.Numeric(18, 4), nullable=False),
        sa.Column("invitacion_restringida_miles", sa.Numeric(18, 4), nullable=False),
        sa.Column("adjudicacion_directa_servicio_miles", sa.Numeric(18, 4), nullable=True),
        sa.Column("invitacion_restringida_servicio_miles", sa.Numeric(18, 4), nullable=True),
        sa.Column("ley", sa.String(120), nullable=False),
        sa.Column("articulo_referencia", sa.String(120), nullable=False),
        sa.Column("fuente", sa.String(500), nullable=False),
        sa.Column("fuente_uri", sa.String(1000), nullable=True),
        sa.Column("fecha_publicacion", sa.String(20), nullable=True),
        sa.Column("estado_dato", sa.String(30), nullable=False, server_default="PENDIENTE"),
        sa.Column("notas", sa.Text(), nullable=True),
        sa.Column("active", sa.Boolean(), nullable=False, server_default=sa.text("true")),
        sa.UniqueConstraint(
            "tenant_id",
            "jurisdiction_code",
            "tipo_contratacion",
            "ejercicio_fiscal",
            "presupuesto_min_miles",
            name="uq_procedure_threshold_tramo",
        ),
    )
    op.create_index(
        "idx_procedure_threshold_lookup",
        "procedure_thresholds",
        ["jurisdiction_code", "tipo_contratacion", "ejercicio_fiscal", "active"],
    )
    op.create_index("ix_procedure_thresholds_tenant_id", "procedure_thresholds", ["tenant_id"])
    op.create_index("ix_procedure_thresholds_jurisdiction_code", "procedure_thresholds", ["jurisdiction_code"])
    op.create_index("ix_procedure_thresholds_tipo_contratacion", "procedure_thresholds", ["tipo_contratacion"])
    op.create_index("ix_procedure_thresholds_ejercicio_fiscal", "procedure_thresholds", ["ejercicio_fiscal"])


def downgrade() -> None:
    op.drop_index("ix_procedure_thresholds_ejercicio_fiscal", table_name="procedure_thresholds")
    op.drop_index("ix_procedure_thresholds_tipo_contratacion", table_name="procedure_thresholds")
    op.drop_index("ix_procedure_thresholds_jurisdiction_code", table_name="procedure_thresholds")
    op.drop_index("ix_procedure_thresholds_tenant_id", table_name="procedure_thresholds")
    op.drop_index("idx_procedure_threshold_lookup", table_name="procedure_thresholds")
    op.drop_table("procedure_thresholds")
