# Copyright © 2026 Cristian Rodriguez
# All rights reserved.
# Unauthorized copying, modification, distribution, or use is prohibited
# without prior written permission.

"""Worker OCR: el mensaje sólo transporta el id durable del dominio."""
from __future__ import annotations

import asyncio
from hashlib import sha256
from uuid import UUID

from app.engines.ia.ocr_metrados import MotorOCRMetrados
from app.workers.celery_app import celery_app


@celery_app.task(
    bind=True,
    time_limit=300,
    max_retries=2,
    acks_late=True,
    reject_on_worker_lost=True,
    track_started=True,
)
def extraer_metrados_ocr(self, job_id: str):
    async def _claim():
        from app.workers.database import AsyncSessionLocal
        from app.models.ocr_job import OCRJob
        from app.services.ocr_jobs import OCRJobService

        async with AsyncSessionLocal() as db:
            job = await db.get(OCRJob, UUID(job_id))
            if job is None:
                return None
            service = OCRJobService(db, job.tenant_id)
            claimed, token = await service.claim(UUID(job_id))
            if claimed is None:
                return None
            return {
                "token": token,
                "status": claimed.status,
                "tenant_id": str(claimed.tenant_id),
                "filename": claimed.filename,
                "storage_path": claimed.storage_path,
                "source_sha256": claimed.source_sha256,
            }

    async def _complete(token: str, resultado) -> bool:
        from app.workers.database import AsyncSessionLocal
        from app.models.ocr_job import OCRJob
        from app.services.ocr_jobs import OCRJobService

        async with AsyncSessionLocal() as db:
            job = await db.get(OCRJob, UUID(job_id))
            if job is None:
                return False
            return await OCRJobService(
                db, job.tenant_id
            ).completar(UUID(job_id), token, resultado)

    async def _fail(token: str, exc: Exception) -> str:
        from app.workers.database import AsyncSessionLocal
        from app.models.ocr_job import OCRJob
        from app.services.ocr_jobs import OCRJobService

        async with AsyncSessionLocal() as db:
            job = await db.get(OCRJob, UUID(job_id))
            if job is None:
                return "MISSING"
            return await OCRJobService(
                db, job.tenant_id
            ).fallar(UUID(job_id), token, exc)

    claim = asyncio.run(_claim())
    if claim is None:
        return {"status": "MISSING_OR_STALE", "job_id": job_id}
    token = claim["token"]
    if token is None:
        return {
            "status": "IGNORED_DUPLICATE",
            "job_id": job_id,
            "job_status": claim["status"],
        }

    try:
        from app.integrations.supabase_storage import storage_documentos

        async def download():
            from app.integrations.supabase_storage import worker_storage_scope
            async with worker_storage_scope():
                return await storage_documentos().descargar(claim["storage_path"])
        file_bytes = asyncio.run(download())
        digest = sha256(file_bytes).hexdigest()
        if digest != claim["source_sha256"]:
            raise RuntimeError(
                "El contenido OCR descargado no coincide con el hash persistido."
            )

        resultado = MotorOCRMetrados().procesar_documento(
            file_bytes,
            claim["filename"],
            job_id,
        )
        if not asyncio.run(_complete(token, resultado)):
            return {"status": "IGNORED_STALE_ATTEMPT", "job_id": job_id}
        return {
            "status": "SUCCESS",
            "job_id": job_id,
            "total_metrados": resultado.total_metrados,
        }
    except Exception as exc:
        state = asyncio.run(_fail(token, exc))
        if state == "PENDING" and self.request.retries < self.max_retries:
            raise self.retry(
                countdown=30 * (self.request.retries + 1),
                exc=exc,
            )
        if state in {"STALE", "MISSING"}:
            return {"status": "IGNORED_STALE_ATTEMPT", "job_id": job_id}
        if state == "PENDING":
            # El reconciliador del dominio lo republicará.
            return {"status": "PENDING", "job_id": job_id}
        raise
