# Copyright © 2026 Cristian Rodriguez
"""Router de licitaciones — Máquina de estados legal completa."""
from app.core.rate_limit import rate_limit_standard, rate_limit_strict
from typing import Optional
from uuid import UUID
from fastapi import APIRouter, Depends, Query, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.deps import require_mutation_access, get_db, get_current_user
from app.models.user import User
from app.schemas.licitacion import (
    LicitacionCreate, LicitacionOut, LicitacionUpdate, LicitacionList,
    JuntaAclaracionCreate, JuntaAclaracionOut,
    ProposicionCreate, ProposicionOut, RevisionDocumentalCreate,
    EvaluacionCreate, EvaluacionAutomaticaCreate, EvaluacionOut,
    TransicionEstadoCreate,
)
from app.services.licitacion_service import LicitacionService
from app.core.errors import handle_megalodon_errors

router = APIRouter(dependencies=[Depends(require_mutation_access)], tags=["Licitaciones"])  # prefijo va solo en router.py
service = LicitacionService()

# ─── CRUD BÁSICO ───────────────────────────────────────────────────────────

@router.post("", response_model=LicitacionOut, status_code=status.HTTP_201_CREATED)
@handle_megalodon_errors
async def crear_licitacion(
    data: LicitacionCreate,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user), _rate_limit: bool = Depends(rate_limit_strict),
):
    """Crea una nueva licitación en estado PLANEACION."""
    return await service.crear(db, data, current_user)

@router.get("", response_model=LicitacionList)
@handle_megalodon_errors
async def listar_licitaciones(
    estado: Optional[str] = Query(None),
    tipo_procedimiento: Optional[str] = Query(None),
    expediente_id: Optional[UUID] = Query(None),
    skip: int = Query(0, ge=0),
    limit: int = Query(50, ge=1, le=200),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user), _rate_limit: bool = Depends(rate_limit_standard),
):
    """Lista licitaciones con filtros."""
    from app.models.licitacion import EstadoLicitacion, TipoProcedimiento
    est = EstadoLicitacion(estado) if estado else None
    tp = TipoProcedimiento(tipo_procedimiento) if tipo_procedimiento else None
    return await service.listar(db, current_user, est, tp, expediente_id, skip, limit)

@router.get("/{licitacion_id}", response_model=LicitacionOut)
@handle_megalodon_errors
async def obtener_licitacion(
    licitacion_id: UUID,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user), _rate_limit: bool = Depends(rate_limit_standard),
):
    """Obtiene una licitación por ID."""
    return await service.obtener(db, licitacion_id, current_user)

@router.patch("/{licitacion_id}", response_model=LicitacionOut)
@handle_megalodon_errors
async def actualizar_licitacion(
    licitacion_id: UUID,
    data: LicitacionUpdate,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user), _rate_limit: bool = Depends(rate_limit_strict),
):
    """Actualiza una licitación (solo en estados tempranos)."""
    return await service.actualizar(db, licitacion_id, data, current_user)

# ─── TRANSICIÓN DE ESTADO ────────────────────────────────────────────────────

@router.post("/{licitacion_id}/transicionar", response_model=LicitacionOut)
@handle_megalodon_errors
async def transicionar_estado_licitacion(
    licitacion_id: UUID,
    data: TransicionEstadoCreate,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user), _rate_limit: bool = Depends(rate_limit_strict),
):
    """Transiciona el estado con validación de máquina de estados legal."""
    return await service.transicionar_estado(db, licitacion_id, data, current_user)

# ─── JUNTA DE ACLARACIONES ─────────────────────────────────────────────────

@router.post(
    "/{licitacion_id}/junta-aclaraciones",
    response_model=JuntaAclaracionOut,
    status_code=status.HTTP_201_CREATED,
)
@handle_megalodon_errors
async def registrar_junta_aclaraciones(
    licitacion_id: UUID,
    data: JuntaAclaracionCreate,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
    _rate_limit: bool = Depends(rate_limit_strict),
):
    """Registra el acta y los cambios de una junta celebrada externamente."""
    return await service.registrar_junta(db, licitacion_id, data, current_user)

