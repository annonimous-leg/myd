# Copyright © 2026 Cristian Rodriguez
# All rights reserved.
# Unauthorized copying, modification, distribution, or use is prohibited
# without prior written permission.

"""
Schemas de dashboard / analytics.
"""
from typing import Optional, List
from pydantic import BaseModel


class DashboardStats(BaseModel):
    total_expedientes: int
    expedientes_activos: int
    expedientes_archivados: int
    total_presupuestos: int
    monto_total_comprometido: float
    total_licitaciones: int
    licitaciones_en_proceso: int
    total_contratos: int
    contratos_vigentes: int
    total_proveedores: int
    proveedores_activos: int
    total_documentos: int
    documentos_pendientes_firma: int


class KPIData(BaseModel):
    label: str
    value: float
    change_pct: Optional[float] = None
    trend: Optional[str] = None  # up, down, stable


class DashboardResponse(BaseModel):
    stats: DashboardStats
    kpis: List[KPIData]
    recent_activity: List[dict]
