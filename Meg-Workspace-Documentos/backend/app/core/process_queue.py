"""Durable delivery and atomic BIM results, safe against repeated messages.

Services commit savepoints inside the executor's outer transaction. Domain
results and job completion become visible together, including 4D creation.
"""
import asyncio
import logging
from datetime import datetime, timedelta, timezone
from uuid import UUID, uuid4
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from app.config import settings
from app.core.errors import MegalodonException, ErrorCode
from app.models.base import engine
from app.models.bim import ModeloBIM, GeneracionBIM4D5D, AnalisisClash, DibujoBIM
from app.models.process_job import TrabajoProceso

logger = logging.getLogger(__name__)
MAX_INTENTOS = 3
PLAZO_ENTREGA = 2400  # longer than the 30-minute worker hard limit
ENTIDADES = {'BIM_IFC': (ModeloBIM, 'estado_procesamiento', 'error_procesamiento'),
             'BIM_4D': (GeneracionBIM4D5D, 'estado', 'error'),
             'BIM_CLASH': (AnalisisClash, 'estado', 'error'),
             'BIM_DRAWING': (DibujoBIM, 'estado', 'error'),
             'BIM_DRAWING_CLEANUP': (DibujoBIM, 'estado', 'error')}


def registrar_trabajo(db, registro, tipo, parametros):
    """Add the intent to the caller's transaction; never commit here."""
    if tipo not in ENTIDADES:
        raise ValueError('Tipo de trabajo no permitido')
    job = TrabajoProceso(id=uuid4(), tenant_id=registro.tenant_id,
        entidad_id=registro.id, tipo=tipo, parametros=parametros,
        estado='PENDIENTE', intentos=0, proxima_publicacion=datetime.now(timezone.utc))
    db.add(job)
    return job


def _enviar(job_id, tipo):
    from app.workers.process_tasks import ejecutar_proceso

    options = {}
    if tipo == "BIM_IFC":
        options["time_limit"] = settings.IFC_PROCESSING_TIMEOUT_SECONDS
        if settings.IFC_DEDICATED_QUEUE:
            options["queue"] = "megalodon-ifc"
    ejecutar_proceso.apply_async(kwargs={"trabajo_id": job_id}, task_id=job_id, retry=False, **options)


async def publicar_pendientes(db_engine=engine, *, enviar=None, limite=20):
    """Publish due/expired deliveries independently of Redis availability."""
    enviados = 0
    for _ in range(limite):
        async with db_engine.begin() as connection:
            if connection.dialect.name == 'sqlite':
                await connection.exec_driver_sql('BEGIN IMMEDIATE')
            async with AsyncSession(bind=connection, expire_on_commit=False) as db:
                now = datetime.now(timezone.utc)
                job = await db.scalar(select(TrabajoProceso).where(
                    TrabajoProceso.estado.in_(['PENDIENTE', 'ENVIADO', 'EJECUTANDO']),
                    TrabajoProceso.proxima_publicacion <= now
                ).order_by(TrabajoProceso.proxima_publicacion).limit(1)
                  .with_for_update(skip_locked=True))
                if job is None:
                    break
                if job.intentos >= MAX_INTENTOS:
                    job.error = 'Se agotaron los intentos de procesamiento. Revisa el archivo y vuelve a intentar.'
                    try:
                        entity, state_field, error_field = await _entidad(db, job)
                    except MegalodonException:
                        job.estado = 'ERROR'
                        logger.warning('process_entity_deleted', extra={'job_id':str(job.id)})
                    else:
                        if job.tipo == 'BIM_DRAWING':
                            # A worker may be killed after writing one or more
                            # remote objects. Exhaustion must reconcile those
                            # deterministic paths before exposing terminal error.
                            job.estado = 'ESPERA_LIMPIEZA'
                            await _schedule_drawing_cleanup(
                                db, entity, job, _drawing_artifact_paths(entity), 'ERROR'
                            )
                            setattr(entity, state_field, 'PENDIENTE')
                            setattr(entity, error_field, 'Limpieza de artefactos pendiente.')
                        elif job.tipo == 'BIM_DRAWING_CLEANUP':
                            job.estado = 'ERROR'
                            setattr(entity, state_field, 'ERROR')
                            setattr(entity, error_field, job.error)
                            try:
                                original_id = UUID(str((job.parametros or {})['original_job_id']))
                            except (KeyError, TypeError, ValueError):
                                logger.error('drawing_cleanup_missing_original_job', extra={'job_id': str(job.id)})
                            else:
                                original = await db.scalar(
                                    select(TrabajoProceso).where(
                                        TrabajoProceso.id == original_id,
                                        TrabajoProceso.tenant_id == job.tenant_id,
                                        TrabajoProceso.entidad_id == job.entidad_id,
                                        TrabajoProceso.tipo == 'BIM_DRAWING',
                                    ).with_for_update()
                                )
                                if original is not None and original.estado == 'ESPERA_LIMPIEZA':
                                    original.estado = 'ERROR'
                                    original.error = 'No se pudo limpiar el almacenamiento después de varios intentos.'
                                    original.proxima_publicacion = now
                        else:
                            job.estado = 'ERROR'
                            setattr(entity, state_field, 'ERROR')
                            setattr(entity, error_field, job.error)
                    await db.flush()
                    continue
                try:
                    if enviar is None:
                        await asyncio.to_thread(_enviar, str(job.id), job.tipo)
                    else:
                        await asyncio.to_thread(enviar, str(job.id))
                except Exception:
                    job.error_publicacion = 'Esperando conexión con el servicio de procesamiento'
                    job.proxima_publicacion = now + timedelta(seconds=15)
                    logger.warning('process_publish_unavailable', extra={'job_id':str(job.id)})
                else:
                    job.estado = 'ENVIADO'
                    job.error_publicacion = None
                    job.proxima_publicacion = now + timedelta(seconds=PLAZO_ENTREGA)
                    enviados += 1
                await db.flush()
    return enviados


