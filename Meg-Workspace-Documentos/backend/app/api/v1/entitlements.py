# Copyright © 2026 Cristian Rodriguez
# All rights reserved.
# Unauthorized copying, modification, distribution, or use is prohibited
# without prior written permission.

"""
API de entitlements: plan actual del tenant, catálogo de módulos para
el launcher, y administración (GodAdmin) de planes/módulos/tenants.
"""
from app.core.rate_limit import rate_limit_standard, rate_limit_strict
from typing import Any, Dict, List, Optional

from fastapi import APIRouter, Depends
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.deps import get_current_user, get_db
from app.core.entitlements import requiere_godadmin
from app.core.errors import handle_megalodon_errors, MegalodonException, ErrorCode
from app.models.user import User, Tenant
from app.models.entitlements import PlanLimite, AppModulo
from app.services.entitlements_service import EntitlementsService

router = APIRouter(tags=["Entitlements"])


class MiPlanOut(BaseModel):
    plan: str
    plan_efectivo: str
    plan_vencimiento: Optional[str] = None
    limites: Dict[str, Any]
    uso_actual: Dict[str, int]


class ModuloOut(BaseModel):
    app_id: str
    nombre: str
    estado: str
    requiere_plan: Optional[str] = None
    requiere_rol: Optional[List[str]] = None
    desbloqueado: bool
    motivo_bloqueo: Optional[str] = None


class PlanLimiteUpdate(BaseModel):
    max_proyectos_activos: Optional[int] = None
    max_corridas_costeo_mes: Optional[int] = None
    max_consultas_legl_mes: Optional[int] = None
    max_catalogos: Optional[int] = None
    max_usuarios: Optional[int] = None
    permite_api: Optional[bool] = None
    permite_jobs_pesados: Optional[bool] = None
    permite_multi_tenant: Optional[bool] = None
    precio_mensual: Optional[float] = None


class ModuloUpdate(BaseModel):
    estado: Optional[str] = None
    requiere_plan: Optional[str] = None
    requiere_rol: Optional[List[str]] = None
    activo: Optional[bool] = None


class TenantPlanManualUpdate(BaseModel):
    plan: str
    dias_vigencia: int = 31


@router.get("/mi-plan", response_model=MiPlanOut)
@handle_megalodon_errors
async def obtener_mi_plan(
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user), _rate_limit: bool = Depends(rate_limit_standard),
):
    tenant = await db.get(Tenant, current_user.tenant_id)
    service = EntitlementsService(db)
    plan_efectivo = service.calcular_plan_efectivo(tenant)
    limites = await service.obtener_limites(plan_efectivo)
    uso = await service._obtener_o_crear_uso(tenant.id)

    return MiPlanOut(
        plan=tenant.plan,
        plan_efectivo=plan_efectivo,
        plan_vencimiento=tenant.plan_vencimiento.isoformat() if tenant.plan_vencimiento else None,
        limites={
            "max_proyectos_activos": limites.max_proyectos_activos,
            "max_corridas_costeo_mes": limites.max_corridas_costeo_mes,
            "max_consultas_legl_mes": limites.max_consultas_legl_mes,
            "max_catalogos": limites.max_catalogos,
            "max_usuarios": limites.max_usuarios,
            "permite_api": limites.permite_api,
            "permite_jobs_pesados": limites.permite_jobs_pesados,
            "permite_multi_tenant": limites.permite_multi_tenant,
        } if limites else {},
        uso_actual={"corridas_costeo": uso.corridas_costeo, "consultas_legl": uso.consultas_legl},
    )


@router.get("/modulos", response_model=List[ModuloOut])
@handle_megalodon_errors
async def listar_modulos(
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user), _rate_limit: bool = Depends(rate_limit_standard),
):
    """Fuente de verdad para el launcher del frontend: qué apps existen,
    con qué estado (core/demo/internal/admin_only) y si ESTE usuario/
    tenant las puede abrir ahora mismo."""
    tenant = await db.get(Tenant, current_user.tenant_id)
    service = EntitlementsService(db)
    modulos = await service.listar_modulos_para(tenant, current_user.role)
    return modulos


# ─── GodAdmin: administración de planes y módulos ──────────────────

@router.get("/admin/planes", response_model=List[Dict[str, Any]])
@handle_megalodon_errors
async def admin_listar_planes(
    db: AsyncSession = Depends(get_db),
    _: None = Depends(requiere_godadmin), _rate_limit: bool = Depends(rate_limit_standard),
):
    result = await db.execute(select(PlanLimite))
    return [
        {c.name: getattr(p, c.name) for c in PlanLimite.__table__.columns}
        for p in result.scalars().all()
    ]


