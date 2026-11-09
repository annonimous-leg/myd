# Copyright © 2026 Cristian Rodriguez
# All rights reserved.
# Unauthorized copying, modification, distribution, or use is prohibited
# without prior written permission.

"""
API de gestión documental avanzada (CDE).
Clasificación, versionado, duplicados y búsqueda.
"""
from app.core.rate_limit import rate_limit_standard, rate_limit_strict
from typing import List, Optional
from uuid import UUID
from datetime import datetime

from fastapi import APIRouter, Depends, Query, Body
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.deps import (
    get_current_user, get_db, verificar_expediente_tenant, verificar_documento_tenant,
)
from app.models.user import User
from app.modules.documentos.service import DocumentoModuleService
from app.models.documento import TipoDocumento, EstadoDocumento

router = APIRouter()


@router.post("/{documento_id}/clasificar")
async def clasificar_documento(
    documento_id: UUID,
    tipo_sugerido: Optional[TipoDocumento] = None,
    confianza: Optional[float] = None,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
    _tenant_ok: None = Depends(verificar_documento_tenant), _rate_limit: bool = Depends(rate_limit_strict),
):
    """Clasifica un documento por tipo."""
    service = DocumentoModuleService(db)
    return await service.clasificar_documento(
        documento_id, tipo_sugerido=tipo_sugerido, confianza=confianza
    )


@router.get("/duplicados/{expediente_id}")
async def detectar_duplicados(
    expediente_id: UUID,
    umbral_similitud: float = Query(0.95, ge=0.0, le=1.0),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
    _tenant_ok: None = Depends(verificar_expediente_tenant), _rate_limit: bool = Depends(rate_limit_standard),
):
    """Detecta documentos duplicados en un expediente."""
    service = DocumentoModuleService(db)
    return await service.detectar_duplicados(
        expediente_id, umbral_similitud=umbral_similitud
    )


@router.get("/busqueda-avanzada")
async def busqueda_avanzada(
    q: Optional[str] = None,
    tipo: Optional[TipoDocumento] = None,
    estado: Optional[EstadoDocumento] = None,
    expediente_id: Optional[UUID] = None,
    fecha_inicio: Optional[datetime] = None,
    fecha_fin: Optional[datetime] = None,
    tags: Optional[List[str]] = Query(None),
    skip: int = Query(0, ge=0),
    limit: int = Query(100, ge=1, le=500),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user), _rate_limit: bool = Depends(rate_limit_standard),
):
    """Búsqueda avanzada de documentos con múltiples filtros."""
    service = DocumentoModuleService(db)
    return await service.busqueda_avanzada(
        query=q,
        tipo=tipo,
        estado=estado,
        expediente_id=expediente_id,
        tenant_id=current_user.tenant_id,
        fecha_inicio=fecha_inicio,
        fecha_fin=fecha_fin,
        tags=tags,
        skip=skip,
        limit=limit,
    )


@router.post("/{documento_id}/nueva-version")
async def nueva_version(
    documento_id: UUID,
    nuevo_contenido_url: str = Body(...),
    cambios_descripcion: Optional[str] = Body(None),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
    _tenant_ok: None = Depends(verificar_documento_tenant), _rate_limit: bool = Depends(rate_limit_strict),
):
    """Crea una nueva versión de un documento."""
    service = DocumentoModuleService(db)
    return await service.crear_version_documento(
        documento_id,
        nuevo_contenido_url=nuevo_contenido_url,
        cambios_descripcion=cambios_descripcion,
        creado_por_id=current_user.id,
    )


@router.get("/{documento_id}/versiones")
async def arbol_versiones(
    documento_id: UUID,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
    _tenant_ok: None = Depends(verificar_documento_tenant), _rate_limit: bool = Depends(rate_limit_standard),
):
    """Obtiene el árbol de versiones de un documento."""
    service = DocumentoModuleService(db)
    return await service.obtener_arbol_versiones(documento_id)


@router.get("/estadisticas/{expediente_id}")
async def estadisticas_documentales(
    expediente_id: UUID,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
    _tenant_ok: None = Depends(verificar_expediente_tenant), _rate_limit: bool = Depends(rate_limit_standard),
):
    """Estadísticas del repositorio documental de un expediente."""
    service = DocumentoModuleService(db)
    return await service.estadisticas_documentales(expediente_id=expediente_id)
