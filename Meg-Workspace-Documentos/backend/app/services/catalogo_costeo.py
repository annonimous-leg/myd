"""Resolve an auditable catalogue price before writing budget detail."""
from copy import deepcopy
from decimal import Decimal, ROUND_HALF_UP

from pydantic import ValidationError
from sqlalchemy import select

from app.core.errors import ErrorCode, MegalodonException
from app.engines.costos.motor_costeo import ConceptoCosteo, InsumoCosteo
from app.engines.topografia.evidencia import huella
from app.models.catalogo_apu import CatalogoAPU
from app.schemas.apu_costeo import InsumoCosteoInput
from app.services.catalogo_importacion import verify_projection


async def resolve_catalogue(db, tenant_id, catalogue_id, actor_id):
    catalogue = await db.scalar(select(CatalogoAPU).where(CatalogoAPU.id == catalogue_id,
        CatalogoAPU.tenant_id == tenant_id).with_for_update(read=True).execution_options(populate_existing=True))
    if catalogue is None:
        raise MegalodonException(ErrorCode.DOCUMENTO_NO_ENCONTRADO, 'Concepto de catálogo no encontrado', status_code=404)
    if catalogue.tipo != 'CONCEPTO':
        raise MegalodonException(ErrorCode.PRESUPUESTO_ERROR, 'Seleccione un concepto de trabajo cotizable; los insumos requieren un APU')
    if catalogue.incluye_iva:
        raise MegalodonException(ErrorCode.PRESUPUESTO_ERROR, 'Se requiere un precio sin IVA; el impuesto se calcula en el presupuesto')
    await verify_projection(db, catalogue)
    try:
        inputs = [InsumoCosteoInput.model_validate(item) for item in (catalogue.desglose or {}).get('insumos', [])]
    except ValidationError as exc:
        raise MegalodonException(ErrorCode.PRESUPUESTO_ERROR, 'El desglose del catálogo requiere revisión') from exc
    if any(item.actualizacion_precio is not None for item in inputs):
        raise MegalodonException(ErrorCode.PRESUPUESTO_ERROR, 'Revise la actualización de índices antes de asignar este desglose')
    concept = ConceptoCosteo(clave=catalogue.clave, descripcion=catalogue.descripcion, unidad=catalogue.unidad,
        insumos=[InsumoCosteo(**item.model_dump(exclude={'actualizacion_precio'})) for item in inputs]) if inputs else None
    price = (concept.costo_directo_unitario if concept else Decimal(str(catalogue.precio_unitario))).quantize(Decimal('.01'), rounding=ROUND_HALF_UP)
    if not price.is_finite() or price <= 0:
        raise MegalodonException(ErrorCode.PRESUPUESTO_ERROR, 'El concepto no tiene un precio positivo verificable')
    snapshot = {'catalogo_id': str(catalogue.id), 'clave': catalogue.clave, 'descripcion': catalogue.descripcion,
        'unidad': catalogue.unidad, 'fuente': catalogue.fuente, 'vigencia_inicio': catalogue.vigencia_inicio,
        'vigencia_fin': catalogue.vigencia_fin, 'zona_economica': catalogue.zona_economica,
        'precio_observado': str(catalogue.precio_unitario), 'precio_aplicado': str(price),
        'desglose': [item.model_dump(mode='json') for item in inputs], 'usuario_id': str(actor_id),
        'origen_importacion': deepcopy(catalogue.origen)}
    snapshot['sha256'] = huella(snapshot)
    return catalogue, concept, price, snapshot
