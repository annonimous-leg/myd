"""BIM 4D/5D: zona_4d, generaciones_bim_4d5d, elemento_bim_actividad

Revision ID: 9f3a1c7d2b4e
Revises: 06d589924524
Create Date: 2026-07-30 00:00:00.000000

Soporte de datos para BIM 4D (cronograma) y 5D (costeo real) nativos:

- `elementos_bim.zona_4d`: agrupación de trabajo editable por el usuario,
  independiente de `nivel` (que viene fijo del IFC). Un elemento puede
  necesitar agruparse distinto para efectos de secuencia constructiva
  de como está repartido por planta -- ver notas en BIMService.

- `generaciones_bim_4d5d`: registro (agregado raíz, con AuditMixin) de
  cada corrida de generación de cronograma 4D desde un modelo BIM. Se
  encola a Celery porque agrupar/crear actividades para un modelo con
  miles de elementos no es instantáneo; este registro es lo que el
  frontend hace polling mientras corre (mismo patrón que
  ModeloBIM.estado_procesamiento, no el WebSocket genérico).

- `elemento_bim_actividad`: tabla puente muchos-a-muchos entre
  ElementoBIM y ActividadPrograma. Es una entidad hija que se inserta
  en lote (como ElementoBIM o ActividadPrograma) -- sin AuditMixin, ver
  convención documentada en app/models/base.py.

ACTUALIZACIÓN (2026-08-08): el gap de baseline que describía este
docstring ya se cerró en 55225d1e7443, que ahora corre ANTES que esta
migración y crea el esquema completo delegando en `Base.metadata`
(incluye `elementos_bim`, `actividades_programa`, y -- porque ya están
declaradas en `app/models/bim.py` -- también `zona_4d`,
`generaciones_bim_4d5d` y `elemento_bim_actividad`, que son
exactamente lo que este archivo crea a mano abajo).

Para no depender de que la baseline gane la carrera siempre (una base
de datos real pudo haber sido parchada a mano antes de que existiera
la baseline, tal como asumía la versión original de este docstring),
`upgrade()` ahora es idempotente: usa `sqlalchemy.inspect()` para
revisar qué ya existe antes de crear cada columna/tabla/índice. Sea
cual sea el estado de la base (recién creada por la baseline, parchada
a mano, o a medias), el resultado final es el mismo esquema.
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy import UniqueConstraint, inspect
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision: str = "9f3a1c7d2b4e"
down_revision: Union[str, None] = "55225d1e7443"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    bind = op.get_bind()
    inspector = inspect(bind)
    existing_tables = set(inspector.get_table_names())

    # --- elementos_bim.zona_4d ---
    existing_columns = {c["name"] for c in inspector.get_columns("elementos_bim")}
    if "zona_4d" not in existing_columns:
        op.add_column(
            "elementos_bim",
            sa.Column("zona_4d", sa.String(length=255), nullable=True),
        )
    existing_indexes = {ix["name"] for ix in inspector.get_indexes("elementos_bim")}
    if "idx_elemento_bim_zona_4d" not in existing_indexes:
        op.create_index(
            "idx_elemento_bim_zona_4d", "elementos_bim", ["zona_4d"]
        )

    # --- generaciones_bim_4d5d ---
    if "generaciones_bim_4d5d" not in existing_tables:
        op.create_table(
            "generaciones_bim_4d5d",
            sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
            sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
            sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), onupdate=sa.func.now(), nullable=False),
            sa.Column("modelo_id", postgresql.UUID(as_uuid=True),
                      sa.ForeignKey("modelos_bim.id", ondelete="CASCADE"), nullable=False),
            sa.Column("expediente_id", postgresql.UUID(as_uuid=True),
                      sa.ForeignKey("expedientes_obra.id", ondelete="CASCADE"), nullable=False),
            sa.Column("programa_id", postgresql.UUID(as_uuid=True),
                      sa.ForeignKey("programas_obra.id", ondelete="SET NULL"), nullable=True),
            sa.Column("estado", sa.String(length=50), nullable=False, server_default="PENDIENTE"),
            sa.Column("error", sa.Text(), nullable=True),
            sa.Column("agrupar_por", sa.String(length=20), nullable=False, server_default="zona_4d"),
            sa.Column("dias_por_defecto", sa.Numeric(8, 2), nullable=False, server_default="5.0"),
            sa.Column("num_actividades_generadas", sa.Integer(), nullable=True),
            sa.Column("creado_por_id", postgresql.UUID(as_uuid=True),
                      sa.ForeignKey("users.id", ondelete="SET NULL"), nullable=True),
            sa.Column("actualizado_por_id", postgresql.UUID(as_uuid=True),
                      sa.ForeignKey("users.id", ondelete="SET NULL"), nullable=True),
        )
        op.create_index("idx_generacion_4d5d_modelo", "generaciones_bim_4d5d", ["modelo_id"])
        op.create_index("idx_generacion_4d5d_expediente", "generaciones_bim_4d5d", ["expediente_id"])

    # --- elemento_bim_actividad (puente M:N) ---
    if "elemento_bim_actividad" not in existing_tables:
        op.create_table(
            "elemento_bim_actividad",
            sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
            sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
            sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), onupdate=sa.func.now(), nullable=False),
            sa.Column("elemento_bim_id", postgresql.UUID(as_uuid=True),
                      sa.ForeignKey("elementos_bim.id", ondelete="CASCADE"), nullable=False),
            sa.Column("actividad_id", postgresql.UUID(as_uuid=True),
                      sa.ForeignKey("actividades_programa.id", ondelete="CASCADE"), nullable=False),
            sa.UniqueConstraint("elemento_bim_id", "actividad_id", name="uq_elemento_bim_actividad"),
        )
        op.create_index("idx_eba_elemento", "elemento_bim_actividad", ["elemento_bim_id"])
        op.create_index("idx_eba_actividad", "elemento_bim_actividad", ["actividad_id"])


def downgrade() -> None:
    bind = op.get_bind()
    inspector = inspect(bind)
    existing_tables = set(inspector.get_table_names())

    if "elemento_bim_actividad" in existing_tables:
        op.drop_index("idx_eba_actividad", table_name="elemento_bim_actividad")
        op.drop_index("idx_eba_elemento", table_name="elemento_bim_actividad")
        op.drop_table("elemento_bim_actividad")

    if "generaciones_bim_4d5d" in existing_tables:
        op.drop_index("idx_generacion_4d5d_expediente", table_name="generaciones_bim_4d5d")
        op.drop_index("idx_generacion_4d5d_modelo", table_name="generaciones_bim_4d5d")
        op.drop_table("generaciones_bim_4d5d")

    existing_columns = {c["name"] for c in inspector.get_columns("elementos_bim")}
    if "zona_4d" in existing_columns:
        op.drop_index("idx_elemento_bim_zona_4d", table_name="elementos_bim")
        op.drop_column("elementos_bim", "zona_4d")
