# Copyright © 2026 Cristian Rodriguez
# All rights reserved.
# Unauthorized copying, modification, distribution, or use is prohibited
# without prior written permission.

"""
FirmaService - Orquestación del módulo de firma electrónica.

BUG ORIGINAL (el más grave del backend hasta ahora): firmar_documento()
hacía `pdf_bytes = b""` -- un placeholder -- y `validar_firma()` hacía
exactamente lo mismo. O sea, firmar un documento no firmaba NADA: tomaba
bytes vacíos, les ponía una "firma" encima, y el resultado (que tampoco se
guardaba en ningún lado -- otro TODO sin implementar) se descartaba.
Cualquier "documento firmado" hasta ahora nunca existió.

Ahora sí: descarga el documento real de Supabase Storage, lo descifra si
aplica, lo firma de verdad con PAdES-LT + sello de tiempo RFC 3161 real
(TSA), y sube el resultado firmado de vuelta a storage -- sin pisar el
original (control de versiones mínimo: original y firmado quedan como
paths distintos, referenciados en los metadatos del documento).
"""
import hashlib
import asyncio
from functools import partial
import logging
import os
import tempfile
from datetime import datetime, timedelta, timezone
from typing import Optional, Dict, Any, List
from uuid import UUID, uuid4

from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select

from app.modules.firma.firma_electronica import (
    ModuloFirmaElectronica, CertificadoFIEL, FirmaDocumento
)
from app.modules.firma.pades_lt import PAdESLTSigner
from app.modules.firma.cfdi40 import CFDISATSigner
from app.modules.firma.plataformas import (
    PlataformaLicitacion, formato_requerido, advertencias_previas_a_firma,
)
from app.models.expediente import Documento, ExpedienteObra
from app.integrations.supabase_storage import storage_documentos, storage_exportaciones
from app.core.crypto import descifrar_sobre, cifrar_sobre
from app.core.authorization import authorize_by_id
from app.core.errors import MegalodonException, ErrorCode
from app.config import settings

logger = logging.getLogger(__name__)


