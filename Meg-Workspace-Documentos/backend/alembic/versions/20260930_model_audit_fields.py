"""Reconcile persisted audit fields with the shared application model.

Renames preserve catalogue authors. Existing webhook timestamps derive from
their recorded processing time, rather than inventing an ingestion history.
"""
from alembic import op
import sqlalchemy as sa

revision = '20260930_model_audit_fields'
down_revision = '20260925_cost_parameters'
branch_labels = None
depends_on = None


def upgrade():
    for old, new in (('created_by_id', 'creado_por_id'), ('updated_by_id', 'actualizado_por_id')):
        op.alter_column('catalog_terms', old, new_column_name=new)
        op.create_foreign_key(f'fk_catalog_terms_{new}', 'catalog_terms', 'users', [new], ['id'], ondelete='SET NULL')
    for name in ('created_at', 'updated_at'):
        op.add_column('webhook_eventos_procesados', sa.Column(name, sa.DateTime(timezone=True), nullable=True))
    op.execute('UPDATE webhook_eventos_procesados SET created_at = procesado_en, updated_at = procesado_en')
    for name in ('created_at', 'updated_at'):
        op.alter_column('webhook_eventos_procesados', name, nullable=False, server_default=sa.func.now())


def downgrade():
    for name in ('updated_at', 'created_at'):
        op.drop_column('webhook_eventos_procesados', name)
    for old, new in (('created_by_id', 'creado_por_id'), ('updated_by_id', 'actualizado_por_id')):
        op.drop_constraint(f'fk_catalog_terms_{new}', 'catalog_terms', type_='foreignkey')
        op.alter_column('catalog_terms', new, new_column_name=old)
