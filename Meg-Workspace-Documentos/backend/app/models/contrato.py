# Copyright © 2026 Cristian Rodriguez
# All rights reserved.
# Unauthorized copying, modification, distribution, or use is prohibited
# without prior written permission.

"""
Modelos de contratos, convenios modificatorios y administración contractual.
Incluye: estimaciones, entregables, garantías, penas, finiquito.
"""
from enum import Enum
from uuid import uuid4
from typing import TYPE_CHECKING

from sqlalchemy import String, Text, Numeric, ForeignKey, Index, DateTime, Integer, Boolean, UniqueConstraint
from app.db.types import UUID, JSONB
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models.base import Base, UUIDMixin, TenantMixin, AuditMixin

if TYPE_CHECKING:
    from app.models.expediente import ExpedienteObra
    from app.models.licitacion import Licitacion
    from app.models.proveedor import Proveedor


class EstadoContrato(str, Enum):
    EN_FIRMA = "EN_FIRMA"
    VIGENTE = "VIGENTE"
    EN_MODIFICACION = "EN_MODIFICACION"
    SUSPENDIDO = "SUSPENDIDO"
    TERMINADO = "TERMINADO"
    RESCINDIDO = "RESCINDIDO"
    CERRADO = "CERRADO"


class TipoGarantia(str, Enum):
    CUMPLIMIENTO = "CUMPLIMIENTO"
    ANTICIPO = "ANTICIPO"
    VICIOS_OCULTOS = "VICIOS_OCULTOS"
    ESTABILIDAD = "ESTABILIDAD"


class TipoModificacion(str, Enum):
    PLAZO = "PLAZO"
    MONTO = "MONTO"
    ALCANCE = "ALCANCE"
    PRECIO_UNITARIO = "PRECIO_UNITARIO"


class TipoPenalizacion(str, Enum):
    ATRASO = "ATRASO"
    INCUMPLIMIENTO = "INCUMPLIMIENTO"
    CALIDAD = "CALIDAD"
    SEGURIDAD = "SEGURIDAD"


class Contrato(Base, UUIDMixin, TenantMixin, AuditMixin):
    """Contrato de obra pública o adquisición con administración completa."""
    __tablename__ = "contratos"

    expediente_id: Mapped[str] = mapped_column(
        UUID(as_uuid=True), ForeignKey("expedientes_obra.id", ondelete="CASCADE"), nullable=False, index=True
    )
    licitacion_id: Mapped[str | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("licitaciones.id", ondelete="SET NULL"), nullable=True
    )
    proveedor_id: Mapped[str] = mapped_column(
        UUID(as_uuid=True), ForeignKey("proveedores.id", ondelete="RESTRICT"), nullable=False
    )

    numero_contrato: Mapped[str] = mapped_column(String(100), unique=False, nullable=False, index=True)
    estado: Mapped[EstadoContrato] = mapped_column(String(50), default=EstadoContrato.EN_FIRMA, index=True)

    # Partes
    objeto: Mapped[str] = mapped_column(Text, nullable=False)
    monto_total: Mapped[float] = mapped_column(Numeric(18, 4), nullable=False)
    monto_original: Mapped[float | None] = mapped_column(Numeric(18, 4), nullable=True)
    plazo_dias: Mapped[int] = mapped_column(nullable=False)
    plazo_original: Mapped[int | None] = mapped_column(nullable=True)

    # Fechas
    fecha_firma: Mapped[str | None] = mapped_column(String(10), nullable=True)
    fecha_inicio: Mapped[str | None] = mapped_column(String(10), nullable=True)
    fecha_termino: Mapped[str | None] = mapped_column(String(10), nullable=True)
    fecha_termino_original: Mapped[str | None] = mapped_column(String(10), nullable=True)

    # Cláusulas y obligaciones
    clausulas: Mapped[dict | None] = mapped_column(JSONB, nullable=True)
    obligaciones: Mapped[dict | None] = mapped_column(JSONB, nullable=True)

    # Administración contractual
    anticipo_otorgado: Mapped[float] = mapped_column(Numeric(18, 4), default=0)
    avance_fisico: Mapped[float] = mapped_column(Numeric(5, 2), default=0)
    avance_financiero: Mapped[float] = mapped_column(Numeric(5, 2), default=0)

    # Finiquito
    fecha_finiquito: Mapped[str | None] = mapped_column(String(10), nullable=True)
    monto_finiquito: Mapped[float | None] = mapped_column(Numeric(18, 4), nullable=True)

    # Relaciones
    expediente: Mapped["ExpedienteObra"] = relationship("ExpedienteObra", back_populates="contratos")
    licitacion: Mapped["Licitacion"] = relationship("Licitacion", back_populates="contrato")
    proveedor: Mapped["Proveedor"] = relationship("Proveedor", back_populates="contratos")
    modificatorios: Mapped[list["ConvenioModificatorio"]] = relationship("ConvenioModificatorio", back_populates="contrato", cascade="all, delete-orphan")
    garantias: Mapped[list["GarantiaContrato"]] = relationship("GarantiaContrato", back_populates="contrato", cascade="all, delete-orphan")
    entregables: Mapped[list["EntregableContrato"]] = relationship("EntregableContrato", back_populates="contrato", cascade="all, delete-orphan")
    penalizaciones: Mapped[list["PenalizacionContrato"]] = relationship("PenalizacionContrato", back_populates="contrato", cascade="all, delete-orphan")

    __table_args__ = (
        UniqueConstraint("expediente_id", "numero_contrato", name="uq_contrato_expediente_numero"),
        UniqueConstraint("licitacion_id", name="uq_contrato_licitacion"),
    )


