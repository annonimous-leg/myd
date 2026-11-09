# Copyright © 2026 Cristian Rodriguez
# All rights reserved.
# Unauthorized copying, modification, distribution, or use is prohibited
# without prior written permission.

"""
Schemas comunes: paginación, filtros, respuestas base.
"""
from typing import Optional, List, Generic, TypeVar
from pydantic import BaseModel, Field


class PaginationParams(BaseModel):
    skip: int = Field(0, ge=0)
    limit: int = Field(100, ge=1, le=1000)


class PaginatedResponse(BaseModel):
    total: int
    skip: int
    limit: int
    items: List


class FilterParams(BaseModel):
    q: Optional[str] = None
    fecha_desde: Optional[str] = None
    fecha_hasta: Optional[str] = None
    estado: Optional[str] = None
    tenant_id: Optional[str] = None


class MessageResponse(BaseModel):
    message: str
    detail: Optional[str] = None


class HealthCheck(BaseModel):
    status: str
    version: str
    environment: str
