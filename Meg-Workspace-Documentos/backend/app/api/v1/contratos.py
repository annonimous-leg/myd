# Copyright © 2026 Cristian Rodriguez
"""Router de contratos — Ciclo contractual completo."""
from app.core.rate_limit import rate_limit_standard, rate_limit_strict
from typing import Optional
from uuid import UUID
from fastapi import APIRouter, Depends, Query, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.deps import require_mutation_access, get_db, get_current_user
from app.models.user import User
from app.schemas.contrato import (
    ContratoCreate, ContratoOut, ContratoUpdate, ContratoList, FiniquitoCreate,
    ConvenioModificatorioCreate, ConvenioModificatorioOut,
    GarantiaCreate, GarantiaOut,
    EntregableCreate, EntregableOut,
    PenalizacionCreate, PenalizacionOut,
)
from app.services.contrato_service import ContratoService
from app.core.errors import handle_megalodon_errors

router = APIRouter(dependencies=[Depends(require_mutation_access)], tags=["Contratos"])  # prefijo va solo en router.py
service = ContratoService()

# ─── CONTRATOS CRUD ────────────────────────────────────────────────────────

@router.post("", response_model=ContratoOut, status_code=status.HTTP_201_CREATED)
@handle_megalodon_errors
async def crear_contrato(
    data: ContratoCreate,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user), _rate_limit: bool = Depends(rate_limit_strict),
):
    """Crea un nuevo contrato en estado EN_FIRMA."""
    return await service.crear(db, data, current_user)

@router.get("", response_model=ContratoList)
@handle_megalodon_errors
async def listar_contratos(
    estado: Optional[str] = Query(None),
    expediente_id: Optional[UUID] = Query(None),
    proveedor_id: Optional[UUID] = Query(None),
    skip: int = Query(0, ge=0),
    limit: int = Query(50, ge=1, le=200),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user), _rate_limit: bool = Depends(rate_limit_standard),
):
    """Lista contratos con filtros."""
    return await service.listar(db, current_user, estado, expediente_id, proveedor_id, skip, limit)

@router.get("/{contrato_id}", response_model=ContratoOut)
@handle_megalodon_errors
async def obtener_contrato(
    contrato_id: UUID,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user), _rate_limit: bool = Depends(rate_limit_standard),
):
    """Obtiene un contrato por ID."""
    return await service.obtener(db, contrato_id, current_user)

@router.patch("/{contrato_id}", response_model=ContratoOut)
@handle_megalodon_errors
async def actualizar_contrato(
    contrato_id: UUID,
    data: ContratoUpdate,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user), _rate_limit: bool = Depends(rate_limit_strict),
):
    """Actualiza un contrato (solo en estados tempranos)."""
    return await service.actualizar(db, contrato_id, data, current_user)

@router.post("/{contrato_id}/transicionar")
@handle_megalodon_errors
async def transicionar_estado_contrato(
    contrato_id: UUID,
    nuevo_estado: str,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user), _rate_limit: bool = Depends(rate_limit_strict),
):
    """Transiciona el estado del contrato con validación de máquina de estados."""
    from app.models.contrato import EstadoContrato
    return await service.transicionar_estado(db, contrato_id, EstadoContrato(nuevo_estado), current_user)

@router.post('/{contrato_id}/finiquito', response_model=ContratoOut)
@handle_megalodon_errors
async def cerrar_finiquito(
    contrato_id: UUID, data: FiniquitoCreate, db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user), _rate_limit: bool = Depends(rate_limit_strict),
):
    return await service.cerrar_finiquito(db, contrato_id, data.fecha_finiquito, current_user)


# ─── CONVENIOS MODIFICATORIOS ────────────────────────────────────────────────

@router.post("/{contrato_id}/modificatorios", response_model=ConvenioModificatorioOut, status_code=status.HTTP_201_CREATED)
@handle_megalodon_errors
async def crear_modificatorio(
    contrato_id: UUID,
    data: ConvenioModificatorioCreate,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user), _rate_limit: bool = Depends(rate_limit_strict),
):
    """Crea un convenio modificatorio."""
    return await service.crear_modificatorio(db, contrato_id, data, current_user)

