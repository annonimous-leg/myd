# Copyright © 2026 Cristian Rodriguez
# All rights reserved.
# Unauthorized copying, modification, distribution, or use is prohibited
# without prior written permission.

"""
Proveedor Mercado Pago -- suscripciones recurrentes vía la API de
Preapproval (https://api.mercadopago.com/preapproval), que es la API de
Mercado Pago pensada para cobros mensuales recurrentes (a diferencia de
Checkout Pro / Preferences, que es para pagos únicos).

NOTA DE VERIFICACIÓN: esta implementación sigue el contrato públicamente
documentado de la API de Mercado Pago (endpoints, forma del payload,
esquema de firma de webhooks). No se pudo ejecutar contra credenciales
de sandbox reales en este entorno (sin acceso a red ni claves de
prueba), así que antes de producción hay que correr un ciclo real
contra el ambiente de pruebas de Mercado Pago (checkout de prueba +
webhook real) y ajustar cualquier detalle de payload que haya cambiado.
"""
import hashlib
import hmac
import time
from typing import Any, Dict, Optional

import httpx
import structlog

from app.config import settings
from app.integrations.payments.base import PaymentProvider, ResultadoCheckout, ResultadoWebhook

logger = structlog.get_logger()

MP_API_BASE = "https://api.mercadopago.com"

# Mapeo de status de Mercado Pago (Preapproval) -> EstadoSuscripcion
# (ver app.models.entitlements.EstadoSuscripcion). "authorized" es el
# único estado en el que la suscripción realmente está cobrando.
_ESTADO_MP_A_INTERNO = {
    "pending": "PENDIENTE_PAGO",
    "authorized": "ACTIVA",
    "paused": "VENCIDA",
    "cancelled": "CANCELADA",
}


# Ventana de tolerancia para el timestamp del webhook (anti-replay). MP no
# publica un número exacto de tolerancia en su documentación de firma
# (documenta CÓMO extraer/verificar ts, no una ventana máxima); 300s (5 min)
# es la tolerancia estándar de la industria para webhooks firmados por HMAC
# con ts (p. ej. Stripe usa el mismo valor) -- elección defensiva propia,
# documentada como tal, no un requisito de MP.
_VENTANA_REPLAY_SEGUNDOS = 300


