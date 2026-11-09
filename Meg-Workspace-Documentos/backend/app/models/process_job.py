"""Database-owned BIM delivery intent and result."""
from datetime import datetime
from uuid import UUID
from sqlalchemy import DateTime, Index, Integer, JSON, String, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column
from app.db.types import UUID as DBUUID
from app.models.base import Base, UUIDMixin, TenantMixin


class TrabajoProceso(Base, UUIDMixin, TenantMixin):
    __tablename__ = 'trabajos_proceso'
    tipo: Mapped[str] = mapped_column(String(30), nullable=False)
    entidad_id: Mapped[UUID] = mapped_column(DBUUID(as_uuid=True), nullable=False)
    parametros: Mapped[dict] = mapped_column(JSON, nullable=False)
    estado: Mapped[str] = mapped_column(String(20), nullable=False, default='PENDIENTE')
    intentos: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    proxima_publicacion: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    error_publicacion: Mapped[str | None] = mapped_column(String(500))
    error: Mapped[str | None] = mapped_column(String(500))
    id_ejecucion: Mapped[UUID | None] = mapped_column(DBUUID(as_uuid=True))
    __table_args__ = (UniqueConstraint('tipo', 'entidad_id', name='uq_trabajo_tipo_entidad'),
        Index('ix_trabajos_proceso_publicacion', 'estado', 'proxima_publicacion'))
