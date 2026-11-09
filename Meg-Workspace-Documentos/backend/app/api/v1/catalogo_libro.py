"""Read-only source catalogue available to authenticated estimators."""
from fastapi import APIRouter, Depends, Query
from app.core.deps import get_current_user
from app.core.rate_limit import rate_limit_standard
from app.services.catalogo_libro import buscar

router = APIRouter(dependencies=[Depends(get_current_user), Depends(rate_limit_standard)])


@router.get("")
async def listar(q: str = Query("", max_length=200), skip: int = Query(0, ge=0),
                 limit: int = Query(50, ge=1, le=100)):
    return buscar(q, skip, limit)
