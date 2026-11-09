# Copyright © 2026 Cristian Rodriguez
# All rights reserved.
# Unauthorized copying, modification, distribution, or use is prohibited
# without prior written permission.

"""
Worker Celery para procesamiento asíncrono de archivos IFC.

Antes era un stub que devolvía elementos_count:0 / tipos:{} -- los
endpoints BIM síncronos funcionaban pero un modelo IFC grande (>50MB)
bloqueaba el request completo. Este worker descarga el IFC de Supabase
Storage (donde ya lo subió el endpoint síncrono de upload), lo procesa
con BIMService.procesar_ifc() y actualiza el estado del modelo.

El endpoint de upload todavía registra el ModeloBIM y sube el archivo;
cuando el modelo tiene PROCESANDO_EN_WORKER como estado, el frontend
puede hacer polling a GET /modelos/{id} hasta que el estado cambie a
COMPLETADO o ERROR.
"""
import asyncio
import structlog
from uuid import UUID
from typing import List, Optional

from app.workers.celery_app import celery_app

logger = structlog.get_logger()


@celery_app.task(bind=True, time_limit=900, max_retries=2)
def procesar_ifc(
    self,
    modelo_id: str,
    expediente_id: str,
    tenant_id: str,
    tipos_elementos: Optional[List[str]] = None,
    extraer_malla: bool = True,
):
    """Descarga el IFC de Supabase Storage, lo procesa y persiste elementos.

    Retorna:
        {"status": "SUCCESS", "modelo_id": ..., "num_elementos": ..., "tipos": {...}}
    """
    try:
        async def _run():
            from app.models.base import AsyncSessionLocal
            from app.services.bim_service import BIMService
            from app.integrations.supabase_storage import storage_bim
            from app.models.bim import ModeloBIM
            from sqlalchemy import select

            async with AsyncSessionLocal() as db:
                # Leer ruta del archivo desde el modelo ya registrado
                modelo = (await db.execute(select(ModeloBIM).where(ModeloBIM.id == UUID(modelo_id), ModeloBIM.expediente_id == UUID(expediente_id), ModeloBIM.tenant_id == UUID(tenant_id)))).scalar_one_or_none()
                if not modelo:
                    raise ValueError(f"Modelo BIM {modelo_id} no encontrado")

                # Descargar IFC de Supabase Storage
                storage = storage_bim()
                file_content = await storage.descargar(modelo.ruta_archivo)

                # Procesar con el servicio real
                service = BIMService(db, tenant_id=UUID(tenant_id))
                modelo_procesado = await service.procesar_ifc(
                    modelo_id=UUID(modelo_id),
                    file_content=file_content,
                    tipos_elementos=tipos_elementos,
                    extraer_malla=extraer_malla,
                )

            # Construir resumen para el resultado del task
            tipos_count: dict = {}
            num_elementos = 0
            async with AsyncSessionLocal() as db2:
                from sqlalchemy import select, func
                from app.models.bim import ElementoBIM, ModeloBIM
                from sqlalchemy import select
                result = await db2.execute(
                    select(ElementoBIM.tipo, func.count(ElementoBIM.id))
                    .join(ModeloBIM, ModeloBIM.id == ElementoBIM.modelo_id)
                    .where(ElementoBIM.modelo_id == UUID(modelo_id), ModeloBIM.tenant_id == UUID(tenant_id))
                    .group_by(ElementoBIM.tipo)
                )
                for tipo, count in result.all():
                    tipos_count[tipo] = count
                    num_elementos += count

            return {
                "status": "SUCCESS",
                "modelo_id": modelo_id,
                "expediente_id": expediente_id,
                "num_elementos": num_elementos,
                "tipos": tipos_count,
            }

        return asyncio.run(_run())

    except Exception as exc:
        error_message = str(exc)
        logger.warning("bim_tasks.procesar_ifc: fallo procesando IFC", modelo_id=modelo_id, error=error_message)
        # Marcar el modelo en ERROR para que el frontend no quede en polling
        try:
            async def _marcar_error():
                from app.models.base import AsyncSessionLocal
                from app.models.bim import ModeloBIM
                from sqlalchemy import select
                from app.models.base import EstadoProceso
                async with AsyncSessionLocal() as db:
                    modelo = (await db.execute(select(ModeloBIM).where(ModeloBIM.id == UUID(modelo_id), ModeloBIM.expediente_id == UUID(expediente_id), ModeloBIM.tenant_id == UUID(tenant_id)).with_for_update())).scalar_one_or_none()
                    if modelo and modelo.estado_procesamiento != EstadoProceso.COMPLETADO.value:
                        modelo.estado_procesamiento = EstadoProceso.ERROR.value
                        modelo.error_procesamiento = error_message[:500]
                        await db.commit()
            asyncio.run(_marcar_error())
        except Exception as marcar_exc:
            # No se relanza (no queremos encadenar un error del *manejo*
            # de errores), pero antes esto era un `pass` total: si la
            # marca de ERROR fallaba (p.ej. DB caída), el ModeloBIM se
            # quedaba en PROCESANDO_EN_WORKER para siempre y el frontend
            # hacía polling indefinido sin que quedara ningún rastro en
            # ningún lado de qué pasó. Ahora al menos queda en logs.
            logger.error(
                "bim_tasks.procesar_ifc: fallo al marcar modelo en ERROR",
                modelo_id=modelo_id, error_original=error_message, error_al_marcar=str(marcar_exc),
            )

        self.retry(countdown=60, exc=exc)


