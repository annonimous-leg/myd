"""Tenant-owned, immutable source editions and their extraction evidence."""
from sqlalchemy import ForeignKey, ForeignKeyConstraint, Index, String, UniqueConstraint, Numeric
from sqlalchemy.orm import Mapped, mapped_column

from app.db.types import JSONB, UUID
from app.models.base import Base, UUIDMixin, TenantMixin, AuditMixin


class CatalogoImportacion(Base, UUIDMixin, TenantMixin, AuditMixin):
    __tablename__ = 'catalogo_importaciones'
    paquete_sha256: Mapped[str] = mapped_column(String(64), nullable=False)
    seleccion_sha256: Mapped[str] = mapped_column(String(64), nullable=False)
    fuentes: Mapped[list] = mapped_column(JSONB, nullable=False)
    resumen: Mapped[dict] = mapped_column(JSONB, nullable=False)
    __table_args__ = (
        UniqueConstraint('tenant_id', 'paquete_sha256', 'seleccion_sha256', name='uq_catalogo_importacion_edicion'),
        UniqueConstraint('id', 'tenant_id', name='uq_catalogo_importacion_tenant'),
    )


class CatalogoRegistro(Base, UUIDMixin, TenantMixin):
    __tablename__ = 'catalogo_registros'
    importacion_id: Mapped[object] = mapped_column(UUID(as_uuid=True), nullable=False)
    tabla: Mapped[str] = mapped_column(String(50), nullable=False)
    entidad_id: Mapped[str] = mapped_column(String(160), nullable=False)
    fuente_id: Mapped[str] = mapped_column(String(100), nullable=False)
    estado: Mapped[str] = mapped_column(String(30), nullable=False)
    motivos: Mapped[list] = mapped_column(JSONB, nullable=False)
    original: Mapped[dict] = mapped_column(JSONB, nullable=False)
    sha256: Mapped[str] = mapped_column(String(64), nullable=False)
    __table_args__ = (
        ForeignKeyConstraint(['importacion_id', 'tenant_id'], ['catalogo_importaciones.id', 'catalogo_importaciones.tenant_id'], ondelete='CASCADE'),
        UniqueConstraint('importacion_id', 'tabla', 'entidad_id', name='uq_catalogo_registro_identidad'),
        UniqueConstraint('id', 'tenant_id', name='uq_catalogo_registro_tenant'),
        Index('ix_catalogo_registro_consulta', 'tenant_id', 'importacion_id', 'tabla', 'estado'),
    )


class EstimacionParametrica(Base, UUIDMixin, TenantMixin, AuditMixin):
    __tablename__ = 'estimaciones_parametricas'
    modelo_registro_id: Mapped[object] = mapped_column(UUID(as_uuid=True), nullable=False)
    factor_registro_id: Mapped[object] = mapped_column(UUID(as_uuid=True), nullable=False)
    cantidad: Mapped[object] = mapped_column(Numeric(18, 4), nullable=False)
    monto: Mapped[object] = mapped_column(Numeric(18, 2), nullable=False)
    evidencia: Mapped[dict] = mapped_column(JSONB, nullable=False)
    __table_args__ = (
        ForeignKeyConstraint(['modelo_registro_id', 'tenant_id'], ['catalogo_registros.id', 'catalogo_registros.tenant_id']),
        ForeignKeyConstraint(['factor_registro_id', 'tenant_id'], ['catalogo_registros.id', 'catalogo_registros.tenant_id']),
    )
