# Copyright © 2026 Cristian Rodriguez
# All rights reserved.
# Unauthorized copying, modification, distribution, or use is prohibited
# without prior written permission.

"""
Schemas de programación de obra.
"""
from typing import Optional, List
from datetime import datetime
from pydantic import BaseModel, Field

from app.models.programacion import TipoActividad, EstadoPrograma


class ActividadCreate(BaseModel):
    clave: str = Field(..., max_length=50)
    nombre: str = Field(..., max_length=500)
    tipo: TipoActividad = TipoActividad.CONSTRUCCION
    duracion_dias: int = Field(..., gt=0)
    predecesoras: Optional[List[str]] = Field(default_factory=list)
    fecha_inicio: Optional[str] = None
    fecha_fin: Optional[str] = None


class ProgramaCreate(BaseModel):
    expediente_id: str
    nombre: str = Field(..., max_length=255)
    descripcion: Optional[str] = None
    actividades: Optional[List[ActividadCreate]] = Field(default_factory=list)


class ProgramaOut(BaseModel):
    id: str
    expediente_id: str
    nombre: str
    descripcion: Optional[str]
    estado: str
    fecha_inicio: Optional[str]
    fecha_fin: Optional[str]
    duracion_total: Optional[int]
    created_at: datetime

    class Config:
        from_attributes = True


class AvanceUpdate(BaseModel):
    avance_pct: float = Field(..., ge=0, le=100)
    fecha_reporte: Optional[str] = None
    notas: Optional[str] = None
