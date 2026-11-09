# Copyright © 2026 Cristian Rodriguez
"""Router de compliance — Reglas, inconformidades, sanciones y evaluación."""
from app.core.rate_limit import rate_limit_standard, rate_limit_strict
from typing import Optional
from uuid import UUID
from fastapi import APIRouter, Depends, Query, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.deps import get_db, get_current_user
from app.models.user import User
from app.schemas.compliance import (
    ReglaCumplimientoCreate, ReglaCumplimientoOut,
    InconformidadCreate, InconformidadUpdate, InconformidadOut,
    SancionCreate, SancionOut,
)
from app.services.compliance_service import ComplianceService
from app.core.errors import handle_megalodon_errors

router = APIRouter(tags=["Compliance"])  # prefijo va solo en router.py
service = ComplianceService()

# ─── REGLAS ──────────────────────────────────────────────────────────────────

@router.post("/reglas", response_model=ReglaCumplimientoOut, status_code=status.HTTP_201_CREATED)
@handle_megalodon_errors
async def crear_regla(
    data: ReglaCumplimientoCreate,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user), _rate_limit: bool = Depends(rate_limit_strict),
):
    """Crea una regla de cumplimiento."""
    return await service.crear_regla(db, data, current_user)

@router.get("/reglas", response_model=dict)
@handle_megalodon_errors
async def listar_reglas(
    tipo_procedimiento: Optional[str] = Query(None),
    etapa: Optional[str] = Query(None),
    activa: Optional[bool] = Query(None),
    skip: int = Query(0, ge=0),
    limit: int = Query(50, ge=1, le=200),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user), _rate_limit: bool = Depends(rate_limit_standard),
):
    """Lista reglas de cumplimiento con filtros."""
    return await service.listar_reglas(db, current_user, tipo_procedimiento, etapa, activa, skip, limit)

@router.get("/reglas/{regla_id}", response_model=ReglaCumplimientoOut)
@handle_megalodon_errors
async def obtener_regla(
    regla_id: UUID,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user), _rate_limit: bool = Depends(rate_limit_standard),
):
    """Obtiene una regla por ID."""
    return await service.obtener_regla(db, regla_id, current_user)

@router.patch("/reglas/{regla_id}", response_model=ReglaCumplimientoOut)
@handle_megalodon_errors
async def actualizar_regla(
    regla_id: UUID,
    data: ReglaCumplimientoCreate,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user), _rate_limit: bool = Depends(rate_limit_strict),
):
    """Actualiza una regla de cumplimiento."""
    return await service.actualizar_regla(db, regla_id, data, current_user)

@router.delete("/reglas/{regla_id}", status_code=status.HTTP_204_NO_CONTENT)
@handle_megalodon_errors
async def eliminar_regla(
    regla_id: UUID,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user), _rate_limit: bool = Depends(rate_limit_strict),
):
    """Elimina una regla."""
    await service.eliminar_regla(db, regla_id, current_user)

# ─── INCONFORMIDADES ───────────────────────────────────────────────────────

@router.post("/inconformidades", response_model=InconformidadOut, status_code=status.HTTP_201_CREATED)
@handle_megalodon_errors
async def crear_inconformidad(
    data: InconformidadCreate,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user), _rate_limit: bool = Depends(rate_limit_strict),
):
    """Registra una inconformidad."""
    return await service.crear_inconformidad(db, data, current_user)

@router.get("/inconformidades", response_model=dict)
@handle_megalodon_errors
async def listar_inconformidades(
    estado: Optional[str] = Query(None),
    severidad: Optional[str] = Query(None),
    expediente_id: Optional[str] = Query(None),
    skip: int = Query(0, ge=0),
    limit: int = Query(50, ge=1, le=200),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user), _rate_limit: bool = Depends(rate_limit_standard),
):
    """Lista inconformidades con filtros."""
    return await service.listar_inconformidades(db, current_user, estado, severidad, expediente_id, skip, limit)

@router.get("/inconformidades/{inconformidad_id}", response_model=InconformidadOut)
@handle_megalodon_errors
async def obtener_inconformidad(
    inconformidad_id: UUID,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user), _rate_limit: bool = Depends(rate_limit_standard),
):
    """Obtiene una inconformidad por ID."""
    return await service.obtener_inconformidad(db, inconformidad_id, current_user)

@router.patch("/inconformidades/{inconformidad_id}", response_model=InconformidadOut)
@handle_megalodon_errors
async def actualizar_inconformidad(
    inconformidad_id: UUID,
    data: InconformidadUpdate,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user), _rate_limit: bool = Depends(rate_limit_strict),
):
    """Actualiza una inconformidad."""
    return await service.actualizar_inconformidad(db, inconformidad_id, data, current_user)

# ─── SANCIONES ───────────────────────────────────────────────────────────────

@router.post("/sanciones", response_model=SancionOut, status_code=status.HTTP_201_CREATED)
@handle_megalodon_errors
async def crear_sancion(
    data: SancionCreate,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user), _rate_limit: bool = Depends(rate_limit_strict),
):
    """Registra una sanción."""
    return await service.crear_sancion(db, data, current_user)

@router.get("/sanciones", response_model=dict)
@handle_megalodon_errors
async def listar_sanciones(
    proveedor_id: Optional[str] = Query(None),
    tipo: Optional[str] = Query(None),
    skip: int = Query(0, ge=0),
    limit: int = Query(50, ge=1, le=200),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user), _rate_limit: bool = Depends(rate_limit_standard),
):
    """Lista sanciones con filtros."""
    return await service.listar_sanciones(db, current_user, proveedor_id, tipo, skip, limit)

@router.get("/sanciones/{sancion_id}", response_model=SancionOut)
@handle_megalodon_errors
async def obtener_sancion(
    sancion_id: UUID,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user), _rate_limit: bool = Depends(rate_limit_standard),
):
    """Obtiene una sanción por ID."""
    return await service.obtener_sancion(db, sancion_id, current_user)

# ─── EVALUACIÓN ──────────────────────────────────────────────────────────────

@router.post("/evaluar/{expediente_id}")
@handle_megalodon_errors
async def evaluar_expediente(
    expediente_id: str,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user), _rate_limit: bool = Depends(rate_limit_strict),
):
    """Evalúa un expediente contra todas las reglas de cumplimiento activas."""
    return await service.evaluar_expediente(db, expediente_id, current_user)
