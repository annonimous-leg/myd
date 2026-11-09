"""Durable public job boundary: rollback, redelivery and real domain effects."""
from datetime import datetime, timezone
from uuid import uuid4

import pytest
from sqlalchemy import select

from app.core.process_queue import registrar_trabajo, ejecutar_trabajo, publicar_pendientes
from app.models.process_job import TrabajoProceso
from app.models.bim import ElementoBIM, GeneracionBIM4D5D
from app.models.programacion import ProgramaObra
from tests.conftest import engine_test
from tests.integration.test_bim_regressions import model


@pytest.mark.asyncio
async def test_killed_executor_consumes_attempt_and_recovers_without_duplicate(db_session, tenant_a_user):
    import asyncio
    import os
    import subprocess
    import sys
    tenant, user = tenant_a_user
    exp, obj = await model(db_session, tenant, user)
    db_session.add(ElementoBIM(modelo_id=obj.id, global_id=uuid4().hex,
        express_id=1, tipo='IfcWall', area=16, volumen=2, longitud=4))
    gen = GeneracionBIM4D5D(id=uuid4(), tenant_id=tenant.id,
        modelo_id=obj.id, expediente_id=exp.id, dias_por_defecto=5, creado_por_id=user.id)
    db_session.add(gen)
    job = registrar_trabajo(db_session, gen, 'BIM_4D', {
        'fecha_inicio_iso':'2026-10-06T00:00:00+00:00','dias_por_defecto':5})
    job_id, exp_id = job.id, exp.id
    await db_session.commit()
    # Kill a separate process during domain execution, after its durable start.
    code = '''import asyncio, os, signal
import app.models
from app.core import process_queue
async def crash(*args):
    os.kill(os.getpid(), signal.SIGKILL)
process_queue._procesar = crash
asyncio.run(process_queue.ejecutar_trabajo(os.environ['CRASH_JOB_ID']))
'''
    result = await asyncio.to_thread(subprocess.run, [sys.executable,'-c',code],
        env=dict(os.environ,CRASH_JOB_ID=str(job_id),
                 DATABASE_URL=engine_test.url.render_as_string(hide_password=False)),
        capture_output=True,timeout=20)
    assert result.returncode == -9
    db_session.expire_all()
    job = await db_session.get(TrabajoProceso,job_id)
    assert job.intentos == 1 and job.estado == 'EJECUTANDO'
    assert not list(await db_session.scalars(select(ProgramaObra).where(ProgramaObra.expediente_id == exp_id)))
    job.proxima_publicacion = datetime.now(timezone.utc)
    await db_session.commit()
    assert await ejecutar_trabajo(job_id,engine_test) == 'COMPLETADO'
    db_session.expire_all()
    assert (await db_session.get(TrabajoProceso,job_id)).intentos == 2
    assert len(list(await db_session.scalars(select(ProgramaObra).where(ProgramaObra.expediente_id == exp_id)))) == 1


@pytest.mark.asyncio
async def test_job_and_generation_rollback_together(db_session, tenant_a_user):
    tenant, user = tenant_a_user
    exp, obj = await model(db_session, tenant, user)
    generation = GeneracionBIM4D5D(id=uuid4(), tenant_id=tenant.id,
        modelo_id=obj.id, expediente_id=exp.id, dias_por_defecto=5, creado_por_id=user.id)
    db_session.add(generation)
    job = registrar_trabajo(db_session, generation, 'BIM_4D', {
        'modelo_id':str(obj.id), 'expediente_id':str(exp.id),
        'fecha_inicio_iso':'2026-10-06T00:00:00+00:00', 'dias_por_defecto':5})
    job_id, generation_id = job.id, generation.id
    await db_session.flush()
    await db_session.rollback()
    assert await db_session.get(TrabajoProceso, job_id) is None
    assert await db_session.get(GeneracionBIM4D5D, generation_id) is None