async def _entidad(db, job):
    cls, state_field, error_field = ENTIDADES[job.tipo]
    entity = await db.scalar(select(cls).where(cls.id == job.entidad_id,
        cls.tenant_id == job.tenant_id).with_for_update())
    if entity is None:
        raise MegalodonException(ErrorCode.DOCUMENTO_NO_ENCONTRADO,
            'El registro de este trabajo ya no existe', status_code=404)
    return entity, state_field, error_field


async def _procesar(db, job, entity):
    params = job.parametros or {}
    if job.tipo == 'BIM_DRAWING_CLEANUP':
        from app.services.bim_drawing_service import storage_bim
        expected_paths = _drawing_artifact_paths(entity)
        paths = params.get('paths')
        if (
            not isinstance(paths, list)
            or not all(isinstance(path, str) for path in paths)
            or len(paths) != len(set(paths))
            or set(paths) != set(expected_paths)
        ):
            raise MegalodonException(
                ErrorCode.BIM_ERROR,
                "El trabajo de limpieza no coincide con las rutas privadas del dibujo",
            )
        if paths:
            await storage_bim().eliminar(paths)
        return

    from app.services.bim_service import BIMService
    service = BIMService(db, job.tenant_id)
    if job.tipo == 'BIM_IFC':
        from app.integrations.supabase_storage import storage_bim
        content = await storage_bim().descargar(entity.ruta_archivo)
        await service.procesar_ifc(modelo_id=entity.id, file_content=content,
            tipos_elementos=params.get('tipos_elementos'), extraer_malla=params.get('extraer_malla', True))
    elif job.tipo == 'BIM_DRAWING':
        from app.services.bim_drawing_service import BIMDrawingService
        await BIMDrawingService(db, job.tenant_id).procesar_dibujo(entity)
    elif job.tipo == 'BIM_4D':
        from sqlalchemy import func
        from app.models.programacion import ActividadPrograma
        program = await service.generar_actividades_4d(modelo_id=entity.modelo_id,
            expediente_id=entity.expediente_id,
            fecha_inicio=datetime.fromisoformat(params['fecha_inicio_iso']),
            dias_por_defecto=params['dias_por_defecto'],
            creado_por_id=entity.creado_por_id, tenant_id=job.tenant_id)
        entity.programa_id = program.id
        entity.num_actividades_generadas = await db.scalar(select(func.count()).where(
            ActividadPrograma.programa_id == program.id))
    else:
        from app.services.clash_service import ClashService
        await ClashService(db, job.tenant_id).ejecutar_analisis_worker(entity.id)




def _drawing_artifact_paths(drawing):
    """Return deterministic private output keys for one drawing aggregate."""
    prefix = (
        f"tenant/{drawing.tenant_id}/{drawing.expediente_id}/{drawing.modelo_id}"
        f"/drawings/{drawing.id}"
    )
    formats = set(drawing.formatos or [])
    paths = []
    if "SVG" in formats:
        paths.append(f"{prefix}/drawing.svg")
    if "DXF" in formats:
        paths.append(f"{prefix}/drawing.dxf")
    if "PDF" in formats:
        paths.append(f"{prefix}/drawing.pdf")
    return paths


