"""Import, inspect quarantines and calculate real parametric antebudgets."""
from decimal import Decimal
from contextlib import asynccontextmanager
from pathlib import Path
from tempfile import TemporaryDirectory
from uuid import UUID

from fastapi import APIRouter, Depends, File, Form, HTTPException, Query, UploadFile
from pydantic import BaseModel, Field
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession
from starlette.concurrency import run_in_threadpool

from app.config import settings
from app.core.deps import get_current_user, get_db, module_access
from app.core.errors import handle_megalodon_errors
from app.core.rate_limit import rate_limit_standard, rate_limit_strict
from app.models.catalogo_importacion import CatalogoImportacion, CatalogoRegistro, EstimacionParametrica
from app.models.user import User
from app.services.catalogo_importacion import estimate, import_package
from app.services.catalogo_package import CatalogPackageError, strict_json, verify_package
from app.services.catalogo_zip import MAX_UPLOAD, extract_package

router = APIRouter(dependencies=[Depends(module_access('megalodon-costos'))])


@asynccontextmanager
async def uploaded_package(archivo):
    if not settings.CATALOGO_ORIGINALES_DIR or not Path(settings.CATALOGO_ORIGINALES_DIR).is_dir():
        raise HTTPException(503, 'Configure los PDF originales verificados antes de importar')
    try:
        with TemporaryDirectory(prefix='megalodon-catalogo-') as temporary:
            root = Path(temporary)
            upload, size = root / 'package.zip', 0
            with upload.open('wb') as stream:
                while chunk := await archivo.read(1024 * 1024):
                    size += len(chunk)
                    if size > MAX_UPLOAD: raise HTTPException(413, 'Paquete demasiado grande')
                    stream.write(chunk)
            package = await run_in_threadpool(extract_package, upload, root / 'verified')
            yield package
    finally:
        await archivo.close()


def batch_out(batch, created=None):
    result = {'id': str(batch.id), 'paquete_sha256': batch.paquete_sha256,
              'fuentes': batch.fuentes, 'resumen': batch.resumen}
    if created is not None: result['creada'] = created
    return result


@router.post('/importaciones/verificar', dependencies=[Depends(rate_limit_strict)])
async def verificar(archivo: UploadFile = File(...)):
    try:
        async with uploaded_package(archivo) as package:
            result = await run_in_threadpool(verify_package, package, Path(settings.CATALOGO_ORIGINALES_DIR))
            return {'paquete_sha256': result.package_sha256, 'resumen': result.report(), 'fuentes': [
                {**source, 'original_cotejado': source['fuente_id'] in result.verified_source_ids}
                for source in result.records['fuente']]}
    except (CatalogPackageError, ValueError, KeyError) as exc:
        raise HTTPException(422, f'Paquete rechazado: {exc}') from exc


@router.post('/importaciones', dependencies=[Depends(rate_limit_strict)])
@handle_megalodon_errors
async def importar(archivo: UploadFile = File(...), fuentes: str = Form(...),
                   db: AsyncSession = Depends(get_db), user: User = Depends(get_current_user)):
    try:
        selected = strict_json(fuentes)
        if not isinstance(selected, list) or not selected or any(not isinstance(s, str) for s in selected):
            raise ValueError('Indique una lista de identidades de fuente')
        async with uploaded_package(archivo) as package:
            batch, created = await import_package(db, user, package, Path(settings.CATALOGO_ORIGINALES_DIR), set(selected))
            return batch_out(batch, created)
    except (CatalogPackageError, ValueError, KeyError) as exc:
        raise HTTPException(422, f'Paquete rechazado: {exc}') from exc


@router.get('/importaciones', dependencies=[Depends(rate_limit_standard)])
async def listar(db: AsyncSession = Depends(get_db), user: User = Depends(get_current_user),
                 skip: int = Query(0, ge=0), limit: int = Query(50, ge=1, le=100)):
    where = CatalogoImportacion.tenant_id == user.tenant_id
    total = await db.scalar(select(func.count()).select_from(CatalogoImportacion).where(where))
    batches = (await db.scalars(select(CatalogoImportacion).where(where).order_by(
        CatalogoImportacion.created_at.desc(), CatalogoImportacion.id).offset(skip).limit(limit))).all()
    return {'total': total, 'items': [batch_out(b) for b in batches]}


@router.get('/importaciones/{importacion_id}/registros', dependencies=[Depends(rate_limit_standard)])
async def registros(importacion_id: UUID, tabla: str = Query('partida_catalogo'), estado: str | None = None,
                    skip: int = Query(0, ge=0), limit: int = Query(100, ge=1, le=500),
                    db: AsyncSession = Depends(get_db), user: User = Depends(get_current_user)):
    if not await db.scalar(select(CatalogoImportacion.id).where(CatalogoImportacion.id == importacion_id,
                                                              CatalogoImportacion.tenant_id == user.tenant_id)):
        raise HTTPException(404, 'Importación no encontrada')
    query = select(CatalogoRegistro).where(CatalogoRegistro.importacion_id == importacion_id,
        CatalogoRegistro.tenant_id == user.tenant_id)
    if tabla != '*':
        query = query.where(CatalogoRegistro.tabla == tabla)
    if estado: query = query.where(CatalogoRegistro.estado == estado)
    total = await db.scalar(select(func.count()).select_from(query.subquery()))
    items = (await db.scalars(query.order_by(CatalogoRegistro.tabla, CatalogoRegistro.entidad_id,
                                           CatalogoRegistro.id).offset(skip).limit(limit))).all()
    return {'total': total, 'items': [{'id': str(r.id), 'fuente_id': r.fuente_id, 'entidad_id': r.entidad_id,
        'tabla': r.tabla, 'estado': r.estado, 'motivos': r.motivos, 'original': r.original, 'sha256': r.sha256} for r in items]}


class EstimarInput(BaseModel):
    modelo_registro_id: UUID
    factor_registro_id: UUID
    cantidad: Decimal = Field(gt=0, max_digits=18, decimal_places=4, allow_inf_nan=False)
    ajuste_proyecto: Decimal = Field(Decimal(1), gt=0, le=100, decimal_places=6, allow_inf_nan=False)
    justificacion: str = Field(min_length=10, max_length=3000)


@router.post('/estimaciones-parametricas', dependencies=[Depends(rate_limit_strict)])
@handle_megalodon_errors
async def estimar(data: EstimarInput, db: AsyncSession = Depends(get_db), user: User = Depends(get_current_user)):
    result = await estimate(db, user, data.modelo_registro_id, data.factor_registro_id,
                            data.cantidad, data.ajuste_proyecto, data.justificacion)
    return {'id': str(result.id), 'monto': str(result.monto), 'evidencia': result.evidencia}


@router.get('/estimaciones-parametricas/{estimacion_id}', dependencies=[Depends(rate_limit_standard)])
async def obtener_estimacion(estimacion_id: UUID, db: AsyncSession = Depends(get_db), user: User = Depends(get_current_user)):
    result = await db.scalar(select(EstimacionParametrica).where(EstimacionParametrica.id == estimacion_id,
                                                               EstimacionParametrica.tenant_id == user.tenant_id))
    if result is None: raise HTTPException(404, 'Estimación no encontrada')
    return {'id': str(result.id), 'monto': str(result.monto), 'evidencia': result.evidencia}
