# Copyright © 2026 Cristian Rodriguez
# All rights reserved.
# Unauthorized copying, modification, distribution, or use is prohibited
# without prior written permission.

"""
API de Programación de Obra (CPM, PERT, EVM, Gantt, Curva S).
"""
from app.core.rate_limit import rate_limit_standard, rate_limit_strict
from typing import List, Optional, Dict
from uuid import UUID
from datetime import datetime

from fastapi import APIRouter, Depends, Query
from pydantic import BaseModel, Field
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.deps import require_mutation_access, get_current_user, get_db, verificar_expediente_tenant
from app.services.programacion_service import ProgramacionService
from app.models.user import User

router = APIRouter(dependencies=[Depends(require_mutation_access), Depends(verificar_expediente_tenant)])


class ActividadCreate(BaseModel):
    id: str = Field(..., min_length=1, max_length=50)
    nombre: str = Field(..., min_length=1, max_length=500)
    descripcion: Optional[str] = None
    wbs_codigo: Optional[str] = ""
    wbs_nivel: int = 0
    duracion: float = Field(..., gt=0)
    duracion_optimista: Optional[float] = None
    duracion_probable: Optional[float] = None
    duracion_pesimista: Optional[float] = None
    tipo: str = "CONSTRUCCION"
    costo_presupuestado: float = 0.0
    costo_real: float = 0.0
    porcentaje_avance: float = 0.0
    predecesoras: List[str] = Field(default_factory=list)
    dependencias_tipo: Optional[dict] = Field(default_factory=dict)
    metadatos: Optional[dict] = Field(default_factory=dict)


class ProgramaCreate(BaseModel):
    nombre: str = Field(..., min_length=1, max_length=500)
    descripcion: Optional[str] = None
    fecha_inicio: datetime
    actividades: List[ActividadCreate]


class AvanceUpdate(BaseModel):
    porcentaje: float = Field(..., ge=0, le=100)
    costo_real: Optional[float] = None


class ActividadUpdate(BaseModel):
    """Edición de una actividad ya creada -- soporta lo que la vista de
    Gantt necesita (duración, secuencia/dependencias, datos generales).
    Las fechas NO se editan aquí directamente: las calcula el CPM a
    partir de duración + predecesoras, igual que antes; permitir
    fecha_inicio/fecha_fin manuales rompería esa consistencia."""
    nombre: Optional[str] = Field(None, min_length=1, max_length=500)
    wbs_codigo: Optional[str] = None
    duracion: Optional[float] = Field(None, gt=0)
    tipo: Optional[str] = None
    predecesoras: Optional[List[str]] = None
    dependencias_tipo: Optional[dict] = None


# BUG ORIGINAL (mismo patrón ya corregido en presupuestos.py): estos
# endpoints regresaban el objeto ORM crudo sin response_model -- riesgo
# real de DetachedInstanceError al serializar relaciones no cargadas
# después de que get_db cierra la sesión, y de paso exponía columnas
# internas sin control.
class ActividadOut(BaseModel):
    id: UUID
    identificador: str
    nombre: str
    descripcion: Optional[str] = None
    wbs_codigo: str
    wbs_nivel: int
    duracion: float
    tipo: str
    costo_presupuestado: float
    costo_real: float
    porcentaje_avance: float
    inicio_temprano: Optional[datetime] = None
    fin_temprano: Optional[datetime] = None
    inicio_tardio: Optional[datetime] = None
    fin_tardio: Optional[datetime] = None
    holgura_total: float
    holgura_libre: float
    en_ruta_critica: bool
    predecesoras: Optional[List[str]] = None
    dependencias_tipo: Optional[Dict[str, str]] = None

    class Config:
        from_attributes = True


class ProgramaOut(BaseModel):
    id: UUID
    identificador: str
    nombre: str
    descripcion: Optional[str] = None
    expediente_id: UUID
    fecha_inicio_plan: datetime
    fecha_fin_plan: Optional[datetime] = None
    duracion_plan_dias: int
    estado: str

    class Config:
        from_attributes = True


