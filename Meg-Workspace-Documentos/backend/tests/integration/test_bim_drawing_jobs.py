"""Durable BIM drawing request, worker output and source-revision protection."""
from __future__ import annotations

from io import BytesIO
from pathlib import Path
import xml.etree.ElementTree as ET
from contextlib import asynccontextmanager
from datetime import datetime, timezone
from uuid import uuid4

import pytest
from pypdf import PdfReader
from sqlalchemy import event, select

from app.core.errors import ErrorCode, MegalodonException
from app.core.process_queue import ejecutar_trabajo, publicar_pendientes, reintentar_trabajo_dibujo
from app.models.bim import DibujoBIM, ElementoBIM
from app.models.process_job import TrabajoProceso
from app.services.bim_drawing_service import BIMDrawingService
from tests.conftest import engine_test
from tests.integration.test_bim_regressions import model as make_model


VERTICES = [
    0, 0, 0,  2, 0, 0,  2, 1, 0,  0, 1, 0,
    0, 0, 3,  2, 0, 3,  2, 1, 3,  0, 1, 3,
]
FACES = [
    0, 2, 1, 0, 3, 2,
    4, 5, 6, 4, 6, 7,
    0, 1, 5, 0, 5, 4,
    1, 2, 6, 1, 6, 5,
    2, 3, 7, 2, 7, 6,
    3, 0, 4, 3, 4, 7,
]


class MemoryStorage:
    def __init__(self):
        self.objects = {}
        self.uploads = []

    async def subir(self, path, content, **options):
        self.objects[path] = bytes(content)
        self.uploads.append((path, options.get("content_type"), options.get("overwrite")))

    async def descargar(self, path):
        return self.objects[path]

    async def eliminar(self, paths):
        for path in paths:
            self.objects.pop(path, None)


async def completed_model(db_session, tenant, user, *, with_mesh=True):
    expediente, model = await make_model(db_session, tenant, user)
    model.estado_procesamiento = "COMPLETADO"
    model.version_ifc = "IFC4"
    element = ElementoBIM(
        modelo_id=model.id,
        global_id="2xKq-" + uuid4().hex[:18],
        express_id=1,
        tipo="IfcWall",
        nombre="IFC fixture wall",
        area=6,
        volumen=2.4,
        malla_vertices=VERTICES if with_mesh else None,
        malla_caras=FACES if with_mesh else None,
    )
    db_session.add(element)
    await db_session.commit()
    await db_session.refresh(model)
    return expediente, model, element


@pytest.mark.asyncio
async def test_drawing_request_and_durable_job_are_committed_together(db_session, tenant_a_user):
    tenant, user = tenant_a_user
    expediente, model, _ = await completed_model(db_session, tenant, user)

    drawing = await BIMDrawingService(db_session, tenant.id).crear_dibujo(
        expediente_id=expediente.id,
        modelo_id=model.id,
        creado_por_id=user.id,
        tipo="PLAN",
        titulo="Planta nivel 1",
        parametros={"elevacion_m": 1.5},
        formatos=["SVG", "DXF"],
    )

    job = await db_session.scalar(
        select(TrabajoProceso).where(
            TrabajoProceso.tipo == "BIM_DRAWING",
            TrabajoProceso.entidad_id == drawing.id,
            TrabajoProceso.tenant_id == tenant.id,
        )
    )
    persisted = await db_session.get(DibujoBIM, drawing.id)

    assert persisted is not None
    assert persisted.estado == "PENDIENTE"
    assert persisted.source_num_elementos == 1
    assert len(persisted.source_geometry_sha256) == 64
    assert job is not None
    assert job.estado == "PENDIENTE"