class MercadoPagoProvider(PaymentProvider):
    nombre = "MERCADOPAGO"

    def __init__(self) -> None:
        self._access_token = settings.MERCADOPAGO_ACCESS_TOKEN

    @property
    def disponible(self) -> bool:
        return bool(self._access_token)

    def _headers(self) -> Dict[str, str]:
        return {
            "Authorization": f"Bearer {self._access_token}",
            "Content-Type": "application/json",
        }

    async def crear_checkout(
        self,
        *,
        tenant_id: str,
        plan: str,
        precio: float,
        moneda: str,
        email_cliente: str,
        url_retorno_exito: str,
        url_retorno_fallo: str,
    ) -> ResultadoCheckout:
        if not self.disponible:
            return ResultadoCheckout(
                disponible=False,
                mensaje="Mercado Pago no está configurado (falta MERCADOPAGO_ACCESS_TOKEN).",
            )

        body = {
            "reason": f"Megalodon CostOS -- Plan {plan}",
            "external_reference": f"{tenant_id}:{plan}",
            "payer_email": email_cliente,
            "back_url": url_retorno_exito,
            "auto_recurring": {
                "frequency": 1,
                "frequency_type": "months",
                "transaction_amount": float(precio),
                "currency_id": moneda,
            },
            "status": "pending",
        }

        try:
            async with httpx.AsyncClient(timeout=15.0) as client:
                resp = await client.post(
                    f"{MP_API_BASE}/preapproval", json=body, headers=self._headers()
                )
                resp.raise_for_status()
                data = resp.json()
        except httpx.HTTPStatusError as exc:
            logger.error("mercadopago_crear_checkout_error", status=exc.response.status_code, body=exc.response.text)
            return ResultadoCheckout(
                disponible=True,
                mensaje=f"Mercado Pago rechazó la solicitud ({exc.response.status_code}).",
            )
        except httpx.HTTPError as exc:
            logger.error("mercadopago_crear_checkout_error", error=str(exc))
            return ResultadoCheckout(disponible=True, mensaje="No se pudo contactar a Mercado Pago.")

        return ResultadoCheckout(
            disponible=True,
            url_pago=data.get("init_point"),
            external_id=data.get("id"),
        )

    def verificar_firma_webhook(self, payload: bytes, headers: Dict[str, str]) -> bool:
        """Valida x-signature siguiendo el esquema documentado de MP:
        HMAC-SHA256 sobre "id:{data_id};request-id:{x-request-id};ts:{ts};"
        con el webhook secret, comparado contra el campo v1 de x-signature."""
        if not settings.MERCADOPAGO_WEBHOOK_SECRET:
            logger.error("mercadopago_webhook_rechazado_sin_secreto")
            return False

        x_signature = headers.get("x-signature", "")
        x_request_id = headers.get("x-request-id", "")
        if not x_signature:
            return False

        partes = dict(p.split("=", 1) for p in x_signature.split(",") if "=" in p)
        ts = partes.get("ts", "")
        v1_recibido = partes.get("v1", "")

        # data.id viene en el query string de la notificación, no en el
        # body -- el caller (el endpoint del webhook) debe pasarlo en
        # headers["_data_id"] antes de llamar a esta función. Ver
        # app/api/v1/pagos.py::webhook_mercadopago.
        data_id = headers.get("_data_id", "")
        manifest = f"id:{data_id};request-id:{x_request_id};ts:{ts};"
        firma_calculada = hmac.new(
            settings.MERCADOPAGO_WEBHOOK_SECRET.encode(), manifest.encode(), hashlib.sha256
        ).hexdigest()

        if not hmac.compare_digest(firma_calculada, v1_recibido):
            return False

        # CORREGIDO (F-07): antes no había ninguna comprobación de
        # frescura de ts. Una notificación firmada válida, capturada una
        # sola vez, seguía siendo válida para siempre (la firma no
        # caduca sola) -- permitía volver a mandarla y que se
        # reprocesara como si fuera nueva. Se rechaza si ts es más viejo
        # que _VENTANA_REPLAY_SEGUNDOS o viene del futuro más allá de la
        # misma tolerancia (holgura de reloj entre servidores).
        if not ts.isdigit():
            logger.warning("mercadopago_webhook_ts_invalido", ts=ts)
            return False
        ts_segundos = int(ts)
        if ts_segundos > 10**12:
            # MP documenta ts unas veces como segundos y otras como
            # milisegundos según la página; los ejemplos reales que sí
            # pudimos verificar (ts=1704908010) son segundos. Por si un
            # merchant/integración manda milisegundos, se normaliza en
            # vez de rechazar de forma silenciosamente incorrecta.
            ts_segundos //= 1000
        ahora = int(time.time())
        if abs(ahora - ts_segundos) > _VENTANA_REPLAY_SEGUNDOS:
            logger.warning(
                "mercadopago_webhook_rechazado_por_antiguedad",
                ts=ts_segundos, ahora=ahora, diferencia_segundos=abs(ahora - ts_segundos),
            )
            return False

        return True

    async def procesar_webhook(
        self, payload: Dict[str, Any], headers: Dict[str, str]
    ) -> ResultadoWebhook:
        tipo = payload.get("type") or payload.get("topic")
        data_id = (payload.get("data") or {}).get("id") or payload.get("id")

        if tipo not in ("preapproval", "subscription_preapproval") or not data_id:
            return ResultadoWebhook(valido=True, mensaje="Evento ignorado (no es de suscripción).")

        if not self.disponible:
            return ResultadoWebhook(valido=False, mensaje="Mercado Pago no configurado.")

        try:
            async with httpx.AsyncClient(timeout=15.0) as client:
                resp = await client.get(f"{MP_API_BASE}/preapproval/{data_id}", headers=self._headers())
                resp.raise_for_status()
                detalle = resp.json()
        except httpx.HTTPError as exc:
            logger.error("mercadopago_webhook_fetch_error", error=str(exc))
            return ResultadoWebhook(valido=False, mensaje="No se pudo confirmar el estado con Mercado Pago.")

        estado_mp = detalle.get("status", "")
        return ResultadoWebhook(
            valido=True,
            external_id=str(data_id),
            estado=_ESTADO_MP_A_INTERNO.get(estado_mp, "PENDIENTE_PAGO"),
            datos_crudos=detalle,
        )

    async def cancelar_suscripcion(self, external_id: str) -> bool:
        if not self.disponible:
            return False
        try:
            async with httpx.AsyncClient(timeout=15.0) as client:
                resp = await client.put(
                    f"{MP_API_BASE}/preapproval/{external_id}",
                    json={"status": "cancelled"},
                    headers=self._headers(),
                )
                resp.raise_for_status()
            return True
        except httpx.HTTPError as exc:
            logger.error("mercadopago_cancelar_error", error=str(exc))
            return False
