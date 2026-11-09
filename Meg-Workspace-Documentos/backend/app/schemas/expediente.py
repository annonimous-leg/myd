# Copyright © 2026 Cristian Rodriguez
# All rights reserved.
# Unauthorized copying, modification, distribution, or use is prohibited
# without prior written permission.

"""
Schemas de expedientes.
"""
from typing import Optional, List
from datetime import datetime
from pydantic import BaseModel, Field

from app.models.expediente import EstadoExpediente, TipoContrato, ClasificacionSeguridad


class ExpedienteCreate(BaseModel):
    titulo: str = Field(..., min_length=5, max_length=500)
    descripcion: Optional[str] = None
    organo: str
    unidad_administrativa: str
    serie_documental: str
    subserie_documental: str
    proyecto_nombre: Optional[str] = None
    ubicacion_obra: Optional[str] = None
    monto_contrato: Optional[float] = None
    plazo_dias: Optional[int] = None
    tipo_contrato: TipoContrato = TipoContrato.PRECIOS_UNITARIOS
    responsable_tecnico: Optional[str] = None
    responsable_ejecutivo: Optional[str] = None


class ExpedienteUpdate(BaseModel):
    titulo: Optional[str] = None
    descripcion: Optional[str] = None
    estado: Optional[EstadoExpediente] = None
    monto_contrato: Optional[float] = None
    plazo_dias: Optional[int] = None
    responsable_tecnico: Optional[str] = None
    responsable_ejecutivo: Optional[str] = None


class ExpedienteOut(BaseModel):
    id: str
    identificador: str
    titulo: str
    descripcion: Optional[str]
    estado: str
    organo: str
    unidad_administrativa: str
    monto_contrato: Optional[float]
    plazo_dias: Optional[int]
    tipo_contrato: str
    responsable_tecnico: Optional[str]
    responsable_ejecutivo: Optional[str]
    created_at: datetime
    updated_at: datetime
    creado_por_id: Optional[str]

    class Config:
        from_attributes = True


class ExpedienteList(BaseModel):
    total: int
    items: List[ExpedienteOut]
