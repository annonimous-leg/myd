# Copyright © 2026 Cristian Rodriguez
# All rights reserved.
# Unauthorized copying, modification, distribution, or use is prohibited
# without prior written permission.

"""
API avanzada de presupuestos programables.
Análisis de variación, proyecciones, flujo de caja y comparativos.
"""
from typing import Optional
from uuid import UUID

from fastapi import APIRouter, Depends, Query, Body
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.rate_limit import rate_limit_standard, rate_limit_strict
from app.core.deps import (
    get_current_user,
    get_db,
    verificar_presupuesto_tenant,
    verificar_expediente_tenant,
)
from app.models.user import User
from app.models.presupuesto import ZonaEconomica
from app.modules.presupuestos.service import PresupuestoModuleService

router = APIRouter(dependencies=[Depends(verificar_expediente_tenant)])


@router.get("/{presupuesto_id}/analisis-variacion")
async def analisis_variacion(
    presupuesto_id: UUID,
    _presupuesto_ok: None = Depends(verificar_presupuesto_tenant),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user), _rate_limit: bool = Depends(rate_limit_standard),
):
    """Analiza las variaciones de costos entre planeado y real."""
    service = PresupuestoModuleService(db, current_user.tenant_id)
    return await service.analisis_variacion_costos(
        presupuesto_id,
        tenant_id=current_user.tenant_id,
    )


@router.get("/{presupuesto_id}/proyeccion-final")
async def proyeccion_final(
    presupuesto_id: UUID,
    metodo: str = Query("lineal", pattern="^(lineal|curva_s|exponencial)$"),
    _presupuesto_ok: None = Depends(verificar_presupuesto_tenant),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user), _rate_limit: bool = Depends(rate_limit_standard),
):
    """Proyecta el costo final basado en el avance actual."""
    service = PresupuestoModuleService(db, current_user.tenant_id)
    return await service.proyeccion_final(
        presupuesto_id,
        metodo=metodo,
        tenant_id=current_user.tenant_id,
    )


@router.get("/{presupuesto_id}/flujo-caja")
async def flujo_caja(
    presupuesto_id: UUID,
    num_periodos: int = Query(12, ge=1, le=60),
    _presupuesto_ok: None = Depends(verificar_presupuesto_tenant),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user), _rate_limit: bool = Depends(rate_limit_standard),
):
    """Genera proyección de flujo de caja por periodos."""
    service = PresupuestoModuleService(db, current_user.tenant_id)
    return await service.flujo_caja(
        presupuesto_id,
        num_periodos=num_periodos,
        tenant_id=current_user.tenant_id,
    )


@router.get("/comparativo-precios/{concepto_clave}")
async def comparativo_precios(
    concepto_clave: str,
    zona_economica: Optional[ZonaEconomica] = None,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user), _rate_limit: bool = Depends(rate_limit_standard),
):
    """Compara precios de un concepto contra históricos."""
    service = PresupuestoModuleService(db, current_user.tenant_id)
    return await service.comparativo_precios(
        concepto_clave,
        zona_economica=zona_economica,
        tenant_id=current_user.tenant_id,
    )


@router.post("/{presupuesto_id}/reprogramar")
async def reprogramar(
    presupuesto_id: UUID,
    nuevo_monto: Optional[float] = Body(None),
    nuevo_plazo: Optional[int] = Body(None),
    motivo: str = Body(...),
    _presupuesto_ok: None = Depends(verificar_presupuesto_tenant),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user), _rate_limit: bool = Depends(rate_limit_strict),
):
    """Crea una reprogramación del presupuesto."""
    service = PresupuestoModuleService(db, current_user.tenant_id)
    return await service.reprogramar_presupuesto(
        presupuesto_id,
        nuevo_monto=nuevo_monto,
        nuevo_plazo=nuevo_plazo,
        motivo=motivo,
        creado_por_id=current_user.id,
        tenant_id=current_user.tenant_id,
    )
