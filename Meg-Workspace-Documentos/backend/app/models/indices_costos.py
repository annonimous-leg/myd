"""Evidencia de índices inmutable; originales separados de estimaciones."""
import uuid
from datetime import date
from decimal import Decimal

from sqlalchemy import (
    CheckConstraint,
    Date,
    ForeignKey,
    ForeignKeyConstraint,
    Integer,
    LargeBinary,
    Numeric,
    String,
    Text,
    UniqueConstraint,
)
from sqlalchemy.orm import Mapped, mapped_column

from app.db.types import JSONB, UUID
from app.models.base import Base, UUIDMixin


class SerieIndiceCosto(Base, UUIDMixin):
    __tablename__ = 'series_indices_costos'
    codigo: Mapped[str] = mapped_column(String(120), nullable=False)
    version_metodologia: Mapped[str] = mapped_column(String(120), nullable=False)
    nombre: Mapped[str] = mapped_column(String(300), nullable=False)
    region: Mapped[str] = mapped_column(String(120), nullable=False)
    condiciones_precio: Mapped[str] = mapped_column(Text, nullable=False)
    periodo_referencia: Mapped[str] = mapped_column(String(100), nullable=False)
    evidencia: Mapped[dict] = mapped_column(JSONB, nullable=False)
    contrato_inegi: Mapped[dict | None] = mapped_column(JSONB, nullable=True)
    # Preserve the authenticated reviewer's identity even if the account is removed.
    registrado_por: Mapped[str] = mapped_column(String(36), nullable=False)
    __table_args__ = (UniqueConstraint('codigo', 'version_metodologia', name='uq_serie_indice_version'),)


class CargaIndiceCosto(Base, UUIDMixin):
    __tablename__ = 'cargas_indices_costos'
    serie_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey('series_indices_costos.id', ondelete='RESTRICT'), nullable=False)
    documento_sha256: Mapped[str] = mapped_column(String(64), nullable=False)
    publicado_el: Mapped[date] = mapped_column(Date, nullable=False)
    mes_inicio: Mapped[date] = mapped_column(Date, nullable=False)
    mes_fin: Mapped[date] = mapped_column(Date, nullable=False)
    ultima_actualizacion: Mapped[str] = mapped_column(String(120), nullable=False)
    evidencia: Mapped[dict] = mapped_column(JSONB, nullable=False)
    archivo: Mapped[bytes] = mapped_column(LargeBinary, nullable=False)
    registrado_por: Mapped[str] = mapped_column(String(36), nullable=False)
    __table_args__ = (
        UniqueConstraint('serie_id', 'documento_sha256', name='uq_carga_indice_archivo'),
        UniqueConstraint('id', 'serie_id', 'documento_sha256', 'publicado_el', name='uq_carga_indice_identidad'),
        CheckConstraint("encode(sha256(archivo), 'hex') = documento_sha256", name='ck_carga_indice_sha').ddl_if(dialect='postgresql'),
        CheckConstraint('octet_length(archivo) BETWEEN 1 AND 2097152', name='ck_carga_indice_tamano').ddl_if(dialect='postgresql'),
        CheckConstraint('mes_inicio <= mes_fin', name='ck_carga_indice_intervalo'),
    )


class ObservacionIndiceCosto(Base, UUIDMixin):
    __tablename__ = 'observaciones_indices_costos'
    serie_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey('series_indices_costos.id', ondelete='RESTRICT'), nullable=False, index=True)
    mes: Mapped[date] = mapped_column(Date, nullable=False)
    valor: Mapped[Decimal] = mapped_column(Numeric(30, 20), nullable=False)
    carga_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), nullable=True, index=True)
    publicado_el: Mapped[date] = mapped_column(Date, nullable=False)
    documento_sha256: Mapped[str] = mapped_column(String(64), nullable=False)
    revision_captura: Mapped[int] = mapped_column(Integer, nullable=False, default=1, server_default='1')
    sustituye_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), ForeignKey('observaciones_indices_costos.id', ondelete='RESTRICT'), unique=True)
    evidencia: Mapped[dict] = mapped_column(JSONB, nullable=False)
    registrado_por: Mapped[str] = mapped_column(String(36), nullable=False)
    __table_args__ = (
        ForeignKeyConstraint(['carga_id', 'serie_id', 'documento_sha256', 'publicado_el'],
            ['cargas_indices_costos.id', 'cargas_indices_costos.serie_id', 'cargas_indices_costos.documento_sha256', 'cargas_indices_costos.publicado_el'],
            name='fk_observacion_carga', ondelete='RESTRICT'),
        UniqueConstraint('serie_id', 'mes', 'documento_sha256', 'revision_captura', name='uq_observacion_indice_captura'),
        CheckConstraint('(revision_captura = 1 AND sustituye_id IS NULL) OR (revision_captura > 1 AND sustituye_id IS NOT NULL)', name='ck_indice_revision_captura'),
        CheckConstraint('valor > 0 AND valor < 10000000000', name='ck_indice_nivel_positivo'),
        CheckConstraint('publicado_el > mes', name='ck_indice_publicacion_posterior'),
    )


class VinculoIndiceInsumo(Base, UUIDMixin):
    __tablename__ = 'vinculos_indices_insumos'
    tenant_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey('tenants.id', ondelete='RESTRICT'), nullable=False, index=True)
    insumo_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey('insumos_catalogo.id', ondelete='RESTRICT'), nullable=False, index=True)
    serie_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey('series_indices_costos.id', ondelete='RESTRICT'), nullable=False, index=True)
    mes_base: Mapped[date] = mapped_column(Date, nullable=False)
    precio_original: Mapped[Decimal] = mapped_column(Numeric(18, 4), nullable=False)
    insumo_original: Mapped[dict] = mapped_column(JSONB, nullable=False)
    fundamento: Mapped[str] = mapped_column(Text, nullable=False)
    evidencia: Mapped[dict] = mapped_column(JSONB, nullable=False)
    revisado_por: Mapped[str] = mapped_column(String(36), nullable=False)
    __table_args__ = (CheckConstraint('precio_original > 0', name='ck_vinculo_precio_positivo'),)


class RetiroIndiceCosto(Base, UUIDMixin):
    __tablename__ = 'retiros_indices_costos'
    observacion_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), ForeignKey('observaciones_indices_costos.id', ondelete='RESTRICT'), unique=True)
    vinculo_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), ForeignKey('vinculos_indices_insumos.id', ondelete='RESTRICT'), unique=True)
    motivo: Mapped[str] = mapped_column(Text, nullable=False)
    registrado_por: Mapped[str] = mapped_column(String(36), nullable=False)
    __table_args__ = (CheckConstraint('(observacion_id IS NULL) <> (vinculo_id IS NULL)', name='ck_retiro_un_recurso'),)
