# Copyright © 2026 Cristian Rodriguez
# All rights reserved.
# Unauthorized copying, modification, distribution, or use is prohibited
# without prior written permission.

"""
Modelos de expediente electrónico.
"""
from datetime import datetime
from enum import Enum
from uuid import uuid4
from typing import TYPE_CHECKING

from sqlalchemy import UniqueConstraint, String, Text, Numeric, ForeignKey, Index, DateTime, Integer
from app.db.types import UUID, JSONB
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models.base import Base, UUIDMixin, TenantMixin, AuditMixin

if TYPE_CHECKING:
    from app.models.compliance import Inconformidad
    from app.models.contrato import Contrato
    from app.models.documento import DocumentoCDE
    from app.models.licitacion import Licitacion
    from app.models.presupuesto import Presupuesto
    from app.models.user import Tenant, User


class EstadoExpediente(str, Enum):
    INICIADO = "INICIADO"
    EN_TRAMITE = "EN_TRAMITE"
    PENDIENTE_DOCUMENTACION = "PENDIENTE_DOCUMENTACION"
    EN_FIRMA = "EN_FIRMA"
    ARCHIVADO = "ARCHIVADO"
    CERRADO = "CERRADO"
    EN_INTEROPERABILIDAD = "EN_INTEROPERABILIDAD"


class ClasificacionSeguridad(str, Enum):
    PUBLICO = "PUBLICO"
    RESERVADO = "RESERVADO"
    CONFIDENCIAL = "CONFIDENCIAL"


class TipoContrato(str, Enum):
    PRECIOS_UNITARIOS = "PRECIOS_UNITARIOS"
    PRECIO_ALZADO = "PRECIO_ALZADO"
    MIXTO = "MIXTO"
    OBRA_PUBLICA = "OBRA_PUBLICA"
    SERVICIO_RELACIONADO = "SERVICIO_RELACIONADO"
    ADQUISICION = "ADQUISICION"


