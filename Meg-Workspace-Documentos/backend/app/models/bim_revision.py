"""Immutable coverage snapshots and append-only contractual measurement decisions."""
from uuid import UUID
from sqlalchemy import ForeignKeyConstraint, String, Integer, JSON, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column
from app.db.types import UUID as UUIDType
from app.models.base import Base, UUIDMixin, TenantMixin, AuditMixin


class RevisionBIM(Base, UUIDMixin, TenantMixin, AuditMixin):
    __tablename__ = 'bim_revisiones'
    modelo_id: Mapped[UUID] = mapped_column(UUIDType(as_uuid=True), nullable=False, index=True)
    fuente_sha256: Mapped[str] = mapped_column(String(64), nullable=False)
    geometria_sha256: Mapped[str] = mapped_column(String(64), nullable=False)
    huella: Mapped[str] = mapped_column(String(64), nullable=False)
    cobertura: Mapped[list] = mapped_column(JSON, nullable=False)
    tipos_admitidos: Mapped[list] = mapped_column(JSON, nullable=False)
    __table_args__ = (
        ForeignKeyConstraint(['modelo_id', 'tenant_id'], ['modelos_bim.id', 'modelos_bim.tenant_id']),
        UniqueConstraint('id', 'tenant_id', name='uq_bim_revision_tenant'),
        UniqueConstraint('modelo_id', 'huella', name='uq_bim_revision_content'),
    )


class DecisionMedicionBIM(Base, UUIDMixin, TenantMixin, AuditMixin):
    __tablename__ = 'bim_decisiones_medicion'
    revision_id: Mapped[UUID] = mapped_column(UUIDType(as_uuid=True), nullable=False, index=True)
    familia_global_id: Mapped[str] = mapped_column(String(100), nullable=False)
    version: Mapped[int] = mapped_column(Integer, nullable=False)
    criterio: Mapped[str] = mapped_column(String(20), nullable=False)
    confirmada: Mapped[bool] = mapped_column(nullable=False, default=False)
    datos: Mapped[dict] = mapped_column(JSON, nullable=False)
    __table_args__ = (
        ForeignKeyConstraint(['revision_id', 'tenant_id'], ['bim_revisiones.id', 'bim_revisiones.tenant_id']),
        UniqueConstraint('revision_id', 'familia_global_id', 'version', name='uq_bim_decision_version'),
    )
