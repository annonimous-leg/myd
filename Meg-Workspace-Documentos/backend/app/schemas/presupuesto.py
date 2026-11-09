# Copyright © 2026 Cristian Rodriguez
# All rights reserved.
# Unauthorized copying, modification, distribution, or use is prohibited
# without prior written permission.

"""
Schemas de presupuestos.
"""
from typing import Optional, List
from datetime import datetime
from pydantic import BaseModel, Field

from app.models.presupuesto import EstadoPresupuesto, ZonaEconomica


class PartidaCreate(BaseModel):
    numero: str
    descripcion: str
    unidad: str
    cantidad: float
    precio_unitario: float


class ConceptoCreate(BaseModel):
    clave: str
    descripcion: str
    unidad: str
    cantidad: float
    precio_unitario: float
    partida_id: Optional[str] = None


class InsumoCreate(BaseModel):
    clave: str
    descripcion: str
    unidad: str
    cantidad: float
    precio_unitario: float
    tipo: str  # MATERIAL, MANO_OBRA, MAQUINARIA, INDIRECTO


class PresupuestoCreate(BaseModel):
    expediente_id: str
    nombre: str = Field(..., max_length=255)
    descripcion: Optional[str] = None
    zona_economica: ZonaEconomica = ZonaEconomica.CENTRO
    partidas: Optional[List[PartidaCreate]] = Field(default_factory=list)


class PresupuestoOut(BaseModel):
    id: str
    expediente_id: str
    nombre: str
    descripcion: Optional[str]
    estado: str
    zona_economica: str
    monto_total: Optional[float]
    indirectos_pct: Optional[float]
    financiamiento_pct: Optional[float]
    utilidad_pct: Optional[float]
    cargo_adicional_pct: Optional[float]
    created_at: datetime
    updated_at: datetime

    class Config:
        from_attributes = True


class PresupuestoList(BaseModel):
    total: int
    items: List[PresupuestoOut]
