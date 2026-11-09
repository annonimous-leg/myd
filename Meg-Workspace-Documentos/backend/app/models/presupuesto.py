# Copyright © 2026 Cristian Rodriguez
# All rights reserved.
# Unauthorized copying, modification, distribution, or use is prohibited
# without prior written permission.

"""
Modelos de presupuesto, partidas, conceptos e insumos.
"""
from enum import Enum
from uuid import uuid4
from typing import TYPE_CHECKING

from sqlalchemy import CheckConstraint, String, Text, Numeric, ForeignKey, ForeignKeyConstraint, Index, Integer, UniqueConstraint
from app.db.types import UUID, JSONB
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models.base import Base, UUIDMixin, AuditMixin, TenantMixin

if TYPE_CHECKING:
    from app.models.expediente import ExpedienteObra


class ZonaEconomica(str, Enum):
    NORTE = "NORTE"
    CENTRO = "CENTRO"
    SUR = "SUR"
    NOROESTE = "NOROESTE"
    NORESTE = "NORESTE"
    OCCIDENTE = "OCCIDENTE"
    SURESTE = "SURESTE"


class TipoInsumo(str, Enum):
    MATERIAL = "MATERIAL"
    MANO_OBRA = "MANO_OBRA"
    EQUIPO = "EQUIPO"
    SUBCONTRATO = "SUBCONTRATO"
    HERRAMIENTA = "HERRAMIENTA"


class EstadoPresupuesto(str, Enum):
    """No existía ningún campo de estado en Presupuesto -- el artefacto
    central del sistema no distinguía borrador de aprobado. BORRADOR al
    crear; CALCULADO después de recalcular() (ver PresupuestoService);
    VALIDADO/RECHAZADO los pone el flujo de validadores; APROBADO es una
    acción explícita separada de "validado" (puede pasar validadores y
    aun así no estar autorizado para ejecutarse)."""
    BORRADOR = "BORRADOR"
    CALCULADO = "CALCULADO"
    VALIDADO = "VALIDADO"
    RECHAZADO = "RECHAZADO"
    APROBADO = "APROBADO"