@pytest.mark.asyncio
async def test_durable_worker_generates_private_svg_dxf_and_pdf_once(
    db_session, tenant_a_user, monkeypatch
):
    from app.services import bim_drawing_service

    tenant, user = tenant_a_user
    expediente, model, element = await completed_model(db_session, tenant, user)
    expediente.proyecto_nombre = "Proyecto de la prueba"
    await db_session.commit()
    storage = MemoryStorage()
    fixture = Path(__file__).parents[1] / "fixtures" / "ifc" / "wall_millimetres.ifc"
    source = fixture.read_bytes().replace(
        b"ENDSEC;\nEND-ISO-10303-21;",
        b"#999=IFCCARTESIANPOINT((0.,0.,1500.));\n"
        b"#998=IFCAXIS2PLACEMENT3D(#999,$,$);\n"
        b"#997=IFCLOCALPLACEMENT(#28,#998);\n"
        b"#996=IFCBUILDINGSTOREY('0ww2UeVUP0iABYFc9B52Cz',$,'Nivel uno',$,$,#997,$,$,.ELEMENT.,$);\n"
        b"ENDSEC;\nEND-ISO-10303-21;",
    )
    storage.objects[model.ruta_archivo] = source
    monkeypatch.setattr(bim_drawing_service, "storage_bim", lambda: storage)

    drawing = await BIMDrawingService(db_session, tenant.id).crear_dibujo(
        expediente_id=expediente.id,
        modelo_id=model.id,
        creado_por_id=user.id,
        tipo="PLAN",
        titulo="Planta de prueba",
        parametros={
            "elevacion_m": 1.5,
            "cotas_elementos": True,
            "niveles_ifc": True,
            "nota_lamina": "Revisión (obra) · paño",
        },
        formatos=["SVG", "DXF", "PDF"],
    )
    job = await db_session.scalar(
        select(TrabajoProceso).where(TrabajoProceso.entidad_id == drawing.id)
    )

    assert await ejecutar_trabajo(job.id, engine_test) == "COMPLETADO"
    await db_session.refresh(drawing)
    await db_session.refresh(job)

    assert drawing.estado == "COMPLETADO"
    assert job.estado == "COMPLETADO"
    assert drawing.elementos_fuente == drawing.elementos_con_malla == 1
    assert drawing.elementos_sin_malla == 0
    assert drawing.sha256_svg and len(drawing.sha256_svg) == 64
    assert drawing.sha256_dxf and len(drawing.sha256_dxf) == 64
    assert drawing.sha256_pdf and len(drawing.sha256_pdf) == 64
    page = PdfReader(BytesIO(storage.objects[drawing.ruta_pdf])).pages[0]
    assert float(page.mediabox.width) == pytest.approx(420 * 72 / 25.4, abs=0.01)
    assert float(page.mediabox.height) == pytest.approx(297 * 72 / 25.4, abs=0.01)
    assert "Proyecto de la prueba" in page.extract_text()
    assert "Planta de prueba" in page.extract_text()
    assert "Revisión (obra) · paño" in page.extract_text()
    assert "+1.500" in page.extract_text()
    assert drawing.metadatos["niveles_ifc"] == [{"nombre": "Nivel uno", "z_m": 1.5}]
    assert drawing.metadatos["cotas_elementos"] == [
        {"clave": "E01", "global_id": element.global_id, "ancho_m": 2.0, "alto_m": 1.0}
    ]
    assert len(drawing.metadatos["source_ifc_sha256"]) == 64
    assert drawing.ruta_svg in storage.objects
    assert drawing.ruta_dxf in storage.objects
    ET.fromstring(storage.objects[drawing.ruta_svg])
    assert storage.objects[drawing.ruta_dxf].splitlines()[-2:] == [b"0", b"EOF"]
    assert len(storage.uploads) == 3

    assert await ejecutar_trabajo(job.id, engine_test) == "COMPLETADO"
    assert len(storage.uploads) == 3