@router.get("/{licitacion_id}/junta-aclaraciones", response_model=list[JuntaAclaracionOut])
@handle_megalodon_errors
async def listar_juntas_aclaraciones(
    licitacion_id: UUID,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user), _rate_limit: bool = Depends(rate_limit_standard),
):
    """Lista juntas de aclaraciones."""
    return await service.listar_juntas(db, licitacion_id, current_user)

# ─── PROPOSICIONES ─────────────────────────────────────────────────────────

@router.post("/{licitacion_id}/proposiciones", response_model=ProposicionOut, status_code=status.HTTP_201_CREATED)
@handle_megalodon_errors
async def registrar_proposicion(
    licitacion_id: UUID,
    data: ProposicionCreate,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user), _rate_limit: bool = Depends(rate_limit_strict),
):
    """Registra una proposición u oferta."""
    return await service.registrar_proposicion(db, licitacion_id, data, current_user)

@router.get("/{licitacion_id}/proposiciones", response_model=list[ProposicionOut])
@handle_megalodon_errors
async def listar_proposiciones(
    licitacion_id: UUID,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user), _rate_limit: bool = Depends(rate_limit_standard),
):
    """Lista proposiciones de una licitación."""
    return await service.listar_proposiciones(db, licitacion_id, current_user)

# ─── EVALUACIÓN ────────────────────────────────────────────────────────────

@router.post("/{licitacion_id}/proposiciones/{proposicion_id}/revision-documental", response_model=ProposicionOut)
@handle_megalodon_errors
async def revisar_documentacion_proposicion(
    licitacion_id: UUID,
    proposicion_id: UUID,
    data: RevisionDocumentalCreate,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
    _rate_limit: bool = Depends(rate_limit_strict),
):
    """Atestación del revisor con soporte documental; no es una consulta al SAT."""
    return await service.revisar_documentacion(db, licitacion_id, proposicion_id, data, current_user)

@router.post("/{licitacion_id}/evaluaciones", response_model=EvaluacionOut, status_code=status.HTTP_201_CREATED)
@handle_megalodon_errors
async def crear_evaluacion(
    licitacion_id: UUID,
    data: EvaluacionCreate,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user), _rate_limit: bool = Depends(rate_limit_strict),
):
    """Registra una evaluación de proposición."""
    return await service.crear_evaluacion(db, licitacion_id, data, current_user)


@router.post("/{licitacion_id}/bases/congelar", response_model=LicitacionOut)
@handle_megalodon_errors
async def congelar_bases(
    licitacion_id: UUID,
    version_esperada: Optional[int] = Query(None, ge=1),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    return await LicitacionService().congelar_bases(db, licitacion_id, current_user, version_esperada=version_esperada)


@router.post("/{licitacion_id}/evaluaciones/automatica", response_model=EvaluacionOut, status_code=status.HTTP_201_CREATED)
@handle_megalodon_errors
async def evaluar_proposicion_automatica(
    licitacion_id: UUID,
    data: EvaluacionAutomaticaCreate,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user), _rate_limit: bool = Depends(rate_limit_strict),
):
    """Evalúa una proposición con el motor real (legal/técnica/económica
    por criterio, con veto legal y pesos reales) en vez de recibir un
    veredicto ya decidido manualmente -- ver
    LicitacionService.evaluar_proposicion_automatica()."""
    return await service.evaluar_proposicion_automatica(db, licitacion_id, data, current_user)

# ─── FALLO ─────────────────────────────────────────────────────────────────

@router.post("/{licitacion_id}/fallo")
@handle_megalodon_errors
async def emitir_fallo(
    licitacion_id: UUID,
    proposicion_ganadora_id: UUID,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user), _rate_limit: bool = Depends(rate_limit_strict),
):
    """Emite el fallo de la licitación."""
    return await service.emitir_fallo(db, licitacion_id, proposicion_ganadora_id, current_user)

# ─── RESUMEN ─────────────────────────────────────────────────────────────────

@router.get("/{licitacion_id}/resumen")
@handle_megalodon_errors
async def resumen_licitacion(
    licitacion_id: UUID,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user), _rate_limit: bool = Depends(rate_limit_standard),
):
    """Genera resumen completo del proceso de licitación."""
    return await service.resumen_licitacion(db, licitacion_id, current_user)
