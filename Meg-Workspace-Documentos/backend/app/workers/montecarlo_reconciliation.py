from __future__ import annotations

import asyncio

from app.workers.database import AsyncSessionLocal
from app.services.montecarlo_service import MonteCarloService
from app.workers.celery_app import celery_app


@celery_app.task(
    bind=True,
    autoretry_for=(Exception,),
    retry_backoff=True,
    retry_backoff_max=60,
    retry_kwargs={"max_retries": 5},
    acks_late=True,
)
def reconcile_montecarlo_runs(self):
    return asyncio.run(_reconcile_montecarlo_runs())


async def _reconcile_montecarlo_runs() -> int:
    async with AsyncSessionLocal() as db:
        return await MonteCarloService.reconciliar_pendientes(
            db,
            limite=50,
            stale_after_seconds=1320,
        )
