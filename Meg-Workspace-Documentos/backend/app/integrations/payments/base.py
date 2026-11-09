# Copyright © 2026 Cristian Rodriguez
# All rights reserved.
# Unauthorized copying, modification, distribution, or use is prohibited
# without prior written permission.

"""
Interfaz común de proveedores de pago.

Mercado Pago es el proveedor principal (arranque real de negocio).
Stripe queda implementado con la misma interfaz pero es OPCIONAL: si no
hay STRIPE_SECRET_KEY configurada (o el paquete `stripe` no está
instalado), StripeProvider.disponible es False y el backend sigue
funcionando normal solo con Mercado Pago -- ver
app.services.suscripcion_service para cómo se orquesta esto.
"""
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from datetime import datetime
from typing import Any, Dict, Optional


@dataclass
class ResultadoCheckout:
    disponible: bool
    url_pago: Optional[str] = None
    external_id: Optional[str] = None
    mensaje: Optional[str] = None


@dataclass
class ResultadoWebhook:
    valido: bool
    external_id: Optional[str] = None
    estado: Optional[str] = None  # se mapea a EstadoSuscripcion en el service
    mensaje: Optional[str] = None
    datos_crudos: Dict[str, Any] = field(default_factory=dict)
    checkout_id: Optional[str] = None
    periodo_fin: Optional[datetime] = None


class PaymentProvider(ABC):
    """Contrato común. Cada proveedor concreto debe exponer `disponible`
    ANTES de que se le pida hacer nada -- así el orquestador puede caer
    limpiamente a "proveedor no disponible" (409/503 de negocio) en vez
    de tronar con un error de configuración a medio checkout."""

    nombre: str = "base"

    @property
    @abstractmethod
    def disponible(self) -> bool:
        """True si el proveedor tiene credenciales configuradas y puede usarse."""

    @abstractmethod
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
        """Crea la suscripción/checkout del lado del proveedor y regresa
        la URL a la que hay que mandar al usuario para pagar."""

    @abstractmethod
    def verificar_firma_webhook(self, payload: bytes, headers: Dict[str, str]) -> bool:
        """Valida que el webhook realmente venga del proveedor (HMAC/firma)."""

    @abstractmethod
    async def procesar_webhook(
        self, payload: Dict[str, Any], headers: Dict[str, str]
    ) -> ResultadoWebhook:
        """Interpreta el payload ya recibido y regresa el estado normalizado."""

    @abstractmethod
    async def cancelar_suscripcion(self, external_id: str) -> bool:
        """Cancela una suscripción activa del lado del proveedor."""
