# Copyright © 2026 Cristian Rodriguez
# All rights reserved.
# Unauthorized copying, modification, distribution, or use is prohibited
# without prior written permission.

"""
Schemas de licitaciones con máquina de estados legal.
"""
from typing import Optional, List, Annotated
from uuid import UUID
from datetime import datetime
from pydantic import BaseModel, Field, ConfigDict, StringConstraints, StrictBool, field_validator

from app.models.licitacion import TipoProcedimiento, EstadoLicitacion, TipoEvaluacion, ResultadoEvaluacion


JurisdictionCode = Annotated[str, StringConstraints(strip_whitespace=True, to_upper=True, min_length=1, max_length=120)]


# ─── Junta de Aclaraciones ─────────────────────────────────────────────

class JuntaAclaracionCreate(BaseModel):
    fecha: str
    acta: Optional[str] = None
    preguntas_respuestas: Optional[dict] = None
    cambios_bases: Optional[str] = None
    numero_junta: int = 1
    fecha_limite_solicitudes: Optional[str] = None


class JuntaAclaracionOut(BaseModel):
    id: UUID
    licitacion_id: UUID
    fecha: str
    acta: Optional[str]
    preguntas_respuestas: Optional[dict]
    cambios_bases: Optional[str]
    numero_junta: int
    fecha_limite_solicitudes: Optional[str]
    created_at: datetime

    class Config:
        from_attributes = True


# ─── Proposición ───────────────────────────────────────────────────────

class ProposicionCreate(BaseModel):
    proveedor_id: UUID
    monto: float = Field(..., ge=0)
    plazo_dias: int = Field(..., gt=0)
    sobres_digitales: Optional[dict] = None


class ProposicionOut(BaseModel):
    id: UUID
    licitacion_id: UUID
    proveedor_id: UUID
    monto: float
    plazo_dias: int
    estado: str
    firma_valida: Optional[bool]
    integridad_valida: Optional[bool]
    cumplimiento_documental: Optional[bool]
    verificacion_documental: Optional[dict]
    motivo_desecho: Optional[str]
    created_at: datetime

    class Config:
        from_attributes = True


# ─── Evaluación ────────────────────────────────────────────────────────

class RevisionDocumentalCreate(BaseModel):
    """Human review of signature evidence and compliance, with stored support.

    This is not an automated SAT/TSA trust decision. The service calculates
    the integrity of document bytes independently of these declarations.
    """
    model_config = ConfigDict(extra="forbid")
    documentos_soporte: list[UUID] = Field(min_length=1, max_length=100)
    firma_valida: StrictBool
    cumplimiento_documental: StrictBool
    dictamen: Annotated[str, StringConstraints(strip_whitespace=True, min_length=20, max_length=10000)]


class EvaluacionCreate(BaseModel):
    proposicion_id: UUID
    tipo: TipoEvaluacion
    resultado: ResultadoEvaluacion
    puntaje: Optional[float] = Field(None, ge=0, le=100)
    dictamen: Optional[str] = None
    criterios: Optional[dict] = None


class EvaluacionAutomaticaCreate(BaseModel):
    """Evaluación calculada por MotorEvaluacion en vez de traer ya
    resultado/puntaje decididos por un humano fuera del sistema (eso es
    lo que hace EvaluacionCreate arriba). `datos` trae los valores crudos
    por criterio -- para LEGAL, booleanos por cada CriterioLegal
    (ver app/engines/juridico/motor_evaluacion.py); para TECNICA/ECONOMICA,
    puntajes 0-100 por cada CriterioTecnico/CriterioEconomico."""
    proposicion_id: UUID
    tipo: TipoEvaluacion
    datos: dict
    model_config = ConfigDict(extra="forbid")


class EvaluacionOut(BaseModel):
    id: UUID
    licitacion_id: UUID
    proposicion_id: UUID
    tipo: str
    revision: int
    resultado: str
    puntaje: Optional[float]
    dictamen: Optional[str]
    criterios: Optional[dict]
    created_at: datetime

    class Config:
        from_attributes = True


# ─── Licitación ────────────────────────────────────────────────────────