@celery_app.task(bind=True, time_limit=1200, max_retries=1)
def generar_4d5d_desde_bim(
    self,
    generacion_id: str,
    modelo_id: str,
    expediente_id: str,
    tenant_id: str,
    fecha_inicio_iso: str,
    dias_por_defecto: float = 5.0,
    creado_por_id: Optional[str] = None,
):
    """Genera un ProgramaObra 4D (BIMService.generar_actividades_4d) para
    un modelo con potencialmente miles de elementos -- agruparlos y crear
    actividades + vínculos M:N no es instantáneo, de ahí la cola.

    El registro GeneracionBIM4D5D (`generacion_id`) es lo que el frontend
    hace polling; self.update_state(...) además deja progreso disponible
    para quien sí se suscriba al WebSocket genérico -- son dos caminos
    redundantes a propósito (el WS es best-effort, no sobrevive un
    restart del proceso API; la fila en BD sí).
    """
    from uuid import UUID as _UUID

    try:
        async def _run():
            from app.models.base import AsyncSessionLocal, EstadoProceso
            from app.models.bim import GeneracionBIM4D5D
            from app.models.programacion import ActividadPrograma
            from app.services.bim_service import BIMService
            from app.core.errors import MegalodonException
            from sqlalchemy import select, func
            from datetime import datetime

            async with AsyncSessionLocal() as db:
                generacion = (await db.execute(select(GeneracionBIM4D5D).where(GeneracionBIM4D5D.id == _UUID(generacion_id), GeneracionBIM4D5D.tenant_id == _UUID(tenant_id)))).scalar_one_or_none()
                if not generacion:
                    raise ValueError(f"GeneracionBIM4D5D {generacion_id} no encontrada")
                generacion.estado = EstadoProceso.EN_PROCESO.value
                await db.commit()

                self.update_state(state="PROGRESS", meta={"progress": 10})

                service = BIMService(db, tenant_id=generacion.tenant_id)
                try:
                    programa = await service.generar_actividades_4d(
                        modelo_id=_UUID(modelo_id),
                        expediente_id=_UUID(expediente_id),
                        fecha_inicio=datetime.fromisoformat(fecha_inicio_iso),
                        dias_por_defecto=dias_por_defecto,
                        creado_por_id=_UUID(creado_por_id) if creado_por_id else None,
                        tenant_id=generacion.tenant_id,
                    )
                except MegalodonException:
                    # Falla determinística (sin elementos, unidad no
                    # derivable, etc.) -- reintentar no va a cambiar el
                    # resultado. Se relanza para que el except de afuera
                    # marque ERROR sin reintentar.
                    raise

                self.update_state(state="PROGRESS", meta={"progress": 90})

                count_result = await db.execute(
                    select(func.count()).select_from(ActividadPrograma)
                    .where(ActividadPrograma.programa_id == programa.id)
                )
                num_actividades = count_result.scalar() or 0

                generacion.estado = EstadoProceso.COMPLETADO.value
                generacion.programa_id = programa.id
                generacion.num_actividades_generadas = num_actividades
                await db.commit()

                return {
                    "status": "SUCCESS",
                    "generacion_id": generacion_id,
                    "programa_id": str(programa.id),
                    "num_actividades": num_actividades,
                }

        return asyncio.run(_run())

    except Exception as exc:
        from app.core.errors import MegalodonException as _MegalodonException

        error_message = str(exc)
        logger.warning("bim_tasks.generar_4d5d_desde_bim: fallo generando 4D/5D", generacion_id=generacion_id, error=error_message)

        try:
            async def _marcar_error():
                from app.models.base import AsyncSessionLocal
                from app.models.base import EstadoProceso
                from app.models.bim import GeneracionBIM4D5D
                from sqlalchemy import select
                async with AsyncSessionLocal() as db:
                    generacion = (await db.execute(select(GeneracionBIM4D5D).where(GeneracionBIM4D5D.id == _UUID(generacion_id), GeneracionBIM4D5D.tenant_id == _UUID(tenant_id)))).scalar_one_or_none()
                    if generacion:
                        generacion.estado = EstadoProceso.ERROR.value
                        generacion.error = error_message[:500]
                        await db.commit()
            asyncio.run(_marcar_error())
        except Exception as marcar_exc:
            logger.error(
                "bim_tasks.generar_4d5d_desde_bim: fallo al marcar generación en ERROR",
                generacion_id=generacion_id, error_original=error_message, error_al_marcar=str(marcar_exc),
            )

        if isinstance(exc, _MegalodonException):
            raise  # determinístico -- no reintentar
        self.retry(countdown=60, exc=exc)


