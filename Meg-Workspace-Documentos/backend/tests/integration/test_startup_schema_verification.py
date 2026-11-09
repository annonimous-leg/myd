"""Check startup schema rejection against real transactional PostgreSQL DDL."""
import pytest
from sqlalchemy import text

from scripts.verify_migrated_schema import verify


@pytest.mark.asyncio
async def test_startup_rejects_stale_revision_and_missing_column_without_repair(db_session):
    if db_session.bind.dialect.name != "postgresql":
        pytest.skip("Schema rejection uses transactional PostgreSQL DDL")
    try:
        connection = await db_session.connection()
        await connection.execute(text("UPDATE alembic_version SET version_num = '20260930_tez_timestamps'"))
        with pytest.raises(RuntimeError, match="not at application head"):
            await connection.run_sync(verify)
        # A failed validation must not silently upgrade the revision.
        current = await connection.scalar(text("SELECT version_num FROM alembic_version"))
        assert current == "20260930_tez_timestamps"
    finally:
        await db_session.rollback()
    try:
        connection = await db_session.connection()
        await connection.execute(text("ALTER TABLE users DROP COLUMN auth_version"))
        with pytest.raises(RuntimeError, match="users.auth_version: missing column"):
            await connection.run_sync(verify)
        remaining = await connection.scalar(text(
            "SELECT count(*) FROM information_schema.columns "
            "WHERE table_schema = 'public' AND table_name = 'users' AND column_name = 'auth_version'"))
        assert remaining == 0
    finally:
        await db_session.rollback()
    # Both failures leave the durable migrated schema intact after rollback.
    connection = await db_session.connection()
    await connection.run_sync(verify)
