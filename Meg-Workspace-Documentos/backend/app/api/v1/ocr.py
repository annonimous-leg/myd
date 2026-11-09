# Copyright © 2026 Cristian Rodriguez
# All rights reserved.
# Unauthorized copying, modification, distribution, or use is prohibited
# without prior written permission.

"""API OCR con fuente durable en storage y estado propio del dominio."""
from pathlib import Path
from typing import Optional
from uuid import UUID, uuid4

from fastapi import APIRouter, Depends, File, Form, Header, UploadFile
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import settings
from app.core.deps import get_current_user, get_db
from app.core.rate_limit import rate_limit_standard, rate_limit_strict
from app.integrations.supabase_storage import storage_documentos
from app.models.ocr_job import OCRJob, OCRJobStatus
from app.models.user import User
from app.services.ocr_jobs import OCRJobService
from app.services.ocr_service import OCRService
from app.utils.upload_limits import read_upload_with_limit

router = APIRouter()


@router.post("/extraer")
async def extraer_metrados(
    file: UploadFile = File(...),
    presupuesto_id: Optional[UUID] = Form(None),
    idempotency_key: Optional[str] = Header(
        default=None, alias="Idempotency-Key", max_length=128
    ),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
    _rate_limit: bool = Depends(rate_limit_strict),
):
    """Registra OCR durable; el broker sólo recibe el id del trabajo."""
    content = await read_upload_with_limit(
        file, settings.TENDER_SOURCE_MAX_FILE_SIZE_MB
    )
    filename = Path(file.filename or "documento").name
    service = OCRJobService(db, current_user.tenant_id)
    request_hash = service.request_hash(
        source_bytes=content,
        filename=filename,
        presupuesto_id=presupuesto_id,
    )

    existing = await service.recuperar_por_idempotencia(
        idempotency_key, request_hash
    )
    if existing is not None:
        if existing.status == OCRJobStatus.PENDING.value:
            existing = await service.publicar(existing.id)
        return {
            "job_id": str(existing.id),
            "task_id": existing.task_id,
            "status": existing.status,
            "progress": existing.progress,
            "filename": existing.filename,
            "idempotent_replay": True,
        }

    await service.validar_presupuesto(presupuesto_id)

    job_id = uuid4()
    suffix = Path(filename).suffix.lower()
    storage_path = (
        f"tenant/{current_user.tenant_id}/ocr/{job_id}/source{suffix}"
    )
    storage = storage_documentos()
    await storage.subir(
        storage_path,
        content,
        content_type=file.content_type or "application/octet-stream",
        overwrite=False,
    )

    try:
        job, replay = await service.crear(
            user=current_user,
            job_id=job_id,
            filename=filename,
            content_type=file.content_type,
            storage_path=storage_path,
            source_bytes=content,
            presupuesto_id=presupuesto_id,
            idempotency_key=idempotency_key,
            request_hash=request_hash,
        )
    except Exception:
        # A commit failure can be ambiguous: never delete a durable job's input.
        # If the database cannot confirm absence, retain the object for recovery.
        try:
            await db.rollback()
            persisted = await db.scalar(select(OCRJob.id).where(OCRJob.id == job_id))
        except Exception:
            persisted = job_id
        if persisted is None:
            await storage.eliminar([storage_path])
        raise

    if replay:
        # Otra request con la misma key ganó mientras subíamos. Su job tiene
        # su propia fuente; esta subida ya no referencia nada y se compensa.
        await storage.eliminar([storage_path])

    if job.status == OCRJobStatus.PENDING.value:
        job = await service.publicar(job.id)

    return {
        "job_id": str(job.id),
        "task_id": job.task_id,
        "status": job.status,
        "progress": job.progress,
        "filename": job.filename,
        "idempotent_replay": replay,
    }


@router.get("/extraer/{task_id}/status")
async def consultar_ocr(
    task_id: str,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
    _rate_limit: bool = Depends(rate_limit_standard),
):
    job = await OCRJobService(
        db, current_user.tenant_id
    ).get_by_task(task_id)
    response = {
        "job_id": str(job.id),
        "task_id": job.task_id,
        "status": job.status,
        "progress": job.progress,
        "attempts": job.attempts,
        "filename": job.filename,
        "created_at": job.created_at,
        "started_at": job.started_at,
        "finished_at": job.finished_at,
    }
    if job.status == OCRJobStatus.SUCCEEDED.value:
        response["result"] = job.result
    elif job.status == OCRJobStatus.FAILED.value:
        response["error"] = {
            "code": job.error_code,
            "message": job.error_message,
        }
    return response


@router.post("/validar")
async def validar_metrados(
    metrados: list,
    umbral_confianza: float = 60.0,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
    _rate_limit: bool = Depends(rate_limit_strict),
):
    """Valida metrados extraídos por OCR."""
    from app.engines.ia.ocr_metrados import MetradoExtraido

    service = OCRService(db, tenant_id=current_user.tenant_id)
    metrados_objs = [MetradoExtraido(**m) for m in metrados]
    return await service.validar_metrados(
        metrados_objs, umbral_confianza
    )