@pytest.mark.asyncio
async def test_worker_rejects_geometry_changed_after_request_without_uploading(
    db_session, tenant_a_user, monkeypatch
):
    from app.services import bim_drawing_service

    tenant, user = tenant_a_user
    expediente, model, element = await completed_model(db_session, tenant, user)
    storage = MemoryStorage()
    monkeypatch.setattr(bim_drawing_service, "storage_bim", lambda: storage)

    drawing = await BIMDrawingService(db_session, tenant.id).crear_dibujo(
        expediente_id=expediente.id,
        modelo_id=model.id,
        creado_por_id=user.id,
        tipo="PLAN",
        titulo="Planta con geometría versionada",
        parametros={"elevacion_m": 1.5},
        formatos=["SVG", "DXF"],
    )
    job = await db_session.scalar(
        select(TrabajoProceso).where(TrabajoProceso.entidad_id == drawing.id)
    )
    element.malla_vertices = [*VERTICES[:-1], 4]
    await db_session.commit()

    assert await ejecutar_trabajo(job.id, engine_test) == "ERROR"
    await db_session.refresh(drawing)
    await db_session.refresh(job)

    assert drawing.estado == "ERROR"
    assert job.estado == "ERROR"
    assert storage.objects == {}
    assert storage.uploads == []


@pytest.mark.asyncio
async def test_drawing_creation_cannot_cross_tenant_model_boundary(
    db_session, tenant_a_user, tenant_b_user
):
    tenant, user = tenant_a_user
    other_tenant, other_user = tenant_b_user
    expediente, model, _ = await completed_model(db_session, tenant, user)

    with pytest.raises(MegalodonException) as exc:
        await BIMDrawingService(db_session, other_tenant.id).crear_dibujo(
            expediente_id=expediente.id,
            modelo_id=model.id,
            creado_por_id=other_user.id,
            tipo="PLAN",
            titulo="Cross tenant attempt",
            parametros={"elevacion_m": 1.5},
            formatos=["SVG"],
        )

    assert exc.value.status_code == 404



class FailingDrawingStorage(MemoryStorage):
    """Inject upload/delete failures without bypassing the real worker flow."""

    def __init__(self, *, fail_upload_number=2, fail_first_delete=False, fail_all_deletes=False, after_upload=None):
        super().__init__()
        self.upload_attempts = 0
        self.fail_upload_number = fail_upload_number
        self.delete_attempts = 0
        self.fail_first_delete = fail_first_delete
        self.fail_all_deletes = fail_all_deletes
        self.after_upload = after_upload

    async def subir(self, path, content, **options):
        self.upload_attempts += 1
        if self.fail_upload_number is not None and self.upload_attempts == self.fail_upload_number:
            raise MegalodonException(
                ErrorCode.ARCHIVO_ERROR,
                "Injected failure on second drawing artifact upload",
            )
        await super().subir(path, content, **options)
        if self.after_upload is not None:
            self.after_upload()

    async def eliminar(self, paths):
        self.delete_attempts += 1
        if self.fail_all_deletes or (self.fail_first_delete and self.delete_attempts == 1):
            raise MegalodonException(
                ErrorCode.ARCHIVO_ERROR,
                "Injected temporary storage deletion failure",
            )
        await super().eliminar(paths)


async def create_plan_drawing(db_session, tenant, user, expediente, model, *, formats=("SVG", "DXF")):
    drawing = await BIMDrawingService(db_session, tenant.id).crear_dibujo(
        expediente_id=expediente.id,
        modelo_id=model.id,
        creado_por_id=user.id,
        tipo="PLAN",
        titulo="Planta con compensación",
        parametros={"elevacion_m": 1.5},
        formatos=list(formats),
    )
    job = await db_session.scalar(
        select(TrabajoProceso).where(
            TrabajoProceso.tipo == "BIM_DRAWING",
            TrabajoProceso.entidad_id == drawing.id,
        )
    )
    return drawing, job


@pytest.mark.asyncio
async def test_second_artifact_upload_failure_removes_first_uploaded_artifact(
    db_session, tenant_a_user, monkeypatch
):
    from app.services import bim_drawing_service

    tenant, user = tenant_a_user
    expediente, model, _ = await completed_model(db_session, tenant, user)
    storage = FailingDrawingStorage()
    monkeypatch.setattr(bim_drawing_service, "storage_bim", lambda: storage)
    drawing, job = await create_plan_drawing(db_session, tenant, user, expediente, model)

    result = await ejecutar_trabajo(job.id, engine_test)
    await db_session.refresh(drawing)
    await db_session.refresh(job)

    assert result == "PENDIENTE"
    assert drawing.estado == "PENDIENTE"
    assert job.estado == "PENDIENTE"
    assert storage.upload_attempts == 2
    assert storage.delete_attempts == 1
    assert storage.objects == {}


