# Copyright © 2026 Cristian Rodriguez
# All rights reserved.
# Unauthorized copying, modification, distribution, or use is prohibited
# without prior written permission.

"""
Modelos de compliance, inconformidades y sanciones.
Evaluación automática por estado del procedimiento.
"""
from enum import Enum
from uuid import uuid4
from typing import TYPE_CHECKING, Optional

from sqlalchemy import String, Text, Numeric, ForeignKey, Index, DateTime, Boolean, false
from app.db.types import UUID, JSONB
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models.base import Base, UUIDMixin, TenantMixin, AuditMixin

if TYPE_CHECKING:
    from app.models.contrato import Contrato
    from app.models.expediente import ExpedienteObra
    from app.models.licitacion import Licitacion
    from app.models.proveedor import Proveedor
    from app.models.user import User


class EstadoInconformidad(str, Enum):
    REGISTRADA = "REGISTRADA"
    EN_ANALISIS = "EN_ANALISIS"
    RESPONDIDA = "RESPONDIDA"
    RESUELTA = "RESUELTA"
    ARCHIVADA = "ARCHIVADA"


class TipoSancion(str, Enum):
    INHABILITACION = "INHABILITACION"
    MULTA = "MULTA"
    AMONESTACION = "AMONESTACION"
    DESTITUCION = "DESTITUCION"


class EstadoRegla(str, Enum):
    CUMPLIDA = "CUMPLIDA"
    NO_CUMPLIDA = "NO_CUMPLIDA"
    PENDIENTE = "PENDIENTE"
    NO_APLICA = "NO_APLICA"


class SeveridadInconformidad(str, Enum):
    BAJA = "BAJA"
    MEDIA = "MEDIA"
    ALTA = "ALTA"
    CRITICA = "CRITICA"


class ReglaCumplimiento(Base, UUIDMixin, TenantMixin, AuditMixin):
    """Regla de cumplimiento por etapa / tipo de procedimiento."""
    __tablename__ = "reglas_cumplimiento"

    nombre: Mapped[str] = mapped_column(String(255), nullable=False)
    descripcion: Mapped[str | None] = mapped_column(Text, nullable=True)
    tipo_procedimiento: Mapped[str] = mapped_column(String(50), nullable=False, index=True)
    etapa: Mapped[str] = mapped_column(String(50), nullable=False, index=True)
    requisitos: Mapped[dict | None] = mapped_column(JSONB, nullable=True)
    obligatorio: Mapped[bool] = mapped_column(Boolean, default=True)
    activa: Mapped[bool] = mapped_column(Boolean, default=True)

    # Motor de evaluación (app/engines/compliance/motor_compliance.py).
    # Formato soportado -- UNA sola comparación "campo operador valor", NO
    # expresiones compuestas con AND/OR ni pseudo-SQL "IS NOT NULL":
    #   "estado == CONVOCATORIA"        (sin comillas: el parser no las quita)
    #   "monto_estimado > 1000000"
    #   "fecha_convocatoria is_not_none"   (usar is_not_none/is_none, no IS NOT NULL)
    #   "tipo_procedimiento in [LICITACION_PUBLICA, INVITACION_TRES]"
    # Corregido 2026-09-01: el ejemplo anterior aquí ("estado == 'CONVOCATORIA'
    # AND fecha_convocatoria IS NOT NULL") no correspondía a la gramática que
    # MotorCompliance.evaluar_condicion() realmente soporta (split() simple,
    # sin AND/OR) -- llevaba a reglas irrepetibles/mal evaluadas si alguien
    # las escribía copiando ese ejemplo.
    condicion_evaluacion: Mapped[str | None] = mapped_column(Text, nullable=True)


class Inconformidad(Base, UUIDMixin, TenantMixin, AuditMixin):
    """Inconformidad registrada en un procedimiento."""
    __tablename__ = "inconformidades"

    expediente_id: Mapped[str] = mapped_column(
        UUID(as_uuid=True), ForeignKey("expedientes_obra.id", ondelete="CASCADE"), nullable=False, index=True
    )
    licitacion_id: Mapped[str | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("licitaciones.id", ondelete="SET NULL"), nullable=True
    )
    contrato_id: Mapped[str | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("contratos.id", ondelete="SET NULL"), nullable=True
    )
    # CORREGIDO (F-02): compliance_service.crear_inconformidad() ya
    # construía Inconformidad con severidad/regla_id/asignado_a/fecha_limite
    # -- estas columnas no existían y el ORM tronaba con TypeError en cada
    # alta. Se agregan aquí como campos reales, no se le quitó la
    # funcionalidad al servicio.
    regla_id: Mapped[str | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("reglas_cumplimiento.id", ondelete="SET NULL"), nullable=True, index=True
    )
    asignado_a: Mapped[str | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id", ondelete="SET NULL"), nullable=True, index=True
    )

    expediente: Mapped["ExpedienteObra"] = relationship("ExpedienteObra", foreign_keys=[expediente_id])
    licitacion: Mapped[Optional["Licitacion"]] = relationship("Licitacion", foreign_keys=[licitacion_id])
    contrato: Mapped[Optional["Contrato"]] = relationship("Contrato", foreign_keys=[contrato_id])
    regla: Mapped[Optional["ReglaCumplimiento"]] = relationship("ReglaCumplimiento", foreign_keys=[regla_id])
    asignado: Mapped[Optional["User"]] = relationship("User", foreign_keys=[asignado_a])

    titulo: Mapped[str] = mapped_column(String(500), nullable=False)
    descripcion: Mapped[str] = mapped_column(Text, nullable=False)
    severidad: Mapped[SeveridadInconformidad | None] = mapped_column(String(20), nullable=True, index=True)
    estado: Mapped[EstadoInconformidad] = mapped_column(String(50), default=EstadoInconformidad.REGISTRADA, index=True)
    fecha_limite: Mapped[str | None] = mapped_column(String(10), nullable=True)

    evidencia: Mapped[dict | None] = mapped_column(JSONB, nullable=True)
    respuesta: Mapped[str | None] = mapped_column(Text, nullable=True)
    resolucion: Mapped[str | None] = mapped_column(Text, nullable=True)

    # Legal: dictamen
    dictamen: Mapped[str | None] = mapped_column(Text, nullable=True)
    fecha_dictamen: Mapped[str | None] = mapped_column(String(10), nullable=True)


