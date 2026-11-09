# Copyright © 2026 Cristian Rodriguez
# All rights reserved.
# Unauthorized copying, modification, distribution, or use is prohibited
# without prior written permission.

"""
API de pagos: crear checkout de suscripción y recibir webhooks.

Mercado Pago es el proveedor por default. Stripe se puede pedir
explícitamente (?proveedor=stripe) pero si no está configurado,
crear_checkout regresa disponible=False con un mensaje claro -- nunca
una excepción de import ni un 500.
"""
from app.core.rate_limit import rate_limit_standard, rate_limit_strict
from typing import Optional

from fastapi import APIRouter, Depends, Request
from pydantic import BaseModel

from sqlalchemy.ext.asyncio import AsyncSession

from app.api.v1.users import require_tenant_admin
from app.core.deps import get_db
from app.core.errors import handle_megalodon_errors
from app.models.user import User
from app.services.suscripcion_service import SuscripcionService

router = APIRouter(tags=["Pagos"])


class CrearCheckoutRequest(BaseModel):
    plan: str
    proveedor: str = "MERCADOPAGO"


@router.post("/checkout")
@handle_megalodon_errors
async def crear_checkout(
    data: CrearCheckoutRequest,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_tenant_admin), _rate_limit: bool = Depends(rate_limit_strict),
):
    service = SuscripcionService(db)
    return await service.crear_checkout(
        tenant_id=current_user.tenant_id,
        plan=data.plan.upper(),
        email_cliente=current_user.email,
        proveedor=data.proveedor.upper(),
    )


@router.post("/cancelar")
@handle_megalodon_errors
async def cancelar_suscripcion(
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_tenant_admin), _rate_limit: bool = Depends(rate_limit_strict),
):
    service = SuscripcionService(db)
    cancelada = await service.cancelar(current_user.tenant_id)
    return {"cancelada": cancelada}


@router.post("/webhook/mercadopago")
@handle_megalodon_errors
async def webhook_mercadopago(request: Request, db: AsyncSession = Depends(get_db), _rate_limit: bool = Depends(rate_limit_standard)):
    """Mercado Pago manda `data.id` en el query string, no en el body,
    para las notificaciones de tipo 'preapproval'."""
    payload = await request.json()
    headers = dict(request.headers)
    headers["_data_id"] = request.query_params.get("data.id", "") or request.query_params.get("id", "")

    service = SuscripcionService(db)
    provider = service._proveedor("MERCADOPAGO")
    body_bytes = await request.body()
    if not provider.verificar_firma_webhook(body_bytes, headers):
        return {"recibido": False, "motivo": "firma_invalida"}

    await service.procesar_webhook("MERCADOPAGO", payload, headers)
    return {"recibido": True}


@router.post("/webhook/stripe")
@handle_megalodon_errors
async def webhook_stripe(request: Request, db: AsyncSession = Depends(get_db), _rate_limit: bool = Depends(rate_limit_standard)):
    body_bytes = await request.body()
    headers = dict(request.headers)

    service = SuscripcionService(db)
    provider = service._proveedor("STRIPE")

    if not provider.disponible:
        # Stripe no está activo en este ambiente -- no hay nada que
        # procesar, pero se responde 200 para que el proveedor (si algún
        # día se activa mal configurado del otro lado) no reintente
        # indefinidamente contra un endpoint que nunca va a aceptar.
        return {"recibido": False, "motivo": "stripe_no_configurado"}

    if not provider.verificar_firma_webhook(body_bytes, headers):
        return {"recibido": False, "motivo": "firma_invalida"}

    payload = await request.json()
    await service.procesar_webhook("STRIPE", payload, headers)
    return {"recibido": True}
