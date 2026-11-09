# Copyright © 2026 Cristian Rodriguez
# All rights reserved.
# Unauthorized copying, modification, distribution, or use is prohibited
# without prior written permission.

"""Tenant-safe ownership checks for asynchronous Celery tasks.

The application database is the source of truth for task ownership.
Celery task IDs are persisted by the OCR, Monte Carlo, and procurement
job aggregates; querying those tenant-scoped rows avoids a second,
best-effort Redis registration step and works for previously queued jobs.

Access is denied for missing/invalid identifiers, unknown tasks, tasks
belonging to a different tenant, and database lookup failures.
"""
from __future__ import annotations

from uuid import UUID

import structlog
from sqlalchemy import literal, select, union_all
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.montecarlo import MonteCarloRun
from app.models.ocr_job import OCRJob
from app.models.procurement_jobs import ProcurementJob

logger = structlog.get_logger()


async def verify_task_owner(
    db: AsyncSession,
    task_id: str,
    *,
    tenant_id: UUID | str,
) -> bool:
    """Return true only when a persisted task belongs to the supplied tenant.

    The three task-producing domains store their Celery ID on a tenant-
    scoped aggregate. They are queried together so authorization does not
    depend on Redis state or on a post-enqueue side effect.
    """
    if not isinstance(task_id, str) or not task_id.strip():
        return False

    try:
        owner_tenant_id = tenant_id if isinstance(tenant_id, UUID) else UUID(str(tenant_id))
    except (AttributeError, TypeError, ValueError):
        logger.info("task_owner_invalid_tenant")
        return False

    try:
        statement = union_all(
            select(literal(1))
            .select_from(OCRJob)
            .where(OCRJob.task_id == task_id, OCRJob.tenant_id == owner_tenant_id),
            select(literal(1))
            .select_from(MonteCarloRun)
            .where(MonteCarloRun.task_id == task_id, MonteCarloRun.tenant_id == owner_tenant_id),
            select(literal(1))
            .select_from(ProcurementJob)
            .where(
                ProcurementJob.task_id == task_id,
                ProcurementJob.tenant_id == owner_tenant_id,
            ),
        ).limit(1)
        return (await db.scalar(statement)) is not None
    except Exception as exc:
        # Fail closed; keep database details out of structured logs.
        logger.warning(
            "task_owner_verify_error",
            error_type=type(exc).__name__,
        )
        return False
