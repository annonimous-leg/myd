# Copyright © 2026 Cristian Rodriguez
# All rights reserved.
# Unauthorized copying, modification, distribution, or use is prohibited
# without prior written permission.

"""
Modelos de gestión documental / CDE (Common Data Environment).
openCDE compliant.
"""
from enum import Enum
from uuid import uuid4
from typing import TYPE_CHECKING

from sqlalchemy import String, Text, ForeignKey, Index, DateTime, UniqueConstraint
from app.db.types import UUID, JSONB
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models.base import Base, UUIDMixin, TenantMixin, AuditMixin

if TYPE_CHECKING:
    from app.models.expediente import ExpedienteObra


class EstadoDocumento(str, Enum):
    BORRADOR = "BORRADOR"
    EN_REVISION = "EN_REVISION"
    APROBADO = "APROBADO"
    PUBLICADO = "PUBLICADO"
    ARCHIVADO = "ARCHIVADO"
    OBSOLETO = "OBSOLETO"


class TipoDocumento(str, Enum):
    CONVOCATORIA = "CONVOCATORIA"
    BASES = "BASES"
    ANEXO_TECNICO = "ANEXO_TECNICO"
    ACTA = "ACTA"
    FALLA = "FALLA"
    CONTRATO = "CONTRATO"
    ESTIMACION = "ESTIMACION"
    FACTURA = "FACTURA"
    PLANO = "PLANO"
    REPORTE_FOTOGRAFICO = "REPORTE_FOTOGRAFICO"
    OFICIO = "OFICIO"
    DICTAMEN = "DICTAMEN"
    RESOLUCION = "RESOLUCION"
    BIM_IFC = "BIM_IFC"
    BIM_BCF = "BIM_BCF"
    BIM_IDS = "BIM_IDS"
    OTRO = "OTRO"


class DocumentoCDE(Base, UUIDMixin, TenantMixin, AuditMixin):
    """Documento en el CDE / Repositorio documental."""
    __tablename__ = "documentos_cde"

    expediente_id: Mapped[str] = mapped_column(
        UUID(as_uuid=True), ForeignKey("expedientes_obra.id", ondelete="CASCADE"), nullable=False, index=True
    )

    nombre: Mapped[str] = mapped_column(String(500), nullable=False)
    descripcion: Mapped[str | None] = mapped_column(Text, nullable=True)
    contenido_url: Mapped[str | None] = mapped_column(String(1000), nullable=True)
    contrato_id: Mapped[str | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("contratos.id", ondelete="SET NULL"), nullable=True, index=True
    )
    tipo: Mapped[TipoDocumento] = mapped_column(String(50), nullable=False, index=True)
    estado: Mapped[EstadoDocumento] = mapped_column(String(50), default=EstadoDocumento.BORRADOR, index=True)

    # Metadatos del archivo
    mime_type: Mapped[str | None] = mapped_column(String(100), nullable=True)
    tamaño_bytes: Mapped[int | None] = mapped_column(nullable=True)
    hash_sha256: Mapped[str | None] = mapped_column(String(64), nullable=True, index=True)

    # Rutas de almacenamiento
    ruta_storage: Mapped[str | None] = mapped_column(String(1000), nullable=True)
    ruta_supabase: Mapped[str | None] = mapped_column(String(1000), nullable=True)

    # Versionado
    version: Mapped[int] = mapped_column(default=1)
    documento_padre_id: Mapped[str | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("documentos_cde.id", ondelete="SET NULL"), nullable=True
    )

    # Firma y sellado
    firmado: Mapped[bool] = mapped_column(default=False)
    firma_electronica_id: Mapped[str | None] = mapped_column(String(255), nullable=True)
    sello_tiempo: Mapped[str | None] = mapped_column(String(255), nullable=True)

    # OCR y extracción
    texto_extraido: Mapped[str | None] = mapped_column(Text, nullable=True)
    ocr_completado: Mapped[bool] = mapped_column(default=False)
    ocr_task_id: Mapped[str | None] = mapped_column(String(255), nullable=True)

    # Metadatos adicionales
    metadatos: Mapped[dict | None] = mapped_column(JSONB, nullable=True)

    # Relaciones
    expediente: Mapped["ExpedienteObra"] = relationship("ExpedienteObra", back_populates="documentos_cde")

    __table_args__ = (
        UniqueConstraint("tenant_id", "hash_sha256", name="uq_documento_tenant_hash"),
        Index("ix_documento_expediente_tipo", "expediente_id", "tipo", "estado"),
    )
