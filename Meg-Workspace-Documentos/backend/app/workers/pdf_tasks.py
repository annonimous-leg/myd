# Copyright © 2026 Cristian Rodriguez
# All rights reserved.
# Unauthorized copying, modification, distribution, or use is prohibited
# without prior written permission.

"""
Worker Celery para generación de PDF de presupuesto.

Llama a PresupuestoService.generar_pdf() (que usa MotorCosteo.generar_pdf()
con reportlab -- ya estaba declarado en pyproject.toml para PAdES-LT de
firma electrónica, pero nunca se usaba en ningún lado del proyecto hasta
ahora) y sube el resultado a Supabase Storage. Mismo patrón que
excel_tasks.py.

Antes: devolvía {"status":"SUCCESS","pdf_url":""} -- SUCCESS falso, el
frontend no podía descargar nada real.
"""
import asyncio
from uuid import UUID

from app.workers.celery_app import celery_app


@celery_app.task(bind=True, time_limit=300, max_retries=2)
def generar_pdf_presupuesto(self, presupuesto_id: str, expediente_id: str, tenant_id: str):
    """Genera el PDF del presupuesto y lo sube a storage.

    Retorna:
        {"status": "SUCCESS", "pdf_url": "<url firmada>", "expires_in": 3600}
    """
    try:
        async def _run():
            from app.models.base import AsyncSessionLocal
            from app.services.presupuesto_service import PresupuestoService
            from app.integrations.supabase_storage import storage_exportaciones

            async with AsyncSessionLocal() as db:
                service = PresupuestoService(db, UUID(tenant_id))
                pdf_bytes = await service.generar_pdf(
                    UUID(presupuesto_id),
                    expediente_id=UUID(expediente_id),
                )

            storage = storage_exportaciones()
            path = f"tenant/{tenant_id}/presupuestos/{expediente_id}/{presupuesto_id}/presupuesto.pdf"
            await storage.subir(path, pdf_bytes, content_type="application/pdf")
            url = await storage.url_firmada(path, expira_segundos=3600)
            return url

        url = asyncio.run(_run())
        return {
            "status": "SUCCESS",
            "pdf_url": url,
            "expires_in": 3600,
            "presupuesto_id": presupuesto_id,
        }
    except Exception as exc:
        self.retry(countdown=30, exc=exc)
