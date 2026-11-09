# Copyright © 2026 Cristian Rodriguez
# All rights reserved.
# Unauthorized copying, modification, distribution, or use is prohibited
# without prior written permission.

"""
Schemas de BIM / IFC.
"""
from typing import Optional, List
from datetime import datetime
from pydantic import BaseModel, Field


class ModeloBIMCreate(BaseModel):
    expediente_id: str
    nombre: str = Field(..., max_length=255)
    descripcion: Optional[str] = None
    ifc_data: Optional[bytes] = None


class ModeloBIMOut(BaseModel):
    id: str
    expediente_id: str
    nombre: str
    descripcion: Optional[str]
    estado: str
    elementos_count: Optional[int]
    created_at: datetime

    class Config:
        from_attributes = True


class ClashDetectionRequest(BaseModel):
    tolerancia: float = 0.01


class ClashResultOut(BaseModel):
    id: str
    elemento_a_id: str
    elemento_b_id: str
    tipo_interferencia: str
    severidad: str
    estado: str

    class Config:
        from_attributes = True
