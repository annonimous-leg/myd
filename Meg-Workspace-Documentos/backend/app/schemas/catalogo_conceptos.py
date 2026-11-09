# Copyright © 2026 Cristian Rodriguez
# All rights reserved.
# Unauthorized copying, modification, distribution, or use is prohibited
# without prior written permission.

"""
Schemas de catálogos de conceptos reales (CFE, CMIC, CONAGA).
"""
from typing import Optional, List
from uuid import UUID
from datetime import datetime
from pydantic import BaseModel, Field

from app.models.catalogo_conceptos import TipoCatalogo


class CatalogoFuenteCreate(BaseModel):
    nombre: str = Field(..., max_length=100)
    tipo: TipoCatalogo
    vigencia_inicio: str
    vigencia_fin: str
    descripcion: Optional[str] = None
    url_fuente: Optional[str] = None
    moneda: Optional[str] = Field(None, pattern=r'^[A-Z]{3}$')


class CatalogoFuenteOut(BaseModel):
    id: UUID
    nombre: str
    tipo: TipoCatalogo
    vigencia_inicio: str
    vigencia_fin: str
    descripcion: Optional[str] = None
    url_fuente: Optional[str] = None
    moneda: Optional[str] = None
    moneda_evidencia: Optional[dict] = None
    activo: bool
    created_at: datetime

    class Config:
        from_attributes = True


class ConceptoCatalogoCreate(BaseModel):
    fuente_id: UUID
    clave: str = Field(..., max_length=50)
    descripcion: str
    descripcion_larga: Optional[str] = None
    unidad: str = Field(..., max_length=20)
    precio_unitario: float = Field(..., ge=0)
    zona_economica: Optional[str] = None
    estado: Optional[str] = None
    region: Optional[str] = None
    incluye_iva: bool = False
    desglose: Optional[dict] = None


class ConceptoCatalogoOut(BaseModel):
    id: UUID
    fuente_id: UUID
    clave: str
    descripcion: str
    descripcion_larga: Optional[str]
    unidad: str
    precio_unitario: float
    zona_economica: Optional[str]
    estado: Optional[str]
    region: Optional[str]
    incluye_iva: bool
    activo: bool
    created_at: datetime

    class Config:
        from_attributes = True


class ConceptoCatalogoList(BaseModel):
    total: int
    items: List[ConceptoCatalogoOut]


class InsumoCatalogoCreate(BaseModel):
    fuente_id: UUID
    clave: str = Field(..., max_length=50)
    descripcion: str
    tipo: str  # MATERIAL, MANO_OBRA, MAQUINARIA, SALARIO_PROFESIONAL
    unidad: str = Field(..., max_length=20)
    precio_unitario: float = Field(..., ge=0)
    categoria: Optional[str] = None
    subcategoria: Optional[str] = None
    zona_economica: Optional[str] = None
    estado: Optional[str] = None
    incluye_iva: bool = False


class InsumoCatalogoOut(BaseModel):
    id: UUID
    fuente_id: UUID
    clave: str
    descripcion: str
    tipo: str
    unidad: str
    precio_unitario: float
    categoria: Optional[str]
    zona_economica: Optional[str]
    estado: Optional[str]
    activo: bool

    class Config:
        from_attributes = True
