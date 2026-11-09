"""Immutable catalogue editions, typed evidence and six-decimal APU consumption."""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql as pg

revision = '20261009_catalogo_importacion'
down_revision = '20261008_topografia_evidencia'
branch_labels = None
depends_on = None


def common(audit=False):
    columns = [sa.Column('id', pg.UUID(as_uuid=True), primary_key=True),
        sa.Column('tenant_id', pg.UUID(as_uuid=True), sa.ForeignKey('tenants.id', ondelete='CASCADE'), nullable=False),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column('updated_at', sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False)]
    if audit:
        columns.extend([sa.Column('creado_por_id', pg.UUID(as_uuid=True), sa.ForeignKey('users.id', ondelete='SET NULL')),
                        sa.Column('actualizado_por_id', pg.UUID(as_uuid=True), sa.ForeignKey('users.id', ondelete='SET NULL'))])
    return columns


def upgrade():
    op.create_table('catalogo_importaciones', *common(True),
        sa.Column('paquete_sha256', sa.String(64), nullable=False),
        sa.Column('seleccion_sha256', sa.String(64), nullable=False),
        sa.Column('fuentes', pg.JSONB(), nullable=False), sa.Column('resumen', pg.JSONB(), nullable=False),
        sa.UniqueConstraint('tenant_id', 'paquete_sha256', 'seleccion_sha256', name='uq_catalogo_importacion_edicion'),
        sa.UniqueConstraint('id', 'tenant_id', name='uq_catalogo_importacion_tenant'))
    op.create_table('catalogo_registros', *common(),
        sa.Column('importacion_id', pg.UUID(as_uuid=True), nullable=False),
        sa.Column('tabla', sa.String(50), nullable=False), sa.Column('entidad_id', sa.String(160), nullable=False),
        sa.Column('fuente_id', sa.String(100), nullable=False), sa.Column('estado', sa.String(30), nullable=False),
        sa.Column('motivos', pg.JSONB(), nullable=False), sa.Column('original', pg.JSONB(), nullable=False),
        sa.Column('sha256', sa.String(64), nullable=False),
        sa.ForeignKeyConstraint(['importacion_id', 'tenant_id'], ['catalogo_importaciones.id', 'catalogo_importaciones.tenant_id'], ondelete='CASCADE'),
        sa.UniqueConstraint('importacion_id', 'tabla', 'entidad_id', name='uq_catalogo_registro_identidad'),
        sa.UniqueConstraint('id', 'tenant_id', name='uq_catalogo_registro_tenant'))
    op.create_index('ix_catalogo_registro_consulta', 'catalogo_registros', ['tenant_id', 'importacion_id', 'tabla', 'estado'])
    op.create_table('estimaciones_parametricas', *common(True),
        sa.Column('modelo_registro_id', pg.UUID(as_uuid=True), nullable=False),
        sa.Column('factor_registro_id', pg.UUID(as_uuid=True), nullable=False),
        sa.Column('cantidad', sa.Numeric(18, 4), nullable=False), sa.Column('monto', sa.Numeric(18, 2), nullable=False),
        sa.Column('evidencia', pg.JSONB(), nullable=False),
        sa.ForeignKeyConstraint(['modelo_registro_id', 'tenant_id'], ['catalogo_registros.id', 'catalogo_registros.tenant_id']),
        sa.ForeignKeyConstraint(['factor_registro_id', 'tenant_id'], ['catalogo_registros.id', 'catalogo_registros.tenant_id']))
    for table in ['catalogo_importaciones', 'catalogo_registros', 'estimaciones_parametricas']:
        op.create_index(f'ix_{table}_tenant_id', table, ['tenant_id'])
    for table in ['catalogo_importaciones', 'estimaciones_parametricas']:
        op.create_index(f'ix_{table}_creado_por_id', table, ['creado_por_id'])
    op.add_column('catalogos_apu', sa.Column('registro_importado_id', pg.UUID(as_uuid=True), nullable=True))
    op.add_column('catalogos_apu', sa.Column('origen', pg.JSONB(), nullable=True))
    op.create_unique_constraint('uq_catalogos_apu_registro_importado', 'catalogos_apu', ['registro_importado_id'])
    op.create_foreign_key('fk_catalogo_apu_registro_tenant', 'catalogos_apu', 'catalogo_registros',
                          ['registro_importado_id', 'tenant_id'], ['id', 'tenant_id'])
    # Preserve the historical 14 integer digits while adding two fractional
    # digits. Numeric(18,6) would narrow the range and reject valid old rows.
    op.alter_column('insumos', 'cantidad', existing_type=sa.Numeric(18, 4), type_=sa.Numeric(20, 6), existing_nullable=False)


def downgrade():
    # A rollback may not silently round real catalogue consumption or erase
    # imported editions referenced by price snapshots in historical budgets.
    conn = op.get_bind()
    if conn.execute(sa.text('SELECT 1 FROM catalogo_importaciones LIMIT 1')).first():
        raise RuntimeError('Exporte y migre las ediciones importadas antes de revertir esta migración')
    if conn.execute(sa.text('SELECT 1 FROM insumos WHERE cantidad <> round(cantidad, 4) LIMIT 1')).first():
        raise RuntimeError('Hay consumos APU con seis decimales; el downgrade perdería evidencia')
    op.alter_column('insumos', 'cantidad', existing_type=sa.Numeric(20, 6), type_=sa.Numeric(18, 4), existing_nullable=False)
    op.drop_constraint('fk_catalogo_apu_registro_tenant', 'catalogos_apu', type_='foreignkey')
    op.drop_constraint('uq_catalogos_apu_registro_importado', 'catalogos_apu', type_='unique')
    op.drop_column('catalogos_apu', 'origen')
    op.drop_column('catalogos_apu', 'registro_importado_id')
    op.drop_table('estimaciones_parametricas')
    op.drop_table('catalogo_registros')
    op.drop_table('catalogo_importaciones')
