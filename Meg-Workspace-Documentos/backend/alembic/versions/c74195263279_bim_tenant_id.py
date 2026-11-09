"""BIM tenant_id: modelos_bim, analisis_clash, generaciones_bim_4d5d

Revision ID: c74195263279
Revises: 9f3a1c7d2b4e
Create Date: 2026-08-10 00:00:00.000000

RESTAURACIÓN (FASE1 multi-tenant): 18 modelos del resto del sistema
(ExpedienteObra, CatalogoAPU, Contrato, Licitacion, etc.) recibieron
TenantMixin en la refactorización multi-tenant. Las 3 raíces de
agregado de BIM (ModeloBIM, AnalisisClash, GeneracionBIM4D5D -- las
únicas de este módulo con AuditMixin, mismo criterio que el resto del
sistema) se quedaron sin tenant_id propio -- dependían solo de la
cadena de FKs (modelo_id -> expediente_id -> tenant_id), que sigue
siendo tenant-segura vía verificar_expediente_tenant en el router, pero
no consistente con el patrón de columna directa que ya tiene el resto
del dominio.

Esta migración:
1. Agrega tenant_id (nullable primero) a las 3 tablas -- si no existe
   ya, igual que 9f3a1c7d2b4e usa sqlalchemy.inspect() para ser segura
   de correr sobre una BD en cualquier estado.
2. Backfillea desde la cadena de FKs que YA existía:
   - modelos_bim.tenant_id <- expedientes_obra.tenant_id (via expediente_id)
   - generaciones_bim_4d5d.tenant_id <- expedientes_obra.tenant_id (via expediente_id, columna directa)
   - analisis_clash.tenant_id <- modelos_bim.tenant_id (via modelo_id) --
     tiene que ir DESPUÉS del backfill de modelos_bim en la misma corrida.
3. Dejar la columna NOT NULL + FK a tenants.id + índice, solo si el
   backfill no dejó ningún NULL (si dejó NULLs -- dato huérfano, FK
   apuntando a un expediente/modelo borrado -- se deja nullable y se
   registra un warning en vez de tronar la migración completa).

SIN VERIFICAR EN ESTE SANDBOX (sin red, sin Postgres real): la lógica
de idempotencia y el orden de backfill se revisaron por lectura
cuidadosa contra el mismo patrón ya usado (y probado en un Postgres
real, según ESTADO_Y_PLAN) en 9f3a1c7d2b4e.
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy import inspect
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision: str = "c74195263279"
down_revision: Union[str, None] = "9f3a1c7d2b4e"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


_TABLAS = ("modelos_bim", "analisis_clash", "generaciones_bim_4d5d")


def _agregar_columna_si_falta(inspector, tabla: str) -> None:
    columnas = {c["name"] for c in inspector.get_columns(tabla)}
    if "tenant_id" not in columnas:
        op.add_column(tabla, sa.Column("tenant_id", postgresql.UUID(as_uuid=True), nullable=True))


def upgrade() -> None:
    bind = op.get_bind()
    inspector = inspect(bind)

    for tabla in _TABLAS:
        _agregar_columna_si_falta(inspector, tabla)

    # Orden importa: modelos_bim primero (analisis_clash depende de su
    # tenant_id ya backfilleado).
    bind.execute(sa.text("""
        UPDATE modelos_bim
        SET tenant_id = expedientes_obra.tenant_id
        FROM expedientes_obra
        WHERE modelos_bim.expediente_id = expedientes_obra.id
          AND modelos_bim.tenant_id IS NULL
    """))

    bind.execute(sa.text("""
        UPDATE generaciones_bim_4d5d
        SET tenant_id = expedientes_obra.tenant_id
        FROM expedientes_obra
        WHERE generaciones_bim_4d5d.expediente_id = expedientes_obra.id
          AND generaciones_bim_4d5d.tenant_id IS NULL
    """))

    bind.execute(sa.text("""
        UPDATE analisis_clash
        SET tenant_id = modelos_bim.tenant_id
        FROM modelos_bim
        WHERE analisis_clash.modelo_id = modelos_bim.id
          AND analisis_clash.tenant_id IS NULL
    """))

    # Re-inspeccionar tras el backfill: solo se endurece a NOT NULL +
    # FK + índice si de verdad no quedó ningún huérfano. Con FKs
    # ondelete=CASCADE/SET NULL ya vigentes desde 9f3a1c7d2b4e y la
    # baseline, no debería haber huérfanos en una BD sana -- pero una
    # migración de esquema no es el lugar para asumirlo sin comprobar.
    for tabla in _TABLAS:
        huerfanos = bind.execute(
            sa.text(f"SELECT COUNT(*) FROM {tabla} WHERE tenant_id IS NULL")
        ).scalar()

        existing_indexes = {ix["name"] for ix in inspector.get_indexes(tabla)}
        idx_name = f"idx_{tabla}_tenant_id"

        if huerfanos and huerfanos > 0:
            print(
                f"⚠️  {tabla}: {huerfanos} fila(s) con tenant_id NULL tras "
                "el backfill (huérfanas -- expediente/modelo padre ya no "
                "existe). Se deja la columna NULLABLE en vez de romper la "
                "migración; revisar esas filas a mano antes de forzar NOT NULL."
            )
            if idx_name not in existing_indexes:
                op.create_index(idx_name, tabla, ["tenant_id"])
            continue

        op.alter_column(tabla, "tenant_id", nullable=False)

        existing_fks = {fk["name"] for fk in inspector.get_foreign_keys(tabla) if fk.get("name")}
        fk_name = f"fk_{tabla}_tenant_id_tenants"
        if fk_name not in existing_fks:
            op.create_foreign_key(fk_name, tabla, "tenants", ["tenant_id"], ["id"], ondelete="CASCADE")

        if idx_name not in existing_indexes:
            op.create_index(idx_name, tabla, ["tenant_id"])


def downgrade() -> None:
    bind = op.get_bind()
    inspector = inspect(bind)

    for tabla in _TABLAS:
        existing_indexes = {ix["name"] for ix in inspector.get_indexes(tabla)}
        idx_name = f"idx_{tabla}_tenant_id"
        if idx_name in existing_indexes:
            op.drop_index(idx_name, table_name=tabla)

        existing_fks = {fk["name"] for fk in inspector.get_foreign_keys(tabla) if fk.get("name")}
        fk_name = f"fk_{tabla}_tenant_id_tenants"
        if fk_name in existing_fks:
            op.drop_constraint(fk_name, tabla, type_="foreignkey")

        columnas = {c["name"] for c in inspector.get_columns(tabla)}
        if "tenant_id" in columnas:
            op.drop_column(tabla, "tenant_id")