@router.patch("/admin/planes/{plan}", response_model=Dict[str, Any])
@handle_megalodon_errors
async def admin_actualizar_plan(
    plan: str,
    data: PlanLimiteUpdate,
    db: AsyncSession = Depends(get_db),
    _: None = Depends(requiere_godadmin), _rate_limit: bool = Depends(rate_limit_strict),
):
    """Ajustar límites/precio de un plan sin redeploy."""
    result = await db.execute(select(PlanLimite).where(PlanLimite.plan == plan))
    limite = result.scalar_one_or_none()
    if not limite:
        raise MegalodonException(ErrorCode.DOCUMENTO_NO_ENCONTRADO, f"Plan '{plan}' no encontrado")
    for campo, valor in data.model_dump(exclude_unset=True).items():
        setattr(limite, campo, valor)
    await db.commit()
    return {c.name: getattr(limite, c.name) for c in PlanLimite.__table__.columns}


@router.get("/admin/modulos", response_model=List[Dict[str, Any]])
@handle_megalodon_errors
async def admin_listar_modulos(
    db: AsyncSession = Depends(get_db),
    _: None = Depends(requiere_godadmin), _rate_limit: bool = Depends(rate_limit_standard),
):
    result = await db.execute(select(AppModulo).order_by(AppModulo.orden))
    return [
        {c.name: getattr(m, c.name) for c in AppModulo.__table__.columns}
        for m in result.scalars().all()
    ]


@router.patch("/admin/modulos/{app_id}", response_model=Dict[str, Any])
@handle_megalodon_errors
async def admin_actualizar_modulo(
    app_id: str,
    data: ModuloUpdate,
    db: AsyncSession = Depends(get_db),
    _: None = Depends(requiere_godadmin), _rate_limit: bool = Depends(rate_limit_strict),
):
    result = await db.execute(select(AppModulo).where(AppModulo.app_id == app_id))
    modulo = result.scalar_one_or_none()
    if not modulo:
        raise MegalodonException(ErrorCode.DOCUMENTO_NO_ENCONTRADO, f"Módulo '{app_id}' no encontrado")
    for campo, valor in data.model_dump(exclude_unset=True).items():
        setattr(modulo, campo, valor)
    await db.commit()
    return {c.name: getattr(modulo, c.name) for c in AppModulo.__table__.columns}


@router.get("/admin/tenants", response_model=List[Dict[str, Any]])
@handle_megalodon_errors
async def admin_listar_tenants(
    db: AsyncSession = Depends(get_db),
    _: None = Depends(requiere_godadmin), _rate_limit: bool = Depends(rate_limit_standard),
):
    """GodAdmin: ver todos los tenants y su plan (para soporte/ventas)."""
    result = await db.execute(select(Tenant))
    return [
        {
            "id": str(t.id), "name": t.name, "slug": t.slug, "is_active": t.is_active,
            "plan": t.plan, "plan_vencimiento": t.plan_vencimiento.isoformat() if t.plan_vencimiento else None,
        }
        for t in result.scalars().all()
    ]


@router.patch("/admin/tenants/{tenant_id}/plan", response_model=Dict[str, Any])
@handle_megalodon_errors
async def admin_activar_plan_manual(
    tenant_id: str,
    data: TenantPlanManualUpdate,
    db: AsyncSession = Depends(get_db),
    _: None = Depends(requiere_godadmin), _rate_limit: bool = Depends(rate_limit_strict),
):
    """Bandera manual de plan (sin pasar por Mercado Pago/Stripe) --
    para cuentas de cortesía, pruebas, o mientras se resuelve un pago
    fuera de banda."""
    from datetime import datetime, timedelta, timezone

    tenant = await db.get(Tenant, tenant_id)
    if not tenant:
        raise MegalodonException(ErrorCode.DOCUMENTO_NO_ENCONTRADO, f"Tenant {tenant_id} no encontrado")
    tenant.plan = data.plan
    tenant.plan_vencimiento = (
        datetime.now(timezone.utc) + timedelta(days=data.dias_vigencia)
        if data.plan != "FREE" else None
    )
    await db.commit()
    return {"tenant_id": str(tenant.id), "plan": tenant.plan, "plan_vencimiento": tenant.plan_vencimiento}


@router.post("/admin/sembrar-defaults", response_model=Dict[str, int])
@handle_megalodon_errors
async def admin_sembrar_defaults(
    db: AsyncSession = Depends(get_db),
    _: None = Depends(requiere_godadmin), _rate_limit: bool = Depends(rate_limit_strict),
):
    """Siembra el catálogo default de planes y módulos si la instalación
    todavía no tiene ninguno (idempotente)."""
    service = EntitlementsService(db)
    planes = await service.sembrar_planes_default()
    modulos = await service.sembrar_modulos_default()
    return {"planes_creados": planes, "modulos_creados": modulos}
