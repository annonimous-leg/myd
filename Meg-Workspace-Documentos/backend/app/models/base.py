# Copyright © 2026 Cristian Rodriguez
# All rights reserved.
# Unauthorized copying, modification, distribution, or use is prohibited
# without prior written permission.

"""
Base declarativa SQLAlchemy 2.0 con soporte PostGIS.

Este módulo también es la única fuente de verdad del engine async y de las
sesiones de base de datos. Antes, cada router creaba su propio `engine` y
`sessionmaker` duplicados (y varios importaban `engine` desde aquí sin que
existiera), lo que provocaba un ImportError inmediato al arrancar la app.
Ahora el engine se crea una sola vez aquí y todos los routers deben usar
`app.core.deps.get_db` para obtener una sesión.
"""
from datetime import datetime
from enum import Enum as PyEnum
from typing import AsyncIterator, Optional
from uuid import uuid4, UUID as UUIDType

from sqlalchemy import DateTime, ForeignKey, func
from app.db.types import UUID
from sqlalchemy.ext.asyncio import (
    AsyncEngine,
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column
from sqlalchemy.pool import NullPool

from app.config import settings


class Base(DeclarativeBase):
    """Base declarativa con columnas comunes."""

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        nullable=False,
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        onupdate=func.now(),
        nullable=False,
    )


class TenantMixin:
    """Mixin para multi-tenancy."""
    tenant_id: Mapped[UUID] = mapped_column(
        UUID(as_uuid=True),
        # BUG ORIGINAL: no tenía ForeignKey, así que cualquier
        # relationship("Tenant", ...) definida en un modelo que use este
        # mixin (User, ExpedienteObra) tronaba con NoForeignKeysError al
        # configurar los mappers, es decir, en la primera request.
        ForeignKey("tenants.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )


class UUIDMixin:
    """Mixin para IDs UUID."""
    id: Mapped[UUID] = mapped_column(
        UUID(as_uuid=True),
        primary_key=True,
        default=uuid4,
    )


class AuditMixin:
    """Mixin de auditoría: quién creó y quién modificó por última vez un
    registro. Se aplica a los agregados raíz (lo que un usuario crea con
    una acción explícita: expediente, documento, presupuesto, modelo BIM,
    análisis de clash, levantamiento, cálculo de volumen, programa,
    validación) -- no a las entidades hijas que se insertan en lote como
    parte de esa acción (partida/concepto/insumo, elemento BIM, actividad
    de programa, punto topográfico, resultado de clash individual), donde
    el creado_por_id del padre ya cubre la trazabilidad de "quién" sin
    duplicar la columna en miles de filas.

    Nullable a propósito: hay registros que se crean desde un worker
    async sin que haya un usuario humano en ese momento exacto de la
    ejecución (aunque sí lo haya en el request que disparó la tarea). No
    se fuerza un usuario ficticio "sistema" porque eso ensuciaría la
    trazabilidad real -- null significa honestamente "no se registró
    quién", no "lo hizo el sistema".

    BaseService.create()/update() (ver app/services/base.py) ya llenan
    estas columnas automáticamente cuando se les pasa creado_por_id/
    actualizado_por_id -- los servicios de cada dominio no necesitan
    lógica propia para esto."""
    creado_por_id: Mapped[Optional[UUID]] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id", ondelete="SET NULL"), nullable=True, index=True
    )
    actualizado_por_id: Mapped[Optional[UUID]] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id", ondelete="SET NULL"), nullable=True
    )


class EstadoProceso(str, PyEnum):
    """Estado canónico para cualquier operación de procesamiento
    asíncrono/de larga duración (BIM, clash detection, y lo que se sume
    después -- OCR, exportaciones). Antes había dos enums casi idénticos
    con nombres distintos para "terminó bien" (EstadoProcesamientoBIM.
    PROCESADO vs EstadoAnalisisClash.COMPLETADO) -- se unifican aquí."""
    PENDIENTE = "PENDIENTE"
    EN_PROCESO = "EN_PROCESO"
    COMPLETADO = "COMPLETADO"
    ERROR = "ERROR"


# ─── Engine y sesión (única fuente de verdad) ────────────────────────
# BUG ORIGINAL: este módulo nunca creaba `engine`, pero 7 archivos de
# app/api/v1/*.py hacían `from app.models.base import engine` y además
# cada uno definía su propio sessionmaker duplicado -> ImportError al
# importar cualquier router, la app no arrancaba.
_database_connection = settings.database_connection
_engine_kwargs = {
    "echo": settings.DEBUG,
    "pool_pre_ping": True,
}
if settings.database_async_url.startswith("sqlite"):
    _engine_kwargs.update(
        {
            "connect_args": {"check_same_thread": False},
            "poolclass": NullPool,
        }
    )
else:
    _engine_kwargs.update(
        {
            "pool_size": settings.DATABASE_POOL_SIZE,
            "max_overflow": settings.DATABASE_MAX_OVERFLOW,
        }
    )
    if _database_connection.connect_args:
        _engine_kwargs["connect_args"] = _database_connection.connect_args

engine: AsyncEngine = create_async_engine(
    _database_connection.url,
    **_engine_kwargs,
)

AsyncSessionLocal = async_sessionmaker(
    engine,
    class_=AsyncSession,
    expire_on_commit=False,
    autoflush=False,
)


async def get_session() -> AsyncIterator[AsyncSession]:
    """Generador de sesión de base de datos por request.

    Vive aquí (y no solo en app.core.deps) para que sea importable sin
    ciclos desde cualquier módulo que ya dependa de app.models.base.
    """
    async with AsyncSessionLocal() as session:
        yield session