class ConvenioModificatorio(Base, UUIDMixin, TenantMixin, AuditMixin):
    """Convenio modificatorio al contrato."""
    __tablename__ = "convenios_modificatorios"

    contrato_id: Mapped[str] = mapped_column(
        UUID(as_uuid=True), ForeignKey("contratos.id", ondelete="CASCADE"), nullable=False, index=True
    )

    numero: Mapped[str] = mapped_column(String(50), nullable=False)
    tipo: Mapped[TipoModificacion] = mapped_column(String(50), nullable=False)
    descripcion: Mapped[str | None] = mapped_column(Text, nullable=True)

    monto_anterior: Mapped[float | None] = mapped_column(Numeric(18, 4), nullable=True)
    monto_nuevo: Mapped[float | None] = mapped_column(Numeric(18, 4), nullable=True)
    plazo_anterior: Mapped[int | None] = mapped_column(nullable=True)
    plazo_nuevo: Mapped[int | None] = mapped_column(nullable=True)
    justificacion: Mapped[str | None] = mapped_column(Text, nullable=True)

    # Legal: aprobación
    aprobado_por: Mapped[str | None] = mapped_column(UUID(as_uuid=True), ForeignKey("users.id", ondelete="SET NULL"), nullable=True)
    fecha_aprobacion: Mapped[str | None] = mapped_column(String(10), nullable=True)

    contrato: Mapped["Contrato"] = relationship("Contrato", back_populates="modificatorios")


class GarantiaContrato(Base, UUIDMixin, TenantMixin, AuditMixin):
    """Garantía del contrato (cumplimiento, anticipo, etc.)."""
    __tablename__ = "garantias_contrato"

    contrato_id: Mapped[str] = mapped_column(
        UUID(as_uuid=True), ForeignKey("contratos.id", ondelete="CASCADE"), nullable=False, index=True
    )

    tipo: Mapped[TipoGarantia] = mapped_column(String(50), nullable=False)
    monto: Mapped[float] = mapped_column(Numeric(18, 4), nullable=False)
    institucion: Mapped[str | None] = mapped_column(String(200), nullable=True)
    numero_poliza: Mapped[str | None] = mapped_column(String(100), nullable=True)
    vigencia_inicio: Mapped[str | None] = mapped_column(String(10), nullable=True)
    vigencia_fin: Mapped[str | None] = mapped_column(String(10), nullable=True)

    # Estados
    activa: Mapped[bool] = mapped_column(Boolean, default=True)
    liberada: Mapped[bool] = mapped_column(Boolean, default=False)
    ejecutada: Mapped[bool] = mapped_column(Boolean, default=False)
    fecha_liberacion: Mapped[str | None] = mapped_column(String(10), nullable=True)

    contrato: Mapped["Contrato"] = relationship("Contrato", back_populates="garantias")


class EntregableContrato(Base, UUIDMixin, TenantMixin, AuditMixin):
    """Estimación / entregable del contrato."""
    __tablename__ = "entregables_contrato"

    contrato_id: Mapped[str] = mapped_column(
        UUID(as_uuid=True), ForeignKey("contratos.id", ondelete="CASCADE"), nullable=False, index=True
    )

    numero_estimacion: Mapped[int] = mapped_column(nullable=False)
    periodo_inicio: Mapped[str | None] = mapped_column(String(10), nullable=True)
    periodo_fin: Mapped[str | None] = mapped_column(String(10), nullable=True)
    monto_ejecutado: Mapped[float] = mapped_column(Numeric(18, 4), default=0)
    avance_fisico: Mapped[float] = mapped_column(Numeric(5, 2), default=0)
    avance_financiero: Mapped[float] = mapped_column(Numeric(5, 2), default=0)

    # Legal: aprobación
    aprobado: Mapped[bool] = mapped_column(Boolean, default=False)
    fecha_aprobacion: Mapped[str | None] = mapped_column(String(10), nullable=True)
    aprobado_por: Mapped[str | None] = mapped_column(UUID(as_uuid=True), ForeignKey("users.id", ondelete="SET NULL"), nullable=True)

    contrato: Mapped["Contrato"] = relationship("Contrato", back_populates="entregables")


class PenalizacionContrato(Base, UUIDMixin, TenantMixin, AuditMixin):
    """Penalización / retención por incumplimiento."""
    __tablename__ = "penalizaciones_contrato"

    contrato_id: Mapped[str] = mapped_column(
        UUID(as_uuid=True), ForeignKey("contratos.id", ondelete="CASCADE"), nullable=False, index=True
    )

    tipo: Mapped[TipoPenalizacion] = mapped_column(String(50), nullable=False)
    monto: Mapped[float] = mapped_column(Numeric(18, 4), nullable=False)
    dias_atraso: Mapped[int | None] = mapped_column(nullable=True)
    descripcion: Mapped[str] = mapped_column(Text, nullable=False)

    # Legal: tope máximo
    tope_legal: Mapped[float] = mapped_column(Numeric(18, 4), nullable=False)
    dentro_tope: Mapped[bool] = mapped_column(Boolean, default=True)

    # Estado
    aplicada: Mapped[bool] = mapped_column(Boolean, default=False)
    fecha_aplicacion: Mapped[str | None] = mapped_column(String(10), nullable=True)

    contrato: Mapped["Contrato"] = relationship("Contrato", back_populates="penalizaciones")
