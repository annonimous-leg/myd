# Copyright © 2026 Cristian Rodriguez
# All rights reserved.
# Unauthorized copying, modification, distribution, or use is prohibited
# without prior written permission.

"""
API de auditoría y bitácora inmutable.
Consultas de historial, verificación de integridad y reportes.
"""
from app.core.rate_limit import rate_limit_standard, rate_limit_strict
from typing import List, Optional
from uuid import UUID
from datetime import datetime

from fastapi import APIRouter, Depends, Query
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.deps import (
    get_current_user, get_db, verificar_expediente_tenant, verificar_documento_tenant,
)
from app.core.entitlements import requiere_godadmin
from app.core.errors import MegalodonException, ErrorCode
from app.models.user import User
from app.modules.audit.service import AuditService
from app.models.audit_ledger import TipoAccion

router = APIRouter()


@router.get("/historial/expediente/{expediente_id}")
async def historial_expediente(
    expediente_id: UUID,
    skip: int = Query(0, ge=0),
    limit: int = Query(100, ge=1, le=500),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
    _tenant_ok: None = Depends(verificar_expediente_tenant), _rate_limit: bool = Depends(rate_limit_standard),
):
    """Obtiene el historial de auditoría de un expediente."""
    service = AuditService(db)
    return await service.obtener_historial_expediente(
        expediente_id, skip=skip, limit=limit, tenant_id=current_user.tenant_id
    )


@router.get("/historial/documento/{documento_id}")
async def historial_documento(
    documento_id: UUID,
    skip: int = Query(0, ge=0),
    limit: int = Query(100, ge=1, le=500),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
    _tenant_ok: None = Depends(verificar_documento_tenant), _rate_limit: bool = Depends(rate_limit_standard),
):
    """Obtiene el historial de auditoría de un documento."""
    service = AuditService(db)
    return await service.obtener_historial_documento(
        documento_id, skip=skip, limit=limit, tenant_id=current_user.tenant_id
    )


@router.get("/verificar-integridad/{entidad_tipo}/{entidad_id}", dependencies=[Depends(requiere_godadmin)])
async def verificar_integridad(
    entidad_tipo: str,
    entidad_id: str,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user), _rate_limit: bool = Depends(rate_limit_standard),
):
    """Verifica la integridad criptográfica de la cadena de registros."""
    service = AuditService(db)
    return await service.verificar_integridad_cadena(entidad_tipo, entidad_id, global_scope=True)


@router.get("/reporte/usuario/{user_id}")
async def reporte_usuario(
    user_id: UUID,
    fecha_inicio: Optional[datetime] = None,
    fecha_fin: Optional[datetime] = None,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user), _rate_limit: bool = Depends(rate_limit_standard),
):
    """Genera reporte de actividad de un usuario."""
    # BUG ORIGINAL: no había ningún control de acceso -- cualquier usuario
    # autenticado de cualquier tenant podía pedir el reporte de actividad
    # de CUALQUIER user_id de CUALQUIER otro tenant. Se restringe a
    # usuarios del mismo tenant (o SUPERADMIN, que sí ve toda la
    # plataforma).
    objetivo = await db.get(User, user_id)
    if not objetivo or (
        current_user.role != "superadmin"
        and objetivo.tenant_id != current_user.tenant_id
    ):
        raise MegalodonException(
            ErrorCode.DOCUMENTO_NO_ENCONTRADO, "Usuario no encontrado"
        )
    service = AuditService(db)
    if objetivo.tenant_id is None:
        if current_user.role != "superadmin":
            raise MegalodonException(
                ErrorCode.DOCUMENTO_NO_ENCONTRADO, "Usuario no encontrado"
            )
        return await service.reporte_actividad_usuario(
            user_id, fecha_inicio=fecha_inicio, fecha_fin=fecha_fin, global_scope=True
        )
    return await service.reporte_actividad_usuario(
        user_id,
        fecha_inicio=fecha_inicio,
        fecha_fin=fecha_fin,
        tenant_id=objetivo.tenant_id,
    )


@router.get("/reporte/sistema", dependencies=[Depends(requiere_godadmin)])
async def reporte_sistema(
    fecha_inicio: Optional[datetime] = None,
    fecha_fin: Optional[datetime] = None,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user), _rate_limit: bool = Depends(rate_limit_standard),
):
    """Genera reporte global de actividad del sistema (todos los tenants).

    BUG ORIGINAL: sin gate de rol -- cualquier usuario autenticado de
    cualquier tenant (incluido plan Free) podía pedir el reporte de
    actividad de TODA la plataforma, todos los tenants. Esto es
    exactamente lo que el freeze técnico reserva a GodAdmin
    ("auditoría global"); un Admin de empresa normal no debe verlo.
    """
    service = AuditService(db)
    return await service.reporte_actividad_sistema(
        fecha_inicio=fecha_inicio, fecha_fin=fecha_fin, global_scope=True
    )
