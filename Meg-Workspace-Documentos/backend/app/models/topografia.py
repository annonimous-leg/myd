# Copyright © 2026 Cristian Rodriguez
# All rights reserved.
# Unauthorized copying, modification, distribution, or use is prohibited
# without prior written permission.

"""
Modelos de topografía con PostGIS.
"""
from datetime import datetime
from uuid import uuid4

from geoalchemy2 import Geometry
from sqlalchemy import CheckConstraint, String, Text, Numeric, ForeignKey, Index, Integer, JSON, DateTime, func, UniqueConstraint
from app.db.types import UUID, JSONB
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models.base import Base, UUIDMixin, AuditMixin
from enum import Enum


class TipoLevantamiento(str, Enum):
    """Tipos de levantamiento topográfico.

    RESTAURADO: app/schemas/topografia.py (importado por app/schemas/__init__.py,
    así que un fallo aquí tumba TODO el paquete app.schemas) ya esperaba esta
    clase vía `from app.models.topografia import TipoLevantamiento`, pero
    nunca se había definido -- mismo patrón que ValidacionPropuesta."""
    POLIGONAL = "POLIGONAL"
    ALTIMETRICO = "ALTIMETRICO"
    BATIMETRICO = "BATIMETRICO"
    CATASTRAL = "CATASTRAL"
    GEODESICO = "GEODESICO"


class EstadoLevantamiento(str, Enum):
    """Estados del ciclo de vida de un levantamiento."""
    EN_CAMPO = "EN_CAMPO"
    PROCESANDO = "PROCESANDO"
    VALIDADO = "VALIDADO"
    ARCHIVADO = "ARCHIVADO"


class Levantamiento(Base, UUIDMixin, AuditMixin):
    """Levantamiento topográfico."""
    __tablename__ = "levantamientos"

    # BUG ORIGINAL: este modelo no tenía ningún vínculo con expediente_id
    # -- quedaba huérfano, sin relación con el resto del sistema (a
    # diferencia de ModeloBIM, Presupuesto, ProgramaObra, que sí lo
    # tienen todos).
    expediente_id: Mapped[UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("expedientes_obra.id", ondelete="CASCADE"), nullable=False, index=True
    )
    identificador: Mapped[str] = mapped_column(String(100), unique=False, nullable=False)
    nombre: Mapped[str] = mapped_column(String(500), nullable=False)
    descripcion: Mapped[str | None] = mapped_column(Text, nullable=True)

    # Clasificación (ver TipoLevantamiento/EstadoLevantamiento arriba).
    tipo: Mapped[str] = mapped_column(String(20), default=TipoLevantamiento.POLIGONAL, nullable=False, index=True)
    estado: Mapped[str] = mapped_column(String(20), default=EstadoLevantamiento.EN_CAMPO, nullable=False, index=True)

    # Sistema de coordenadas
    crs: Mapped[str] = mapped_column(String(50), default="EPSG:6362")  # Mexico ITRF92 / LCC
    srid: Mapped[int] = mapped_column(Integer, default=6362)

    # Metadatos
    metadatos: Mapped[dict | None] = mapped_column(JSONB, default=dict)

    # Relaciones
    puntos: Mapped[list["PuntoTopografico"]] = relationship(
        "PuntoTopografico", back_populates="levantamiento", cascade="all, delete-orphan"
    )

    __table_args__ = (
        UniqueConstraint("expediente_id", "identificador", name="uq_levantamiento_expediente_identificador"),
    )


class PuntoTopografico(Base, UUIDMixin):
    """Punto de levantamiento con geometría PostGIS."""
    __tablename__ = "puntos_topograficos"

    identificador: Mapped[str] = mapped_column(String(50), nullable=False)
    etiqueta: Mapped[str | None] = mapped_column(String(100), nullable=True)
    descripcion: Mapped[str | None] = mapped_column(Text, nullable=True)

    # Coordenadas numéricas
    x: Mapped[float] = mapped_column(Numeric(18, 6), nullable=False)
    y: Mapped[float] = mapped_column(Numeric(18, 6), nullable=False)
    z: Mapped[float | None] = mapped_column(Numeric(18, 6), nullable=True)

    # Precisión
    precision_xy: Mapped[float] = mapped_column(Numeric(8, 4), default=0.02)
    precision_z: Mapped[float | None] = mapped_column(Numeric(8, 4), nullable=True)

    # Geometría PostGIS
    geom = mapped_column(
        # Points can carry measured Z; two-dimensional capture has NULL numeric z.
        # A PostGIS check restricts geometry to POINT, with the survey's SRID.
        Geometry(geometry_type=None, srid=-1, spatial_index=True),
        nullable=False,
    )

    # Metadatos
    fuente: Mapped[str | None] = mapped_column(String(255), nullable=True)
    metadatos: Mapped[dict | None] = mapped_column(JSONB, default=dict)

    # Relaciones
    levantamiento_id: Mapped[UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("levantamientos.id", ondelete="CASCADE"), nullable=False
    )
    levantamiento: Mapped["Levantamiento"] = relationship("Levantamiento", back_populates="puntos")

    __table_args__ = (
        Index("idx_puntos_levantamiento", "levantamiento_id"),
        CheckConstraint("GeometryType(geom) = 'POINT' AND ST_NDims(geom) IN (2, 3)",
                        name="ck_punto_tipo_geometria").ddl_if(dialect="postgresql"),
    )