class Presupuesto(Base, UUIDMixin, TenantMixin, AuditMixin):
    """Presupuesto programable de obra.

    tenant_id es denormalizado desde expediente.tenant_id (ver
    PresupuestoService.crear_desde_costeo / BaseService.create): se fija
    una sola vez al crear y nunca se recalcula por FK, precisamente para
    que BaseService pueda filtrar/aislar por tenant sin tener que hacer
    join a expedientes_obra en cada query. La FK compuesta
    (tenant_id, expediente_id) hace que sea imposible a nivel de DB que
    un presupuesto quede asociado a un expediente de otro tenant.
    """
    __tablename__ = "presupuestos"

    identificador: Mapped[str] = mapped_column(String(100), unique=False, nullable=False)
    nombre: Mapped[str] = mapped_column(String(500), nullable=False)
    descripcion: Mapped[str | None] = mapped_column(Text, nullable=True)

    # Montos
    monto_directo: Mapped[float] = mapped_column(Numeric(18, 2), default=0.0)
    monto_indirecto: Mapped[float] = mapped_column(Numeric(18, 2), default=0.0)
    monto_financiamiento: Mapped[float] = mapped_column(Numeric(18, 2), default=0.0)
    monto_utilidad: Mapped[float] = mapped_column(Numeric(18, 2), default=0.0)
    monto_riesgo: Mapped[float | None] = mapped_column(Numeric(18, 2), nullable=True)
    monto_cargos_adicionales: Mapped[float] = mapped_column(Numeric(18, 2), default=0.0)
    monto_impuesto: Mapped[float] = mapped_column(Numeric(18, 2), default=0.0)
    monto_total: Mapped[float] = mapped_column(Numeric(18, 2), default=0.0)
    moneda: Mapped[str] = mapped_column(String(3), default="MXN")

    # Factores
    factor_indirecto: Mapped[float] = mapped_column(Numeric(8, 4), nullable=False)
    factor_financiamiento: Mapped[float] = mapped_column(Numeric(8, 4), nullable=False, default=0.0)
    factor_utilidad: Mapped[float] = mapped_column(Numeric(8, 4), nullable=False)
    factor_cargos_adicionales: Mapped[float] = mapped_column(Numeric(8, 4), nullable=False, default=0.0)
    factor_impuesto: Mapped[float] = mapped_column(Numeric(8, 4), nullable=False)
    factor_riesgo: Mapped[float | None] = mapped_column(Numeric(8, 4), nullable=True)
    zona_economica: Mapped[ZonaEconomica] = mapped_column(String(50), default=ZonaEconomica.CENTRO)
    plazo_dias: Mapped[int | None] = mapped_column(nullable=True)
    metadatos: Mapped[dict | None] = mapped_column(JSONB, default=dict)

    # Resultados
    resultado_montecarlo: Mapped[dict | None] = mapped_column(JSONB, nullable=True)
    resultado_determinista: Mapped[dict | None] = mapped_column(JSONB, nullable=True)

    # Estado del ciclo de vida (ver EstadoPresupuesto arriba)
    estado: Mapped[str] = mapped_column(String(20), default=EstadoPresupuesto.BORRADOR.value, index=True)

    # Relaciones
    # Nota: la FK simple a expedientes_obra.id se mantiene por compatibilidad
    # (varias queries existentes hacen join solo por expediente_id), pero la
    # integridad tenant real la da el ForeignKeyConstraint compuesto de abajo.
    expediente_id: Mapped[UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("expedientes_obra.id", ondelete="CASCADE"), nullable=False, index=True
    )
    expediente: Mapped["ExpedienteObra"] = relationship(
        "ExpedienteObra",
        back_populates="presupuestos",
        foreign_keys=[expediente_id],
    )
    partidas: Mapped[list["Partida"]] = relationship(
        "Partida",
        back_populates="presupuesto",
        cascade="all, delete-orphan",
        foreign_keys="Partida.presupuesto_id",
    )

    __table_args__ = (
        UniqueConstraint("expediente_id", "identificador", name="uq_presupuesto_expediente_identificador"),
        Index("idx_presupuesto_expediente", "expediente_id"),
        Index("idx_presupuesto_tenant", "tenant_id"),
        # Unique compuesta para que Partida pueda anclarse a (tenant_id, presupuesto_id).
        UniqueConstraint("tenant_id", "id", name="uq_presupuesto_tenant_id"),
        ForeignKeyConstraint(
            ["tenant_id", "expediente_id"],
            ["expedientes_obra.tenant_id", "expedientes_obra.id"],
            name="fk_presupuesto_tenant_expediente",
            ondelete="CASCADE",
        ),
        CheckConstraint("factor_indirecto BETWEEN 0 AND 1", name="ck_presupuesto_factor_indirecto"),
        CheckConstraint("factor_financiamiento BETWEEN 0 AND 1", name="ck_presupuesto_factor_financiamiento"),
        CheckConstraint("factor_utilidad BETWEEN 0 AND 1", name="ck_presupuesto_factor_utilidad"),
        CheckConstraint("factor_cargos_adicionales BETWEEN 0 AND 1", name="ck_presupuesto_factor_cargos_adicionales"),
        CheckConstraint("factor_impuesto BETWEEN 0 AND 1", name="ck_presupuesto_factor_impuesto"),
        CheckConstraint("factor_riesgo BETWEEN 0 AND 1", name="ck_presupuesto_factor_riesgo"),
    )


