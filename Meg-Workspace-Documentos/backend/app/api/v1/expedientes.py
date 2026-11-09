# Copyright © 2026 Cristian Rodriguez
# All rights reserved.
# Unauthorized copying, modification, distribution, or use is prohibited
# without prior written permission.

"""
API de expedientes electrónicos conectada a ExpedienteService.
"""
from app.core.rate_limit import rate_limit_standard, rate_limit_strict
from typing import List, Optional
from uuid import UUID
from datetime import datetime

from fastapi import APIRouter, Depends, Query, UploadFile, File, Form
from pydantic import BaseModel, Field
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.deps import require_mutation_access, get_current_user, get_db
from app.services.expediente_service import ExpedienteService
from app.config import settings
from app.utils.upload_limits import read_upload_with_limit
from app.services.documento_service import DocumentoService
from app.services.entitlements_service import EntitlementsService
from app.models.user import User, Tenant
from app.models.expediente import EstadoExpediente, TipoContrato
from app.core.errors import MegalodonException, ErrorCode
from sqlalchemy import select, func

router = APIRouter(dependencies=[Depends(require_mutation_access)], )


class ExpedienteCreate(BaseModel):
    titulo: str = Field(..., min_length=5, max_length=500)
    descripcion: Optional[str] = None
    organo: str
    unidad_administrativa: str
    serie_documental: str
    subserie_documental: str
    proyecto_nombre: Optional[str] = None
    ubicacion_obra: Optional[str] = None
    monto_contrato: Optional[float] = None
    plazo_dias: Optional[int] = None
    tipo_contrato: TipoContrato = TipoContrato.PRECIOS_UNITARIOS
    responsable_tecnico: Optional[str] = None
    responsable_ejecutivo: Optional[str] = None


class ExpedienteOut(BaseModel):
    id: UUID
    identificador: str
    titulo: str
    estado: str
    monto_contrato: Optional[float]
    created_at: datetime

    class Config:
        from_attributes = True


@router.post("", response_model=ExpedienteOut)
async def crear_expediente(
    data: ExpedienteCreate,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user), _rate_limit: bool = Depends(rate_limit_strict),
):
    # BUG ORIGINAL: max_proyectos_activos vive en PlanLimite (y se le
    # muestra al usuario en /entitlements/mi-plan) pero nada lo hacía
    # cumplir -- un tenant Free podía crear expedientes sin límite real.
    ents_service = EntitlementsService(db)
    tenant = await db.get(Tenant, current_user.tenant_id)
    plan_efectivo = ents_service.calcular_plan_efectivo(tenant)
    limites = await ents_service.obtener_limites(plan_efectivo)
    if limites and limites.max_proyectos_activos is not None:
        from app.models.expediente import ExpedienteObra
        conteo = await db.scalar(
            select(func.count()).select_from(ExpedienteObra).where(
                ExpedienteObra.tenant_id == current_user.tenant_id,
                ExpedienteObra.estado.notin_(
                    [EstadoExpediente.ARCHIVADO.value, EstadoExpediente.CERRADO.value]
                ),
            )
        )
        if (conteo or 0) >= limites.max_proyectos_activos:
            raise MegalodonException(
                ErrorCode.VALIDACION_FALLIDA,
                f"Alcanzaste el límite de tu plan ({plan_efectivo}): "
                f"{limites.max_proyectos_activos} proyectos activos. "
                "Mejora tu plan o archiva un expediente para continuar.",
                status_code=402,
            )

    service = ExpedienteService(db, current_user.tenant_id)

    expediente = await service.create_expediente(
        titulo=data.titulo,
        organo=data.organo,
        unidad_administrativa=data.unidad_administrativa,
        serie_documental=data.serie_documental,
        subserie_documental=data.subserie_documental,
        tenant_id=current_user.tenant_id,
        descripcion=data.descripcion,
        proyecto_nombre=data.proyecto_nombre,
        ubicacion_obra=data.ubicacion_obra,
        monto_contrato=data.monto_contrato,
        plazo_dias=data.plazo_dias,
        tipo_contrato=data.tipo_contrato.value,
        creado_por_id=current_user.id,
        responsable_tecnico=data.responsable_tecnico,
        responsable_ejecutivo=data.responsable_ejecutivo,
        responsable_id=current_user.id,
    )

    return expediente