@pytest.mark.asyncio
async def test_redelivery_creates_exactly_one_real_program(db_session, tenant_a_user):
    tenant, user = tenant_a_user
    exp, obj = await model(db_session, tenant, user)
    db_session.add(ElementoBIM(modelo_id=obj.id, global_id=uuid4().hex,
        express_id=1, tipo='IfcWall', area=16, volumen=2, longitud=4, nivel='PB'))
    gen = GeneracionBIM4D5D(id=uuid4(), tenant_id=tenant.id,
        modelo_id=obj.id, expediente_id=exp.id, dias_por_defecto=5, creado_por_id=user.id)
    db_session.add(gen)
    job = registrar_trabajo(db_session, gen, 'BIM_4D', {
        'modelo_id':str(obj.id), 'expediente_id':str(exp.id),
        'fecha_inicio_iso':'2026-10-06T00:00:00+00:00', 'dias_por_defecto':5})
    job_id, gen_id, exp_id = job.id, gen.id, exp.id
    await db_session.commit()
    if engine_test.dialect.name == 'postgresql':
        import asyncio
        # Independent connections execute duplicate deliveries concurrently.
        results = await asyncio.gather(ejecutar_trabajo(job_id, engine_test),
            ejecutar_trabajo(job_id, engine_test))
        assert 'COMPLETADO' in results
        assert set(results) <= {'COMPLETADO', 'EN_PROCESO'}
    else:
        assert await ejecutar_trabajo(job_id, engine_test) == 'COMPLETADO'
        assert await ejecutar_trabajo(job_id, engine_test) == 'COMPLETADO'
    db_session.expire_all()
    generation = await db_session.get(GeneracionBIM4D5D, gen_id)
    assert generation.estado == 'COMPLETADO'
    assert (await db_session.get(TrabajoProceso, job_id)).estado == 'COMPLETADO'
    programs = (await db_session.scalars(select(ProgramaObra).where(
        ProgramaObra.expediente_id == exp_id))).all()
    assert len(programs) == 1
    assert generation.programa_id == programs[0].id


@pytest.mark.asyncio
async def test_broker_failure_retains_work_for_later_publication(db_session, tenant_a_user):
    tenant, user = tenant_a_user
    exp, obj = await model(db_session, tenant, user)
    job = registrar_trabajo(db_session, obj, 'BIM_IFC', {'extraer_malla':True})
    job_id = job.id
    await db_session.commit()
    def unavailable(job_id):
        raise ConnectionError('Broker is temporarily unavailable')
    await publicar_pendientes(engine_test, enviar=unavailable)
    await db_session.refresh(job)
    assert job.estado == 'PENDIENTE'
    assert job.error_publicacion
    # Advancing the due date models passage of time, without blocking sleeps.
    job.proxima_publicacion = datetime.now(timezone.utc)
    await db_session.commit()
    delivered = []
    await publicar_pendientes(engine_test, enviar=delivered.append)
    assert str(job_id) in delivered
    await db_session.refresh(job)
    assert job.estado == 'ENVIADO'


@pytest.mark.asyncio
async def test_real_ifc_file_survives_new_executor_and_redelivery(db_session, tenant_a_user, tmp_path, monkeypatch):
    from pathlib import Path
    from app.config import settings
    from app.services.bim_service import BIMService
    from app.models.bim import ModeloBIM
    monkeypatch.setattr(settings, 'BIM_STORAGE_PROVIDER', 'filesystem')
    monkeypatch.setattr(settings, 'BIM_LOCAL_STORAGE_PATH', str(tmp_path))
    tenant, user = tenant_a_user
    exp, _ = await model(db_session, tenant, user)
    content = (Path(__file__).parents[1] / 'fixtures/ifc/wall_millimetres.ifc').read_bytes()
    uploaded = await BIMService(db_session, tenant.id).crear_modelo(
        expediente_id=exp.id, nombre='Physical wall', file_content=content, filename='wall.ifc')
    job = await db_session.scalar(select(TrabajoProceso).where(TrabajoProceso.entidad_id == uploaded.id))
    job_id, model_id = job.id, uploaded.id
    await db_session.commit()
    assert await ejecutar_trabajo(job_id, engine_test) == 'COMPLETADO'
    assert await ejecutar_trabajo(job_id, engine_test) == 'COMPLETADO'
    db_session.expire_all()
    assert (await db_session.get(ModeloBIM, model_id)).num_elementos == 1
    elements = (await db_session.scalars(select(ElementoBIM).where(ElementoBIM.modelo_id == model_id))).all()
    assert len(elements) == 1
    assert float(elements[0].volumen) == pytest.approx(2.4)
    assert elements[0].malla_vertices


