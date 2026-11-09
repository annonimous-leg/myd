# Copyright © 2026 Cristian Rodriguez
"""Router de catálogo de conceptos — Fuentes, conceptos e insumos."""
from app.core.rate_limit import rate_limit_standard, rate_limit_strict
from typing import Optional, List
from uuid import UUID
from fastapi import APIRouter, Depends, Query, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.deps import get_db, get_current_user
from app.core.entitlements import requiere_admin
from app.models.user import User
from app.schemas.catalogo_conceptos import (
    CatalogoFuenteCreate, CatalogoFuenteOut, ConceptoCatalogoCreate,
    ConceptoCatalogoOut, ConceptoCatalogoList, InsumoCatalogoCreate, InsumoCatalogoOut,
)
from app.services.catalogo_conceptos_service import CatalogoConceptosService
from app.core.errors import handle_megalodon_errors

router = APIRouter(tags=["Catálogo Conceptos"], dependencies=[Depends(requiere_admin)])  # prefijo va solo en router.py
service = CatalogoConceptosService()

# ─── FUENTES ─────────────────────────────────────────────────────────────────

@router.post("/fuentes", response_model=CatalogoFuenteOut, status_code=status.HTTP_201_CREATED)
@handle_megalodon_errors
async def crear_fuente(
    data: CatalogoFuenteCreate,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user), _rate_limit: bool = Depends(rate_limit_strict),
):
    """Registra una fuente de catálogo (CFE, CMIC, CONAGA, etc.)."""
    return await service.crear_fuente(db, data, current_user)

@router.get("/fuentes", response_model=List[CatalogoFuenteOut])
@handle_megalodon_errors
async def listar_fuentes(
    activo: Optional[bool] = Query(None),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user), _rate_limit: bool = Depends(rate_limit_standard),
):
    """Lista fuentes de catálogo."""
    return await service.listar_fuentes(db, activo)

# ─── CONCEPTOS ───────────────────────────────────────────────────────────────

@router.post("/conceptos", response_model=ConceptoCatalogoOut, status_code=status.HTTP_201_CREATED)
@handle_megalodon_errors
async def crear_concepto(
    data: ConceptoCatalogoCreate,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user), _rate_limit: bool = Depends(rate_limit_strict),
):
    """Crea un concepto de trabajo en el catálogo."""
    return await service.crear_concepto(db, data, current_user)

@router.get("/conceptos", response_model=ConceptoCatalogoList)
@handle_megalodon_errors
async def listar_conceptos(
    skip: int = Query(0, ge=0),
    limit: int = Query(100, ge=1, le=500),
    fuente_id: Optional[str] = Query(None),
    zona: Optional[str] = Query(None),
    estado: Optional[str] = Query(None),
    q: Optional[str] = Query(None),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user), _rate_limit: bool = Depends(rate_limit_standard),
):
    """Busca/lista conceptos con filtros por fuente, zona, estado y texto."""
    return await service.listar_conceptos(db, skip, limit, fuente_id, zona, estado, q)

@router.get("/conceptos/{concepto_id}", response_model=ConceptoCatalogoOut)
@handle_megalodon_errors
async def obtener_concepto(
    concepto_id: UUID,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user), _rate_limit: bool = Depends(rate_limit_standard),
):
    """Obtiene un concepto por ID."""
    return await service.obtener_concepto(db, concepto_id)

@router.patch("/conceptos/{concepto_id}", response_model=ConceptoCatalogoOut)
@handle_megalodon_errors
async def actualizar_concepto(
    concepto_id: UUID,
    data: ConceptoCatalogoCreate,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user), _rate_limit: bool = Depends(rate_limit_strict),
):
    """Actualiza un concepto existente."""
    return await service.actualizar_concepto(db, concepto_id, data, current_user)

@router.get("/conceptos/{concepto_id}/costo-desglosado")
@handle_megalodon_errors
async def calcular_costo_desglosado(
    concepto_id: UUID,
    cantidad: float = Query(1.0, gt=0),
    tasa_iva: float = Query(0.16, ge=0, le=1),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user), _rate_limit: bool = Depends(rate_limit_standard),
):
    """Calcula el costo desglosado: materiales + mano obra + maquinaria + indirectos + IVA."""
    return await service.calcular_costo_desglosado(db, concepto_id, cantidad, tasa_iva)

# ─── INSUMOS ─────────────────────────────────────────────────────────────────

@router.post("/insumos", response_model=InsumoCatalogoOut, status_code=status.HTTP_201_CREATED)
@handle_megalodon_errors
async def crear_insumo(
    data: InsumoCatalogoCreate,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user), _rate_limit: bool = Depends(rate_limit_strict),
):
    """Crea un insumo desglosado (material, mano de obra, maquinaria, salario profesional)."""
    return await service.crear_insumo(db, data, current_user)

@router.get("/insumos", response_model=List[InsumoCatalogoOut])
@handle_megalodon_errors
async def listar_insumos(
    skip: int = Query(0, ge=0),
    limit: int = Query(100, ge=1, le=500),
    fuente_id: Optional[str] = Query(None),
    tipo: Optional[str] = Query(None),
    categoria: Optional[str] = Query(None),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user), _rate_limit: bool = Depends(rate_limit_standard),
):
    """Lista insumos con filtros."""
    return await service.listar_insumos(db, skip, limit, fuente_id, tipo, categoria)