async def _schedule_drawing_cleanup(db, drawing, original_job, paths, resume_state):
    """Create or reactivate the unique durable cleanup job for a drawing."""
    now = datetime.now(timezone.utc)
    cleanup = await db.scalar(
        select(TrabajoProceso)
        .where(
            TrabajoProceso.tipo == "BIM_DRAWING_CLEANUP",
            TrabajoProceso.entidad_id == drawing.id,
            TrabajoProceso.tenant_id == drawing.tenant_id,
        )
        .with_for_update()
    )
    parameters = {
        "paths": list(paths),
        "original_job_id": str(original_job.id),
        "resume_state": resume_state,
    }
    if cleanup is None:
        registrar_trabajo(db, drawing, "BIM_DRAWING_CLEANUP", parameters)
        return

    cleanup.parametros = parameters
    cleanup.estado = "PENDIENTE"
    cleanup.intentos = 0
    cleanup.proxima_publicacion = now
    cleanup.error = None
    cleanup.error_publicacion = None
    cleanup.id_ejecucion = None


async def _finish_drawing_cleanup(db, cleanup_job, drawing):
    """Resume the original delivery only after its deterministic outputs are removed."""
    parameters = cleanup_job.parametros or {}
    try:
        original_id = UUID(str(parameters["original_job_id"]))
    except (KeyError, TypeError, ValueError):
        raise MegalodonException(
            ErrorCode.BIM_ERROR, "Trabajo de limpieza sin referencia al trabajo original"
        )
    original = await db.scalar(
        select(TrabajoProceso).where(
            TrabajoProceso.id == original_id,
            TrabajoProceso.tenant_id == cleanup_job.tenant_id,
            TrabajoProceso.entidad_id == cleanup_job.entidad_id,
            TrabajoProceso.tipo == "BIM_DRAWING",
        ).with_for_update()
    )
    if original is None or original.estado != "ESPERA_LIMPIEZA":
        return

    resume_state = parameters.get("resume_state")
    if resume_state not in {"PENDIENTE", "ERROR"}:
        raise MegalodonException(ErrorCode.BIM_ERROR, "Estado de reanudación de dibujo inválido")
    original.estado = resume_state
    original.proxima_publicacion = (
        datetime.now(timezone.utc) + timedelta(seconds=15 * original.intentos)
        if resume_state == "PENDIENTE"
        else datetime.now(timezone.utc)
    )
    original.id_ejecucion = None
    original.error = (
        None if resume_state == "PENDIENTE"
        else original.error or "No se pudo completar la generación del dibujo."
    )
    drawing.estado = resume_state
    drawing.error = (
        None if resume_state == "PENDIENTE"
        else original.error
    )