@pytest.mark.asyncio
async def test_failed_compensation_is_recorded_and_blocks_redraw_until_cleanup(
    db_session, tenant_a_user, monkeypatch
):
    from app.services import bim_drawing_service

    tenant, user = tenant_a_user
    expediente, model, _ = await completed_model(db_session, tenant, user)
    storage = FailingDrawingStorage(fail_first_delete=True)
    monkeypatch.setattr(bim_drawing_service, "storage_bim", lambda: storage)
    drawing, original_job = await create_plan_drawing(
        db_session, tenant, user, expediente, model
    )

    result = await ejecutar_trabajo(original_job.id, engine_test)
    await db_session.refresh(original_job)

    assert result == "ESPERA_LIMPIEZA"
    assert original_job.estado == "ESPERA_LIMPIEZA"
    cleanup_job = await db_session.scalar(
        select(TrabajoProceso).where(
            TrabajoProceso.tipo == "BIM_DRAWING_CLEANUP",
            TrabajoProceso.entidad_id == drawing.id,
        )
    )
    assert cleanup_job is not None
    assert cleanup_job.estado == "PENDIENTE"
    assert len(storage.objects) == 1

    assert await ejecutar_trabajo(cleanup_job.id, engine_test) == "COMPLETADO"
    await db_session.refresh(cleanup_job)
    await db_session.refresh(original_job)

    assert cleanup_job.estado == "COMPLETADO"
    assert storage.objects == {}
    assert original_job.estado == "PENDIENTE"


@pytest.mark.asyncio
async def test_database_commit_failure_after_upload_compensates_all_artifacts(
    db_session, tenant_a_user, monkeypatch
):
    from app.services import bim_drawing_service

    tenant, user = tenant_a_user
    expediente, model, _ = await completed_model(db_session, tenant, user)
    should_fail_commit = {"armed": False}

    def fail_one_commit_after_upload(_connection):
        if should_fail_commit["armed"]:
            should_fail_commit["armed"] = False
            raise RuntimeError("Injected database commit failure after drawing upload")

    storage = FailingDrawingStorage(
        fail_upload_number=None,
        after_upload=lambda: should_fail_commit.__setitem__("armed", True),
    )
    monkeypatch.setattr(bim_drawing_service, "storage_bim", lambda: storage)
    drawing, job = await create_plan_drawing(db_session, tenant, user, expediente, model, formats=("SVG", "DXF", "PDF"))

    event.listen(engine_test.sync_engine, "commit", fail_one_commit_after_upload)
    try:
        result = await ejecutar_trabajo(job.id, engine_test)
    finally:
        event.remove(engine_test.sync_engine, "commit", fail_one_commit_after_upload)

    await db_session.refresh(drawing)
    await db_session.refresh(job)

    assert result == "PENDIENTE"
    assert job.estado == "PENDIENTE"
    assert drawing.estado == "PENDIENTE"
    assert storage.upload_attempts == 3
    assert storage.delete_attempts == 1
    assert storage.objects == {}
    assert drawing.ruta_svg is None
    assert drawing.ruta_dxf is None
    assert drawing.ruta_pdf is None



