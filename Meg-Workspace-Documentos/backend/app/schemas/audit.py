# Copyright © 2026 Cristian Rodriguez
# All rights reserved.
# Unauthorized copying, modification, distribution, or use is prohibited
# without prior written permission.

"""
Schemas Pydantic para el módulo de auditoría.
"""
from typing import List, Optional, Dict, Any
from datetime import datetime
from pydantic import BaseModel


class AuditRegistroOut(BaseModel):
    id: str
    user_id: Optional[str]
    user_email: Optional[str]
    user_role: Optional[str]
    entidad_tipo: str
    entidad_id: str
    accion: str
    descripcion: Optional[str]
    datos_anteriores: Optional[Dict[str, Any]]
    datos_nuevos: Optional[Dict[str, Any]]
    hash_registro: str
    hash_previo: Optional[str]
    ip_address: Optional[str]
    created_at: str

    class Config:
        from_attributes = True


class VerificacionIntegridadOut(BaseModel):
    valido: bool
    registros: int
    errores: List[Dict[str, Any]]


class ReporteActividadOut(BaseModel):
    user_id: Optional[str]
    total_registros: int
    periodo: Dict[str, Optional[str]]
    acciones: Dict[str, int]
    entidades_afectadas: Dict[str, int]
    registros: List[Dict[str, Any]]


class ReporteSistemaOut(BaseModel):
    total_registros: int
    periodo: Dict[str, Optional[str]]
    top_usuarios: List[tuple]
    acciones: Dict[str, int]
