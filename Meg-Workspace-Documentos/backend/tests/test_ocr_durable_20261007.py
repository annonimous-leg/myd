from __future__ import annotations

from uuid import uuid4

import pytest

from app.engines.ia.ocr_metrados import MetradoExtraido, ResultadoOCR
from app.models.ocr_job import OCRJob, OCRJobStatus
from app.models.expediente import ExpedienteObra
from app.models.presupuesto import Partida, Presupuesto
from sqlalchemy import select
from app.services.ocr_jobs import OCRJobService


@pytest.mark.asyncio
async def test_ocr_broker_message_contains_only_durable_job_id(
    db_session, tenant_a_user, monkeypatch
):
    tenant, user = tenant_a_user
    service = OCRJobService(db_session, tenant.id)
    job_id = uuid4()
    source = b"not-the-broker-payload"
    job, replay = await service.crear(
        user=user,
        job_id=job_id,
        filename="plano.png",
        content_type="image/png",
        storage_path=f"tenant/{tenant.id}/ocr/{job_id}/source.png",
        source_bytes=source,
        presupuesto_id=None,
    )

    assert replay is False

    sent = []

    def accept(*args, **kwargs):
        sent.append((args, kwargs))
        return object()

    monkeypatch.setattr(
        "app.services.ocr_jobs.celery_app.send_task",
        accept,
    )

    published = await service.publicar(job_id)

    assert published.status == OCRJobStatus.QUEUED.value
    assert len(sent) == 1
    task_name, = sent[0][0]
    assert task_name == "app.workers.ocr_tasks.extraer_metrados_ocr"
    assert sent[0][1]["args"] == [str(job_id)]
    assert sent[0][1]["task_id"] == str(job_id)
    assert source not in repr(sent[0]).encode()


@pytest.mark.asyncio
async def test_ocr_stale_attempt_cannot_complete_after_new_claim(
    db_session, tenant_a_user
):
    tenant, user = tenant_a_user
    service = OCRJobService(db_session, tenant.id)
    job_id = uuid4()
    _, replay = await service.crear(
        user=user,
        job_id=job_id,
        filename="plano.png",
        content_type="image/png",
        storage_path=f"tenant/{tenant.id}/ocr/{job_id}/source.png",
        source_bytes=b"source",
        presupuesto_id=None,
    )

    assert replay is False

    first, token1 = await service.claim(job_id)
    assert first is not None and token1

    # Simula que la lease venció y el reconciliador habilitó un nuevo intento.
    row = await db_session.get(OCRJob, job_id)
    row.status = OCRJobStatus.PENDING.value
    row.claim_token = None
    row.started_at = None
    await db_session.commit()

    second, token2 = await service.claim(job_id)
    assert second is not None and token2 and token2 != token1

    empty_result = ResultadoOCR(
        documento_id=str(job_id),
        total_metrados=0,
        confianza_promedio=0.0,
        metrados=[],
        texto_completo="",
        paginas_procesadas=1,
        errores=[],
    )

    assert await service.completar(job_id, token1, empty_result) is False
    assert await service.completar(job_id, token2, empty_result) is True

    await db_session.refresh(second)
    assert second.status == OCRJobStatus.SUCCEEDED.value
    assert second.attempts == 2


@pytest.mark.asyncio
async def test_ocr_publish_failure_keeps_durable_pending_intent(
    db_session, tenant_a_user, monkeypatch
):
    tenant, user = tenant_a_user
    service = OCRJobService(db_session, tenant.id)
    job_id = uuid4()
    _, replay = await service.crear(
        user=user,
        job_id=job_id,
        filename="plano.pdf",
        content_type="application/pdf",
        storage_path=f"tenant/{tenant.id}/ocr/{job_id}/source.pdf",
        source_bytes=b"%PDF-audit",
        presupuesto_id=None,
    )

    assert replay is False

    def unavailable(*_args, **_kwargs):
        raise ConnectionError("broker down")

    monkeypatch.setattr(
        "app.services.ocr_jobs.celery_app.send_task",
        unavailable,
    )

    with pytest.raises(Exception):
        await service.publicar(job_id)

    row = await db_session.get(OCRJob, job_id)
    await db_session.refresh(row)
    assert row.status == OCRJobStatus.PENDING.value
    assert row.task_id == str(job_id)
    assert row.error_code == "ENQUEUE_FAILED"


