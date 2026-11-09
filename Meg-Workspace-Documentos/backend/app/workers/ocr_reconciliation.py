from __future__ import annotations

import asyncio

from app.workers.database import AsyncSessionLocal
from app.services.ocr_jobs import OCRJobService
from app.workers.celery_app import celery_app


@celery_app.task(
    bind=True,
    autoretry_for=(Exception,),
    retry_backoff=True,
    retry_backoff_max=60,
    retry_kwargs={"max_retries": 5},
    acks_late=True,
)
def reconcile_ocr_jobs(self):
    return asyncio.run(_reconcile())


async def _reconcile() -> int:
    async with AsyncSessionLocal() as db:
        return await OCRJobService.reconciliar(db, limit=50)