@router.post("/{expediente_id}/programas", response_model=ProgramaOut)
async def crear_programa(
    expediente_id: UUID,
    data: ProgramaCreate,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user), _rate_limit: bool = Depends(rate_limit_strict),
):
    service = ProgramacionService(db, current_user.tenant_id, actor_id=current_user.id)
    actividades_data = []
    for act in data.actividades:
        actividades_data.append({
            "id": act.id, "nombre": act.nombre, "descripcion": act.descripcion,
            "wbs_codigo": act.wbs_codigo, "wbs_nivel": act.wbs_nivel,
            "duracion": act.duracion, "duracion_optimista": act.duracion_optimista,
            "duracion_probable": act.duracion_probable, "duracion_pesimista": act.duracion_pesimista,
            "tipo": act.tipo, "costo_presupuestado": act.costo_presupuestado,
            "costo_real": act.costo_real, "porcentaje_avance": act.porcentaje_avance,
            "predecesoras": act.predecesoras, "dependencias_tipo": act.dependencias_tipo,
            "metadatos": act.metadatos,
        })
    programa = await service.crear_programa(
        expediente_id=expediente_id, nombre=data.nombre, descripcion=data.descripcion,
        fecha_inicio=data.fecha_inicio, actividades_data=actividades_data,
        creado_por_id=current_user.id, tenant_id=current_user.tenant_id,
    )
    return programa


@router.get("/{expediente_id}/programas", response_model=List[ProgramaOut])
async def listar_programas(
    expediente_id: UUID, skip: int = Query(0, ge=0), limit: int = Query(20, ge=1, le=100),
    db: AsyncSession = Depends(get_db), current_user: User = Depends(get_current_user), _rate_limit: bool = Depends(rate_limit_standard),
):
    service = ProgramacionService(db, current_user.tenant_id, actor_id=current_user.id)
    return await service.get_multi(skip=skip, limit=limit, filters={"expediente_id": expediente_id})


@router.get("/{expediente_id}/programas/{programa_id}")
async def obtener_programa(
    expediente_id: UUID, programa_id: UUID,
    db: AsyncSession = Depends(get_db), current_user: User = Depends(get_current_user), _rate_limit: bool = Depends(rate_limit_standard),
):
    service = ProgramacionService(db, current_user.tenant_id, actor_id=current_user.id)
    return await service.exportar_programa(programa_id, expediente_id=expediente_id, tenant_id=current_user.tenant_id)


@router.post("/{expediente_id}/programas/{programa_id}/cpm")
async def calcular_cpm(
    expediente_id: UUID, programa_id: UUID, fecha_inicio: Optional[datetime] = None,
    db: AsyncSession = Depends(get_db), current_user: User = Depends(get_current_user), _rate_limit: bool = Depends(rate_limit_strict),
):
    service = ProgramacionService(db, current_user.tenant_id, actor_id=current_user.id)
    resultado = await service.calcular_cpm(programa_id, expediente_id=expediente_id, fecha_inicio=fecha_inicio, tenant_id=current_user.tenant_id)
    return resultado.to_dict()


@router.post("/{expediente_id}/programas/{programa_id}/pert")
async def calcular_pert(
    expediente_id: UUID, programa_id: UUID, fecha_objetivo: Optional[datetime] = None,
    db: AsyncSession = Depends(get_db), current_user: User = Depends(get_current_user), _rate_limit: bool = Depends(rate_limit_strict),
):
    service = ProgramacionService(db, current_user.tenant_id, actor_id=current_user.id)
    resultado = await service.calcular_pert(programa_id, expediente_id=expediente_id, fecha_objetivo=fecha_objetivo, tenant_id=current_user.tenant_id)
    return resultado.to_dict()


@router.post("/{expediente_id}/programas/{programa_id}/evm")
async def calcular_evm(
    expediente_id: UUID, programa_id: UUID, fecha_corte: Optional[datetime] = None,
    db: AsyncSession = Depends(get_db), current_user: User = Depends(get_current_user), _rate_limit: bool = Depends(rate_limit_strict),
):
    service = ProgramacionService(db, current_user.tenant_id, actor_id=current_user.id)
    resultado = await service.calcular_evm(programa_id, expediente_id=expediente_id, fecha_corte=fecha_corte, tenant_id=current_user.tenant_id)
    return resultado.to_dict()


