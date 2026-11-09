# Copyright © 2026 Cristian Rodriguez
# All rights reserved.
# Unauthorized copying, modification, distribution, or use is prohibited
# without prior written permission.

"""
Schemas de contratos con administración contractual completa.
"""
from typing import Optional, List
from datetime import datetime, date
from uuid import UUID
from pydantic import BaseModel, Field, ConfigDict

from app.models.contrato import EstadoContrato, TipoGarantia, TipoModificacion, TipoPenalizacion


# ─── Convenio Modificatorio ────────────────────────────────────────────

class ConvenioModificatorioCreate(BaseModel):
    model_config = ConfigDict(allow_inf_nan=False)
    numero: str = Field(..., max_length=50)
    tipo: TipoModificacion
    descripcion: Optional[str] = None
    monto_anterior: Optional[float] = Field(None, ge=0)
    monto_nuevo: Optional[float] = Field(None, ge=0)
    plazo_anterior: Optional[int] = Field(None, gt=0)
    plazo_nuevo: Optional[int] = Field(None, gt=0)
    justificacion: Optional[str] = None


class ConvenioModificatorioOut(BaseModel):
    id: UUID
    contrato_id: UUID
    numero: str
    tipo: str
    descripcion: Optional[str]
    monto_anterior: Optional[float]
    monto_nuevo: Optional[float]
    plazo_anterior: Optional[int]
    plazo_nuevo: Optional[int]
    justificacion: Optional[str]
    fecha_aprobacion: Optional[str]
    created_at: datetime

    class Config:
        from_attributes = True


# ─── Garantía ──────────────────────────────────────────────────────────

class GarantiaCreate(BaseModel):
    tipo: TipoGarantia
    monto: float = Field(..., ge=0)
    institucion: Optional[str] = None
    numero_poliza: Optional[str] = None
    vigencia_inicio: Optional[str] = None
    vigencia_fin: Optional[str] = None


class GarantiaOut(BaseModel):
    id: UUID
    contrato_id: UUID
    tipo: str
    monto: float
    institucion: Optional[str]
    numero_poliza: Optional[str]
    vigencia_inicio: Optional[str]
    vigencia_fin: Optional[str]
    activa: bool
    liberada: bool
    ejecutada: bool
    fecha_liberacion: Optional[str]
    created_at: datetime

    class Config:
        from_attributes = True


# ─── Entregable / Estimación ───────────────────────────────────────────

class EntregableCreate(BaseModel):
    model_config = ConfigDict(allow_inf_nan=False)
    numero_estimacion: int = Field(..., ge=1)
    periodo_inicio: Optional[str] = None
    periodo_fin: Optional[str] = None
    monto_ejecutado: float = Field(0, ge=0)
    avance_fisico: float = Field(..., ge=0, le=100)
    avance_financiero: float = Field(0, ge=0, le=100)


class EntregableOut(BaseModel):
    id: UUID
    contrato_id: UUID
    numero_estimacion: int
    periodo_inicio: Optional[str]
    periodo_fin: Optional[str]
    monto_ejecutado: float
    avance_fisico: float
    avance_financiero: float
    aprobado: bool
    fecha_aprobacion: Optional[str]
    created_at: datetime

    class Config:
        from_attributes = True


# ─── Penalización ──────────────────────────────────────────────────────

class PenalizacionCreate(BaseModel):
    tipo: TipoPenalizacion
    monto: float = Field(..., ge=0)
    dias_atraso: Optional[int] = None
    descripcion: str
    tope_legal: float


class PenalizacionOut(BaseModel):
    id: UUID
    contrato_id: UUID
    tipo: str
    monto: float
    dias_atraso: Optional[int]
    descripcion: str
    tope_legal: float
    dentro_tope: bool
    aplicada: bool
    fecha_aplicacion: Optional[str]
    created_at: datetime

    class Config:
        from_attributes = True


# ─── Contrato ──────────────────────────────────────────────────────────

class ContratoCreate(BaseModel):
    model_config = ConfigDict(allow_inf_nan=False)
    expediente_id: UUID
    licitacion_id: Optional[UUID] = None
    proveedor_id: UUID
    numero_contrato: str = Field(..., max_length=100)
    objeto: str
    monto_total: float = Field(..., ge=0)
    plazo_dias: int = Field(..., gt=0)
    fecha_firma: Optional[str] = None
    fecha_inicio: Optional[str] = None
    fecha_termino: Optional[str] = None
    clausulas: Optional[dict] = None
    obligaciones: Optional[dict] = None


class ContratoUpdate(BaseModel):
    model_config = ConfigDict(extra='forbid', allow_inf_nan=False)
    monto_total: Optional[float] = Field(None, ge=0)
    plazo_dias: Optional[int] = Field(None, gt=0)
    fecha_firma: Optional[str] = None
    fecha_inicio: Optional[str] = None
    fecha_termino: Optional[str] = None


class FiniquitoCreate(BaseModel):
    fecha_finiquito: date


class ContratoOut(BaseModel):
    id: UUID
    expediente_id: UUID
    licitacion_id: Optional[UUID]
    proveedor_id: UUID
    numero_contrato: str
    estado: str
    objeto: str
    monto_total: float
    monto_original: Optional[float]
    plazo_dias: int
    plazo_original: Optional[int]
    fecha_firma: Optional[str]
    fecha_inicio: Optional[str]
    fecha_termino: Optional[str]
    fecha_termino_original: Optional[str]
    anticipo_otorgado: float
    avance_fisico: float
    avance_financiero: float
    fecha_finiquito: Optional[str]
    monto_finiquito: Optional[float]
    created_at: datetime
    updated_at: datetime

    class Config:
        from_attributes = True


class ContratoList(BaseModel):
    total: int
    items: List[ContratoOut]


class ContratoDetalleOut(ContratoOut):
    modificatorios: List[ConvenioModificatorioOut] = []
    garantias: List[GarantiaOut] = []
    entregables: List[EntregableOut] = []
    penalizaciones: List[PenalizacionOut] = []

    class Config:
        from_attributes = True
