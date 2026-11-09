# Copyright © 2026 Cristian Rodriguez
# All rights reserved.
# Unauthorized copying, modification, distribution, or use is prohibited
# without prior written permission.

"""
Schemas de topografía.
"""
from typing import Optional, List
from datetime import datetime
from pydantic import BaseModel, Field

from app.models.topografia import TipoLevantamiento


class PuntoCreate(BaseModel):
    x: float
    y: float
    z: Optional[float] = None
    codigo: Optional[str] = None
    descripcion: Optional[str] = None


class LevantamientoCreate(BaseModel):
    expediente_id: str
    nombre: str = Field(..., max_length=255)
    tipo: TipoLevantamiento = TipoLevantamiento.POLIGONAL
    puntos: Optional[List[PuntoCreate]] = []


class LevantamientoOut(BaseModel):
    id: str
    expediente_id: str
    nombre: str
    tipo: str
    estado: str
    puntos_count: Optional[int]
    created_at: datetime

    class Config:
        from_attributes = True


class VolumenRequest(BaseModel):
    superficie_id: str
    cota_referencia: float
    metodo: str = "prismoides"  # prismoides, secciones, grid
