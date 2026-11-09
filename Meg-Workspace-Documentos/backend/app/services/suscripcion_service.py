# Copyright © 2026 Cristian Rodriguez
# All rights reserved.
# Unauthorized copying, modification, distribution, or use is prohibited
# without prior written permission.

"""
Orquesta el checkout y la activación de planes pagados, sin importar
qué proveedor de pago se use.

Mercado Pago es el proveedor por default (arranque real del negocio).
Stripe se puede pedir explícitamente, pero si no está configurado se
regresa un error de negocio claro (no una excepción de import ni un
500) -- ver ResultadoCheckout.disponible.
"""
from datetime import datetime, timedelta, timezone
from typing import Optional
from uuid import UUID, uuid4

import structlog
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.entitlements import Suscripcion, EstadoSuscripcion, ProveedorPago, PlanTipo, WebhookEventoProcesado
from app.models.user import Tenant
from app.integrations.payments.base import PaymentProvider
from app.integrations.payments.mercadopago_provider import MercadoPagoProvider
from app.integrations.payments.stripe_provider import StripeProvider
from app.services.entitlements_service import EntitlementsService
from app.core.errors import MegalodonException, ErrorCode

logger = structlog.get_logger()


class SuscripcionService:
    def __init__(self, db: AsyncSession):
        self.db = db
        self.entitlements = EntitlementsService(db)
        self._proveedores = {
            ProveedorPago.MERCADOPAGO.value: MercadoPagoProvider(),
            ProveedorPago.STRIPE.value: StripeProvider(),
        }

    def _proveedor(self, nombre: str) -> PaymentProvider:
        proveedor = self._proveedores.get(nombre.upper())
        if proveedor is None:
            raise MegalodonException(
                ErrorCode.VALIDACION_FALLIDA, f"Proveedor de pago desconocido: {nombre}",
            )
        return proveedor

    async def crear_checkout(
        self, *, tenant_id: UUID, plan: str, email_cliente: str, proveedor: str = "MERCADOPAGO",
    ) -> dict:
        if plan not in (PlanTipo.INTERMEDIO.value, PlanTipo.PRO.value, PlanTipo.ENTERPRISE.value):
            raise MegalodonException(
                ErrorCode.VALIDACION_FALLIDA, f"'{plan}' no es un plan de pago válido.",
            )

        limites = await self.entitlements.obtener_limites(plan)
        if limites is None:
            raise MegalodonException(ErrorCode.VALIDACION_FALLIDA, f"Plan '{plan}' no configurado.")

        proveedor_obj = self._proveedor(proveedor)
        if not proveedor_obj.disponible:
            # Fallback automático a Mercado Pago si se pidió Stripe y no
            # está configurado -- Mercado Pago es el proveedor primario
            # y siempre debería estar disponible en producción real.
            if proveedor.upper() == ProveedorPago.STRIPE.value and self._proveedores[ProveedorPago.MERCADOPAGO.value].disponible:
                proveedor_obj = self._proveedores[ProveedorPago.MERCADOPAGO.value]
            else:
                return {
                    "disponible": False,
                    "mensaje": f"El proveedor {proveedor} no está configurado en este entorno.",
                }

        from app.config import settings
        resultado = await proveedor_obj.crear_checkout(
            tenant_id=str(tenant_id),
            plan=plan,
            precio=float(limites.precio_mensual),
            moneda=limites.moneda,
            email_cliente=email_cliente,
            url_retorno_exito=f"{settings.FRONTEND_URL}/suscripcion/exito",
            url_retorno_fallo=f"{settings.FRONTEND_URL}/suscripcion/error",
        )

        if not resultado.disponible or not resultado.url_pago or not resultado.external_id:
            return {"disponible": False, "mensaje": resultado.mensaje}

        suscripcion = Suscripcion(
            id=uuid4(),
            tenant_id=tenant_id,
            plan=plan,
            proveedor=proveedor_obj.nombre,
            estado=EstadoSuscripcion.PENDIENTE_PAGO.value,
            external_id=resultado.external_id,
            monto=limites.precio_mensual,
            moneda=limites.moneda,
        )
        self.db.add(suscripcion)
        await self.db.commit()

        return {"disponible": True, "url_pago": resultado.url_pago}

    async def procesar_webhook(self, proveedor: str, payload: dict, headers: dict) -> None:
        proveedor_obj = self._proveedor(proveedor)
        resultado = await proveedor_obj.procesar_webhook(payload, headers)
        if not resultado.valido or not resultado.external_id or not resultado.estado:
            return
        now = datetime.now(timezone.utc)
        is_stripe = proveedor == ProveedorPago.STRIPE.value
        if is_stripe and resultado.estado == EstadoSuscripcion.ACTIVA.value and (
            not resultado.periodo_fin or resultado.periodo_fin <= now
        ):
            raise MegalodonException(
                ErrorCode.VALIDACION_FALLIDA, "Stripe no confirmó un periodo vigente", status_code=503
            )


        # CORREGIDO (F-07): deduplicación por evento. "id" en el cuerpo de
        # la notificación identifica ESTA entrega puntual (distinto de
        # data.id/external_id, que identifica el recurso/suscripción y se
        # repite legítimamente en cada renovación mensual real -- por eso
        # NO se puede deduplicar por external_id sin romper renovaciones
        # genuinas). Se inserta primero, con flush inmediato: si el
        # webhook ya se procesó (reenvío/replay), la restricción única
        # (proveedor, evento_id) lo rechaza aquí y se sale ANTES de tocar
        # Suscripcion -- ninguna carrera entre dos entregas casi
        # simultáneas del mismo evento alcanza a aplicar el efecto dos
        # veces.
        evento_id = str(payload.get("id") or "")
        if evento_id:
            self.db.add(WebhookEventoProcesado(
                proveedor=proveedor, evento_id=evento_id,
                procesado_en=datetime.now(timezone.utc),
            ))
            try:
                await self.db.flush()
            except IntegrityError:
                await self.db.rollback()
                logger.info("webhook_evento_duplicado_ignorado", proveedor=proveedor, evento_id=evento_id)
                return
        else:
            # Notificaciones sin "id" propio en el cuerpo (algunos topics
            # viejos, o llamadas de prueba manuales): no hay forma de
            # deduplicar por evento. Se procesan igual que antes -- no se
            # bloquea el flujo legítimo por falta de un dato opcional.
            logger.warning("webhook_sin_id_propio_no_deduplicable", proveedor=proveedor, external_id=resultado.external_id)

        result = await self.db.execute(
            select(Suscripcion).where(
                Suscripcion.proveedor == proveedor,
                Suscripcion.external_id.in_(
                    [resultado.external_id, resultado.checkout_id]
                    if resultado.checkout_id else [resultado.external_id]
                ),
            ).with_for_update()
        )
        suscripcion = result.scalar_one_or_none()
        if suscripcion is None:
            return  # webhook de una suscripción que no creamos nosotros (o de prueba) -- se ignora

        if resultado.checkout_id:
            suscripcion.external_id = resultado.external_id
        suscripcion.estado = resultado.estado
        suscripcion.metadatos = resultado.datos_crudos

        if resultado.estado == EstadoSuscripcion.ACTIVA.value:
            if suscripcion.fecha_inicio is None:
                suscripcion.fecha_inicio = datetime.now(timezone.utc)
            suscripcion.fecha_fin = resultado.periodo_fin if is_stripe else now + timedelta(days=31)

            tenant = await self.db.get(Tenant, suscripcion.tenant_id)
            if tenant is not None:
                tenant.plan = suscripcion.plan
                tenant.plan_vencimiento = suscripcion.fecha_fin

        elif resultado.estado in (EstadoSuscripcion.CANCELADA.value, EstadoSuscripcion.VENCIDA.value):
            tenant = await self.db.get(Tenant, suscripcion.tenant_id)
            # BUG A EVITAR: no se "congela" retroactivamente en el
            # instante del webhook si ya se pagó el periodo -- el freeze
            # real ocurre cuando plan_vencimiento pasa (ver
            # EntitlementsService.calcular_plan_efectivo /
            # revisar_vencimientos_globales). Aquí solo se refleja el
            # estado de la suscripción; el tenant conserva su plan hasta
            # que venza el periodo ya pagado.

        await self.db.commit()

    async def cancelar(self, tenant_id: UUID) -> bool:
        from sqlalchemy import select
        result = await self.db.execute(
            select(Suscripcion)
            .where(Suscripcion.tenant_id == tenant_id, Suscripcion.estado == EstadoSuscripcion.ACTIVA.value)
            .order_by(Suscripcion.created_at.desc())
        )
        suscripcion = result.scalars().first()
        if suscripcion is None or not suscripcion.external_id:
            return False

        proveedor_obj = self._proveedor(suscripcion.proveedor)
        ok = await proveedor_obj.cancelar_suscripcion(suscripcion.external_id)
        if ok:
            suscripcion.estado = EstadoSuscripcion.CANCELADA.value
            await self.db.commit()
        return ok