class Sancion(Base, UUIDMixin, TenantMixin, AuditMixin):
    """Sanción aplicada a un proveedor o contratista."""
    __tablename__ = "sanciones"

    proveedor_id: Mapped[str] = mapped_column(
        UUID(as_uuid=True), ForeignKey("proveedores.id", ondelete="CASCADE"), nullable=False, index=True
    )
    expediente_id: Mapped[str | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("expedientes_obra.id", ondelete="SET NULL"), nullable=True
    )
    licitacion_id: Mapped[str | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("licitaciones.id", ondelete="SET NULL"), nullable=True
    )

    proveedor: Mapped["Proveedor"] = relationship("Proveedor", back_populates="sanciones")
    expediente: Mapped[Optional["ExpedienteObra"]] = relationship("ExpedienteObra", foreign_keys=[expediente_id])
    licitacion: Mapped[Optional["Licitacion"]] = relationship("Licitacion", foreign_keys=[licitacion_id])

    tipo: Mapped[TipoSancion] = mapped_column(String(50), nullable=False)
    motivo: Mapped[str] = mapped_column(Text, nullable=False)
    monto_multa: Mapped[float | None] = mapped_column(Numeric(18, 4), nullable=True)

    # Legal: expediente sancionador
    expediente_sancionador: Mapped[str | None] = mapped_column(String(100), nullable=True)
    hechos: Mapped[str | None] = mapped_column(Text, nullable=True)
    pruebas: Mapped[dict | None] = mapped_column(JSONB, nullable=True)
    audiencia_fecha: Mapped[str | None] = mapped_column(String(10), nullable=True)
    resolucion: Mapped[str | None] = mapped_column(Text, nullable=True)

    vigencia_inicio: Mapped[str | None] = mapped_column(String(10), nullable=True)
    vigencia_fin: Mapped[str | None] = mapped_column(String(10), nullable=True)

    # Estado
    # (relación "proveedor" ya declarada arriba -- había una segunda
    # declaración idéntica aquí, código muerto, eliminada 2026-09-01)
    estado: Mapped[str] = mapped_column(String(50), default="VIGENTE")  # VIGENTE, CONCLUIDA, SUSPENDIDA, APELADA

    # Hallazgo 2026-08-30 (auditoría externa, confirmado leyendo el código):
    # /sanciones-publicas devolvía TODAS las sanciones de TODOS los tenants
    # con estado == VIGENTE, sin autenticación y sin filtro de tenant --
    # "vigente" es un estado (en efecto vs. concluida/apelada), no una
    # decisión de publicación. A diferencia de ExpedienteObra, que sí tiene
    # `clasificacion` para gatear su propio endpoint público
    # (/expedientes-publicos), Sancion no tenía ningún campo equivalente.
    # `publicada` cierra eso: por defecto False, así que el endpoint público
    # no expone nada hasta que cada tenant marque explícitamente qué
    # sanciones sí deben aparecer en el portal de transparencia -- mismo
    # principio que "ninguna LegalRule activa sin fundamento verificado".
    publicada: Mapped[bool] = mapped_column(Boolean, default=False, server_default=false())


class EvaluacionCompliance(Base, UUIDMixin, TenantMixin, AuditMixin):
    """Evaluación automática de compliance para un procedimiento."""
    __tablename__ = "evaluaciones_compliance"

    licitacion_id: Mapped[str | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("licitaciones.id", ondelete="CASCADE"), nullable=True
    )
    contrato_id: Mapped[str | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("contratos.id", ondelete="CASCADE"), nullable=True
    )
    regla_id: Mapped[str] = mapped_column(
        UUID(as_uuid=True), ForeignKey("reglas_cumplimiento.id", ondelete="CASCADE"), nullable=False
    )

    estado: Mapped[EstadoRegla] = mapped_column(String(50), default=EstadoRegla.PENDIENTE)
    observaciones: Mapped[str | None] = mapped_column(Text, nullable=True)
    evidencia: Mapped[dict | None] = mapped_column(JSONB, nullable=True)
    evaluador_id: Mapped[str | None] = mapped_column(UUID(as_uuid=True), ForeignKey("users.id", ondelete="SET NULL"), nullable=True)
