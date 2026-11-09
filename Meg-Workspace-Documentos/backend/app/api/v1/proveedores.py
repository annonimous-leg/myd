"""Minimal, persisted supplier registry for licitation operations."""
from fastapi import APIRouter, Depends, Query
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.deps import get_current_user, get_db, require_mutation_access
from app.core.errors import handle_megalodon_errors
from app.core.rate_limit import rate_limit_standard, rate_limit_strict
from app.models.user import User
from app.schemas.proveedor import ProveedorCreate, ProveedorList, ProveedorOut
from app.services.proveedor_service import ProveedorService

router = APIRouter(dependencies=[Depends(require_mutation_access)])
service = ProveedorService()


@router.get("", response_model=ProveedorList)
@handle_megalodon_errors
async def listar(q: str | None = Query(None, max_length=200), skip: int = Query(0, ge=0),
                 limit: int = Query(50, ge=1, le=200), db: AsyncSession = Depends(get_db),
                 current_user: User = Depends(get_current_user), _rate: bool = Depends(rate_limit_standard)):
    return await service.listar(db, current_user, q=q, skip=skip, limit=limit)


@router.post("", response_model=ProveedorOut, status_code=201)
@handle_megalodon_errors
async def crear(data: ProveedorCreate, db: AsyncSession = Depends(get_db),
                current_user: User = Depends(get_current_user), _rate: bool = Depends(rate_limit_strict)):
    return await service.crear(db, current_user, data)