@router.patch("/{expediente_id}/programas/{programa_id}/actividades/{actividad_id}/avance", response_model=ActividadOut)
async def actualizar_avance(
    expediente_id: UUID, programa_id: UUID, actividad_id: str, data: AvanceUpdate,
    db: AsyncSession = Depends(get_db), current_user: User = Depends(get_current_user), _rate_limit: bool = Depends(rate_limit_strict),
):
    service = ProgramacionService(db, current_user.tenant_id, actor_id=current_user.id)
    return await service.actualizar_avance(programa_id, expediente_id=expediente_id, actividad_id=actividad_id, porcentaje=data.porcentaje, costo_real=data.costo_real, tenant_id=current_user.tenant_id)


@router.get("/{expediente_id}/programas/{programa_id}/actividades", response_model=List[ActividadOut])
async def listar_actividades(
    expediente_id: UUID, programa_id: UUID,
    db: AsyncSession = Depends(get_db), current_user: User = Depends(get_current_user), _rate_limit: bool = Depends(rate_limit_standard),
):
    """Actividades completas del programa (incluye predecesoras, tipo,
    costos) -- lo que exportar_programa (usado por GET /programas/{id})
    no trae, porque ese endpoint es para exportación/resumen, no para
    poblar un formulario de edición."""
    service = ProgramacionService(db, current_user.tenant_id, actor_id=current_user.id)
    return await service.listar_actividades(programa_id, expediente_id=expediente_id, tenant_id=current_user.tenant_id)


@router.patch("/{expediente_id}/programas/{programa_id}/actividades/{actividad_id}", response_model=ActividadOut)
async def actualizar_actividad(
    expediente_id: UUID, programa_id: UUID, actividad_id: str, data: ActividadUpdate,
    db: AsyncSession = Depends(get_db), current_user: User = Depends(get_current_user), _rate_limit: bool = Depends(rate_limit_strict),
):
    """Edita duración, secuencia o datos generales de una actividad y
    recalcula el CPM del programa completo (las fechas/holguras/ruta
    crítica de TODAS las actividades pueden cambiar, no solo la editada)."""
    service = ProgramacionService(db, current_user.tenant_id, actor_id=current_user.id)
    return await service.actualizar_actividad(
        programa_id, expediente_id=expediente_id, actividad_id=actividad_id,
        campos=data.model_dump(exclude_unset=True),
        tenant_id=current_user.tenant_id,
    )


@router.get("/{expediente_id}/programas/{programa_id}/gantt")
async def obtener_gantt(
    expediente_id: UUID, programa_id: UUID,
    db: AsyncSession = Depends(get_db), current_user: User = Depends(get_current_user), _rate_limit: bool = Depends(rate_limit_standard),
):
    service = ProgramacionService(db, current_user.tenant_id, actor_id=current_user.id)
    return await service.obtener_gantt(programa_id, expediente_id=expediente_id, tenant_id=current_user.tenant_id)


@router.get("/{expediente_id}/programas/{programa_id}/curva-s")
async def obtener_curva_s(
    expediente_id: UUID, programa_id: UUID,
    db: AsyncSession = Depends(get_db), current_user: User = Depends(get_current_user), _rate_limit: bool = Depends(rate_limit_standard),
):
    service = ProgramacionService(db, current_user.tenant_id, actor_id=current_user.id)
    return await service.obtener_curva_s(programa_id, expediente_id=expediente_id, tenant_id=current_user.tenant_id)


@router.get("/{expediente_id}/programas/{programa_id}/ruta-critica")
async def obtener_ruta_critica(
    expediente_id: UUID, programa_id: UUID,
    db: AsyncSession = Depends(get_db), current_user: User = Depends(get_current_user), _rate_limit: bool = Depends(rate_limit_standard),
):
    service = ProgramacionService(db, current_user.tenant_id, actor_id=current_user.id)
    return await service.obtener_ruta_critica(programa_id, expediente_id=expediente_id, tenant_id=current_user.tenant_id)
