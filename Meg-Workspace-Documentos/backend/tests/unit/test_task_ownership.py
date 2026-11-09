from uuid import uuid4
from unittest.mock import AsyncMock

import pytest

from app.core.task_ownership import verify_task_owner


@pytest.mark.asyncio
async def test_verify_task_owner_uses_tenant_scoped_domain_records() -> None:
    db = AsyncMock()
    db.scalar.return_value = 1
    tenant_id = uuid4()

    assert await verify_task_owner(db, "celery-task-123", tenant_id=tenant_id) is True

    statement = db.scalar.await_args.args[0]
    sql = str(statement)
    params = statement.compile().params

    for table in ("ocr_jobs", "monte_carlo_runs", "procurement_jobs"):
        assert table in sql
    assert sql.count("task_id") >= 3
    assert sql.count("tenant_id") >= 3
    assert "celery-task-123" in params.values()
    assert sum(value == tenant_id for value in params.values()) >= 3


@pytest.mark.asyncio
async def test_verify_task_owner_denies_unknown_or_other_tenant_tasks() -> None:
    db = AsyncMock()
    db.scalar.return_value = None

    assert await verify_task_owner(db, "foreign-task", tenant_id=uuid4()) is False


@pytest.mark.asyncio
async def test_verify_task_owner_rejects_invalid_tenant_without_query() -> None:
    db = AsyncMock()

    assert await verify_task_owner(db, "celery-task-123", tenant_id="not-a-uuid") is False

    db.scalar.assert_not_awaited()


@pytest.mark.asyncio
async def test_verify_task_owner_fails_closed_when_database_lookup_errors() -> None:
    db = AsyncMock()
    db.scalar.side_effect = RuntimeError("database unavailable")

    assert await verify_task_owner(db, "celery-task-123", tenant_id=uuid4()) is False
