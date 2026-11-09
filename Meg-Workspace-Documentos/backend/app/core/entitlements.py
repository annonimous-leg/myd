# Copyright © 2026 Cristian Rodriguez
# All rights reserved.
# Unauthorized copying, modification, distribution, or use is prohibited
# without prior written permission.

"""
Dependencias de FastAPI para exigir plan mínimo o rol específico.

Uso:
    @router.post("/algo-pro")
    async def endpoint(
        current_user: User = Depends(get_current_user),
        _: None = Depends(requiere_plan_minimo(PlanTipo.PRO)),
    ):
        ...

Estas dependencias son la aplicación REAL del entitlement -- el
frontend puede (y debe) ocultar botones según lo que
GET /entitlements/modulos le diga, pero eso es solo UX. Quien de verdad
bloquea el acceso es esto: sin el header/rol/plan correctos, ni
ocultando el botón en React se puede saltar.
"""
from typing import Callable

from fastapi import Depends, HTTPException

from app.core.deps import get_current_user, get_db
from app.models.user import User, UserRole, Tenant
from app.models.entitlements import PlanTipo, ORDEN_PLAN
from app.services.entitlements_service import EntitlementsService
from sqlalchemy.ext.asyncio import AsyncSession


def requiere_plan_minimo(minimo: PlanTipo) -> Callable:
    async def _dependencia(
        current_user: User = Depends(get_current_user),
        db: AsyncSession = Depends(get_db),
    ) -> None:
        tenant = await db.get(Tenant, current_user.tenant_id)
        if tenant is None:
            raise HTTPException(status_code=403, detail="Tenant no encontrado o inactivo")
        service = EntitlementsService(db)
        plan_efectivo = service.calcular_plan_efectivo(tenant)
        if ORDEN_PLAN.get(PlanTipo(plan_efectivo), 0) < ORDEN_PLAN.get(minimo, 0):
            raise HTTPException(
                status_code=402,
                detail=(
                    f"Esta función requiere el plan {minimo.value} o superior. "
                    f"Tu plan actual es {plan_efectivo}."
                ),
            )

    return _dependencia


def requiere_rol(*roles: UserRole) -> Callable:
    async def _dependencia(current_user: User = Depends(get_current_user)) -> None:
        if current_user.role not in [r.value if isinstance(r, UserRole) else r for r in roles]:
            raise HTTPException(status_code=403, detail="No tienes permiso para acceder a esto.")

    return _dependencia


async def requiere_admin(current_user: User = Depends(get_current_user)) -> None:
    if current_user.role != UserRole.ADMIN.value:
        raise HTTPException(status_code=403, detail="No tienes permiso para acceder a esto.")


async def requiere_godadmin(current_user: User = Depends(get_current_user)) -> None:
    if current_user.role != UserRole.SUPERADMIN.value:
        raise HTTPException(status_code=403, detail="No tienes permiso para acceder a esto.")
