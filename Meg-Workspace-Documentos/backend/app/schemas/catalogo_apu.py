# Copyright © 2026 Cristian Rodriguez
# All rights reserved.
# Unauthorized copying, modification, distribution, or use is prohibited
# without prior written permission.

"""
Schemas de catálogo APU.
"""
from typing import Optional, List
from datetime import datetime
from uuid import UUID
from pydantic import BaseModel, Field

from app.models.catalogo_apu import TipoConceptoAPU, UnidadMedida


class CatalogoAPUCreate(BaseModel):
    clave: str = Field(..., max_length=50)
    descripcion: str
    tipo: TipoConceptoAPU
    unidad: UnidadMedida
    precio_unitario: float = Field(..., ge=0)
    fuente: str = Field(..., max_length=100)
    zona_economica: Optional[str] = None
    estado: Optional[str] = None
    incluye_iva: bool = False
    desglose: Optional[dict] = None


class CatalogoAPUOut(BaseModel):
    id: UUID
    clave: str
    descripcion: str
    tipo: str
    unidad: str
    precio_unitario: float
    fuente: str
    zona_economica: Optional[str]
    estado: Optional[str]
    incluye_iva: bool
    vigencia_inicio: Optional[str]
    vigencia_fin: Optional[str]
    origen: Optional[dict] = None
    created_at: datetime

    class Config:
        from_attributes = True


class CatalogoAPUList(BaseModel):
    total: int
    items: List[CatalogoAPUOut]