@pytest.mark.asyncio
async def test_ocr_idempotency_key_rejects_different_source(
    db_session, tenant_a_user
):
    tenant, user = tenant_a_user
    service = OCRJobService(db_session, tenant.id)
    key = "same-client-request"
    first_id = uuid4()
    first_hash = service.request_hash(
        source_bytes=b"one",
        filename="plano.png",
        presupuesto_id=None,
    )
    first, replay = await service.crear(
        user=user,
        job_id=first_id,
        filename="plano.png",
        content_type="image/png",
        storage_path=f"tenant/{tenant.id}/ocr/{first_id}/source.png",
        source_bytes=b"one",
        presupuesto_id=None,
        idempotency_key=key,
        request_hash=first_hash,
    )
    assert replay is False

    second_hash = service.request_hash(
        source_bytes=b"two",
        filename="plano.png",
        presupuesto_id=None,
    )
    with pytest.raises(Exception):
        await service.recuperar_por_idempotencia(key, second_hash)

    recovered = await service.recuperar_por_idempotencia(key, first_hash)
    assert recovered is not None
    assert recovered.id == first.id


@pytest.mark.asyncio
async def test_ocr_budget_suggestions_persist_provenance_atomically(
    db_session, tenant_a_user
):
    tenant, user = tenant_a_user
    expediente = ExpedienteObra(
        tenant_id=tenant.id,
        creado_por_id=user.id,
        actualizado_por_id=user.id,
        identificador=f"OCR-{uuid4().hex[:10]}",
        titulo="OCR provenance regression",
        organo="CI",
        unidad_administrativa="CI",
        serie_documental="OBRA_PUBLICA",
        subserie_documental="LICITACION",
        responsable_id=user.id,
    )
    db_session.add(expediente)
    await db_session.flush()
    presupuesto = Presupuesto(
        tenant_id=tenant.id,
        creado_por_id=user.id,
        actualizado_por_id=user.id,
        expediente_id=expediente.id,
        identificador=f"OCR-BUD-{uuid4().hex[:8]}",
        nombre="OCR budget",
        factor_indirecto=0,
        factor_utilidad=0,
        factor_impuesto=0,
        monto_directo=0,
        monto_indirecto=0,
        monto_utilidad=0,
        monto_impuesto=0,
        monto_total=0,
    )
    db_session.add(presupuesto)
    await db_session.commit()
    presupuesto_id = presupuesto.id

    service = OCRJobService(db_session, tenant.id)
    job_id = uuid4()
    _, replay = await service.crear(
        user=user,
        job_id=job_id,
        filename="cuantificacion.png",
        content_type="image/png",
        storage_path=f"tenant/{tenant.id}/ocr/{job_id}/source.png",
        source_bytes=b"source",
        presupuesto_id=presupuesto_id,
    )
    assert replay is False
    _, token = await service.claim(job_id)
    assert token

    result = ResultadoOCR(
        documento_id=str(job_id),
        total_metrados=1,
        confianza_promedio=91.0,
        metrados=[
            MetradoExtraido(
                concepto="MURO-01",
                descripcion="Muro de prueba",
                unidad="m2",
                cantidad=12.5,
                confianza=91.0,
                pagina=2,
                bbox=(0, 0, 20, 10),
                texto_original="MURO-01 Muro de prueba 12.5 m2",
            )
        ],
        texto_completo="",
        paginas_procesadas=2,
        errores=[],
    )

    assert await service.completar(job_id, token, result) is True

    partidas = (
        await db_session.scalars(
            select(Partida).where(
                Partida.presupuesto_id == presupuesto_id,
                Partida.tenant_id == tenant.id,
            )
        )
    ).all()
    assert len(partidas) == 1
    assert partidas[0].metadatos["fuente"] == "OCR"
    assert partidas[0].metadatos["confianza"] == 91.0
    assert partidas[0].metadatos["pagina"] == 2
