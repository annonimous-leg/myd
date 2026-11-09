"""Durable BIM delivery intents; historical parameters are never invented."""
from alembic import op
import sqlalchemy as sa

revision = '20261006_trabajos_durables'
down_revision = '20261006_bim_integridad'
branch_labels = None
depends_on = None


def upgrade():
    op.create_table('trabajos_proceso',
        sa.Column('id', sa.Uuid(), primary_key=True),
        sa.Column('tenant_id', sa.Uuid(), sa.ForeignKey('tenants.id', ondelete='CASCADE'), nullable=False),
        sa.Column('tipo', sa.String(30), nullable=False),
        sa.Column('entidad_id', sa.Uuid(), nullable=False),
        sa.Column('parametros', sa.JSON(), nullable=False),
        sa.Column('estado', sa.String(20), nullable=False),
        sa.Column('intentos', sa.Integer(), nullable=False),
        sa.Column('proxima_publicacion', sa.DateTime(timezone=True), nullable=False),
        sa.Column('error_publicacion', sa.String(500)), sa.Column('error', sa.String(500)),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column('updated_at', sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.UniqueConstraint('tipo', 'entidad_id', name='uq_trabajo_tipo_entidad'))
    op.create_index('ix_trabajos_proceso_tenant_id', 'trabajos_proceso', ['tenant_id'])
    op.create_index('ix_trabajos_proceso_publicacion', 'trabajos_proceso', ['estado', 'proxima_publicacion'])


def downgrade():
    op.drop_table('trabajos_proceso')
