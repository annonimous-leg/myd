"""Explicit catalogue currency and corrections of immutable transcription evidence."""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision = '20261001_indices_revision'
down_revision = '20261001_indices_materiales'
branch_labels = None
depends_on = None


def upgrade():
    # Historical currencies remain unknown, never assumed to be MXN.
    op.add_column('catalogo_fuentes', sa.Column('moneda', sa.String(3), nullable=True))
    op.add_column('catalogo_fuentes', sa.Column('moneda_evidencia', postgresql.JSONB(), nullable=True))
    op.add_column('observaciones_indices_costos', sa.Column('revision_captura', sa.Integer(), nullable=False, server_default='1'))
    op.add_column('observaciones_indices_costos', sa.Column('sustituye_id', postgresql.UUID(as_uuid=True), nullable=True))
    op.create_foreign_key('fk_indice_sustituye', 'observaciones_indices_costos', 'observaciones_indices_costos', ['sustituye_id'], ['id'], ondelete='RESTRICT')
    op.create_unique_constraint('uq_indice_sustituye', 'observaciones_indices_costos', ['sustituye_id'])
    op.drop_constraint('uq_observacion_indice_edicion', 'observaciones_indices_costos', type_='unique')
    op.create_unique_constraint('uq_observacion_indice_captura', 'observaciones_indices_costos', ['serie_id', 'mes', 'documento_sha256', 'revision_captura'])
    op.create_check_constraint('ck_indice_revision_captura', 'observaciones_indices_costos',
                               '(revision_captura = 1 AND sustituye_id IS NULL) OR (revision_captura > 1 AND sustituye_id IS NOT NULL)')


def downgrade():
    raise RuntimeError('Migración forward-only: conservar moneda acreditada y revisiones de captura')
