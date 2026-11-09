# Copyright © 2026 Cristian Rodriguez
# All rights reserved.
# Unauthorized copying, modification, distribution, or use is prohibited
# without prior written permission.

"""
Schemas de transparencia / open data.
"""
from typing import Optional, List
from datetime import datetime
from pydantic import BaseModel


class ExpedientePublico(BaseModel):
    id: str
    folio: str
    tipo_procedimiento: str
    estado: str
    objeto: str
    monto_estimado: Optional[float]
    monto_adjudicado: Optional[float]
    fecha_convocatoria: Optional[str]
    fecha_fallo: Optional[str]
    proveedor_ganador: Optional[str]
    documentos_publicos: List[dict]


class DatasetExport(BaseModel):
    formato: str  # csv, json, xlsx
    filtros: Optional[dict] = None
    url_descarga: Optional[str] = None
