from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, Query, File, Form, UploadFile, HTTPException, Response
from pydantic import ValidationError
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.deps import get_current_user, get_db
from app.core.rate_limit import rate_limit_standard, rate_limit_strict
from app.models.user import User
from app.schemas.indices_costos import (
    AcreditacionMonedaCreate,
    ActualizacionPrecioInput,
    ObservacionIndiceCreate,
    RetiroIndiceCreate,
    SerieIndiceCreate,
    VinculoIndiceCreate,
    CargaINEGIInput,
    SeleccionPublicacionInput,
)
from app.engines.costos.ingesta_inegi import MAX_ARCHIVO
from app.services.indices_costos_service import IndicesCostosService

router = APIRouter(dependencies=[Depends(get_current_user)])


def servicio(db: Annotated[AsyncSession, Depends(get_db)], usuario: Annotated[User, Depends(get_current_user)]):
    return IndicesCostosService(db, usuario)


@router.post('/series', status_code=201, dependencies=[Depends(rate_limit_strict)])
async def crear_serie(data: SerieIndiceCreate, service: Annotated[IndicesCostosService, Depends(servicio)]):
    return await service.crear_serie(data)


@router.get('/series', dependencies=[Depends(rate_limit_standard)])
async def listar_series(service: Annotated[IndicesCostosService, Depends(servicio)], skip: int = Query(0, ge=0), limit: int = Query(100, ge=1, le=500)):
    return await service.listar_series(skip, limit)


@router.get('/inventario', dependencies=[Depends(rate_limit_standard)])
async def inventario(service: Annotated[IndicesCostosService, Depends(servicio)],
                     skip: int = Query(0, ge=0), limit: int = Query(50, ge=1, le=100)):
    return await service.inventario(skip, limit)


@router.post('/observaciones', status_code=201, dependencies=[Depends(rate_limit_strict)])
async def crear_observacion(data: ObservacionIndiceCreate, service: Annotated[IndicesCostosService, Depends(servicio)]):
    return await service.crear_observacion(data)


@router.get('/observaciones', dependencies=[Depends(rate_limit_standard)])
async def listar_observaciones(serie_id: UUID, service: Annotated[IndicesCostosService, Depends(servicio)], skip: int = Query(0, ge=0), limit: int = Query(100, ge=1, le=500)):
    return await service.listar_observaciones(serie_id, skip, limit)


@router.post('/vinculos', status_code=201, dependencies=[Depends(rate_limit_strict)])
async def crear_vinculo(data: VinculoIndiceCreate, service: Annotated[IndicesCostosService, Depends(servicio)]):
    return await service.crear_vinculo(data)


@router.get('/vinculos', dependencies=[Depends(rate_limit_standard)])
async def listar_vinculos(service: Annotated[IndicesCostosService, Depends(servicio)], skip: int = Query(0, ge=0), limit: int = Query(100, ge=1, le=500)):
    return await service.listar_vinculos(skip, limit)


@router.post('/calcular', dependencies=[Depends(rate_limit_standard)])
async def calcular(data: ActualizacionPrecioInput, service: Annotated[IndicesCostosService, Depends(servicio)]):
    return await service.resolver(data)


@router.post('/seleccionar-publicacion', dependencies=[Depends(rate_limit_standard)])
async def seleccionar_publicacion(data: SeleccionPublicacionInput,
                                  service: Annotated[IndicesCostosService, Depends(servicio)]):
    return await service.seleccionar_publicacion(data)


@router.post('/retiros', status_code=201, dependencies=[Depends(rate_limit_strict)])
async def retirar(data: RetiroIndiceCreate, service: Annotated[IndicesCostosService, Depends(servicio)]):
    return await service.retirar(data)


@router.post('/acreditaciones-moneda', status_code=201, dependencies=[Depends(rate_limit_strict)])
async def acreditar_moneda(data: AcreditacionMonedaCreate, service: Annotated[IndicesCostosService, Depends(servicio)]):
    return await service.acreditar_moneda(data)


@router.post('/cargas/inegi', dependencies=[Depends(rate_limit_strict)])
async def cargar_inegi(service: Annotated[IndicesCostosService, Depends(servicio)],
                      archivo: Annotated[UploadFile, File()], metadatos: Annotated[str, Form(max_length=12000)],
                      confirmar: bool = Query(False)):
    # Validate before reading; this administrative path never makes remote requests.
    service._autorizar(global_=True)
    try:
        try:
            data = CargaINEGIInput.model_validate_json(metadatos)
        except ValidationError as exc:
            raise HTTPException(422, 'Metadatos de carga inválidos') from exc
        body = await archivo.read(MAX_ARCHIVO + 1)
        if len(body) > MAX_ARCHIVO:
            raise HTTPException(413, 'Archivo mayor a 2 MiB')
        return await service.cargar_inegi(data, body, confirmar=confirmar)
    finally:
        await archivo.close()


@router.get('/cargas/{carga_id}/archivo', dependencies=[Depends(rate_limit_strict)])
async def archivo_carga(carga_id: UUID, service: Annotated[IndicesCostosService, Depends(servicio)]):
    body = await service.archivo_carga(carga_id)
    return Response(body, media_type='application/json', headers={
        'Content-Disposition': f'attachment; filename="indice-{carga_id}.json"',
        'Cache-Control': 'no-store', 'X-Content-Type-Options': 'nosniff'})