class FirmaService:
    """Servicio de firma electrónica para documentos de obra pública."""

    def __init__(self, db: AsyncSession):
        self.db = db
        self.modulo = ModuloFirmaElectronica()

    @staticmethod
    def _storage_for_document(documento):
        """Resolve only the application-owned bucket declared by Documento."""
        bucket = getattr(documento, "storage_bucket", None) or settings.SUPABASE_BUCKET_DOCUMENTOS
        if bucket == settings.SUPABASE_BUCKET_DOCUMENTOS:
            return storage_documentos()
        if bucket == settings.SUPABASE_BUCKET_EXPORTS:
            return storage_exportaciones()
        raise MegalodonException(
            ErrorCode.ARCHIVO_ERROR,
            "El documento referencia un bucket de almacenamiento no autorizado.",
            409,
        )

    async def _obtener_documento(self, documento_id: UUID, *, bloquear=False) -> Documento:
        query = select(Documento).where(Documento.id == documento_id)
        if bloquear:
            query = query.with_for_update().execution_options(populate_existing=True)
        result = await self.db.execute(query)
        documento = result.scalar_one_or_none()
        if not documento:
            raise MegalodonException(ErrorCode.DOCUMENTO_NO_ENCONTRADO, f"Documento {documento_id} no encontrado")
        return documento

    async def _tenant_documento(self, documento):
        tenant_id = await self.db.scalar(select(ExpedienteObra.tenant_id).where(
            ExpedienteObra.id == documento.expediente_id))
        if tenant_id is None:
            raise MegalodonException(ErrorCode.DOCUMENTO_NO_ENCONTRADO, "Expediente no encontrado")
        return tenant_id

    async def _autorizar_firma(self, documento, usuario_id):
        tenant_id = await self._tenant_documento(documento)
        await authorize_by_id(self.db, usuario_id, tenant_id, "approve")
        return tenant_id

    @staticmethod
    async def _crypto_call(function, *args, **kwargs):
        # pyHanko's synchronous facade owns an event loop. Run it off the API
        # loop, and wait for cancellation to settle before deleting key files.
        task = asyncio.create_task(asyncio.to_thread(partial(function, *args, **kwargs)))
        try:
            return await asyncio.shield(task)
        except asyncio.CancelledError:
            try:
                await task
            finally:
                raise

    @staticmethod
    def _check_hash(content, expected):
        if not expected or hashlib.sha256(content).hexdigest() != expected:
            raise MegalodonException(ErrorCode.FIRMA_INVALIDA, "El contenido no coincide con la evidencia SHA-256.", 409)

    @staticmethod
    def _signed_path(documento, signature):
        path = signature.get("storage_path_firmado")
        if not isinstance(path, str) or not (
            path == f"{documento.storage_path}.firmado.pdf" or
            (path.startswith(f"{documento.storage_path}.firmado.") and path.endswith(".pdf")
             and "/" not in path[len(documento.storage_path):])
        ):
            raise MegalodonException(ErrorCode.FIRMA_INVALIDA, "La cadena contiene una ruta de storage inválida.", 409)
        return path

    async def _signed_content(self, documento, signature, tenant_id):
        content = await self._storage_for_document(documento).descargar(self._signed_path(documento, signature))
        if signature.get("cifrado"):
            if not all(signature.get(key) for key in ("nonce", "tag", "encrypted_dek")):
                raise MegalodonException(
                    ErrorCode.FIRMA_INVALIDA,
                    "Faltan metadatos de cifrado de la versión firmada.",
                    409,
                )
            content = descifrar_sobre(
                content,
                nonce=bytes.fromhex(signature["nonce"]),
                tag=bytes.fromhex(signature["tag"]),
                encrypted_dek_hex=signature["encrypted_dek"],
                tenant_id=str(tenant_id),
            )
        expected_hash = signature.get("sha256_firmado")
        if expected_hash:
            self._check_hash(content, expected_hash)
        elif not signature.get("firma_id"):
            # V1 metadata did not persist a rendition digest. Do not invent
            # historical provenance: extend the legacy rendition only when the
            # PDF passes the currently configured trust/revocation policy.
            verdict = await self._crypto_call(self.modulo.validar_firma_pdf, content)
            if not verdict.get("aceptacion_completa"):
                raise MegalodonException(
                    ErrorCode.FIRMA_INVALIDA,
                    "La firma histórica no cumple la política de confianza/revocación vigente.",
                    409,
                )
        else:
            raise MegalodonException(
                ErrorCode.FIRMA_INVALIDA,
                "La versión firmada carece de una huella verificable.",
                409,
            )
        return content

    async def _contenido_real(self, documento: Documento, tenant_id) -> bytes:
        """Descarga el contenido real del documento (descifrando si aplica).
        Antes esto siempre era b"" -- un placeholder que nunca tocaba storage."""
        storage = self._storage_for_document(documento)
        contenido = await storage.descargar(documento.storage_path)
        if documento.cifrado:
            if not all((documento.nonce_cifrado, documento.tag_cifrado, documento.encryption_key_enc)):
                raise MegalodonException(ErrorCode.FIRMA_INVALIDA, "Faltan datos del cifrado del documento.", 409)
            contenido = descifrar_sobre(contenido, nonce=bytes.fromhex(documento.nonce_cifrado),
                tag=bytes.fromhex(documento.tag_cifrado), encrypted_dek_hex=documento.encryption_key_enc,
                tenant_id=str(tenant_id))
        self._check_hash(contenido, documento.hash_sha256)
        return contenido

    async def firmar_documento(
        self,
        *,
        documento_id: UUID,
        certificado_cer: bytes,
        certificado_key: bytes,
        password: str,
        razon: str = "Firma de documento de obra pública",
        ubicacion: str = "México",
        usuario_id: UUID,
        usar_tsa: bool = True,
        tsa_url: Optional[str] = None,
        commit: bool = True,
    ) -> Dict[str, Any]:
        """Firma un documento real del expediente con e.firma (PAdES-LT +
        sello de tiempo RFC 3161 si usar_tsa=True)."""
        try:
            return await self._firmar_documento_locked(
                documento_id=documento_id, certificado_cer=certificado_cer,
                certificado_key=certificado_key, password=password, razon=razon,
                ubicacion=ubicacion, usuario_id=usuario_id, usar_tsa=usar_tsa,
                tsa_url=tsa_url, commit=commit)
        except BaseException:
            await self.db.rollback()
            raise

    async def _firmar_documento_locked(
        self, *, documento_id, certificado_cer, certificado_key,
        password, razon, ubicacion, usuario_id, usar_tsa, tsa_url, commit,
    ):
        documento = await self._obtener_documento(documento_id, bloquear=True)
        tenant_id = await self._autorizar_firma(documento, usuario_id)
        storage = self._storage_for_document(documento)
        metadatos = dict(documento.metadatos or {})
        firmas_previas = list(metadatos.get("firmas") or [])
        legacy_records = [
            item for item in firmas_previas
            if not item.get("firma_id") and not item.get("sha256_firmado")
        ]
        if len(legacy_records) > 1:
            raise MegalodonException(
                ErrorCode.FIRMA_INVALIDA,
                "La cadena histórica contiene varias firmas sin huellas independientes y no puede reconstruirse con seguridad.",
                409,
            )

        # Co-firmas are cumulative: sign the latest immutable signed rendition,
        # not the unsigned original again. Legacy fixed-path signatures are
        # accepted as an input once so existing records can continue forward.
        source_path = None
        if firmas_previas:
            source_path = self._signed_path(documento, firmas_previas[-1])
            pdf_bytes = await self._signed_content(documento, firmas_previas[-1], tenant_id)
        else:
            pdf_bytes = await self._contenido_real(documento, tenant_id)

        if tsa_url is not None:
            allowed_tsa = set(PAdESLTSigner.DEFAULT_TSA_URLS) | set(settings.TSA_ALLOWED_URLS)
            if tsa_url not in allowed_tsa:
                raise MegalodonException(
                    ErrorCode.PARAMETRO_INVALIDO,
                    "La TSA solicitada no está en la allowlist del despliegue.",
                    status_code=422,
                )

        cer_path = key_path = input_path = output_path = None
        path_firmado = None
        try:
            with tempfile.NamedTemporaryFile(suffix=".cer", delete=False) as f:
                f.write(certificado_cer)
                cer_path = f.name
            with tempfile.NamedTemporaryFile(suffix=".key", delete=False) as f:
                f.write(certificado_key)
                key_path = f.name

            # Certificado (para RFC/nombre/vigencia -- el motor de carga
            # ya existente en firma_electronica.py sigue siendo válido).
            cert = await self._crypto_call(self.modulo.cargar_certificado_fiel, cer_path, key_path, password)

            with tempfile.NamedTemporaryFile(suffix=".pdf", delete=False) as f:
                f.write(pdf_bytes)
                input_path = f.name
            output_path = input_path + ".firmado.pdf"

            if usar_tsa:
                # Firma real PAdES-LT con sello de tiempo RFC 3161 desde
                # una TSA pública real (DigiCert por default).
                signer = PAdESLTSigner(
                    cer_path, key_path, password, tsa_url=tsa_url,
                    trust_roots=settings.FIEL_TRUST_ROOT_PATHS,
                    intermediate_certs=settings.FIEL_INTERMEDIATE_CERT_PATHS,
                )
                try:
                    resultado_firma = await self._crypto_call(signer.sign_pades_lt,
                        input_path, output_path, field_name=f"FirmaMegalodon_{uuid4().hex}",
                        reason=razon, location=ubicacion, use_lta=True,
                    )
                finally:
                    signer.cleanup()
            else:
                # Ruta sin TSA (más rápida, sin dependencia de red externa).
                pdf_firmado = await self._crypto_call(self.modulo.firmar_documento_pdf,
                    pdf_bytes=pdf_bytes, certificado=cert, razon=razon,
                    ubicacion=ubicacion, agregar_sello_tiempo=False,
                )
                with open(output_path, "wb") as f:
                    f.write(pdf_firmado)
                resultado_firma = {"profile": "PAdES-B", "tsa_url": None}

            with open(output_path, "rb") as f:
                pdf_firmado_bytes = f.read()

            # Each rendition is immutable and uniquely addressable. A second
            # signer must never overwrite evidence referenced by the first.
            firma_id = uuid4()
            signed_at = datetime.now(timezone.utc)
            sha256_firmado = hashlib.sha256(pdf_firmado_bytes).hexdigest()
            path_firmado = f"{documento.storage_path}.firmado.{firma_id}.pdf"
            encryption = {}
            stored_bytes = pdf_firmado_bytes
            if documento.cifrado:
                stored_bytes, nonce, tag, dek = cifrar_sobre(pdf_firmado_bytes, str(tenant_id))
                encryption = {"cifrado": True, "nonce": nonce.hex(), "tag": tag.hex(), "encrypted_dek": dek}
            await storage.subir(
                path_firmado,
                stored_bytes,
                content_type="application/pdf",
                overwrite=False,
            )

            firma_snapshot = {
                "firma_id": str(firma_id),
                "rfc": cert.rfc,
                "nombre": cert.nombre,
                "fecha": signed_at.isoformat(),
                "razon": razon,
                "usuario_id": str(usuario_id),
                "storage_path_origen_firma": source_path or documento.storage_path,
                "storage_path_firmado": path_firmado,
                "sha256_firmado": sha256_firmado,
                "sha256_origen_firma": hashlib.sha256(pdf_bytes).hexdigest(),
                **encryption,
                "certificado_vigencia_inicio": cert.vigencia_inicio.isoformat(),
                "certificado_vigencia_fin": cert.vigencia_fin.isoformat(),
                "perfil": resultado_firma.get("profile"),
                "tsa_url": resultado_firma.get("tsa_url"),
                "validacion_pades": resultado_firma.get("validation"),
            }
            firmas_previas.append(firma_snapshot)
            metadatos["firmas"] = firmas_previas
            documento.metadatos = metadatos
            if commit:
                try:
                    await self.db.commit()
                except BaseException:
                    await self.db.rollback()
                    try:
                        # A lost commit acknowledgement does not prove rollback.
                        # Never remove a rendition already referenced by the DB.
                        fresh = await self._obtener_documento(documento_id)
                        referenced = {f.get("storage_path_firmado") for f in (fresh.metadatos or {}).get("firmas", [])}
                        if path_firmado not in referenced:
                            await storage.eliminar([path_firmado])
                    except Exception as cleanup_exc:
                        logger.warning(
                            "No se pudo limpiar la versión firmada huérfana %s: %s",
                            path_firmado,
                            cleanup_exc,
                        )
                    raise
            else:
                try:
                    await self.db.flush()
                except BaseException:
                    await self.db.rollback()
                    try:
                        fresh = await self._obtener_documento(documento_id)
                        referenced = {f.get("storage_path_firmado") for f in (fresh.metadatos or {}).get("firmas", [])}
                        if path_firmado not in referenced:
                            await storage.eliminar([path_firmado])
                    except Exception as cleanup_exc:
                        logger.warning(
                            "No se pudo limpiar la versión firmada no confirmada %s: %s",
                            path_firmado,
                            cleanup_exc,
                        )
                    raise

            return {
                "documento_id": str(documento_id),
                "firma_id": str(firma_id),
                "firmante": cert.nombre,
                "rfc": cert.rfc,
                "fecha_firma": signed_at.isoformat(),
                "razon": razon,
                "sello_tiempo": usar_tsa,
                "perfil_firma": resultado_firma.get("profile"),
                "storage_path_firmado": path_firmado,
                "sha256_firmado": sha256_firmado,
            }
        finally:
            for p in (cer_path, key_path, input_path, output_path):
                if p and os.path.exists(p):
                    os.unlink(p)

    async def validar_firma(self, documento_id: UUID) -> Dict[str, Any]:
        """Valida las firmas del documento FIRMADO real (no del original
        sin firmar). Antes: pdf_bytes = b"" -- siempre validaba nada."""
        documento = await self._obtener_documento(documento_id)
        metadatos = documento.metadatos or {}
        firmas = metadatos.get("firmas", [])
        if not firmas:
            raise MegalodonException(ErrorCode.FIRMA_INVALIDA, "Este documento no tiene firmas registradas")

        tenant_id = await self._tenant_documento(documento)
        legacy_records = [
            item for item in firmas
            if not item.get("firma_id") and not item.get("sha256_firmado")
        ]
        if len(legacy_records) > 1:
            raise MegalodonException(
                ErrorCode.FIRMA_INVALIDA,
                "La cadena contiene varias firmas históricas que sobrescribieron la misma ruta; la procedencia completa no puede acreditarse.",
                409,
            )
        previous_path, previous_hash = documento.storage_path, documento.hash_sha256
        for index, signature in enumerate(firmas):
            legacy = not signature.get("firma_id") and not signature.get("sha256_firmado")
            signed_path = self._signed_path(documento, signature)
            if legacy:
                if index != 0 or signed_path != f"{documento.storage_path}.firmado.pdf":
                    raise MegalodonException(
                        ErrorCode.FIRMA_INVALIDA,
                        "La firma histórica no está en la posición/ruta esperada para compatibilidad.",
                        409,
                    )
                # V1 did not persist source-path/digest fields. Its PDF must
                # pass strict trust and revocation checks before further use.
            else:
                if signature.get("storage_path_origen_firma") != previous_path:
                    raise MegalodonException(ErrorCode.FIRMA_INVALIDA, "La cadena de cofirmas está incompleta.", 409)
                if signature.get("sha256_origen_firma") != previous_hash:
                    raise MegalodonException(ErrorCode.FIRMA_INVALIDA, "El predecesor de la firma no coincide.", 409)
            pdf_firmado = await self._signed_content(documento, signature, tenant_id)
            previous_path = signed_path
            previous_hash = signature.get("sha256_firmado") or hashlib.sha256(pdf_firmado).hexdigest()
        return await self._crypto_call(self.modulo.validar_firma_pdf, pdf_firmado)

    async def reconciliar_firmas(self, documento_id, usuario_id, *, eliminar=False):
        """Reconcile crash leftovers without touching referenced/active evidence.

        The document lock is shared with signing; a one-day grace period also
        protects uploads with ambiguous remote acknowledgements. Inventory is
        the default, and malformed/undated objects require operator review.
        """
        try:
            document = await self._obtener_documento(documento_id, bloquear=True)
            await self._autorizar_firma(document, usuario_id)
            storage = self._storage_for_document(document)
            referenced = {f.get("storage_path_firmado") for f in (document.metadatos or {}).get("firmas", [])}
            directory, _, filename = document.storage_path.rpartition("/")
            prefix = filename + ".firmado."
            cutoff = datetime.now(timezone.utc) - timedelta(days=1)
            offset, orphans = 0, []
            while True:
                objects = await storage.listar(directory, offset=offset)
                for obj in objects:
                    name = obj.get("name", "")
                    if not name.startswith(prefix) or not name.endswith(".pdf"):
                        continue
                    path = f"{directory}/{name}" if directory else name
                    if path in referenced:
                        continue
                    try:
                        UUID(name[len(prefix):-4])
                        modified = datetime.fromisoformat(obj["updated_at"].replace("Z", "+00:00"))
                        if modified.tzinfo is None or modified >= cutoff:
                            continue
                    except (ValueError, KeyError, TypeError, AttributeError):
                        continue
                    orphans.append(path)
                if len(objects) < 100:
                    break
                offset += len(objects)
            if eliminar and orphans:
                await storage.eliminar(orphans)
            return {"documento_id": str(documento_id), "huerfanos": orphans,
                    "eliminados": len(orphans) if eliminar else 0}
        finally:
            await self.db.rollback()

    async def firmar_hash_expediente(
        self,
        expediente_id: UUID,
        certificado: CertificadoFIEL,
        *,
        usuario_id: UUID,
    ) -> Dict[str, Any]:
        """Firma el Merkle root de un expediente para trazabilidad."""
        result = await self.db.execute(select(ExpedienteObra).where(
            ExpedienteObra.id == expediente_id).with_for_update().execution_options(populate_existing=True))
        expediente = result.scalar_one_or_none()
        if not expediente:
            raise MegalodonException(ErrorCode.DOCUMENTO_NO_ENCONTRADO, f"Expediente {expediente_id} no encontrado")
        await authorize_by_id(self.db, usuario_id, expediente.tenant_id, "approve")
        if not expediente.merkle_root:
            raise MegalodonException(ErrorCode.FIRMA_INVALIDA, "El expediente no tiene Merkle root calculado")

        merkle_bytes = expediente.merkle_root.encode()
        firma = self.modulo.firmar_hash_documento(merkle_bytes, certificado)

        signed_at = datetime.now(timezone.utc)
        firma_id = uuid4()
        firma_snapshot = {
            "firma_id": str(firma_id),
            "firma": firma,
            "usuario_id": str(usuario_id),
            "rfc": certificado.rfc,
            "fecha": signed_at.isoformat(),
            "certificado_vigencia_inicio": certificado.vigencia_inicio.isoformat(),
            "certificado_vigencia_fin": certificado.vigencia_fin.isoformat(),
            "merkle_root": expediente.merkle_root,
        }
        metadatos = dict(expediente.metadatos or {})
        firmas_merkle = list(metadatos.get("firmas_merkle") or [])
        firmas_merkle.append(firma_snapshot)
        metadatos["firmas_merkle"] = firmas_merkle
        # Backwards-compatible pointer to the latest signature, while the
        # append-only list preserves every historical attestation.
        metadatos["firma_merkle"] = firma_snapshot
        expediente.metadatos = metadatos
        expediente.actualizado_por_id = usuario_id
        await self.db.commit()

        return {
            "expediente_id": str(expediente_id),
            "merkle_root": expediente.merkle_root,
            "firma_id": str(firma_id),
            "firma": firma,
            "firmante": certificado.rfc,
            "fecha_firma": signed_at.isoformat(),
        }

    # ─── CFDI 4.0: sellado digital (NO timbrado -- eso requiere un PAC) ──

    async def sellar_cfdi(
        self,
        *,
        xml_cfdi: bytes,
        certificado_cer: bytes,
        certificado_key: bytes,
        password: str,
    ) -> Dict[str, Any]:
        """Genera cadena original + sello digital de un CFDI 4.0.

        Importante: esto NO timbra el CFDI. El timbrado fiscal requiere
        un PAC (Proveedor Autorizado de Certificación) autorizado por el
        SAT -- este método deja el XML sellado, listo para mandarlo a
        cualquier PAC.
        """
        cer_path = key_path = None
        try:
            with tempfile.NamedTemporaryFile(suffix=".cer", delete=False) as f:
                f.write(certificado_cer)
                cer_path = f.name
            with tempfile.NamedTemporaryFile(suffix=".key", delete=False) as f:
                f.write(certificado_key)
                key_path = f.name

            signer = CFDISATSigner(cer_path, key_path, password)
            resultado = signer.sellar_xml(xml_cfdi)

            if not resultado.success:
                raise MegalodonException(ErrorCode.FIRMA_INVALIDA, resultado.error or "Error al sellar CFDI")

            return {
                "xml_sellado": resultado.xml_sellado,
                "cadena_original": resultado.cadena_original,
                "sello_digital": resultado.sello_digital,
                "no_certificado": resultado.no_certificado,
                "nota": "XML sellado, NO timbrado. El timbrado fiscal requiere un PAC autorizado por el SAT.",
            }
        finally:
            for p in (cer_path, key_path):
                if p and os.path.exists(p):
                    os.unlink(p)

    # ─── Formato de firma exigido por plataforma gubernamental ─────────

    def formato_requerido_plataforma(self, plataforma: PlataformaLicitacion, tipo_documento: str) -> Dict[str, Any]:
        return {
            "plataforma": plataforma.value,
            "tipo_documento": tipo_documento,
            "formato_requerido": formato_requerido(plataforma, tipo_documento),
        }