@router.get("", response_model=List[ExpedienteOut])
async def listar_expedientes(
    skip: int = Query(0, ge=0),
    limit: int = Query(20, ge=1, le=100),
    estado: Optional[str] = None,
    query: Optional[str] = None,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user), _rate_limit: bool = Depends(rate_limit_standard),
):
    service = ExpedienteService(db, current_user.tenant_id)

    expedientes, total = await service.buscar_expedientes(
        tenant_id=current_user.tenant_id,
        query=query,
        estado=estado,
        skip=skip,
        limit=limit,
    )

    return expedientes


@router.get("/{expediente_id}")
async def obtener_expediente(
    expediente_id: UUID,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user), _rate_limit: bool = Depends(rate_limit_standard),
):
    service = ExpedienteService(db, current_user.tenant_id)
    expediente = await service.get_with_relations(expediente_id, tenant_id=current_user.tenant_id)

    if not expediente:
        raise MegalodonException(
            ErrorCode.DOCUMENTO_NO_ENCONTRADO,
            f"Expediente {expediente_id} no encontrado",
        )

    return expediente


@router.patch("/{expediente_id}/estado")
async def cambiar_estado(
    expediente_id: UUID,
    estado: str,
    observacion: Optional[str] = None,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user), _rate_limit: bool = Depends(rate_limit_strict),
):
    service = ExpedienteService(db, current_user.tenant_id)

    try:
        nuevo_estado = EstadoExpediente(estado)
    except ValueError:
        raise MegalodonException(
            ErrorCode.NORMATIVO_GENERICO,
            f"Estado inválido: {estado}",
        )

    expediente = await service.cambiar_estado(
        expediente_id=expediente_id,
        nuevo_estado=nuevo_estado,
        tenant_id=current_user.tenant_id,
        observacion=observacion,
        actualizado_por_id=current_user.id,
    )

    return expediente


@router.get("/{expediente_id}/documentos")
async def listar_documentos_expediente(
    expediente_id: UUID,
    skip: int = Query(0, ge=0),
    limit: int = Query(100, ge=1, le=500),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
    _rate_limit: bool = Depends(rate_limit_standard),
):
    rows = await DocumentoService(db, current_user.tenant_id).listar_por_expediente(
        expediente_id, skip=skip, limit=limit,
    )
    return [{"id": str(doc.id), "nombre": doc.nombre, "tipo_documental": doc.tipo_documental,
             "formato": doc.formato, "size_bytes": doc.size_bytes, "hash_sha256": doc.hash_sha256,
             "row_version": doc.row_version, "created_at": doc.created_at.isoformat()} for doc in rows]


@router.post("/{expediente_id}/documentos")
async def subir_documento(
    expediente_id: UUID,
    file: UploadFile = File(...),
    tipo_documental: str = Form(...),
    cifrar: bool = Form(False),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user), _rate_limit: bool = Depends(rate_limit_strict),
):
    service = DocumentoService(db, current_user.tenant_id)

    content = await read_upload_with_limit(file, settings.GENERAL_UPLOAD_MAX_FILE_SIZE_MB)

    documento = await service.subir_documento(
        expediente_id=expediente_id,
        file_content=content,
        filename=file.filename,
        tipo_documental=tipo_documental,
        cifrar=cifrar,
        tenant_id=str(current_user.tenant_id),
        creado_por_id=current_user.id,
    )

    return documento


@router.get("/{expediente_id}/documentos/{documento_id}/descarga")
async def descargar_documento(
    expediente_id: UUID,
    documento_id: UUID,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user), _rate_limit: bool = Depends(rate_limit_standard),
):
    """Descarga el contenido real de un documento desde Supabase Storage.

    Antes no existía este endpoint -- DocumentoService.descargar_documento
    nunca tenía quién lo llamara desde la API.
    """
    from fastapi.responses import StreamingResponse
    import io

    service = DocumentoService(db, current_user.tenant_id)
    # BUG ORIGINAL: DocumentoService.descargar_documento() valida tenant
    # SOLO si tenant_id no es None -- este router nunca lo pasaba, así
    # que la validación quedaba desactivada en silencio pese a que el
    # código y el docstring del servicio parecían implementarla.
    contenido, nombre = await service.descargar_documento(
        documento_id, expediente_id=expediente_id, tenant_id=str(current_user.tenant_id)
    )

    return StreamingResponse(
        io.BytesIO(contenido),
        media_type="application/octet-stream",
        headers={"Content-Disposition": f"attachment; filename={nombre}"},
    )