class ExpedienteObra(Base, UUIDMixin, TenantMixin, AuditMixin):
    """Expediente de obra pública."""
    __tablename__ = "expedientes_obra"

    identificador: Mapped[str] = mapped_column(
        String(100), unique=False, nullable=False, index=True
    )
    titulo: Mapped[str] = mapped_column(String(500), nullable=False)
    descripcion: Mapped[str | None] = mapped_column(Text, nullable=True)
    organo: Mapped[str] = mapped_column(String(255), nullable=False)
    unidad_administrativa: Mapped[str] = mapped_column(String(255), nullable=False)
    serie_documental: Mapped[str] = mapped_column(String(100), nullable=False)
    subserie_documental: Mapped[str] = mapped_column(String(100), nullable=False)

    # Datos de obra
    proyecto_id: Mapped[str | None] = mapped_column(String(100), nullable=True)
    proyecto_nombre: Mapped[str | None] = mapped_column(String(500), nullable=True)
    ubicacion_obra: Mapped[str | None] = mapped_column(Text, nullable=True)
    monto_contrato: Mapped[float | None] = mapped_column(Numeric(18, 2), nullable=True)
    plazo_dias: Mapped[int | None] = mapped_column(nullable=True)
    tipo_contrato: Mapped[TipoContrato] = mapped_column(
        String(50), default=TipoContrato.PRECIOS_UNITARIOS
    )

    # Estado y clasificación
    estado: Mapped[EstadoExpediente] = mapped_column(
        String(50), default=EstadoExpediente.INICIADO, index=True
    )
    clasificacion: Mapped[ClasificacionSeguridad] = mapped_column(
        String(50), default=ClasificacionSeguridad.PUBLICO
    )

    # Responsables
    responsable_tecnico: Mapped[str | None] = mapped_column(String(255), nullable=True)
    responsable_ejecutivo: Mapped[str | None] = mapped_column(String(255), nullable=True)
    responsable_id: Mapped[UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id", ondelete="SET NULL"), nullable=True
    )

    # Metadatos
    metadatos: Mapped[dict | None] = mapped_column(JSONB, default=dict)
    merkle_root: Mapped[str | None] = mapped_column(String(64), nullable=True)

    # Relaciones
    tenant: Mapped["Tenant"] = relationship("Tenant", back_populates="expedientes")
    responsable_user: Mapped["User"] = relationship(
        "User",
        back_populates="expedientes",
        foreign_keys=[responsable_id],
    )
    documentos: Mapped[list["Documento"]] = relationship(
        "Documento", back_populates="expediente", cascade="all, delete-orphan"
    )
    presupuestos: Mapped[list["Presupuesto"]] = relationship(
        "Presupuesto",
        back_populates="expediente",
        cascade="all, delete-orphan",
        foreign_keys="Presupuesto.expediente_id",
    )

    __table_args__ = (
        UniqueConstraint("tenant_id", "identificador", name="uq_expediente_tenant_identificador"),
        # Requerido para que hijos (Presupuesto, ProgramaObra, TenderPackage,
        # Licitacion, Levantamiento, ...) puedan declarar una FK compuesta
        # (tenant_id, expediente_id) -> (tenant_id, id) y así hacer
        # imposible a nivel de DB una asociación cross-tenant.
        UniqueConstraint("tenant_id", "id", name="uq_expediente_tenant_id"),
        Index("idx_expediente_estado_tenant", "tenant_id", "estado"),
        Index("idx_expediente_organo", "organo"),
    )



    # ─── Relaciones del ciclo de contratación ───────────────────
    licitaciones: Mapped[list["Licitacion"]] = relationship(
        "Licitacion", back_populates="expediente", cascade="all, delete-orphan"
    )
    contratos: Mapped[list["Contrato"]] = relationship(
        "Contrato", back_populates="expediente", cascade="all, delete-orphan"
    )
    documentos_cde: Mapped[list["DocumentoCDE"]] = relationship(
        "DocumentoCDE", back_populates="expediente", cascade="all, delete-orphan"
    )
    inconformidades: Mapped[list["Inconformidad"]] = relationship(
        "Inconformidad", back_populates="expediente", cascade="all, delete-orphan"
    )

class Documento(Base, UUIDMixin, AuditMixin):
    """Documento electrónico dentro de un expediente."""
    __tablename__ = "documentos"
    row_version: Mapped[int] = mapped_column(Integer, default=1, nullable=False)
    __mapper_args__ = {"version_id_col": row_version}

    identificador: Mapped[str] = mapped_column(String(100), nullable=False, index=True)
    nombre: Mapped[str] = mapped_column(String(500), nullable=False)
    tipo_documental: Mapped[str] = mapped_column(String(50), nullable=False)
    formato: Mapped[str] = mapped_column(String(20), nullable=False)

    # Almacenamiento
    storage_path: Mapped[str] = mapped_column(String(1000), nullable=False)
    storage_bucket: Mapped[str] = mapped_column(String(255), nullable=False)
    size_bytes: Mapped[int] = mapped_column(nullable=False)
    hash_sha256: Mapped[str] = mapped_column(String(64), nullable=False)

    # Cifrado (envelope encryption)
    cifrado: Mapped[bool] = mapped_column(default=False)
    nonce_cifrado: Mapped[str | None] = mapped_column(String(255), nullable=True)
    tag_cifrado: Mapped[str | None] = mapped_column(String(255), nullable=True)
    # DEK cifrada con la KEK del tenant (hex). NUNCA se guarda la DEK en plano.
    # Ver app/core/crypto.py -> cifrar_sobre() / descifrar_sobre().
    encryption_key_enc: Mapped[str | None] = mapped_column(String(512), nullable=True)

    # Metadatos
    metadatos: Mapped[dict | None] = mapped_column(JSONB, default=dict)

    # Relaciones
    expediente_id: Mapped[UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("expedientes_obra.id", ondelete="CASCADE"), nullable=False, index=True
    )
    expediente: Mapped["ExpedienteObra"] = relationship("ExpedienteObra", back_populates="documentos")
