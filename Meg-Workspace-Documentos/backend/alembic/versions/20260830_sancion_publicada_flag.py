"""Add sanciones.publicada -- cierra fuga cross-tenant en /sanciones-publicas.

Hallazgo (auditoría externa 2026-08-30, verificado leyendo el código antes
de tocar nada): GET /sanciones-publicas no tiene autenticación y filtraba
solo por `estado == "VIGENTE"` -- sin `tenant_id`. `estado` es un estado
del expediente sancionador (en efecto / concluida / suspendida / apelada),
no una decisión de publicación. Resultado real: el endpoint devolvía las
sanciones de TODOS los tenants mezcladas, incluyendo `motivo` y
`monto_multa`, a cualquiera sin login.

A diferencia de ExpedienteObra, que sí tiene `clasificacion` para gatear su
propio endpoint público (/expedientes-publicos, que además es
intencionalmente cross-tenant por diseño -- mismo patrón que un portal de
transparencia nacional), `Sancion` no tenía ningún campo equivalente para
decidir qué sí es publicable.

Esta migración agrega `publicada` (boolean, default false). Con el default
en false y ningún registro existente marcado, el endpoint público queda
vacío hasta que cada tenant decida explícitamente qué sanciones sí debe
mostrar el portal de transparencia -- no se asume "vigente = pública".
"""
from alembic import op
import sqlalchemy as sa

revision = "20260830_sancion_publicada_flag"
down_revision = "20260827_legal_rule_active_requires_fundamento"
branch_labels = None
depends_on = None


def upgrade() -> None:
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    columns = {c["name"] for c in inspector.get_columns("sanciones")}
    if "publicada" not in columns:
        op.add_column(
            "sanciones",
            sa.Column("publicada", sa.Boolean(), nullable=False, server_default=sa.false()),
        )


def downgrade() -> None:
    op.drop_column("sanciones", "publicada")
