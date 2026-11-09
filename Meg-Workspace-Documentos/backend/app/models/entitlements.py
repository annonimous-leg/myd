# Copyright © 2026 Cristian Rodriguez
# All rights reserved.
# Unauthorized copying, modification, distribution, or use is prohibited
# without prior written permission.

"""
Entitlements: planes, límites, uso y suscripciones.

CONTEXTO: no existía NADA de esto -- Tenant.settings era un JSONB libre
sin ningún campo con significado real. Este módulo es la base de todo el
freemium/paid: qué plan tiene un tenant, qué le permite ese plan, cuánto
ha usado en el periodo actual, y el registro de su suscripción (con qué
proveedor de pago, desde cuándo, hasta cuándo).

Principio de diseño (siguiendo la propia auto-crítica de la
especificación): los LÍMITES POR PLAN viven en una tabla (PlanLimite),
no hardcodeados en Python -- se pueden ajustar sin redeploy. La lista de
MÓDULOS/APPS y su estado (core/demo/internal/admin_only) también vive en
tabla (AppModulo) por la misma razón: el frontend renderiza, el backend
manda.
"""
from datetime import datetime
from enum import Enum
from typing import Optional
from uuid import uuid4

from sqlalchemy import String, Text, ForeignKey, Index, DateTime, Boolean, Integer, Numeric, UniqueConstraint
from app.db.types import UUID, JSONB
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base, UUIDMixin, TenantMixin, AuditMixin


class PlanTipo(str, Enum):
    FREE = "FREE"
    INTERMEDIO = "INTERMEDIO"
    PRO = "PRO"
    ENTERPRISE = "ENTERPRISE"


# Orden de "cuánto desbloquea" cada plan -- se usa para comparar
# "¿el tenant tiene AL MENOS este plan?" sin depender del orden de
# declaración del Enum (que no garantiza orden útil una vez heredas de str).
ORDEN_PLAN = {
    PlanTipo.FREE: 0,
    PlanTipo.INTERMEDIO: 1,
    PlanTipo.PRO: 2,
    PlanTipo.ENTERPRISE: 3,
}


class EstadoSuscripcion(str, Enum):
    PENDIENTE_PAGO = "PENDIENTE_PAGO"
    ACTIVA = "ACTIVA"
    VENCIDA = "VENCIDA"
    CANCELADA = "CANCELADA"


class ProveedorPago(str, Enum):
    MERCADOPAGO = "MERCADOPAGO"
    STRIPE = "STRIPE"
    MANUAL = "MANUAL"  # bandera manual (GodAdmin activa el plan a mano)


class EstadoModulo(str, Enum):
    CORE = "core"
    DEMO = "demo"
    INTERNAL = "internal"
    ADMIN_ONLY = "admin_only"


class PlanLimite(Base, UUIDMixin):
    """Límites y precio de un plan. Una fila por PlanTipo.

    Configurable sin redeploy: GodAdmin puede editar estos números desde
    /api/v1/entitlements/planes/{plan} (ver app/api/v1/entitlements.py).
    Los valores default (sembrados por sembrar_planes_default) reflejan
    la propuesta de negocio: Free $0, Intermedio $49, Pro $249,
    Enterprise desde $699 o por contrato.
    """
    __tablename__ = "plan_limites"

    plan: Mapped[str] = mapped_column(String(20), unique=True, nullable=False, index=True)

    max_proyectos_activos: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)  # None = ilimitado
    max_corridas_costeo_mes: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    max_consultas_legl_mes: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    max_catalogos: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    max_usuarios: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)

    permite_api: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    permite_jobs_pesados: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    permite_multi_tenant: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)

    precio_mensual: Mapped[float] = mapped_column(Numeric(10, 2), default=0, nullable=False)
    moneda: Mapped[str] = mapped_column(String(3), default="MXN", nullable=False)

    # IDs del lado del proveedor de pago para crear el checkout de este
    # plan (price_id de Stripe, o el nombre/plan_id de MercadoPago).
    stripe_price_id: Mapped[Optional[str]] = mapped_column(String(255), nullable=True)
    mercadopago_plan_id: Mapped[Optional[str]] = mapped_column(String(255), nullable=True)


class TenantUso(Base, UUIDMixin, TenantMixin):
    """Contador de uso de un tenant en un periodo (mes calendario,
    formato 'YYYY-MM'). Se compara contra PlanLimite antes de dejar
    correr una acción medida (ver app.core.entitlements)."""
    __tablename__ = "tenant_uso"

    periodo: Mapped[str] = mapped_column(String(7), nullable=False, index=True)  # "2026-07"
    corridas_costeo: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    consultas_legl: Mapped[int] = mapped_column(Integer, default=0, nullable=False)

    __table_args__ = (
        UniqueConstraint("tenant_id", "periodo", name="uq_tenant_uso_periodo"),
    )


