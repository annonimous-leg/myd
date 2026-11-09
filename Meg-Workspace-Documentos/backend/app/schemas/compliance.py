# Copyright © 2026 Cristian Rodriguez
# All rights reserved.
# Unauthorized copying, modification, distribution, or use is prohibited
# without prior written permission.

"""
Schemas de compliance con evaluación automática.
"""
from typing import Optional, List
from datetime import datetime
from pydantic import BaseModel, Field

from app.models.compliance import EstadoInconformidad, TipoSancion, EstadoRegla, SeveridadInconformidad


# ─── Regla de Cumplimiento ─────────────────────────────────────────────

class ReglaCumplimientoCreate(BaseModel):
    nombre: str = Field(..., max_length=255)
    descripcion: Optional[str] = None
    tipo_procedimiento: str
    etapa: str
    requisitos: Optional[dict] = None
    obligatorio: bool = True
    activa: bool = True
    condicion_evaluacion: Optional[str] = None


class ReglaCumplimientoOut(BaseModel):
    id: str
    nombre: str
    descripcion: Optional[str]
    tipo_procedimiento: str
    etapa: str
    obligatorio: bool
    activa: bool
    condicion_evaluacion: Optional[str]
    created_at: datetime

    class Config:
        from_attributes = True


# ─── Inconformidad ─────────────────────────────────────────────────────

class InconformidadCreate(BaseModel):
    expediente_id: str
    licitacion_id: Optional[str] = None
    contrato_id: Optional[str] = None
    titulo: str = Field(..., max_length=500)
    descripcion: str
    severidad: Optional[SeveridadInconformidad] = None
    regla_id: Optional[str] = None
    asignado_a: Optional[str] = None
    fecha_limite: Optional[str] = None
    evidencia: Optional[dict] = None


class InconformidadUpdate(BaseModel):
    titulo: Optional[str] = None
    descripcion: Optional[str] = None
    severidad: Optional[SeveridadInconformidad] = None
    estado: Optional[EstadoInconformidad] = None
    asignado_a: Optional[str] = None
    fecha_limite: Optional[str] = None
    respuesta: Optional[str] = None
    resolucion: Optional[str] = None
    dictamen: Optional[str] = None
    fecha_dictamen: Optional[str] = None
    evidencia: Optional[dict] = None


class InconformidadOut(BaseModel):
    id: str
    expediente_id: str
    licitacion_id: Optional[str]
    contrato_id: Optional[str]
    titulo: str
    descripcion: str
    severidad: Optional[str]
    regla_id: Optional[str]
    asignado_a: Optional[str]
    fecha_limite: Optional[str]
    estado: str
    evidencia: Optional[dict]
    respuesta: Optional[str]
    resolucion: Optional[str]
    dictamen: Optional[str]
    fecha_dictamen: Optional[str]
    created_at: datetime

    class Config:
        from_attributes = True


# ─── Sanción ───────────────────────────────────────────────────────────

class SancionCreate(BaseModel):
    proveedor_id: str
    expediente_id: Optional[str] = None
    licitacion_id: Optional[str] = None
    tipo: TipoSancion
    motivo: str
    monto_multa: Optional[float] = None
    expediente_sancionador: Optional[str] = None
    hechos: Optional[str] = None
    pruebas: Optional[dict] = None
    audiencia_fecha: Optional[str] = None
    resolucion: Optional[str] = None
    vigencia_inicio: Optional[str] = None
    vigencia_fin: Optional[str] = None


class SancionOut(BaseModel):
    id: str
    proveedor_id: str
    expediente_id: Optional[str]
    licitacion_id: Optional[str]
    tipo: str
    motivo: str
    monto_multa: Optional[float]
    expediente_sancionador: Optional[str]
    hechos: Optional[str]
    pruebas: Optional[dict]
    audiencia_fecha: Optional[str]
    resolucion: Optional[str]
    vigencia_inicio: Optional[str]
    vigencia_fin: Optional[str]
    estado: str
    created_at: datetime

    class Config:
        from_attributes = True


# ─── Evaluación de Compliance ──────────────────────────────────────────

class EvaluacionComplianceCreate(BaseModel):
    licitacion_id: Optional[str] = None
    contrato_id: Optional[str] = None
    regla_id: str
    estado: EstadoRegla
    observaciones: Optional[str] = None
    evidencia: Optional[dict] = None


class EvaluacionComplianceOut(BaseModel):
    id: str
    licitacion_id: Optional[str]
    contrato_id: Optional[str]
    regla_id: str
    estado: str
    observaciones: Optional[str]
    evidencia: Optional[dict]
    created_at: datetime

    class Config:
        from_attributes = True


# ─── Listas ────────────────────────────────────────────────────────────

class ComplianceOut(ReglaCumplimientoOut):
    """Representación de una regla de cumplimiento."""


class ComplianceList(BaseModel):
    total: int
    items: List[ComplianceOut]
