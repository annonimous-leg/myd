"""Read-only check of migrated tables/columns before application tests.

Run with: python -m scripts.verify_migrated_schema
Never creates missing tables; a migration gap must fail installation checks.
"""
import asyncio
from pathlib import Path

from alembic.config import Config
from alembic.runtime.migration import MigrationContext
from alembic.script import ScriptDirectory

from sqlalchemy import inspect

import app.models  # noqa: F401
from app.models.base import Base, engine
from tezcatlipoca.db.models import Base as TezBase


def verify(connection, metadata_collection=None):
    backend_root = Path(__file__).resolve().parents[1]
    config = Config(str(backend_root / "alembic.ini"))
    config.set_main_option("script_location", str(backend_root / "alembic"))
    expected = set(ScriptDirectory.from_config(config).get_heads())
    current = set(MigrationContext.configure(connection).get_current_heads())
    if current != expected:
        raise RuntimeError("Database migrations are not at application head; apply alembic upgrade head before startup")
    inspector = inspect(connection)
    gaps = []
    count = 0
    for metadata in metadata_collection if metadata_collection is not None else (Base.metadata, TezBase.metadata):
        for table in metadata.tables.values():
            count += 1
            if not inspector.has_table(table.name, schema=table.schema):
                gaps.append(f'{table.name}: missing table')
                continue
            columns = {c['name'] for c in inspector.get_columns(table.name, schema=table.schema)}
            for name in sorted(set(table.columns.keys()) - columns):
                gaps.append(f'{table.name}.{name}: missing column')
    if gaps:
        raise RuntimeError('Migrated schema does not support application models:\n' + '\n'.join(gaps))
    print(f'Migrated schema contains all required columns across {count} tables.')


async def main():
    # Reuse the canonical runtime engine so this check honors the same asyncpg
    # TLS/CA policy as API and workers. This script never creates or repairs DDL.
    async with engine.connect() as connection:
        await connection.run_sync(verify)


if __name__ == '__main__':
    asyncio.run(main())
