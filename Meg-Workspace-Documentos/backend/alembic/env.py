# Copyright © 2026 Cristian Rodriguez
# All rights reserved.
# Unauthorized copying, modification, distribution, or use is prohibited
# without prior written permission.

"""
Configuración de Alembic para migraciones.
"""
import asyncio
from logging.config import fileConfig

from sqlalchemy import pool, String, inspect, text
from sqlalchemy.engine import Connection
from sqlalchemy.ext.asyncio import async_engine_from_config

from alembic import context
from alembic.ddl.postgresql import PostgresqlImpl
from app.config import settings
from app.models.base import Base

# BUG ORIGINAL (y BUG RECURRENTE): env.py mantenía una lista manual de
# imports de modelos para poblar Base.metadata antes de autogenerate. Ya
# se había corregido una vez (agregando bim/validador) pero la lista
# volvió a quedarse corta -- le faltaban compliance, licitacion,
# contrato, catalogo_apu, catalogo_conceptos, workflow, rules_engine,
# catalogo_juridico, catalogo_procedimiento, proveedor, entidad,
# audit_ledger, documento, planeacion, notifications, y ahora
# entitlements. Una lista mantenida a mano siempre se puede volver a
# quedar corta. Se importa el paquete completo en su lugar: cualquier
# modelo que app/models/__init__.py registre, Alembic lo ve, sin volver
# a tener que acordarse de actualizar esta lista.
import app.models  # noqa: F401  (el import por su efecto secundario: registra todo en Base.metadata)
from tezcatlipoca.db.models import Base as TezBase


class MegalodonPostgresqlImpl(PostgresqlImpl):
    """The historical descriptive revision IDs exceed Alembic's 32 chars."""
    __dialect__ = "postgresql"

    def version_table_impl(self, **kwargs):
        table = super().version_table_impl(**kwargs)
        table.c.version_num.type = String(128)
        return table

config = context.config

if config.config_file_name is not None:
    fileConfig(config.config_file_name)

target_metadata = [Base.metadata, TezBase.metadata]


def get_url():
    """Return the dedicated migration (DDL) DSN, never the runtime DML DSN."""
    return settings.migration_async_url


def run_migrations_offline() -> None:
    url = get_url()
    context.configure(
        url=url,
        target_metadata=target_metadata,
        literal_binds=True,
        dialect_opts={"paramstyle": "named"},
    )
    with context.begin_transaction():
        context.run_migrations()


def do_run_migrations(connection: Connection) -> None:
    context.configure(connection=connection, target_metadata=target_metadata)
    with context.begin_transaction():
        # Widen existing installation metadata too; preserve the recorded ID.
        inspector = inspect(connection)
        if connection.dialect.name == "postgresql" and inspector.has_table("alembic_version"):
            version = next(c for c in inspector.get_columns("alembic_version") if c["name"] == "version_num")
            if getattr(version["type"], "length", None) and version["type"].length < 128:
                connection.execute(text("ALTER TABLE alembic_version ALTER COLUMN version_num TYPE VARCHAR(128)"))
        context.run_migrations()


async def run_async_migrations() -> None:
    configuration = config.get_section(config.config_ini_section)
    configuration["sqlalchemy.url"] = get_url()

    connectable = async_engine_from_config(
        configuration,
        prefix="sqlalchemy.",
        poolclass=pool.NullPool,
        connect_args=settings.migration_database_connection.connect_args,
    )

    async with connectable.connect() as connection:
        await connection.run_sync(do_run_migrations)

    await connectable.dispose()


def run_migrations_online() -> None:
    asyncio.run(run_async_migrations())


if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()
