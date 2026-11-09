from __future__ import annotations

import pytest
from sqlalchemy.ext.asyncio import create_async_engine

from scripts.supabase_preflight import collect_preflight, collect_storage_preflight, expected_alembic_heads


def test_preflight_discovers_repository_migration_heads():
    heads = expected_alembic_heads()

    assert heads
    assert len(heads) == len(set(heads))


@pytest.mark.asyncio
async def test_preflight_refuses_non_postgresql_databases():
    engine = create_async_engine("sqlite+aiosqlite:///:memory:")
    try:
        async with engine.connect() as connection:
            with pytest.raises(RuntimeError, match="PostgreSQL"):
                await collect_preflight(connection, expected_heads=["head"])
    finally:
        await engine.dispose()


@pytest.mark.asyncio
async def test_storage_preflight_is_optional_but_detects_partial_configuration():
    missing = await collect_storage_preflight(
        supabase_url=None,
        service_key=None,
        buckets={"bim": "bim-modelos"},
    )
    assert missing == {"status": "NOT_CONFIGURED", "checked": False}

    partial = await collect_storage_preflight(
        supabase_url="https://project-ref.supabase.co",
        service_key=None,
        buckets={"bim": "bim-modelos"},
    )
    assert partial == {"status": "CONFIGURATION_INCOMPLETE", "checked": False}


@pytest.mark.asyncio
async def test_storage_preflight_refuses_non_https_project_urls():
    result = await collect_storage_preflight(
        supabase_url="http://project-ref.supabase.co",
        service_key="synthetic-service-key",
        buckets={"bim": "bim-modelos"},
    )

    assert result == {"status": "UNSAFE_PROJECT_URL", "checked": False}
