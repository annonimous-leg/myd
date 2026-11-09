# Copyright © 2026 Cristian Rodriguez
# All rights reserved.
# Unauthorized copying, modification, distribution, or use is prohibited
# without prior written permission.

"""
Worker Celery para exportación de presupuesto a Excel.

Llama al PresupuestoService.generar_excel() (que ya estaba implementado y
probado) y sube el resultado a Supabase Storage (bucket de exportaciones).
Regresa la URL firmada temporal para que el frontend pueda descargarlo.

Antes: devolvía {"status":"SUCCESS","excel_url":""} -- SUCCESS falso con
archivo vacío, el frontend no podía descargar nada real.
"""
import asyncio
from uuid import UUID

from app.workers.celery_app import celery_app


@celery_app.task(bind=True, time_limit=300, max_retries=2)
def exportar_excel_presupuesto(self, presupuesto_id: str, expediente_id: str, tenant_id: str):
    """Genera el Excel del presupuesto y lo sube a storage.

    Retorna:
        {"status": "SUCCESS", "excel_url": "<url firmada>", "expires_in": 3600}
    """
    try:
        async def _run():
            from app.models.base import AsyncSessionLocal
            from app.services.presupuesto_service import PresupuestoService
            from app.integrations.supabase_storage import storage_exportaciones

            async with AsyncSessionLocal() as db:
                service = PresupuestoService(db, UUID(tenant_id))
                excel_bytes = await service.generar_excel(
                    UUID(presupuesto_id),
                    expediente_id=UUID(expediente_id),
                )

            storage = storage_exportaciones()
            path = f"tenant/{tenant_id}/presupuestos/{expediente_id}/{presupuesto_id}/presupuesto.xlsx"
            await storage.subir(
                path,
                excel_bytes,
                content_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
            )
            url = await storage.url_firmada(path, expira_segundos=3600)
            return url

        url = asyncio.run(_run())
        return {
            "status": "SUCCESS",
            "excel_url": url,
            "expires_in": 3600,
            "presupuesto_id": presupuesto_id,
        }
    except Exception as exc:
        self.retry(countdown=30, exc=exc)