@celery_app.task(bind=True, time_limit=900, max_retries=1)
def analizar_clash(self, analisis_id: str, tenant_id: str):
    """Corre ClashService.ejecutar_analisis_worker() dentro de un worker
    Celery.

    FIX P0 auditoría BIM 2026-09-14: antes /clash-detection corría
    síncrono dentro del request HTTP (broad phase AABB + narrow phase
    Möller-Trumbore triángulo-triángulo) -- con modelos de miles de
    elementos de malla densa esto arriesgaba timeout, el mismo problema
    que ya se había resuelto para procesar_ifc(). El endpoint ahora solo
    crea el AnalisisClash en PENDIENTE (ClashService.crear_analisis_pendiente,
    rápido) y encola esta tarea; el frontend hace polling a
    GET /clash-detection/{analisis_id} hasta EN_PROCESO -> COMPLETADO/ERROR,
    igual que ya hace con ModeloBIM.
    """
    try:
        async def _run():
            from app.models.base import AsyncSessionLocal
            from app.services.clash_service import ClashService

            async with AsyncSessionLocal() as db:
                service = ClashService(db, tenant_id=UUID(tenant_id))
                analisis = await service.ejecutar_analisis_worker(UUID(analisis_id))
                return {
                    "status": "SUCCESS",
                    "analisis_id": analisis_id,
                    "num_pares_evaluados": analisis.num_pares_evaluados,
                    "num_clashes_duros": analisis.num_clashes_duros,
                    "num_clashes_blandos": analisis.num_clashes_blandos,
                    "tiempo_calculo_ms": analisis.tiempo_calculo_ms,
                }

        return asyncio.run(_run())

    except Exception as exc:
        # ejecutar_analisis_worker() ya deja el AnalisisClash en ERROR con
        # el detalle (ver el except dentro del propio servicio) antes de
        # relanzar -- no hace falta duplicar esa marca aquí, a diferencia
        # de procesar_ifc()/generar_4d5d_desde_bim() donde el estado ERROR
        # se marca solo en el worker porque el servicio no lo hacía.
        logger.warning("bim_tasks.analizar_clash: fallo ejecutando clash detection", analisis_id=analisis_id, error=str(exc))
        self.retry(countdown=30, exc=exc)
