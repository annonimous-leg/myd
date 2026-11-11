"""Preserve IFC coverage revisions and measurement decision history."""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import UUID

revision = '20261111_bim_revision_decisions'
down_revision = '20261109_approved_artifact_bytes'
branch_labels = None
depends_on = None


def columns():
    return [sa.Column('id', UUID(as_uuid=True), primary_key=True),
        sa.Column('tenant_id', UUID(as_uuid=True), sa.ForeignKey('tenants.id'), nullable=False),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column('updated_at', sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column('creado_por_id', UUID(as_uuid=True), sa.ForeignKey('users.id', ondelete='SET NULL')),
        sa.Column('actualizado_por_id', UUID(as_uuid=True), sa.ForeignKey('users.id', ondelete='SET NULL'))]


def upgrade():
    op.create_unique_constraint('uq_modelobim_id_tenant', 'modelos_bim', ['id', 'tenant_id'])
    op.create_table('bim_revisiones', *columns(),
        sa.Column('modelo_id', UUID(as_uuid=True), nullable=False),
        sa.Column('fuente_sha256', sa.String(64), nullable=False),
        sa.Column('huella', sa.String(64), nullable=False),
        sa.Column('geometria_sha256', sa.String(64), nullable=False),
        sa.Column('cobertura', sa.JSON(), nullable=False),
        sa.Column('tipos_admitidos', sa.JSON(), nullable=False),
        sa.ForeignKeyConstraint(['modelo_id', 'tenant_id'], ['modelos_bim.id', 'modelos_bim.tenant_id']),
        sa.UniqueConstraint('id', 'tenant_id', name='uq_bim_revision_tenant'),
        sa.UniqueConstraint('modelo_id', 'huella', name='uq_bim_revision_content'))
    op.create_table('bim_decisiones_medicion', *columns(),
        sa.Column('revision_id', UUID(as_uuid=True), nullable=False),
        sa.Column('familia_global_id', sa.String(100), nullable=False),
        sa.Column('version', sa.Integer(), nullable=False),
        sa.Column('criterio', sa.String(20), nullable=False),
        sa.Column('confirmada', sa.Boolean(), nullable=False),
        sa.Column('datos', sa.JSON(), nullable=False),
        sa.ForeignKeyConstraint(['revision_id', 'tenant_id'], ['bim_revisiones.id', 'bim_revisiones.tenant_id']),
        sa.UniqueConstraint('revision_id', 'familia_global_id', 'version', name='uq_bim_decision_version'))
    for table, column in [('bim_revisiones', 'modelo_id'), ('bim_decisiones_medicion', 'revision_id')]:
        op.create_index(f'ix_{table}_{column}', table, [column])
        for indexed in ('tenant_id', 'created_at', 'creado_por_id'):
            op.create_index(f'ix_{table}_{indexed}', table, [indexed])
    op.add_column('modelos_bim', sa.Column('revision_actual_id', UUID(as_uuid=True), nullable=True))
    op.create_foreign_key('fk_bim_revision_actual', 'modelos_bim', 'bim_revisiones', ['revision_actual_id', 'tenant_id'], ['id', 'tenant_id'])
    op.execute("""CREATE FUNCTION megalodon_bim_snapshot_immutable() RETURNS trigger LANGUAGE plpgsql AS $$
        BEGIN RAISE EXCEPTION 'BIM coverage and decisions are immutable; create a new revision'; END $$""")
    for table, trigger in [('bim_revisiones', 'trg_bim_revision_immutable'), ('bim_decisiones_medicion', 'trg_bim_decision_immutable')]:
        op.execute(f'CREATE TRIGGER {trigger} BEFORE UPDATE OR DELETE ON {table} FOR EACH ROW EXECUTE FUNCTION megalodon_bim_snapshot_immutable()')



def downgrade():
    op.execute('DROP TRIGGER trg_bim_decision_immutable ON bim_decisiones_medicion')
    op.execute('DROP TRIGGER trg_bim_revision_immutable ON bim_revisiones')
    op.execute('DROP FUNCTION megalodon_bim_snapshot_immutable()')
    op.drop_constraint('fk_bim_revision_actual', 'modelos_bim', type_='foreignkey')
    op.drop_column('modelos_bim', 'revision_actual_id')
    op.drop_table('bim_decisiones_medicion')
    op.drop_table('bim_revisiones')
    op.drop_constraint('uq_modelobim_id_tenant', 'modelos_bim', type_='unique')