@pytest.mark.asyncio
async def test_ambiguous_commit_acknowledgement_does_not_delete_committed_artifacts(
    db_session, tenant_a_user, monkeypatch
):
    from app.services import bim_drawing_service

    class CommitAcknowledgementLostEngine:
        """Commit to the database, then simulate losing the commit acknowledgement."""

        def __init__(self, wrapped):
            self.wrapped = wrapped
            self.armed = False

        @asynccontextmanager
        async def begin(self):
            async with self.wrapped.begin() as connection:
                yield connection
            if self.armed:
                self.armed = False
                raise RuntimeError("Injected lost acknowledgement after durable commit")

    tenant, user = tenant_a_user
    expediente, model, _ = await completed_model(db_session, tenant, user)
    db_engine = CommitAcknowledgementLostEngine(engine_test)
    storage = FailingDrawingStorage(
        fail_upload_number=None,
        after_upload=lambda: setattr(db_engine, "armed", True),
    )
    monkeypatch.setattr(bim_drawing_service, "storage_bim", lambda: storage)
    drawing, job = await create_plan_drawing(db_session, tenant, user, expediente, model)

    result = await ejecutar_trabajo(job.id, db_engine)
    await db_session.refresh(drawing)
    await db_session.refresh(job)

    assert result == "COMPLETADO"
    assert job.estado == "COMPLETADO"
    assert drawing.estado == "COMPLETADO"
    assert drawing.ruta_svg in storage.objects
    assert drawing.ruta_dxf in storage.objects
    assert storage.delete_attempts == 0
    assert len(storage.objects) == 2


@pytest.mark.asyncio
async def test_cleanup_exhaustion_marks_original_drawing_failed_and_visible(
    db_session, tenant_a_user, monkeypatch
):
    from app.services import bim_drawing_service

    tenant, user = tenant_a_user
    expediente, model, _ = await completed_model(db_session, tenant, user)
    storage = FailingDrawingStorage(fail_all_deletes=True)
    monkeypatch.setattr(bim_drawing_service, "storage_bim", lambda: storage)
    drawing, original_job = await create_plan_drawing(
        db_session, tenant, user, expediente, model
    )

    assert await ejecutar_trabajo(original_job.id, engine_test) == "ESPERA_LIMPIEZA"
    cleanup_job = await db_session.scalar(
        select(TrabajoProceso).where(
            TrabajoProceso.tipo == "BIM_DRAWING_CLEANUP",
            TrabajoProceso.entidad_id == drawing.id,
        )
    )
    assert cleanup_job is not None

    for _ in range(3):
        await ejecutar_trabajo(cleanup_job.id, engine_test)

    await db_session.refresh(drawing)
    await db_session.refresh(original_job)
    await db_session.refresh(cleanup_job)

    assert cleanup_job.estado == "ERROR"
    assert original_job.estado == "ERROR"
    assert drawing.estado == "ERROR"
    assert "limpiar" in (original_job.error or "").lower()
    assert len(storage.objects) == 1