@router.get("/{contrato_id}/modificatorios", response_model=list[ConvenioModificatorioOut])
@handle_megalodon_errors
async def listar_modificatorios(
    contrato_id: UUID,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user), _rate_limit: bool = Depends(rate_limit_standard),
):
    """Lista convenios modificatorios."""
    return await service.listar_modificatorios(db, contrato_id, current_user)

# ─── GARANTÍAS ───────────────────────────────────────────────────────────────

@router.post("/{contrato_id}/garantias", response_model=GarantiaOut, status_code=status.HTTP_201_CREATED)
@handle_megalodon_errors
async def crear_garantia(
    contrato_id: UUID,
    data: GarantiaCreate,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user), _rate_limit: bool = Depends(rate_limit_strict),
):
    """Registra una garantía de contrato."""
    return await service.crear_garantia(db, contrato_id, data, current_user)

@router.get("/{contrato_id}/garantias", response_model=list[GarantiaOut])
@handle_megalodon_errors
async def listar_garantias(
    contrato_id: UUID,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user), _rate_limit: bool = Depends(rate_limit_standard),
):
    """Lista garantías de un contrato."""
    return await service.listar_garantias(db, contrato_id, current_user)

@router.get("/{contrato_id}/garantias/vigencia")
@handle_megalodon_errors
async def verificar_vigencia_garantias(
    contrato_id: UUID,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user), _rate_limit: bool = Depends(rate_limit_standard),
):
    """Verifica vigencia de garantías y alerta por vencimiento próximo."""
    return await service.verificar_vigencia_garantias(db, contrato_id, current_user)

# ─── ENTREGABLES / ESTIMACIONES ────────────────────────────────────────────

@router.post("/{contrato_id}/entregables", response_model=EntregableOut, status_code=status.HTTP_201_CREATED)
@handle_megalodon_errors
async def crear_entregable(
    contrato_id: UUID,
    data: EntregableCreate,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user), _rate_limit: bool = Depends(rate_limit_strict),
):
    """Registra un entregable o estimación."""
    return await service.crear_entregable(db, contrato_id, data, current_user)

@router.post("/{contrato_id}/entregables/{entregable_id}/aprobar", response_model=EntregableOut)
@handle_megalodon_errors
async def aprobar_entregable(
    contrato_id: UUID, entregable_id: UUID,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user), _rate_limit: bool = Depends(rate_limit_strict),
):
    """Aprueba una estimación persistida y recalcula el avance contractual."""
    return await service.aprobar_entregable(db, contrato_id, entregable_id, current_user)

@router.get("/{contrato_id}/entregables", response_model=list[EntregableOut])
@handle_megalodon_errors
async def listar_entregables(
    contrato_id: UUID,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user), _rate_limit: bool = Depends(rate_limit_standard),
):
    """Lista entregables de un contrato."""
    return await service.listar_entregables(db, contrato_id, current_user)

# ─── PENALIZACIONES ──────────────────────────────────────────────────────────

@router.post("/{contrato_id}/penalizaciones", response_model=PenalizacionOut, status_code=status.HTTP_201_CREATED)
@handle_megalodon_errors
async def crear_penalizacion(
    contrato_id: UUID,
    data: PenalizacionCreate,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user), _rate_limit: bool = Depends(rate_limit_strict),
):
    """Registra una penalización."""
    return await service.crear_penalizacion(db, contrato_id, data, current_user)

@router.get("/{contrato_id}/penalizaciones", response_model=list[PenalizacionOut])
@handle_megalodon_errors
async def listar_penalizaciones(
    contrato_id: UUID,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user), _rate_limit: bool = Depends(rate_limit_standard),
):
    """Lista penalizaciones de un contrato."""
    return await service.listar_penalizaciones(db, contrato_id, current_user)

# ─── RESUMEN CONTRACTUAL ─────────────────────────────────────────────────────

@router.get("/{contrato_id}/resumen")
@handle_megalodon_errors
async def resumen_contrato(
    contrato_id: UUID,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user), _rate_limit: bool = Depends(rate_limit_standard),
):
    """Genera resumen completo: montos, plazos, garantías, alertas."""
    return await service.resumen_contrato(db, contrato_id, current_user)
