# Copyright © 2026 Cristian Rodriguez
# All rights reserved.
# Unauthorized copying, modification, distribution, or use is prohibited
# without prior written permission.

"""
Schemas de documentos / CDE.
"""
from typing import Optional, List
from datetime import datetime
from pydantic import BaseModel, Field, ConfigDict

from app.models.documento import EstadoDocumento, TipoDocumento


class DocumentoCreate(BaseModel):
    model_config = ConfigDict(populate_by_name=True)
    expediente_id: str
    nombre: str = Field(..., max_length=500)
    tipo: TipoDocumento
    metadatos: Optional[dict] = Field(default=None, alias="metadata")


class DocumentoUpdate(BaseModel):
    model_config = ConfigDict(populate_by_name=True)
    nombre: Optional[str] = None
    estado: Optional[EstadoDocumento] = None
    metadatos: Optional[dict] = Field(default=None, alias="metadata")


class DocumentoOut(BaseModel):
    id: str
    expediente_id: str
    nombre: str
    tipo: str
    estado: str
    mime_type: Optional[str]
    tamaño_bytes: Optional[int]
    hash_sha256: Optional[str]
    version: int
    firmado: bool
    ocr_completado: bool
    created_at: datetime
    updated_at: datetime

    class Config:
        from_attributes = True


class DocumentoList(BaseModel):
    total: int
    items: List[DocumentoOut]
