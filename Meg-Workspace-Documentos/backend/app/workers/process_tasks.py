"""Celery boundary. Retry state and results belong to the durable database job."""
import asyncio
from app.workers.celery_app import celery_app


@celery_app.task(acks_late=True, reject_on_worker_lost=True, time_limit=1800)
def ejecutar_proceso(trabajo_id: str):
    from app.core.process_queue import ejecutar_trabajo
    from app.models.base import engine

    async def run():
        try:
            return await ejecutar_trabajo(trabajo_id)
        finally:
            # asyncio.run creates a fresh loop per prefork invocation.
            await engine.dispose()
    return asyncio.run(run())
