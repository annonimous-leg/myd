"""bridge_field_contracts: mapping del bridge Tender<->Licitacion como DB, no como literal en código

Revision ID: 20260914_bridge_field_contracts
Revises: 20260914_structural_source_tables_relations
Create Date: 2026-09-14 00:00:00.000000

AUDITORÍA 2026-09-14 (P1): TenderWorkspaceService.bridge() escribía el
mapping de campos del bridge como un dict literal en Python, con solo 3
reglas TENDER_TO_LICITACION -- sin ninguna regla LICITACION_TO_TENDER. El
endpoint /bridge/licitacion/{id}/sync sí aceptaba direction=LICITACION_TO_TENDER
como válido, pero al no existir ninguna regla con esa dirección la
sincronización no hacía nada y devolvía 200 de todas formas: un caso real
de "funciona" disfrazado.

Esta migración crea bridge_field_contracts (versionada, tenant_id NULL =
contrato global) y siembra la v1 con las 3 reglas originales
TENDER_TO_LICITACION más sus 3 reglas espejo LICITACION_TO_TENDER
-- exactamente los mismos pares de campos, dirección inversa, mismo
allow-list de targets que el motor de sync ya soportaba pero que ningún
contrato activaba.
"""
from typing import Sequence, Union
import json
import uuid

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision: str = "20260914_bridge_field_contracts"
down_revision: Union[str, None] = "20260914_structural_source_tables_relations"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

_DEFAULT_FIELDS = [
    {"source": "tender.jurisdiction_code", "target": "licitacion.jurisdiction_code", "direction": "TENDER_TO_LICITACION", "authority": "TenderPackage", "conflict_policy": "FAIL_CLOSED"},
    {"source": "tender.procedure_type", "target": "licitacion.tipo_procedimiento", "direction": "TENDER_TO_LICITACION", "authority": "TenderPackage", "conflict_policy": "FAIL_CLOSED"},
    {"source": "tender.canonical_model.economic.budget_total", "target": "licitacion.monto_estimado", "direction": "TENDER_TO_LICITACION", "authority": "TenderPackage", "conflict_policy": "FAIL_CLOSED"},
    {"source": "licitacion.jurisdiction_code", "target": "tender.jurisdiction_code", "direction": "LICITACION_TO_TENDER", "authority": "Licitacion", "conflict_policy": "FAIL_CLOSED"},
    {"source": "licitacion.tipo_procedimiento", "target": "tender.procedure_type", "direction": "LICITACION_TO_TENDER", "authority": "Licitacion", "conflict_policy": "FAIL_CLOSED"},
    {"source": "licitacion.monto_estimado", "target": "tender.canonical_model.economic.budget_total", "direction": "LICITACION_TO_TENDER", "authority": "Licitacion", "conflict_policy": "FAIL_CLOSED"},
]


def upgrade() -> None:
    op.create_table(
        "bridge_field_contracts",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("tenant_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("tenants.id", ondelete="CASCADE"), nullable=True),
        sa.Column("version", sa.Integer(), nullable=False),
        sa.Column("is_active", sa.Boolean(), nullable=False, server_default=sa.true()),
        sa.Column("fields", postgresql.JSONB(), nullable=False),
        sa.Column("notes", sa.Text(), nullable=True),
        sa.Column("creado_por_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("actualizado_por_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
        sa.UniqueConstraint("tenant_id", "version", name="uq_bridge_contract_tenant_version"),
    )
    op.create_index("idx_bridge_contract_active", "bridge_field_contracts", ["tenant_id", "is_active"])

    bind = op.get_bind()
    bind.execute(
        sa.text(
            "INSERT INTO bridge_field_contracts (id, tenant_id, version, is_active, fields, notes) "
            "VALUES (:id, NULL, 1, true, CAST(:fields AS JSONB), :notes)"
        ),
        {
            "id": str(uuid.uuid4()),
            "fields": json.dumps(_DEFAULT_FIELDS),
            "notes": "Contrato global v1 sembrado por migración 20260914_bridge_field_contracts "
                     "(reemplaza el mapping hardcodeado en Python; ya incluye reglas LICITACION_TO_TENDER).",
        },
    )


def downgrade() -> None:
    op.drop_index("idx_bridge_contract_active", table_name="bridge_field_contracts")
    op.drop_table("bridge_field_contracts")
