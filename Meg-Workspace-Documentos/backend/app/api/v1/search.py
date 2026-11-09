# Copyright © 2026 Cristian Rodriguez
# All rights reserved.
# Unauthorized copying, modification, distribution, or use is prohibited
# without prior written permission.

"""
API de búsqueda avanzada y semántica.
Búsqueda global, por tags y autocompletado.
"""
from app.core.rate_limit import rate_limit_standard, rate_limit_strict
from typing import List, Optional
from uuid import UUID
from datetime import datetime

from fastapi import APIRouter, Depends, Query
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.deps import get_current_user, get_db
from app.models.user import User
from app.modules.search.service import SearchService

router = APIRouter()


@router.get("/global")
async def busqueda_global(
    q: str,
    dominios: Optional[List[str]] = Query(None),
    fecha_inicio: Optional[datetime] = None,
    fecha_fin: Optional[datetime] = None,
    skip: int = Query(0, ge=0),
    limit: int = Query(50, ge=1, le=200),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user), _rate_limit: bool = Depends(rate_limit_standard),
):
    """Búsqueda global across todos los dominios.

    BUG ORIGINAL: current_user se recibía pero nunca se usaba -- la
    búsqueda corría sin ningún filtro de tenant."""
    service = SearchService(db)
    return await service.busqueda_global(
        q,
        dominios=dominios,
        tenant_id=current_user.tenant_id,
        fecha_inicio=fecha_inicio,
        fecha_fin=fecha_fin,
        skip=skip,
        limit=limit,
    )


@router.get("/tags")
async def busqueda_por_tags(
    tags: List[str] = Query(...),
    operador: str = Query("AND", pattern="^(AND|OR)$"),
    skip: int = Query(0, ge=0),
    limit: int = Query(100, ge=1, le=500),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user), _rate_limit: bool = Depends(rate_limit_standard),
):
    """Búsqueda de documentos por tags."""
    service = SearchService(db)
    return await service.busqueda_por_tags(
        tags, tenant_id=current_user.tenant_id, operador=operador, skip=skip, limit=limit
    )


@router.get("/sugerencias")
async def sugerencias_autocompletar(
    q: str,
    dominio: str = Query("documentos"),
    limit: int = Query(10, ge=1, le=50),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user), _rate_limit: bool = Depends(rate_limit_standard),
):
    """Sugerencias de autocompletado para búsqueda."""
    service = SearchService(db)
    return await service.sugerencias_autocompletar(
        q, tenant_id=current_user.tenant_id, dominio=dominio, limit=limit
    )
