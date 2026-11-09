# Copyright © 2026 Cristian Rodriguez
# All rights reserved.
# Unauthorized copying, modification, distribution, or use is prohibited
# without prior written permission.

"""
API avanzada de expedientes.
Resumen completo, timeline, búsqueda y control de estados.
"""
from app.core.rate_limit import rate_limit_standard, rate_limit_strict
from typing import Optional
from uuid import UUID
from datetime import datetime

from fastapi import APIRouter, Depends, Query, Body
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.deps import require_mutation_access, get_current_user, get_db, verificar_expediente_tenant
from app.models.user import User
from app.models.expediente import EstadoExpediente
from app.modules.expedientes.service import ExpedienteModuleService

router = APIRouter(dependencies=[Depends(require_mutation_access)], )


@router.get("/{expediente_id}/resumen-completo")
async def resumen_completo(
    expediente_id: UUID,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
    _tenant_ok: None = Depends(verificar_expediente_tenant), _rate_limit: bool = Depends(rate_limit_standard),
):
    """Obtiene un resumen completo del expediente con todos sus artefactos."""
    service = ExpedienteModuleService(db, current_user.tenant_id)
    return await service.obtener_resumen_completo(expediente_id, tenant_id=current_user.tenant_id)


@router.get("/{expediente_id}/timeline")
async def timeline(
    expediente_id: UUID,
    skip: int = Query(0, ge=0),
    limit: int = Query(100, ge=1, le=500),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
    _tenant_ok: None = Depends(verificar_expediente_tenant), _rate_limit: bool = Depends(rate_limit_standard),
):
    """Obtiene la línea de tiempo del expediente."""
    service = ExpedienteModuleService(db, current_user.tenant_id)
    return await service.obtener_timeline(
        expediente_id, skip=skip, limit=limit
    )


@router.get("/busqueda-avanzada")
async def buscar_expedientes(
    q: Optional[str] = None,
    estado: Optional[EstadoExpediente] = None,
    tipo_contrato: Optional[str] = None,
    fecha_inicio: Optional[datetime] = None,
    fecha_fin: Optional[datetime] = None,
    monto_min: Optional[float] = None,
    monto_max: Optional[float] = None,
    skip: int = Query(0, ge=0),
    limit: int = Query(100, ge=1, le=500),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user), _rate_limit: bool = Depends(rate_limit_standard),
):
    """Búsqueda avanzada de expedientes."""
    # BUG ORIGINAL: ExpedienteModuleService.buscar_expedientes() ya
    # soporta filtrar por tenant_id (parámetro opcional), pero este router
    # nunca se lo pasaba -- la búsqueda regresaba expedientes de TODOS los
    # tenants, no solo el del usuario que busca.
    service = ExpedienteModuleService(db, current_user.tenant_id)
    return await service.buscar_expedientes(
        query=q,
        tenant_id=current_user.tenant_id,
        estado=estado,
        tipo_contrato=tipo_contrato,
        fecha_inicio=fecha_inicio,
        fecha_fin=fecha_fin,
        monto_min=monto_min,
        monto_max=monto_max,
        skip=skip,
        limit=limit,
    )


@router.post("/{expediente_id}/cambiar-estado")
async def cambiar_estado(
    expediente_id: UUID,
    nuevo_estado: EstadoExpediente = Body(...),
    motivo: Optional[str] = Body(None),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
    _tenant_ok: None = Depends(verificar_expediente_tenant), _rate_limit: bool = Depends(rate_limit_strict),
):
    """Cambia el estado de un expediente con validación de transiciones."""
    service = ExpedienteModuleService(db, current_user.tenant_id)
    return await service.cambiar_estado_expediente(
        expediente_id,
        nuevo_estado,
        motivo=motivo,
        actualizado_por_id=current_user.id,
    )