@pytest.mark.asyncio
async def test_manual_retry_after_deterministic_failure_resumes_original_job(
    db_session, tenant_a_user, monkeypatch
):
    from app.services import bim_drawing_service

    tenant, user = tenant_a_user
    expediente, model, _ = await completed_model(db_session, tenant, user)
    storage = FailingDrawingStorage(
        fail_upload_number=None,
        fail_all_deletes=True,
    )
    monkeypatch.setattr(bim_drawing_service, "storage_bim", lambda: storage)

    original_process = BIMDrawingService.procesar_dibujo

    async def fail_deterministically_after_upload(service, drawing):
        await original_process(service, drawing)
        raise MegalodonException(
            ErrorCode.BIM_ERROR,
            "Injected deterministic validation failure after artifact upload",
        )

    monkeypatch.setattr(
        BIMDrawingService, "procesar_dibujo", fail_deterministically_after_upload
    )
    drawing, original_job = await create_plan_drawing(
        db_session, tenant, user, expediente, model
    )

    assert await ejecutar_trabajo(original_job.id, engine_test) == "ESPERA_LIMPIEZA"
    cleanup_job = await db_session.scalar(
        select(TrabajoProceso).where(
            TrabajoProceso.tipo == "BIM_DRAWING_CLEANUP",
            TrabajoProceso.entidad_id == drawing.id,
        )
    )
    assert cleanup_job is not None
    assert cleanup_job.parametros["resume_state"] == "ERROR"

    for _ in range(3):
        await ejecutar_trabajo(cleanup_job.id, engine_test)

    await db_session.refresh(drawing)
    await db_session.refresh(original_job)
    await db_session.refresh(cleanup_job)
    assert cleanup_job.estado == "ERROR"
    assert original_job.estado == "ERROR"
    assert drawing.estado == "ERROR"
    assert original_job.intentos >= 1
    assert len(storage.objects) == 2

    storage.fail_all_deletes = False
    result = await reintentar_trabajo_dibujo(
        db_session,
        trabajo_id=original_job.id,
        tenant_id=tenant.id,
        expediente_id=expediente.id,
        modelo_id=model.id,
    )
    await db_session.commit()
    await db_session.refresh(original_job)
    await db_session.refresh(cleanup_job)
    assert result["estado"] == "ESPERA_LIMPIEZA"
    assert cleanup_job.estado == "PENDIENTE"
    assert cleanup_job.parametros["resume_state"] == "PENDIENTE"
    assert original_job.estado == "ESPERA_LIMPIEZA"
    assert original_job.intentos == 0

    assert await ejecutar_trabajo(cleanup_job.id, engine_test) == "COMPLETADO"
    await db_session.refresh(original_job)
    await db_session.refresh(drawing)
    assert original_job.estado == "PENDIENTE"
    assert original_job.error is None
    assert original_job.intentos == 0
    assert drawing.estado == "PENDIENTE"
    assert drawing.error is None
    assert storage.objects == {}

    monkeypatch.setattr(BIMDrawingService, "procesar_dibujo", original_process)
    assert await ejecutar_trabajo(original_job.id, engine_test) == "COMPLETADO"
    await db_session.refresh(original_job)
    await db_session.refresh(drawing)
    assert original_job.estado == "COMPLETADO"
    assert drawing.estado == "COMPLETADO"
    assert drawing.ruta_svg in storage.objects
    assert drawing.ruta_dxf in storage.objects


@pytest.mark.asyncio
async def test_reconciliation_outage_never_deletes_artifacts_after_ambiguous_commit(
    db_session, tenant_a_user, monkeypatch
):
    from app.services import bim_drawing_service

    class CommitAckLostThenDatabaseUnavailable:
        def __init__(self, wrapped):
            self.wrapped = wrapped
            self.calls = 0
            self.armed = False

        @asynccontextmanager
        async def begin(self):
            self.calls += 1
            if self.calls == 3:
                raise RuntimeError("Injected database outage during state reconciliation")
            async with self.wrapped.begin() as connection:
                yield connection
            if self.calls == 2 and self.armed:
                self.armed = False
                raise RuntimeError("Injected lost acknowledgement after durable commit")

    tenant, user = tenant_a_user
    expediente, model, _ = await completed_model(db_session, tenant, user)
    db_engine = CommitAckLostThenDatabaseUnavailable(engine_test)
    storage = FailingDrawingStorage(
        fail_upload_number=None,
        after_upload=lambda: setattr(db_engine, "armed", True),
    )
    monkeypatch.setattr(bim_drawing_service, "storage_bim", lambda: storage)
    drawing, job = await create_plan_drawing(db_session, tenant, user, expediente, model)

    with pytest.raises(RuntimeError, match="database outage during state reconciliation"):
        await ejecutar_trabajo(job.id, db_engine)

    await db_session.refresh(drawing)
    await db_session.refresh(job)
    assert job.estado == "COMPLETADO"
    assert drawing.estado == "COMPLETADO"
    assert drawing.ruta_svg in storage.objects
    assert drawing.ruta_dxf in storage.objects
    assert storage.delete_attempts == 0
    assert len(storage.objects) == 2