async def reintentar_trabajo_dibujo(
    db, *, trabajo_id, tenant_id, expediente_id, modelo_id
):
    """Retry a drawing only when no cleanup owns its deterministic artifacts.

    Cleanup retry lock order is cleanup job -> drawing row -> original job,
    matching the worker's order and avoiding a cleanup/retry deadlock.
    The caller owns the transaction and must commit the state transition.
    """
    candidate = await db.scalar(
        select(TrabajoProceso).where(
            TrabajoProceso.id == trabajo_id,
            TrabajoProceso.tenant_id == tenant_id,
            TrabajoProceso.tipo.in_(["BIM_DRAWING", "BIM_DRAWING_CLEANUP"]),
        )
    )
    if candidate is None:
        raise MegalodonException(
            ErrorCode.DOCUMENTO_NO_ENCONTRADO, "Trabajo no encontrado", status_code=404
        )

    async def validar_alcance(drawing):
        if drawing.modelo_id != modelo_id or drawing.expediente_id != expediente_id:
            raise MegalodonException(
                ErrorCode.DOCUMENTO_NO_ENCONTRADO, "Trabajo no encontrado", status_code=404
            )
        from app.services.bim_service import BIMService
        await BIMService(db, tenant_id)._validar_modelo_en_expediente(
            modelo_id, expediente_id
        )

    async def reactivar_limpieza(cleanup_id, *, respuesta_solicitada):
        cleanup = await db.scalar(
            select(TrabajoProceso).where(
                TrabajoProceso.id == cleanup_id,
                TrabajoProceso.tenant_id == tenant_id,
                TrabajoProceso.entidad_id == candidate.entidad_id,
                TrabajoProceso.tipo == "BIM_DRAWING_CLEANUP",
            ).with_for_update()
        )
        if cleanup is None or cleanup.estado != "ERROR":
            raise MegalodonException(
                ErrorCode.BIM_ERROR,
                "La limpieza no está en estado ERROR para reintentarse",
                status_code=409,
            )

        drawing, state_field, error_field = await _entidad(db, cleanup)
        await validar_alcance(drawing)
        parameters = cleanup.parametros or {}
        try:
            original_id = UUID(str(parameters["original_job_id"]))
        except (KeyError, TypeError, ValueError):
            raise MegalodonException(
                ErrorCode.BIM_ERROR, "Trabajo de limpieza sin referencia válida al dibujo"
            )
        resume_state = parameters.get("resume_state")
        if resume_state not in {"PENDIENTE", "ERROR"}:
            raise MegalodonException(
                ErrorCode.BIM_ERROR, "Estado de reanudación de limpieza inválido"
            )
        if respuesta_solicitada == "BIM_DRAWING":
            # Retrying the drawing is a new delivery intent, not merely a
            # request to clean old files. The original deterministic failure
            # must not be restored after cleanup, and its exhausted attempts
            # must not immediately exhaust the newly requested delivery.
            parameters = dict(parameters)
            parameters["resume_state"] = "PENDIENTE"
            cleanup.parametros = parameters
            resume_state = "PENDIENTE"

        original = await db.scalar(
            select(TrabajoProceso).where(
                TrabajoProceso.id == original_id,
                TrabajoProceso.tenant_id == tenant_id,
                TrabajoProceso.entidad_id == drawing.id,
                TrabajoProceso.tipo == "BIM_DRAWING",
            ).with_for_update()
        )
        if original is None:
            raise MegalodonException(
                ErrorCode.DOCUMENTO_NO_ENCONTRADO,
                "Trabajo original del dibujo no encontrado",
                status_code=404,
            )
        if original.estado not in {"ERROR", "ESPERA_LIMPIEZA"}:
            raise MegalodonException(
                ErrorCode.BIM_ERROR,
                "El trabajo original no está esperando limpieza ni requiere recuperación",
                status_code=409,
            )

        now = datetime.now(timezone.utc)
        cleanup.estado = "PENDIENTE"
        cleanup.intentos = 0
        cleanup.proxima_publicacion = now
        cleanup.error = None
        cleanup.error_publicacion = None
        cleanup.id_ejecucion = None
        original.estado = "ESPERA_LIMPIEZA"
        if respuesta_solicitada == "BIM_DRAWING":
            original.intentos = 0
            original.error = "Limpieza de artefactos pendiente antes de reintentar el dibujo."
            original.error_publicacion = None
        original.proxima_publicacion = now
        original.id_ejecucion = None
        setattr(drawing, state_field, "PENDIENTE")
        setattr(drawing, error_field, "Limpieza de artefactos pendiente.")

        if respuesta_solicitada == "BIM_DRAWING":
            return {
                "id": str(original.id),
                "estado": original.estado,
                "trabajo_limpieza_id": str(cleanup.id),
            }
        return {
            "id": str(cleanup.id),
            "estado": cleanup.estado,
            "trabajo_original_id": str(original.id),
        }

    if candidate.tipo == "BIM_DRAWING_CLEANUP":
        # This path deliberately locks cleanup before drawing and original job.
        return await reactivar_limpieza(
            candidate.id, respuesta_solicitada="BIM_DRAWING_CLEANUP"
        )

    # A drawing retry must not race ahead of a pending/running cleanup.
    cleanup_candidate = await db.scalar(
        select(TrabajoProceso).where(
            TrabajoProceso.tipo == "BIM_DRAWING_CLEANUP",
            TrabajoProceso.entidad_id == candidate.entidad_id,
            TrabajoProceso.tenant_id == tenant_id,
        )
    )
    if cleanup_candidate is not None and cleanup_candidate.estado == "ERROR":
        return await reactivar_limpieza(
            cleanup_candidate.id, respuesta_solicitada="BIM_DRAWING"
        )
    if cleanup_candidate is not None and cleanup_candidate.estado != "COMPLETADO":
        raise MegalodonException(
            ErrorCode.BIM_ERROR,
            "La limpieza de artefactos sigue pendiente; no se puede regenerar el dibujo",
            status_code=409,
        )

    # No active cleanup exists. Keep the normal execution lock order: drawing job -> drawing row.
    job = await db.scalar(
        select(TrabajoProceso).where(
            TrabajoProceso.id == trabajo_id,
            TrabajoProceso.tenant_id == tenant_id,
            TrabajoProceso.tipo == "BIM_DRAWING",
        ).with_for_update()
    )
    if job is None:
        raise MegalodonException(
            ErrorCode.DOCUMENTO_NO_ENCONTRADO, "Trabajo no encontrado", status_code=404
        )
    if job.estado != "ERROR":
        raise MegalodonException(
            ErrorCode.BIM_ERROR,
            "Este trabajo ya está en curso o terminado",
            status_code=409,
        )
    drawing, state_field, error_field = await _entidad(db, job)
    await validar_alcance(drawing)
    job.estado = "PENDIENTE"
    job.intentos = 0
    job.error = None
    job.error_publicacion = None
    job.id_ejecucion = None
    job.proxima_publicacion = datetime.now(timezone.utc)
    setattr(drawing, state_field, "PENDIENTE")
    setattr(drawing, error_field, None)
    return {"id": str(job.id), "estado": job.estado}


