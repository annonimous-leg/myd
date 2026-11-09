"""Add inconformidades.severidad/regla_id/asignado_a/fecha_limite -- F-02.

Hallazgo F-02 (auditoría externa 2026-09-01, verificado leyendo el código):
compliance_service.crear_inconformidad() construía el modelo `Inconformidad`
pasando severidad=data.severidad, regla_id=data.regla_id,
asignado_a=data.asignado_a y fecha_limite=data.fecha_limite -- ninguna de
esas cuatro columnas existía en el modelo (ni en InconformidadCreate). Cada
alta de inconformidad fallaba en el ORM. Además EstadoInconformidad.ABIERTA,
usado como estado inicial, tampoco existía en el enum (los valores reales
son REGISTRADA/EN_ANALISIS/RESPONDIDA/RESUELTA/ARCHIVADA).

Corrección: en vez de quitarle esos cuatro campos al servicio (representan
funcionalidad real y esperada -- severidad, regla de cumplimiento vinculada,
responsable asignado, fecha límite), se agregan como columnas reales aquí,
y crear_inconformidad() pasa a usar EstadoInconformidad.REGISTRADA (el
estado inicial correcto que ya existía en el enum) en vez de ABIERTA.

Mismo patrón que 20260830_sancion_publicada_flag.py: el baseline
(55225d1e7443) crea el esquema vía `Base.metadata.create_all(checkfirst=True)`
al momento de correr esa migración -- una base de datos que YA corrió el
baseline antes de este cambio no gana estas columnas automáticamente, por
eso se agregan explícitamente aquí (idempotente: solo si no existen).
"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision = "20260901_inconformidad_compliance_fields"
down_revision = "20260831_procurement_tenant_graph_hardening"
branch_labels = None
depends_on = None

UUID = postgresql.UUID(as_uuid=True)
_TABLA = "inconformidades"


def upgrade() -> None:
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    columns = {c["name"] for c in inspector.get_columns(_TABLA)}

    if "severidad" not in columns:
        op.add_column(_TABLA, sa.Column("severidad", sa.String(length=20), nullable=True))
        op.create_index("ix_inconformidades_severidad", _TABLA, ["severidad"])

    if "regla_id" not in columns:
        op.add_column(
            _TABLA,
            sa.Column("regla_id", UUID, sa.ForeignKey("reglas_cumplimiento.id", ondelete="SET NULL"), nullable=True),
        )
        op.create_index("ix_inconformidades_regla_id", _TABLA, ["regla_id"])

    if "asignado_a" not in columns:
        op.add_column(
            _TABLA,
            sa.Column("asignado_a", UUID, sa.ForeignKey("users.id", ondelete="SET NULL"), nullable=True),
        )
        op.create_index("ix_inconformidades_asignado_a", _TABLA, ["asignado_a"])

    if "fecha_limite" not in columns:
        op.add_column(_TABLA, sa.Column("fecha_limite", sa.String(length=10), nullable=True))


def downgrade() -> None:
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    columns = {c["name"] for c in inspector.get_columns(_TABLA)}

    if "fecha_limite" in columns:
        op.drop_column(_TABLA, "fecha_limite")
    if "asignado_a" in columns:
        op.drop_index("ix_inconformidades_asignado_a", table_name=_TABLA)
        op.drop_column(_TABLA, "asignado_a")
    if "regla_id" in columns:
        op.drop_index("ix_inconformidades_regla_id", table_name=_TABLA)
        op.drop_column(_TABLA, "regla_id")
    if "severidad" in columns:
        op.drop_index("ix_inconformidades_severidad", table_name=_TABLA)
        op.drop_column(_TABLA, "severidad")