class Suscripcion(Base, UUIDMixin, TenantMixin, AuditMixin):
    """Registro de la suscripción de un tenant: qué plan, con qué
    proveedor, y su vigencia. Tenant.plan/plan_vencimiento (ver
    app/models/user.py) son la vista "actual" derivada de la ÚLTIMA
    suscripción activa; este modelo es el historial completo/auditable."""
    __tablename__ = "suscripciones"

    plan: Mapped[str] = mapped_column(String(20), nullable=False, index=True)
    proveedor: Mapped[str] = mapped_column(String(20), nullable=False)
    estado: Mapped[str] = mapped_column(String(20), default=EstadoSuscripcion.PENDIENTE_PAGO.value, index=True)

    # ID del recurso en el proveedor (preference_id de MP, subscription_id
    # de Stripe). Único por proveedor para poder reconciliar webhooks.
    external_id: Mapped[Optional[str]] = mapped_column(String(255), nullable=True, index=True)

    fecha_inicio: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)
    fecha_fin: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)

    monto: Mapped[Optional[float]] = mapped_column(Numeric(10, 2), nullable=True)
    moneda: Mapped[str] = mapped_column(String(3), default="MXN", nullable=False)

    # Payload crudo relevante del proveedor (para auditoría/soporte),
    # nunca datos de tarjeta -- eso lo maneja el proveedor, nunca toca
    # este backend (ni debe).
    metadatos: Mapped[Optional[dict]] = mapped_column(JSONB, nullable=True)

    __table_args__ = (
        Index("ix_suscripcion_tenant_estado", "tenant_id", "estado"),
        # CORREGIDO (F-07): external_id se documentaba como "único por
        # proveedor" pero solo tenía index=True, sin unique=True/constraint
        # -- nada impedía dos filas con el mismo (proveedor, external_id),
        # lo que además vuelve frágil el scalar_one_or_none() de
        # SuscripcionService.procesar_webhook() (tronaría con
        # MultipleResultsFound si llegaran a existir duplicados).
        UniqueConstraint("proveedor", "external_id", name="uq_suscripcion_proveedor_external_id"),
    )


class WebhookEventoProcesado(Base, UUIDMixin):
    """Deduplicación de webhooks de pago ya aplicados (F-07).

    Un webhook firmado y válido puede reenviarse/reproducirse (retry del
    proveedor, o una copia capturada y reproducida por un tercero dentro
    de la ventana de frescura de la firma) -- la firma HMAC sigue siendo
    válida en cada reenvío, así que la sola verificación de firma no basta
    para evitar aplicar el mismo efecto dos veces (p. ej. extender
    fecha_fin otros 31 días).

    `evento_id` es el campo "id" del cuerpo de la notificación de Mercado
    Pago -- el identificador de ESA entrega puntual, DISTINTO de
    data.id/external_id (que identifica al recurso/suscripción y se
    repite legítimamente en cada renovación mensual real). Antes de
    aplicar los efectos de un webhook se intenta insertar aquí
    (proveedor, evento_id) con restricción única; si ya existe, es un
    duplicado y no se vuelve a aplicar.
    """
    __tablename__ = "webhook_eventos_procesados"

    proveedor: Mapped[str] = mapped_column(String(20), nullable=False)
    evento_id: Mapped[str] = mapped_column(String(255), nullable=False)
    procesado_en: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)

    __table_args__ = (
        UniqueConstraint("proveedor", "evento_id", name="uq_webhook_evento_proveedor_id"),
    )


class AppModulo(Base, UUIDMixin):
    """Catálogo de módulos/apps del shell y su nivel de acceso.

    ANTES: el frontend (useAppRegistry.ts) era la única fuente de verdad
    de qué apps existen y con qué categoría -- puro adorno visual, nada
    lo hacía cumplir. Con esta tabla el BACKEND manda: el frontend pide
    GET /api/v1/entitlements/modulos y pinta el launcher según lo que el
    backend diga que este tenant/usuario puede abrir (ver
    app/api/v1/entitlements.py). Así un candado de plan no se puede
    saltar solo editando el bundle de React.
    """
    __tablename__ = "app_modulos"

    app_id: Mapped[str] = mapped_column(String(100), unique=True, nullable=False, index=True)
    nombre: Mapped[str] = mapped_column(String(255), nullable=False)
    estado: Mapped[str] = mapped_column(String(20), nullable=False, default=EstadoModulo.DEMO.value)

    # None = disponible en cualquier plan (incluido Free).
    requiere_plan: Mapped[Optional[str]] = mapped_column(String(20), nullable=True)
    # Lista de UserRole permitidos, p. ej. ["superadmin"] para admin_only.
    # None = cualquier rol autenticado.
    requiere_rol: Mapped[Optional[list]] = mapped_column(JSONB, nullable=True)

    activo: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)  # kill switch global
    orden: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
