# Copyright © 2026 Cristian Rodriguez
# All rights reserved.
# Unauthorized copying, modification, distribution, or use is prohibited
# without prior written permission.

"""
API de firma electrónica.
"""
from app.core.rate_limit import rate_limit_standard, rate_limit_strict
from typing import Optional
from uuid import UUID

from fastapi import APIRouter, Depends, UploadFile, File, Form
from pydantic import BaseModel, Field
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.deps import (
    get_current_user, get_db, verificar_expediente_tenant, verificar_documento_tenant,
)
from app.services.firma_service import FirmaService
from app.config import settings
from app.utils.upload_limits import read_upload_with_limit
from app.models.user import User
from app.modules.firma.plataformas import PlataformaLicitacion

router = APIRouter()


class FirmarDocumentoRequest(BaseModel):
    razon: str = "Firma de documento de obra pública"
    ubicacion: str = "México"


@router.post("/documentos/{documento_id}")
async def firmar_documento(
    documento_id: UUID,
    certificado_cer: UploadFile = File(...),
    certificado_key: UploadFile = File(...),
    password: str = Form(...),
    razon: str = Form("Firma de documento de obra pública"),
    ubicacion: str = Form("México"),
    usar_tsa: bool = Form(True),
    tsa_url: Optional[str] = Form(None),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
    _tenant_ok: None = Depends(verificar_documento_tenant), _rate_limit: bool = Depends(rate_limit_strict),
):
    """Firma un documento real (descargado de storage) con certificado
    FIEL (.cer + .key). Por default usa PAdES-LT con sello de tiempo
    RFC 3161 real (usar_tsa=True); usar_tsa=False para una firma más
    rápida sin depender de una TSA externa."""
    service = FirmaService(db)

    cer_content = await read_upload_with_limit(certificado_cer, settings.CERTIFICATE_MAX_FILE_SIZE_MB)
    key_content = await read_upload_with_limit(certificado_key, settings.CERTIFICATE_MAX_FILE_SIZE_MB)

    resultado = await service.firmar_documento(
        documento_id=documento_id,
        certificado_cer=cer_content,
        certificado_key=key_content,
        password=password,
        razon=razon,
        ubicacion=ubicacion,
        usuario_id=current_user.id,
        usar_tsa=usar_tsa,
        tsa_url=tsa_url,
    )

    return resultado


@router.get("/documentos/{documento_id}/validar")
async def validar_firma_documento(
    documento_id: UUID,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
    _tenant_ok: None = Depends(verificar_documento_tenant), _rate_limit: bool = Depends(rate_limit_standard),
):
    """Valida las firmas de un documento."""
    service = FirmaService(db)
    return await service.validar_firma(documento_id)


@router.post("/documentos/{documento_id}/firmas/reconciliar")
async def reconciliar_firmas_documento(
    documento_id: UUID,
    eliminar_huerfanos: bool = False,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
    _tenant_ok: None = Depends(verificar_documento_tenant),
    _rate_limit: bool = Depends(rate_limit_strict),
):
    return await FirmaService(db).reconciliar_firmas(documento_id, current_user.id,
                                                    eliminar=eliminar_huerfanos)


@router.post("/expedientes/{expediente_id}/merkle")
async def firmar_merkle_expediente(
    expediente_id: UUID,
    certificado_cer: UploadFile = File(...),
    certificado_key: UploadFile = File(...),
    password: str = Form(...),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
    _tenant_ok: None = Depends(verificar_expediente_tenant), _rate_limit: bool = Depends(rate_limit_strict),
):
    """Firma el Merkle root de un expediente para trazabilidad."""
    import tempfile
    import os

    service = FirmaService(db)

    cer_content = await read_upload_with_limit(certificado_cer, settings.CERTIFICATE_MAX_FILE_SIZE_MB)
    key_content = await read_upload_with_limit(certificado_key, settings.CERTIFICATE_MAX_FILE_SIZE_MB)

    with tempfile.NamedTemporaryFile(suffix=".cer", delete=False) as f_cer:
        f_cer.write(cer_content)
        cer_path = f_cer.name

    with tempfile.NamedTemporaryFile(suffix=".key", delete=False) as f_key:
        f_key.write(key_content)
        key_path = f_key.name

    try:
        cert = service.modulo.cargar_certificado_fiel(cer_path, key_path, password)
        resultado = await service.firmar_hash_expediente(expediente_id, cert, usuario_id=current_user.id)
        return resultado
    finally:
        os.unlink(cer_path)
        os.unlink(key_path)


@router.post("/cfdi/sellar")
async def sellar_cfdi(
    xml_cfdi: UploadFile = File(...),
    certificado_cer: UploadFile = File(...),
    certificado_key: UploadFile = File(...),
    password: str = Form(...),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user), _rate_limit: bool = Depends(rate_limit_strict),
):
    """Genera cadena original + sello digital de un CFDI 4.0 (Anexo 20 SAT).

    Importante: esto NO timbra el CFDI -- el timbrado fiscal requiere un
    PAC (Proveedor Autorizado de Certificación). Este endpoint deja el
    XML sellado, listo para mandarlo a cualquier PAC.
    """
    service = FirmaService(db)
    xml_content = await read_upload_with_limit(xml_cfdi, settings.GENERAL_UPLOAD_MAX_FILE_SIZE_MB)
    cer_content = await read_upload_with_limit(certificado_cer, settings.CERTIFICATE_MAX_FILE_SIZE_MB)
    key_content = await read_upload_with_limit(certificado_key, settings.CERTIFICATE_MAX_FILE_SIZE_MB)

    return await service.sellar_cfdi(
        xml_cfdi=xml_content,
        certificado_cer=cer_content,
        certificado_key=key_content,
        password=password,
    )


@router.get("/formato-requerido")
async def formato_requerido_plataforma(
    plataforma: PlataformaLicitacion,
    tipo_documento: str,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user), _rate_limit: bool = Depends(rate_limit_standard),
):
    """Formato de firma (XAdES-EPES / PAdES-basic / PAdES-LT) que exige
    una plataforma gubernamental (CompraNet, IMSS, INFONAVIT, CFE, PEMEX,
    etc.) para un tipo de documento dado."""
    service = FirmaService(db)
    return service.formato_requerido_plataforma(plataforma, tipo_documento)