async def ejecutar_trabajo(trabajo_id, db_engine=engine):
    """Lock delivery and commit exactly one domain result, including restarts."""
    job_id = UUID(str(trabajo_id))
    token = uuid4()
    job_kind = None
    drawing_output_paths = []
    drawing_artifacts_may_have_changed = False
    # Persist the start independently: SIGKILL/timeout must consume an attempt.
    async with db_engine.begin() as connection:
        if connection.dialect.name == 'sqlite':
            await connection.exec_driver_sql('BEGIN IMMEDIATE')
        async with AsyncSession(bind=connection, expire_on_commit=False) as db:
            job = await db.scalar(select(TrabajoProceso).where(
                TrabajoProceso.id == job_id).with_for_update())
            if job is None:
                return 'ELIMINADO'
            if job.estado in ('COMPLETADO', 'ERROR'):
                return job.estado
            due = job.proxima_publicacion
            if due.tzinfo is None:
                due = due.replace(tzinfo=timezone.utc)
            if job.estado == 'EJECUTANDO' and due > datetime.now(timezone.utc):
                return 'EN_PROCESO'
            if job.intentos >= MAX_INTENTOS:
                # Dispatcher finalizes and exposes the exhausted delivery.
                job.proxima_publicacion = datetime.now(timezone.utc)
                await db.flush()
                return 'PENDIENTE'
            job.intentos += 1
            job.estado = 'EJECUTANDO'
            job.id_ejecucion = token
            job.proxima_publicacion = datetime.now(timezone.utc) + timedelta(seconds=PLAZO_ENTREGA)
            await db.flush()
    try:
        async with db_engine.begin() as connection:
            if connection.dialect.name == 'sqlite':
                await connection.exec_driver_sql('BEGIN IMMEDIATE')
            async with AsyncSession(bind=connection, expire_on_commit=False,
                                    join_transaction_mode='create_savepoint') as db:
                job = await db.scalar(select(TrabajoProceso).where(
                    TrabajoProceso.id == job_id).with_for_update())
                if job is None:
                    return 'ELIMINADO'
                if job.estado in ('COMPLETADO', 'ERROR'):
                    return job.estado
                if job.id_ejecucion != token:
                    return 'EN_PROCESO'
                job_kind = job.tipo
                entity, state_field, error_field = await _entidad(db, job)
                if job.tipo == 'BIM_DRAWING':
                    drawing_output_paths = _drawing_artifact_paths(entity)
                if job.tipo == 'BIM_DRAWING_CLEANUP':
                    await _procesar(db, job, entity)
                    await _finish_drawing_cleanup(db, job, entity)
                else:
                    if getattr(entity, state_field) != 'COMPLETADO':
                        setattr(entity, state_field, 'EN_PROCESO')
                        if job.tipo == 'BIM_DRAWING':
                            drawing_artifacts_may_have_changed = True
                        await _procesar(db, job, entity)
                    setattr(entity, state_field, 'COMPLETADO')
                    setattr(entity, error_field, None)
                job.estado = 'COMPLETADO'
                job.error = None
                await db.commit()
                return 'COMPLETADO'
    except Exception as exc:
        logger.exception('process_execution_failed', extra={'job_id':str(job_id)})
        # The database commit may have succeeded even when its acknowledgement
        # was lost. Re-read the authoritative state before deleting any object.
        # If the database cannot be reconciled, this block raises and deliberately
        # leaves Storage untouched; the delivery lease can be recovered later.
        async with db_engine.begin() as connection:
            if connection.dialect.name == 'sqlite':
                await connection.exec_driver_sql('BEGIN IMMEDIATE')
            async with AsyncSession(bind=connection, expire_on_commit=False) as db:
                job = await db.scalar(select(TrabajoProceso).where(
                    TrabajoProceso.id == job_id).with_for_update())
                if job is None:
                    return 'ELIMINADO'
                if job.estado in ('COMPLETADO', 'ERROR'):
                    return job.estado
                if job.id_ejecucion != token:
                    return job.estado

                deterministic = (
                    isinstance(exc, MegalodonException)
                    and exc.code != ErrorCode.ARCHIVO_ERROR
                )
                final = deterministic or job.intentos >= MAX_INTENTOS
                target_state = 'ERROR' if final else 'PENDIENTE'
                job.error = (
                    'No se pudo completar. Revisa los datos y vuelve a intentar.'
                    if final else
                    'Se interrumpió el procesamiento; se reintentará automáticamente.'
                )
                job.proxima_publicacion = (
                    datetime.now(timezone.utc) + timedelta(seconds=15 * job.intentos)
                )

                try:
                    entity, state_field, error_field = await _entidad(db, job)
                except MegalodonException:
                    # If the drawing aggregate was deleted after the attempt,
                    # only previously derived private paths may be compensated.
                    if job.tipo == 'BIM_DRAWING' and drawing_artifacts_may_have_changed:
                        from app.services.bim_drawing_service import storage_bim
                        try:
                            await storage_bim().eliminar(drawing_output_paths)
                        except Exception:
                            logger.exception(
                                'drawing_artifact_compensation_failed',
                                extra={'job_id': str(job_id), 'paths': drawing_output_paths},
                            )
                    logger.warning('process_entity_deleted', extra={'job_id':str(job_id)})
                    job.estado = target_state
                else:
                    if job.tipo == 'BIM_DRAWING' and drawing_artifacts_may_have_changed:
                        # The job is still owned by this attempt and not committed.
                        # Hold its row lock while deleting to prevent a concurrent
                        # retry from racing with the compensating operation.
                        cleanup_failed = False
                        paths = _drawing_artifact_paths(entity)
                        try:
                            from app.services.bim_drawing_service import storage_bim
                            await storage_bim().eliminar(paths)
                        except Exception:
                            cleanup_failed = True
                            logger.exception(
                                'drawing_artifact_compensation_failed',
                                extra={'job_id': str(job_id), 'paths': paths},
                            )
                        if cleanup_failed:
                            job.estado = 'ESPERA_LIMPIEZA'
                            job.error = (
                                'La generación falló; los artefactos esperan limpieza '
                                'antes del reintento.'
                            )
                            await _schedule_drawing_cleanup(
                                db, entity, job, paths, target_state
                            )
                            setattr(entity, state_field, 'PENDIENTE')
                            setattr(entity, error_field, 'Limpieza de artefactos pendiente.')
                        else:
                            job.estado = target_state
                            setattr(entity, state_field, target_state)
                            setattr(entity, error_field, job.error)
                    elif job.tipo == 'BIM_DRAWING_CLEANUP':
                        job.estado = target_state
                        if target_state == 'ERROR':
                            try:
                                original_id = UUID(
                                    str((job.parametros or {})['original_job_id'])
                                )
                            except (KeyError, TypeError, ValueError):
                                logger.error(
                                    'drawing_cleanup_missing_original_job',
                                    extra={'job_id': str(job.id)},
                                )
                            else:
                                original = await db.scalar(
                                    select(TrabajoProceso).where(
                                        TrabajoProceso.id == original_id,
                                        TrabajoProceso.tenant_id == job.tenant_id,
                                        TrabajoProceso.entidad_id == job.entidad_id,
                                        TrabajoProceso.tipo == 'BIM_DRAWING',
                                    ).with_for_update()
                                )
                                if original is not None and original.estado == 'ESPERA_LIMPIEZA':
                                    original.estado = 'ERROR'
                                    original.error = (
                                        'No se pudo limpiar el almacenamiento después de varios intentos.'
                                    )
                                    original.proxima_publicacion = datetime.now(timezone.utc)
                            setattr(entity, state_field, 'ERROR')
                            setattr(entity, error_field, job.error)
                    else:
                        job.estado = target_state
                        setattr(entity, state_field, target_state)
                        setattr(entity, error_field, job.error)

                await db.flush()
                return job.estado