class LicitacionCreate(BaseModel):
    jurisdiction_code: JurisdictionCode
    expediente_id: UUID
    folio: str = Field(..., max_length=100)
    tipo_procedimiento: TipoProcedimiento
    objeto: str
    monto_estimado: Optional[float] = None
    plazo_dias: Optional[int] = None
    fecha_convocatoria: Optional[str] = None
    reglas_participacion: Optional[dict] = None
    bases: Optional[str] = None
    matriz_evaluacion: Optional[dict] = None
    presupuesto_dependencia_miles: Optional[float] = None


class LicitacionUpdate(BaseModel):
    model_config = ConfigDict(extra='forbid')
    version_esperada: Optional[int] = Field(None, ge=1)
    jurisdiction_code: Optional[JurisdictionCode] = None
    folio: Optional[str] = Field(None, min_length=1, max_length=100)
    objeto: Optional[str] = Field(None, min_length=1)
    tipo_procedimiento: Optional[TipoProcedimiento] = None
    reglas_participacion: Optional[dict] = None

    monto_estimado: Optional[float] = None
    plazo_dias: Optional[int] = None
    fecha_convocatoria: Optional[str] = None
    fecha_junta_aclaraciones: Optional[str] = None
    fecha_apertura: Optional[str] = None
    matriz_evaluacion: Optional[dict] = None
    bases: Optional[str] = None
    justificacion_procedimiento: Optional[str] = None
    investigacion_mercado: Optional[dict] = None

    @field_validator('jurisdiction_code')
    @classmethod
    def dependencia_no_nula(cls, value):
        if value is None:
            raise ValueError('La dependencia convocante no puede borrarse')
        return value


class LicitacionOut(BaseModel):
    id: UUID
    expediente_id: UUID
    jurisdiction_code: Optional[str]
    folio: str
    tipo_procedimiento: str
    estado: str
    objeto: str
    monto_estimado: Optional[float]
    plazo_dias: Optional[int]
    fecha_convocatoria: Optional[str]
    fecha_junta_aclaraciones: Optional[str]
    fecha_apertura: Optional[str]
    fecha_fallo: Optional[str]
    fecha_adjudicacion: Optional[str]
    bases_version: int
    bases_congeladas: bool
    row_version: int
    bases: Optional[str]
    matriz_evaluacion: Optional[dict]
    justificacion_procedimiento: Optional[str]
    presupuesto_dependencia_miles: Optional[float]
    created_at: datetime
    updated_at: datetime

    class Config:
        from_attributes = True


class LicitacionList(BaseModel):
    total: int
    items: List[LicitacionOut]


class InsumosEvaluacion(BaseModel):
    model_config = ConfigDict(extra="forbid")
    legal: dict[str, StrictBool]
    tecnico: dict[str, Annotated[float, Field(ge=0, le=100, allow_inf_nan=False)]]
    economico: dict[str, Annotated[float, Field(ge=0, le=100, allow_inf_nan=False)]]


class EvaluacionWorkspaceInput(BaseModel):
    model_config = ConfigDict(extra="forbid")
    revision_esperada: int = Field(ge=1)
    insumos: dict[UUID, InsumosEvaluacion] = Field(min_length=1, max_length=500)


class LicitacionDetalleOut(LicitacionOut):
    juntas_aclaraciones: List[JuntaAclaracionOut] = []
    proposiciones: List[ProposicionOut] = []
    evaluaciones: List[EvaluacionOut] = []

    class Config:
        from_attributes = True


# ─── Transiciones de estado ────────────────────────────────────────────

class TransicionEstadoCreate(BaseModel):
    nuevo_estado: EstadoLicitacion
    justificacion: Optional[str] = None
    datos_adicionales: Optional[dict] = None


class InvestigacionMercadoCreate(BaseModel):
    cotizaciones: List[dict]
    proveedores_contactados: List[str]
    precios_referencia: List[dict]
    oferta_nacional: bool
    dispersion_precios: Optional[float] = None
    conclusion: str


class SelectorProcedimientoOut(BaseModel):
    procedimiento_recomendado: TipoProcedimiento
    justificacion: str
    umbrales_aplicables: dict
    datos_verificados: bool
    es_candidato: bool
    fuente_umbral: Optional[str]
    ejercicio_fiscal: int