@pytest.mark.asyncio
async def test_manual_drawing_retry_refuses_while_cleanup_is_pending(
    db_session, tenant_a_user, monkeypatch
):
    from app.services import bim_drawing_service

    tenant, user = tenant_a_user
    expediente, model, _ = await completed_model(db_session, tenant, user)
    storage = FailingDrawingStorage(fail_first_delete=True)
    monkeypatch.setattr(bim_drawing_service, "storage_bim", lambda: storage)
    drawing, original_job = await create_plan_drawing(
        db_session, tenant, user, expediente, model
    )

    assert await ejecutar_trabajo(original_job.id, engine_test) == "ESPERA_LIMPIEZA"
    cleanup_job = await db_session.scalar(
        select(TrabajoProceso).where(
            TrabajoProceso.tipo == "BIM_DRAWING_CLEANUP",
            TrabajoProceso.entidad_id == drawing.id,
        )
    )
    assert cleanup_job is not None
    assert cleanup_job.estado == "PENDIENTE"

    with pytest.raises(MegalodonException) as exc:
        await reintentar_trabajo_dibujo(
            db_session,
            trabajo_id=original_job.id,
            tenant_id=tenant.id,
            expediente_id=expediente.id,
            modelo_id=model.id,
        )

    assert exc.value.status_code == 409
    await db_session.refresh(original_job)
    await db_session.refresh(cleanup_job)
    await db_session.refresh(drawing)
    assert original_job.estado == "ESPERA_LIMPIEZA"
    assert cleanup_job.estado == "PENDIENTE"
    assert drawing.estado == "PENDIENTE"
    assert len(storage.objects) == 1


@pytest.mark.parametrize("retry_target", ["drawing", "cleanup"])
@pytest.mark.asyncio
async def test_manual_retry_reconciles_exhausted_drawing_cleanup(
    retry_target, db_session, tenant_a_user, monkeypatch
):
    from app.services import bim_drawing_service

    tenant, user = tenant_a_user
    expediente, model, _ = await completed_model(db_session, tenant, user)
    storage = FailingDrawingStorage(fail_all_deletes=True)
    monkeypatch.setattr(bim_drawing_service, "storage_bim", lambda: storage)
    drawing, original_job = await create_plan_drawing(
        db_session, tenant, user, expediente, model
    )

    assert await ejecutar_trabajo(original_job.id, engine_test) == "ESPERA_LIMPIEZA"
    cleanup_job = await db_session.scalar(
        select(TrabajoProceso).where(
            TrabajoProceso.tipo == "BIM_DRAWING_CLEANUP",
            TrabajoProceso.entidad_id == drawing.id,
        )
    )
    assert cleanup_job is not None

    for _ in range(3):
        await ejecutar_trabajo(cleanup_job.id, engine_test)

    await db_session.refresh(drawing)
    await db_session.refresh(original_job)
    await db_session.refresh(cleanup_job)
    assert cleanup_job.estado == original_job.estado == drawing.estado == "ERROR"
    assert len(storage.objects) == 1

    storage.fail_all_deletes = False
    retry_id = original_job.id if retry_target == "drawing" else cleanup_job.id
    result = await reintentar_trabajo_dibujo(
        db_session,
        trabajo_id=retry_id,
        tenant_id=tenant.id,
        expediente_id=expediente.id,
        modelo_id=model.id,
    )
    await db_session.commit()
    await db_session.refresh(drawing)
    await db_session.refresh(original_job)
    await db_session.refresh(cleanup_job)

    if retry_target == "drawing":
        assert result == {
            "id": str(original_job.id),
            "estado": "ESPERA_LIMPIEZA",
            "trabajo_limpieza_id": str(cleanup_job.id),
        }
    else:
        assert result == {
            "id": str(cleanup_job.id),
            "estado": "PENDIENTE",
            "trabajo_original_id": str(original_job.id),
        }
    assert cleanup_job.estado == "PENDIENTE"
    assert cleanup_job.intentos == 0
    assert original_job.estado == "ESPERA_LIMPIEZA"
    assert drawing.estado == "PENDIENTE"

    assert await ejecutar_trabajo(cleanup_job.id, engine_test) == "COMPLETADO"
    await db_session.refresh(drawing)
    await db_session.refresh(original_job)
    await db_session.refresh(cleanup_job)

    assert cleanup_job.estado == "COMPLETADO"
    assert original_job.estado == "PENDIENTE"
    assert original_job.error is None
    assert drawing.estado == "PENDIENTE"
    assert drawing.error is None
    assert storage.objects == {}


