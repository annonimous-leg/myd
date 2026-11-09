"""Preserve original monthly-level precision and immutable reviewed source files."""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision = '20261005_ingesta_inegi'
down_revision = '20261001_indices_revision'
branch_labels = None
depends_on = None


def upgrade():
    op.add_column('series_indices_costos', sa.Column('contrato_inegi', postgresql.JSONB(), nullable=True))
    op.alter_column('observaciones_indices_costos', 'valor', type_=sa.Numeric(30, 20), existing_type=sa.Numeric(18, 8), nullable=False)
    op.create_table('cargas_indices_costos',
        sa.Column('id', postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column('serie_id', postgresql.UUID(as_uuid=True), sa.ForeignKey('series_indices_costos.id', ondelete='RESTRICT'), nullable=False),
        sa.Column('documento_sha256', sa.String(64), nullable=False),
        sa.Column('publicado_el', sa.Date(), nullable=False),
        sa.Column('mes_inicio', sa.Date(), nullable=False),
        sa.Column('mes_fin', sa.Date(), nullable=False),
        sa.Column('ultima_actualizacion', sa.String(120), nullable=False),
        sa.Column('evidencia', postgresql.JSONB(), nullable=False),
        sa.Column('archivo', sa.LargeBinary(), nullable=False),
        sa.Column('registrado_por', sa.String(36), nullable=False),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column('updated_at', sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.UniqueConstraint('serie_id', 'documento_sha256', name='uq_carga_indice_archivo'),
        sa.UniqueConstraint('id', 'serie_id', 'documento_sha256', 'publicado_el', name='uq_carga_indice_identidad'),
        sa.CheckConstraint("encode(sha256(archivo), 'hex') = documento_sha256", name='ck_carga_indice_sha'),
        sa.CheckConstraint('octet_length(archivo) BETWEEN 1 AND 2097152', name='ck_carga_indice_tamano'),
        sa.CheckConstraint('mes_inicio <= mes_fin', name='ck_carga_indice_intervalo'),
    )
    op.add_column('observaciones_indices_costos', sa.Column('carga_id', postgresql.UUID(as_uuid=True), nullable=True))
    op.create_foreign_key('fk_observacion_carga', 'observaciones_indices_costos', 'cargas_indices_costos',
        ['carga_id', 'serie_id', 'documento_sha256', 'publicado_el'],
        ['id', 'serie_id', 'documento_sha256', 'publicado_el'], ondelete='RESTRICT')
    op.create_index('ix_observaciones_indices_costos_carga_id', 'observaciones_indices_costos', ['carga_id'])
    for action, scope in [('UPDATE OR DELETE', 'ROW'), ('TRUNCATE', 'STATEMENT')]:
        suffix = 'inmutable' if scope == 'ROW' else 'no_truncate'
        op.execute(f'CREATE TRIGGER tr_cargas_indices_costos_{suffix} BEFORE {action} ON cargas_indices_costos FOR EACH {scope} EXECUTE FUNCTION indices_costos_evidencia_inmutable()')


def downgrade():
    raise RuntimeError('Migración forward-only: conservar archivos originales y precisión de los niveles')
