# Copyright © 2026 Cristian Rodriguez
# All rights reserved.
# Unauthorized copying, modification, distribution, or use is prohibited
# without prior written permission.

"""
Modelos de programación de obra (CPM, PERT, EVM).
"""
from datetime import datetime
from enum import Enum
from uuid import uuid4
from typing import TYPE_CHECKING

from sqlalchemy import String, Text, Numeric, ForeignKey, ForeignKeyConstraint, Index, DateTime, Integer, Boolean, UniqueConstraint
from app.db.types import UUID, JSONB
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models.base import Base, UUIDMixin, AuditMixin, TenantMixin

if TYPE_CHECKING:
    from app.models.expediente import ExpedienteObra


class TipoDependencia(str, Enum):
    FIN_INICIO = "FS"
    INICIO_INICIO = "SS"
    FIN_FIN = "FF"
    INICIO_FIN = "SF"


class TipoActividad(str, Enum):
    CONSTRUCCION = "CONSTRUCCION"
    SUMINISTRO = "SUMINISTRO"
    INSTALACION = "INSTALACION"
    PRUEBA = "PRUEBA"
    DOCUMENTACION = "DOCUMENTACION"
    HITO = "HITO"


class EstadoPrograma(str, Enum):
    """No existía Enum -- era un str libre con default "PLANIFICADO" sin
    ninguna validación de qué otros valores eran válidos."""
    PLANIFICADO = "PLANIFICADO"
    EN_EJECUCION = "EN_EJECUCION"
    PAUSADO = "PAUSADO"
    COMPLETADO = "COMPLETADO"
    CANCELADO = "CANCELADO"


class ProgramaObra(Base, UUIDMixin, TenantMixin, AuditMixin):
    """Programa maestro de obra."""
    __tablename__ = "programas_obra"

    identificador: Mapped[str] = mapped_column(String(100), unique=False, nullable=False)
    nombre: Mapped[str] = mapped_column(String(500), nullable=False)
    descripcion: Mapped[str | None] = mapped_column(Text, nullable=True)

    # Fechas del programa
    fecha_inicio_plan: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    fecha_fin_plan: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    fecha_inicio_real: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    fecha_fin_real: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

    # Duración
    duracion_plan_dias: Mapped[int] = mapped_column(Integer, default=0)
    duracion_real_dias: Mapped[int | None] = mapped_column(Integer, nullable=True)

    # Estado (ver EstadoPrograma arriba)
    estado: Mapped[str] = mapped_column(String(50), default=EstadoPrograma.PLANIFICADO.value, index=True)

    # Resultados CPM
    resultado_cpm: Mapped[dict | None] = mapped_column(JSONB, nullable=True)
    resultado_pert: Mapped[dict | None] = mapped_column(JSONB, nullable=True)
    resultado_evm: Mapped[dict | None] = mapped_column(JSONB, nullable=True)

    # Relaciones
    expediente_id: Mapped[UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("expedientes_obra.id", ondelete="CASCADE"), nullable=False
    )
    expediente: Mapped["ExpedienteObra"] = relationship(
        "ExpedienteObra", foreign_keys=[expediente_id]
    )
    actividades: Mapped[list["ActividadPrograma"]] = relationship(
        "ActividadPrograma",
        back_populates="programa",
        cascade="all, delete-orphan",
        foreign_keys="ActividadPrograma.programa_id",
    )

    __table_args__ = (
        UniqueConstraint("expediente_id", "identificador", name="uq_programa_expediente_identificador"),
        Index("idx_programa_expediente", "expediente_id"),
        Index("idx_programa_tenant", "tenant_id"),
        UniqueConstraint("tenant_id", "id", name="uq_programa_tenant_id"),
        ForeignKeyConstraint(
            ["tenant_id", "expediente_id"],
            ["expedientes_obra.tenant_id", "expedientes_obra.id"],
            name="fk_programa_tenant_expediente",
            ondelete="CASCADE",
        ),
    )


class ActividadPrograma(Base, UUIDMixin, TenantMixin):
    """Actividad dentro de un programa de obra."""
    __tablename__ = "actividades_programa"

    identificador: Mapped[str] = mapped_column(String(50), nullable=False)
    nombre: Mapped[str] = mapped_column(String(500), nullable=False)
    descripcion: Mapped[str | None] = mapped_column(Text, nullable=True)

    # WBS
    wbs_codigo: Mapped[str] = mapped_column(String(50), default="")
    wbs_nivel: Mapped[int] = mapped_column(Integer, default=0)

    # Duración
    duracion: Mapped[float] = mapped_column(Numeric(8, 2), default=0.0)
    duracion_optimista: Mapped[float | None] = mapped_column(Numeric(8, 2), nullable=True)
    duracion_probable: Mapped[float | None] = mapped_column(Numeric(8, 2), nullable=True)
    duracion_pesimista: Mapped[float | None] = mapped_column(Numeric(8, 2), nullable=True)

    # Tipo
    tipo: Mapped[str] = mapped_column(String(50), default="CONSTRUCCION")

    # Costos
    costo_presupuestado: Mapped[float] = mapped_column(Numeric(18, 2), default=0.0)
    costo_real: Mapped[float] = mapped_column(Numeric(18, 2), default=0.0)

    # Avance
    porcentaje_avance: Mapped[float] = mapped_column(Numeric(5, 2), default=0.0)

    # Fechas CPM
    inicio_temprano: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    fin_temprano: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    inicio_tardio: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    fin_tardio: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

    # Holgura
    holgura_total: Mapped[float] = mapped_column(Numeric(8, 2), default=0.0)
    holgura_libre: Mapped[float] = mapped_column(Numeric(8, 2), default=0.0)
    en_ruta_critica: Mapped[bool] = mapped_column(Boolean, default=False)

    # Dependencias
    predecesoras: Mapped[list[str] | None] = mapped_column(JSONB, default=list)
    dependencias_tipo: Mapped[dict | None] = mapped_column(JSONB, default=dict)

    # Metadatos
    metadatos: Mapped[dict | None] = mapped_column(JSONB, default=dict)

    # Relaciones
    programa_id: Mapped[UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("programas_obra.id", ondelete="CASCADE"), nullable=False, index=True
    )
    programa: Mapped["ProgramaObra"] = relationship(
        "ProgramaObra", back_populates="actividades", foreign_keys=[programa_id]
    )

    __table_args__ = (
        Index("idx_actividad_tenant", "tenant_id"),
        ForeignKeyConstraint(
            ["tenant_id", "programa_id"],
            ["programas_obra.tenant_id", "programas_obra.id"],
            name="fk_actividad_tenant_programa",
            ondelete="CASCADE",
        ),
    )
