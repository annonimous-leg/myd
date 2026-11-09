# Copyright © 2026 Cristian Rodriguez
"""Router de catálogo APU — Análisis de Precios Unitarios."""
from app.core.rate_limit import rate_limit_standard, rate_limit_strict
from typing import Optional
from uuid import UUID
from fastapi import APIRouter, Depends, Query, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.deps import require_mutation_access, get_db, get_current_user
from app.models.user import User
from app.schemas.catalogo_apu import CatalogoAPUCreate, CatalogoAPUOut, CatalogoAPUList
from app.services.catalogo_apu_service import CatalogoAPUService
from app.core.errors import handle_megalodon_errors

router = APIRouter(dependencies=[Depends(require_mutation_access)], tags=["Catálogo APU"])  # prefijo va solo en router.py (ver INTEGRACIÓN ZIP / auditoría de rutas)
service = CatalogoAPUService()

@router.post("", response_model=CatalogoAPUOut, status_code=status.HTTP_201_CREATED)
@handle_megalodon_errors
async def crear_concepto_apu(
    data: CatalogoAPUCreate,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user), _rate_limit: bool = Depends(rate_limit_strict),
):
    """Crea un nuevo concepto APU en el catálogo maestro."""
    return await service.crear(db, data, current_user)

@router.get("", response_model=CatalogoAPUList)
@handle_megalodon_errors
async def listar_conceptos_apu(
    skip: int = Query(0, ge=0),
    limit: int = Query(100, ge=1, le=500),
    fuente: Optional[str] = Query(None),
    zona: Optional[str] = Query(None),
    tipo: Optional[str] = Query(None),
    q: Optional[str] = Query(None, description="Búsqueda en clave, descripción o fuente"),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user), _rate_limit: bool = Depends(rate_limit_standard),
):
    """Lista conceptos APU con filtros y búsqueda full-text."""
    return await service.listar(db, current_user, skip, limit, fuente, zona, tipo, q)

@router.get("/{concepto_id}", response_model=CatalogoAPUOut)
@handle_megalodon_errors
async def obtener_concepto_apu(
    concepto_id: UUID,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user), _rate_limit: bool = Depends(rate_limit_standard),
):
    """Obtiene un concepto APU por ID."""
    return await service.obtener(db, concepto_id, current_user)

@router.patch("/{concepto_id}", response_model=CatalogoAPUOut)
@handle_megalodon_errors
async def actualizar_concepto_apu(
    concepto_id: UUID,
    data: CatalogoAPUCreate,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user), _rate_limit: bool = Depends(rate_limit_strict),
):
    """Actualiza un concepto APU existente."""
    return await service.actualizar(db, concepto_id, data, current_user)

@router.delete("/{concepto_id}", status_code=status.HTTP_204_NO_CONTENT)
@handle_megalodon_errors
async def eliminar_concepto_apu(
    concepto_id: UUID,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user), _rate_limit: bool = Depends(rate_limit_strict),
):
    """Elimina un concepto APU."""
    await service.eliminar(db, concepto_id, current_user)

@router.get("/{concepto_id}/precio-con-iva")
@handle_megalodon_errors
async def obtener_precio_con_iva(
    concepto_id: UUID,
    tasa_iva: float = Query(0.16, ge=0, le=1),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user), _rate_limit: bool = Depends(rate_limit_standard),
):
    """Obtiene precio unitario con y sin IVA (INP al tiempo real)."""
    return await service.obtener_precio_con_iva(db, concepto_id, tasa_iva, current_user)
