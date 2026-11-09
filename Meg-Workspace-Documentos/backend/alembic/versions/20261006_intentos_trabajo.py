"""Durable execution fencing and explicit attention for historical lost work."""
from alembic import op
import sqlalchemy as sa

revision = '20261006_intentos_trabajo'
down_revision = '20261006_trabajos_durables'
branch_labels = None
depends_on = None


def upgrade():
    op.add_column('trabajos_proceso', sa.Column('id_ejecucion', sa.Uuid(), nullable=True))
    # Historical IFC filters and 4D start dates were not persisted. Never
    # synthesize them or leave an indefinite spinner after broker loss.
    for table, kind, state, error in [
        ('modelos_bim', 'BIM_IFC', 'estado_procesamiento', 'error_procesamiento'),
        ('generaciones_bim_4d5d', 'BIM_4D', 'estado', 'error'),
        ('analisis_clash', 'BIM_CLASH', 'estado', 'error')]:
        op.execute(sa.text(f"UPDATE {table} SET {state}='ERROR', {error}="
            "'Trabajo anterior sin orden durable. Revise los parámetros y vuelva a solicitarlo.' "
            f"WHERE {state} IN ('PENDIENTE','EN_PROCESO') AND NOT EXISTS "
            f"(SELECT 1 FROM trabajos_proceso j WHERE j.entidad_id={table}.id AND j.tipo='{kind}')"))


def downgrade():
    op.drop_column('trabajos_proceso', 'id_ejecucion')
