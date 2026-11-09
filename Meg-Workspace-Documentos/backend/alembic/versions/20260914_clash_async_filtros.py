"""analisis_clash: persistir tipos_incluidos/excluidos para clash async

Revision ID: 20260914_clash_async_filtros
Revises: 20260914_bridge_field_contracts
Create Date: 2026-09-14 00:00:00.000000

AUDITORÍA BIM 2026-09-14 (P0): clash detection corría síncrono dentro
del request HTTP -- con modelos de miles de elementos de malla densa
arriesgaba timeout, el mismo problema ya resuelto para procesar_ifc()
moviéndolo a Celery. Al mover clash al mismo patrón (endpoint crea
AnalisisClash en PENDIENTE -> encola worker -> worker hace el cómputo),
los filtros tipos_incluidos/tipos_excluidos que antes solo vivían como
argumentos de función durante el propio request ahora tienen que
sobrevivir hasta que el worker los recoja.
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision: str = "20260914_clash_async_filtros"
down_revision: Union[str, None] = "20260914_bridge_field_contracts"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column("analisis_clash", sa.Column("tipos_incluidos", postgresql.JSON(astext_type=sa.Text()), nullable=True))
    op.add_column("analisis_clash", sa.Column("tipos_excluidos", postgresql.JSON(astext_type=sa.Text()), nullable=True))


def downgrade() -> None:
    op.drop_column("analisis_clash", "tipos_excluidos")
    op.drop_column("analisis_clash", "tipos_incluidos")