class Partida(Base, UUIDMixin, TenantMixin):
    """Partida de presupuesto."""
    __tablename__ = "partidas"

    numero: Mapped[int] = mapped_column(Integer, nullable=False)
    descripcion: Mapped[str] = mapped_column(Text, nullable=False)
    unidad: Mapped[str] = mapped_column(String(20), nullable=False)
    cantidad: Mapped[float] = mapped_column(Numeric(18, 4), nullable=False)
    precio_unitario: Mapped[float] = mapped_column(Numeric(18, 2), nullable=False)
    importe: Mapped[float] = mapped_column(Numeric(18, 2), nullable=False)

    # Proveniencia de cuantificación/importación (OCR, BIM, manual, etc.).
    # Antes OCRService ya intentaba persistir este campo, pero el modelo y
    # la migración no lo tenían: cualquier OCR con presupuesto tronaba al
    # construir Partida antes de llegar siquiera al commit.
    metadatos: Mapped[dict] = mapped_column(JSONB, default=dict, nullable=False)

    # BIM
    elemento_tipo: Mapped[str | None] = mapped_column(String(100), nullable=True)
    elemento_ifc_id: Mapped[str | None] = mapped_column(String(100), nullable=True)

    # Relaciones
    presupuesto_id: Mapped[UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("presupuestos.id", ondelete="CASCADE"), nullable=False, index=True
    )
    presupuesto: Mapped["Presupuesto"] = relationship(
        "Presupuesto", back_populates="partidas", foreign_keys=[presupuesto_id]
    )
    conceptos: Mapped[list["Concepto"]] = relationship(
        "Concepto",
        back_populates="partida",
        cascade="all, delete-orphan",
        foreign_keys="Concepto.partida_id",
    )

    __table_args__ = (
        Index("idx_partida_tenant", "tenant_id"),
        UniqueConstraint("tenant_id", "id", name="uq_partida_tenant_id"),
        ForeignKeyConstraint(
            ["tenant_id", "presupuesto_id"],
            ["presupuestos.tenant_id", "presupuestos.id"],
            name="fk_partida_tenant_presupuesto",
            ondelete="CASCADE",
        ),
    )


class Concepto(Base, UUIDMixin, TenantMixin):
    """Concepto de APU (Análisis de Precios Unitarios)."""
    __tablename__ = "conceptos"

    clave: Mapped[str] = mapped_column(String(50), nullable=False)
    descripcion: Mapped[str] = mapped_column(Text, nullable=False)
    unidad: Mapped[str] = mapped_column(String(20), nullable=False)
    cantidad: Mapped[float] = mapped_column(Numeric(18, 4), default=1.0)

    # Costos
    costo_directo_unitario: Mapped[float] = mapped_column(Numeric(18, 2), default=0.0)

    # Relaciones
    partida_id: Mapped[UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("partidas.id", ondelete="CASCADE"), nullable=False, index=True
    )
    partida: Mapped["Partida"] = relationship(
        "Partida", back_populates="conceptos", foreign_keys=[partida_id]
    )
    insumos: Mapped[list["Insumo"]] = relationship(
        "Insumo",
        back_populates="concepto",
        cascade="all, delete-orphan",
        foreign_keys="Insumo.concepto_id",
    )

    __table_args__ = (
        Index("idx_concepto_tenant", "tenant_id"),
        UniqueConstraint("tenant_id", "id", name="uq_concepto_tenant_id"),
        ForeignKeyConstraint(
            ["tenant_id", "partida_id"],
            ["partidas.tenant_id", "partidas.id"],
            name="fk_concepto_tenant_partida",
            ondelete="CASCADE",
        ),
    )


class Insumo(Base, UUIDMixin, TenantMixin):
    """Insumo de un concepto APU."""
    __tablename__ = "insumos"

    clave: Mapped[str] = mapped_column(String(50), nullable=False)
    descripcion: Mapped[str] = mapped_column(Text, nullable=False)
    tipo: Mapped[TipoInsumo] = mapped_column(String(50), nullable=False)
    unidad: Mapped[str] = mapped_column(String(20), nullable=False)
    cantidad: Mapped[float] = mapped_column(Numeric(20, 6), nullable=False)
    precio_unitario: Mapped[float] = mapped_column(Numeric(18, 2), nullable=False)
    importe: Mapped[float] = mapped_column(Numeric(18, 2), nullable=False)

    # Fuente del catálogo
    fuente_catalogo: Mapped[str | None] = mapped_column(String(100), nullable=True)
    actualizacion_precio: Mapped[dict | None] = mapped_column(JSONB, nullable=True)
    rendimiento: Mapped[float] = mapped_column(Numeric(8, 4), default=1.0)

    # Relaciones
    concepto_id: Mapped[UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("conceptos.id", ondelete="CASCADE"), nullable=False, index=True
    )
    concepto: Mapped["Concepto"] = relationship(
        "Concepto", back_populates="insumos", foreign_keys=[concepto_id]
    )

    __table_args__ = (
        Index("idx_insumo_tenant", "tenant_id"),
        ForeignKeyConstraint(
            ["tenant_id", "concepto_id"],
            ["conceptos.tenant_id", "conceptos.id"],
            name="fk_insumo_tenant_concepto",
            ondelete="CASCADE",
        ),
    )
