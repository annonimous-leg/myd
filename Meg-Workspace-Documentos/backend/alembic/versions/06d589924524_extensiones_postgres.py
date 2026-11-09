"""Extensiones de PostgreSQL (postgis, pg_trgm)

Revision ID: 06d589924524
Revises:
Create Date: 2026-07-23 00:00:00.000000

Movido aquí desde app/main.py (lifespan). CREATE EXTENSION normalmente
requiere privilegios de superusuario en Postgres (salvo extensiones
"trusted"), así que no debe correr en cada arranque de la app con el
usuario de mínimo privilegio que se espera usar en producción. Esta
migración se aplica UNA vez, con un usuario con privilegios adecuados
(el mismo que corre el resto de las migraciones), y ya.

Esta es la primera migración del proyecto (down_revision=None): todavía
no existe una migración baseline con el esquema completo (~30 tablas).
Cuando se genere con `alembic revision --autogenerate`, debe encadenarse
después de ésta (down_revision apuntando a "06d589924524").
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic.
revision: str = "06d589924524"
down_revision: Union[str, None] = None
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.execute("CREATE EXTENSION IF NOT EXISTS postgis")
    op.execute("CREATE EXTENSION IF NOT EXISTS pg_trgm")


def downgrade() -> None:
    # Las extensiones se conservan deliberadamente durante downgrade.
    # Su eliminación es una operación de infraestructura administrada
    # y no forma parte de un rollback de aplicación.
    return None