@pytest.mark.asyncio
async def test_cleanup_rejects_paths_outside_the_same_tenant_drawing_prefix(
    db_session, tenant_a_user, monkeypatch
):
    from app.services import bim_drawing_service

    tenant, user = tenant_a_user
    expediente, model, _ = await completed_model(db_session, tenant, user)
    storage = FailingDrawingStorage(fail_first_delete=True)
    monkeypatch.setattr(bim_drawing_service, "storage_bim", lambda: storage)
    drawing, original_job = await create_plan_drawing(
        db_session, tenant, user, expediente, model
    )

    assert await ejecutar_trabajo(original_job.id, engine_test) == "ESPERA_LIMPIEZA"
    cleanup_job = await db_session.scalar(
        select(TrabajoProceso).where(
            TrabajoProceso.tipo == "BIM_DRAWING_CLEANUP",
            TrabajoProceso.entidad_id == drawing.id,
        )
    )
    assert cleanup_job is not None
    expected_objects = set(storage.objects)
    cleanup_job.parametros = {
        **cleanup_job.parametros,
        "paths": ["tenant/another-tenant/foreign-project/drawings/foreign/drawing.svg"],
    }
    await db_session.commit()

    assert await ejecutar_trabajo(cleanup_job.id, engine_test) == "ERROR"
    await db_session.refresh(cleanup_job)
    await db_session.refresh(original_job)
    await db_session.refresh(drawing)

    assert cleanup_job.estado == "ERROR"
    assert original_job.estado == "ERROR"
    assert drawing.estado == "ERROR"
    assert set(storage.objects) == expected_objects
    assert storage.delete_attempts == 1


@pytest.mark.asyncio
async def test_dispatcher_reconciles_artifacts_after_worker_disappears(
    db_session, tenant_a_user, monkeypatch
):
    from app.services import bim_drawing_service

    tenant, user = tenant_a_user
    expediente, model, _ = await completed_model(db_session, tenant, user)
    storage = MemoryStorage()
    monkeypatch.setattr(bim_drawing_service, "storage_bim", lambda: storage)
    drawing, original_job = await create_plan_drawing(
        db_session, tenant, user, expediente, model, formats=("SVG", "DXF", "PDF")
    )

    prefix = (
        f"tenant/{tenant.id}/{expediente.id}/{model.id}/drawings/{drawing.id}"
    )
    orphan_path = f"{prefix}/drawing.pdf"
    storage.objects[orphan_path] = b"%PDF-partial output from killed worker"
    original_job.estado = "EJECUTANDO"
    original_job.intentos = 3
    # The suite shares a queue. This expired lease must precede unrelated pending jobs.
    original_job.proxima_publicacion = datetime(2000, 1, 1, tzinfo=timezone.utc)
    original_job.id_ejecucion = uuid4()
    await db_session.commit()

    published = await publicar_pendientes(engine_test, enviar=lambda _job_id: None, limite=1)
    await db_session.refresh(original_job)

    cleanup_job = await db_session.scalar(
        select(TrabajoProceso).where(
            TrabajoProceso.tipo == "BIM_DRAWING_CLEANUP",
            TrabajoProceso.entidad_id == drawing.id,
        )
    )
    assert published == 0
    assert original_job.estado == "ESPERA_LIMPIEZA"
    assert cleanup_job is not None
    assert cleanup_job.estado == "PENDIENTE"
    assert orphan_path in storage.objects

    assert await ejecutar_trabajo(cleanup_job.id, engine_test) == "COMPLETADO"
    await db_session.refresh(original_job)
    await db_session.refresh(drawing)

    assert original_job.estado == "ERROR"
    assert drawing.estado == "ERROR"
    assert storage.objects == {}