class SuperficieTIN(Base, UUIDMixin, AuditMixin):
    """Superficie triangulada (TIN) real, generada a partir de los puntos
    de un levantamiento. Antes no existía persistencia de superficies --
    triangular era puramente efímero en cada request."""
    __tablename__ = "superficies_tin"

    # Denormalizado (además de levantamiento_id) para no tener que
    # caminar superficie->levantamiento->expediente en cada validación de
    # pertenencia -- mismo patrón que ClashResult.modelo_id en bim.py.
    expediente_id: Mapped[UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("expedientes_obra.id", ondelete="CASCADE"), nullable=False, index=True
    )
    levantamiento_id: Mapped[UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("levantamientos.id", ondelete="CASCADE"), nullable=False, index=True
    )
    nombre: Mapped[str] = mapped_column(String(200), nullable=False)
    tipo: Mapped[str] = mapped_column(String(20), default="EXISTENTE")  # EXISTENTE | PROYECTO

    # Malla triangulada -- mismo formato que ElementoBIM.malla_vertices/
    # malla_caras, para reusar el mismo visor 3D del frontend.
    malla_vertices: Mapped[list] = mapped_column(JSON, nullable=False)
    malla_caras: Mapped[list] = mapped_column(JSON, nullable=False)

    # Estadísticas ya calculadas (evita recalcular solo para mostrarlas).
    area_plan_m2: Mapped[float] = mapped_column(Numeric(18, 4), nullable=False)
    area_superficie_m2: Mapped[float] = mapped_column(Numeric(18, 4), nullable=False)
    elevacion_min: Mapped[float] = mapped_column(Numeric(10, 4), nullable=False)
    elevacion_max: Mapped[float] = mapped_column(Numeric(10, 4), nullable=False)
    elevacion_media: Mapped[float] = mapped_column(Numeric(10, 4), nullable=False)
    pendiente_media_pct: Mapped[float] = mapped_column(Numeric(8, 2), default=0)
    num_puntos: Mapped[int] = mapped_column(Integer, default=0)
    num_triangulos: Mapped[int] = mapped_column(Integer, default=0)

    # created_at/updated_at ya vienen de Base.
    levantamiento: Mapped["Levantamiento"] = relationship("Levantamiento")


class CalculoVolumen(Base, UUIDMixin, AuditMixin):
    """Cálculo de corte/terraplén entre dos superficies (o una superficie
    contra una elevación de referencia). El puente hacia partida_id sigue
    el mismo patrón que ElementoBIM.partida_id -- topografía también
    puede alimentar presupuesto (movimiento de tierras)."""
    __tablename__ = "calculos_volumen"

    # Denormalizado, mismo motivo que en SuperficieTIN arriba. Antes esto
    # exactamente causó que el endpoint de generar-presupuesto tuviera
    # expediente_id como query param suelto sin poder validarlo.
    expediente_id: Mapped[UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("expedientes_obra.id", ondelete="CASCADE"), nullable=False, index=True
    )
    superficie_existente_id: Mapped[UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("superficies_tin.id", ondelete="CASCADE"), nullable=False
    )
    superficie_proyecto_id: Mapped[UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("superficies_tin.id", ondelete="SET NULL"), nullable=True
    )
    elevacion_referencia: Mapped[float | None] = mapped_column(Numeric(10, 4), nullable=True)

    volumen_corte_m3: Mapped[float] = mapped_column(Numeric(18, 3), nullable=False)
    volumen_terraplen_m3: Mapped[float] = mapped_column(Numeric(18, 3), nullable=False)
    volumen_neto_m3: Mapped[float] = mapped_column(Numeric(18, 3), nullable=False)
    area_analizada_m2: Mapped[float] = mapped_column(Numeric(18, 3), nullable=False)
    # NULL historical evidence is intentional: it must be recalculated, never fabricated.
    evidencia: Mapped[dict | None] = mapped_column(JSONB, nullable=True)

    # Puente hacia costeo, igual que ElementoBIM.partida_id.
    partida_id: Mapped[UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("partidas.id", ondelete="SET NULL"), nullable=True, index=True
    )
    # created_at/updated_at ya vienen de Base.