@pytest.mark.asyncio
async def test_failed_completion_rolls_back_program_and_all_service_commits(db_session, tenant_a_user):
    from sqlalchemy import text
    if engine_test.dialect.name != 'sqlite':
        pytest.skip('SQLite failure injection; PostgreSQL locks covered separately')
    tenant, user = tenant_a_user
    exp, obj = await model(db_session, tenant, user)
    db_session.add(ElementoBIM(modelo_id=obj.id, global_id=uuid4().hex,
        express_id=1, tipo='IfcWall', area=16, volumen=2, longitud=4))
    gen = GeneracionBIM4D5D(id=uuid4(), tenant_id=tenant.id,
        modelo_id=obj.id, expediente_id=exp.id, dias_por_defecto=5, creado_por_id=user.id)
    db_session.add(gen)
    job = registrar_trabajo(db_session, gen, 'BIM_4D', {
        'fecha_inicio_iso':'2026-10-06T00:00:00+00:00', 'dias_por_defecto':5})
    job_id, exp_id = job.id, exp.id
    await db_session.commit()
    await db_session.execute(text("CREATE TRIGGER reject_job_finish BEFORE UPDATE ON trabajos_proceso "
        "WHEN NEW.estado='COMPLETADO' BEGIN SELECT RAISE(ABORT, 'Injected finish failure'); END"))
    await db_session.commit()
    try:
        assert await ejecutar_trabajo(job_id, engine_test) == 'PENDIENTE'
        assert list(await db_session.scalars(select(ProgramaObra).where(ProgramaObra.expediente_id == exp_id))) == []
        await db_session.commit()
    finally:
        await db_session.execute(text('DROP TRIGGER reject_job_finish'))
        await db_session.commit()
    assert await ejecutar_trabajo(job_id, engine_test) == 'COMPLETADO'
    assert len(list(await db_session.scalars(select(ProgramaObra).where(ProgramaObra.expediente_id == exp_id)))) == 1


@pytest.mark.asyncio
async def test_expired_worker_is_bounded_and_visible(db_session, tenant_a_user):
    tenant, user = tenant_a_user
    exp, obj = await model(db_session, tenant, user)
    job = registrar_trabajo(db_session, obj, 'BIM_IFC', {})
    job.estado = 'EJECUTANDO'
    job.intentos = 3
    job.proxima_publicacion = datetime.now(timezone.utc)
    await db_session.commit()
    delivered = []
    await publicar_pendientes(engine_test, enviar=delivered.append)
    await db_session.refresh(job)
    await db_session.refresh(obj)
    assert str(job.id) not in delivered
    assert job.estado == obj.estado_procesamiento == 'ERROR'
    assert 'agotaron' in job.error


@pytest.mark.asyncio
async def test_local_original_download_is_authenticated_and_tenant_scoped(async_client, db_session,
    tenant_a_user, tenant_b_user, auth_headers, tmp_path, monkeypatch):
    from app.config import settings
    from app.services.bim_service import BIMService
    from tests.conftest import _login
    monkeypatch.setattr(settings, 'BIM_STORAGE_PROVIDER', 'filesystem')
    monkeypatch.setattr(settings, 'BIM_LOCAL_STORAGE_PATH', str(tmp_path))
    tenant, user = tenant_a_user
    exp, _ = await model(db_session, tenant, user)
    original = b'ISO-10303-21; real stored bytes'
    uploaded = await BIMService(db_session, tenant.id).crear_modelo(
        expediente_id=exp.id, nombre='Original', file_content=original, filename='original.ifc')
    path = f'/api/v1/bim/{exp.id}/modelos/{uploaded.id}'
    download = await async_client.get(path+'/descarga', headers=auth_headers)
    assert download.status_code == 200
    file = await async_client.get(download.json()['url'], headers=auth_headers)
    assert file.status_code == 200 and file.content == original
    assert download.json()['expira_en_segundos'] == 0
    other_headers = await _login(async_client, tenant_b_user[1].email)
    assert (await async_client.get(path+'/archivo', headers=other_headers)).status_code == 404


@pytest.mark.asyncio
async def test_generation_without_actor_cannot_create_program(db_session, tenant_a_user):
    tenant, user = tenant_a_user
    exp, obj = await model(db_session, tenant, user)
    db_session.add(ElementoBIM(modelo_id=obj.id, global_id=uuid4().hex,
        express_id=1, tipo='IfcWall', area=16, volumen=2, longitud=4))
    gen = GeneracionBIM4D5D(id=uuid4(), tenant_id=tenant.id,
        modelo_id=obj.id, expediente_id=exp.id, dias_por_defecto=5)
    db_session.add(gen)
    job = registrar_trabajo(db_session, gen, 'BIM_4D', {
        'fecha_inicio_iso': '2026-10-06T00:00:00+00:00', 'dias_por_defecto': 5})
    job_id, exp_id = job.id, exp.id
    await db_session.commit()
    assert await ejecutar_trabajo(job_id, engine_test) == 'ERROR'
    assert not list(await db_session.scalars(select(ProgramaObra).where(
        ProgramaObra.expediente_id == exp_id)))
