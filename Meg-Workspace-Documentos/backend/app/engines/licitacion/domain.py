# Copyright © 2026 Cristian Rodriguez
# Domain models for MPPL — Motor de Prevención y Pre-Evaluación Licitatoria

from enum import Enum
from typing import Optional, List, Dict, Any
from datetime import datetime
from uuid import UUID
from pydantic import BaseModel, Field


class NivelRiesgo(str, Enum):
    CRITICO = "CRITICO"      # Afecta solvencia potencialmente
    RELEVANTE = "RELEVANTE"  # Requiere revisión humana
    NO_SUSTANTIVO = "NO_SUSTANTIVO"  # No debería generar desechamiento
    INFORMATIVO = "INFORMATIVO"      # No afecta evaluación


class EstadoRequisito(str, Enum):
    CUMPLE = "CUMPLE"
    NO_CUMPLE = "NO_CUMPLE"
    PARCIAL = "PARCIAL"
    NO_APLICA = "NO_APLICA"


class EstadoSolvencia(str, Enum):
    SOLVENTE = "SOLVENTE"
    NO_SOLVENTE = "NO_SOLVENTE"
    RIESGO = "RIESGO"
    PENDIENTE = "PENDIENTE"


class TipoRequisito(str, Enum):
    LEGAL = "LEGAL"
    ADMINISTRATIVO = "ADMINISTRATIVO"
    TECNICO = "TECNICO"
    ECONOMICO = "ECONOMICO"


class RequisitoEstructurado(BaseModel):
    """Requisito extraído de convocatoria."""
    codigo: str = Field(..., description="REQ-XXX identificador")
    categoria: TipoRequisito
    obligatorio: bool
    descripcion: str
    evidencia_requerida: List[str]
    criterio_evaluacion: str
    causal_desechamiento: Optional[str] = None
    fundamento_legal: str
    seccion_origen: str
    ponderacion: Optional[float] = None
    validaciones: Dict[str, Any] = Field(default_factory=dict)


class CriterioTecnico(BaseModel):
    """Criterio técnico de evaluación."""
    codigo: str
    descripcion: str
    puntaje_maximo: float
    rubrica: Dict[str, Any]
    ponderacion: Optional[float] = None


class CriterioEconomico(BaseModel):
    """Criterio económico de evaluación."""
    codigo: str
    descripcion: str
    formula: str
    ponderacion: float
    umbral_aceptable: Optional[float] = None


class ConvocatoriaEstructurada(BaseModel):
    """Representación parseada de una convocatoria.

    jurisdiction_code is the immutable dependency context used by pre-fall.
    """
    licitacion_id: UUID
    jurisdiction_code: Optional[str] = None
    objeto: str
    tipo_procedimiento: str
    monto_estimado: float
    plazo_dias: int
    requisitos: List[RequisitoEstructurado]
    criterios_tecnicos: List[CriterioTecnico]
    criterios_economicos: List[CriterioEconomico]
    causales_desechamiento: List[str]
    ponderacion_tecnica: Optional[float] = None
    ponderacion_economica: Optional[float] = None
    reglas_economicas: Dict[str, Any] = Field(default_factory=dict)
    fecha_publicacion: Optional[datetime] = None
    fecha_apertura: Optional[datetime] = None
    fecha_fallo: Optional[datetime] = None


class Hallazgo(BaseModel):
    """Hallazgo de validación."""
    id: str = Field(default_factory=lambda: str(__import__('uuid').uuid4())[:8])
    requisito_codigo: str
    nivel_riesgo: NivelRiesgo
    descripcion: str
    documento_afectado: Optional[str] = None
    pagina_referencia: Optional[str] = None
    valor_encontrado: Optional[str] = None
    valor_requerido: Optional[str] = None
    resultado: str  # INCUMPLIMIENTO_MATERIAL, ADVERTENCIA, etc.
    fundamento: str
    confianza: str = "DETERMINISTA"
    fecha_deteccion: datetime = Field(default_factory=datetime.utcnow)


class EvaluacionTecnicaResultado(BaseModel):
    """Resultado de evaluación técnica."""
    criterio_codigo: str
    cumple: bool
    puntaje_obtenido: float
    puntaje_maximo: float
    observaciones: List[str]
    evidencias: List[str]


class EvaluacionEconomicaResultado(BaseModel):
    """Resultado de evaluación económica."""
    criterio_codigo: str
    monto_ofertado: float
    monto_referencia: Optional[float] = None
    discrepancia: Optional[float] = None
    discrepancia_pct: Optional[float] = None
    observaciones: List[str]
    consistente: bool


class PreFallResult(BaseModel):
    """Resultado de simulación pre-fallo."""
    licitacion_id: UUID
    proposicion_id: UUID
    licitante_nombre: str
    estado_general: EstadoSolvencia
    legal_pct: float
    administrativo_pct: float
    tecnico_pct: float
    economico_pct: float
    puntaje_total: Optional[float] = None
    ranking_preliminar: Optional[int] = None
    riesgos_criticos: int
    advertencias: int
    inconsistencias: int
    hallazgos: List[Hallazgo]
    evaluacion_tecnica: List[EvaluacionTecnicaResultado]
    evaluacion_economica: List[EvaluacionEconomicaResultado]
    trazabilidad: List[Dict[str, Any]]
    version: int = 1
    fecha_generacion: datetime = Field(default_factory=datetime.utcnow)


class PropuestaCorreccion(BaseModel):
    """Propuesta de corrección con workflow de aprobación."""
    id: str = Field(default_factory=lambda: str(__import__('uuid').uuid4())[:8])
    hallazgo_id: str
    descripcion_original: str
    descripcion_propuesta: str
    cambio: Dict[str, Any]
    estado: str = "PENDIENTE"  # PENDIENTE, ACEPTADA, RECHAZADA
    usuario_decision: Optional[str] = None
    fecha_decision: Optional[datetime] = None
    fecha_propuesta: datetime = Field(default_factory=datetime.utcnow)


class VersionProposicion(BaseModel):
    """Versionado de proposición."""
    proposicion_id: UUID
    version: int
    estado_validacion: EstadoSolvencia
    hallazgos: List[Hallazgo]
    correcciones_aplicadas: List[PropuestaCorreccion]
    prefall_result: Optional[PreFallResult] = None
    fecha_creacion: datetime = Field(default_factory=datetime.utcnow)
