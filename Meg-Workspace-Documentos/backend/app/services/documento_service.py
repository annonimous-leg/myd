# Copyright © 2026 Cristian Rodriguez
# All rights reserved.
# Unauthorized copying, modification, distribution, or use is prohibited
# without prior written permission.

"""
DocumentoService - Gestión de documentos electrónicos con cifrado.
"""
import hashlib
import io
from datetime import datetime
from typing import Optional, List
from uuid import UUID, uuid4

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.expediente import Documento, ExpedienteObra
from app.services.base import BaseService
from app.core.errors import MegalodonException, ErrorCode
from app.core.crypto import cifrar_sobre, descifrar_sobre
from app.integrations.supabase_storage import storage_documentos


class DocumentoService(BaseService[Documento]):
    """Servicio de gestión documental con cifrado opcional."""

    def __init__(self, db: AsyncSession, tenant_id: UUID | None = None):
        # Documento es el modelo legacy sin tenant_id propio; su aislamiento se
        # hace por la relación ExpedienteObra en los métodos de dominio.
        # No usar tenant_required=True aquí porque BaseService exige una
        # columna tenant_id física y bloquearía todo el módulo documental.
        super().__init__(Documento, db, tenant_id=tenant_id, tenant_required=False)

    async def crear_documento(
        self,
        *,
        expediente_id: UUID,
        file_content: bytes,
        filename: str,
        tipo_documental: str,
        cifrar: bool = False,
        metadatos: Optional[dict] = None,
        tenant_id: Optional[str] = None,
        creado_por_id: Optional[UUID] = None,
    ) -> Documento:
        """Alias canónico para subir_documento.

        Mantiene el mismo contrato de producción y deja explícito el filtro
        de tenant para las validaciones de deduplicación y pertenencia.
        """
        # El filtro real de pertenencia queda en subir_documento():
        #   select(ExpedienteObra).where(ExpedienteObra.id == expediente_id)
        #   if tenant_id: ExpedienteObra.tenant_id == tenant_id
        return await self.subir_documento(
            expediente_id=expediente_id,
            file_content=file_content,
            filename=filename,
            tipo_documental=tipo_documental,
            cifrar=cifrar,
            metadatos=metadatos,
            tenant_id=tenant_id,
            creado_por_id=creado_por_id,
        )

    async def subir_documento(
        self,
        *,
        expediente_id: UUID,
        file_content: bytes,
        filename: str,
        tipo_documental: str,
        cifrar: bool = False,
        metadatos: Optional[dict] = None,
        tenant_id: Optional[str] = None,
        creado_por_id: Optional[UUID] = None,
    ) -> Documento:
        """Sube un documento al expediente y lo persiste en Supabase Storage."""

        from app.core.authorization import authorize_by_id
        from app.core.crypto import calcular_merkle_root
        import logging

        scoped_tenant = UUID(str(tenant_id or self.tenant_id)) if tenant_id or self.tenant_id else None
        if self.tenant_id and scoped_tenant != UUID(str(self.tenant_id)):
            raise MegalodonException(ErrorCode.PERMISO_DENEGADO, "Organización inconsistente", 403)
        await authorize_by_id(self.db, creado_por_id, scoped_tenant, "write")
        if not filename or len(filename) > 500 or not tipo_documental or len(tipo_documental) > 50:
            raise MegalodonException(ErrorCode.PARAMETRO_INVALIDO, "Nombre o tipo documental inválido", 422)
        formato = filename.rsplit(".", 1)[-1].upper() if "." in filename else "DESCONOCIDO"
        if len(formato) > 20:
            raise MegalodonException(ErrorCode.PARAMETRO_INVALIDO, "Extensión de archivo inválida", 422)
        document_id = uuid4()
        storage_path = f"expedientes/{expediente_id}/{document_id}"
        storage = storage_documentos()
        uploaded = False
        try:
            expediente = await self.db.scalar(select(ExpedienteObra).where(
                ExpedienteObra.id == expediente_id, ExpedienteObra.tenant_id == scoped_tenant
            ).with_for_update().execution_options(populate_existing=True))
            if not expediente:
                raise MegalodonException(ErrorCode.DOCUMENTO_NO_ENCONTRADO, "Expediente no encontrado", 404)
            content_hash = hashlib.sha256(file_content).hexdigest()
            duplicate = await self.db.scalar(select(Documento.id).join(ExpedienteObra).where(
                Documento.hash_sha256 == content_hash, ExpedienteObra.tenant_id == scoped_tenant).limit(1))
            if duplicate:
                raise MegalodonException(ErrorCode.ARCHIVO_ERROR, "Documento duplicado detectado por hash", 409)
            content, nonce, tag, encrypted_key = file_content, None, None, None
            if cifrar:
                content, nonce, tag, encrypted_key = cifrar_sobre(file_content, tenant_id=str(scoped_tenant))
            await storage.subir(storage_path, content, content_type="application/octet-stream", overwrite=False)
            uploaded = True
            documento = Documento(
                id=document_id, identificador=f"DOC-{document_id}", nombre=filename,
                tipo_documental=tipo_documental, formato=formato, storage_path=storage_path,
                storage_bucket=storage.bucket, size_bytes=len(file_content), hash_sha256=content_hash,
                cifrado=cifrar, nonce_cifrado=nonce.hex() if nonce else None,
                tag_cifrado=tag.hex() if tag else None, encryption_key_enc=encrypted_key,
                metadatos=metadatos or {}, expediente_id=expediente_id,
                creado_por_id=creado_por_id, actualizado_por_id=creado_por_id,
            )
            self.db.add(documento)
            await self.db.flush()
            hashes = (await self.db.scalars(select(Documento.hash_sha256).where(
                Documento.expediente_id == expediente_id
            ).order_by(Documento.created_at, Documento.id))).all()
            expediente.merkle_root = calcular_merkle_root([value for value in hashes if value])
            expediente.actualizado_por_id = creado_por_id
            await self.db.commit()
            await self.db.refresh(documento)
            return documento
        except BaseException:
            await self.db.rollback()
            if uploaded:
                # A lost commit acknowledgement must never delete a committed object.
                try:
                    persisted = await self.db.get(Documento, document_id)
                    if persisted is None:
                        await storage.eliminar([storage_path])
                except Exception:
                    logging.getLogger(__name__).exception("Document upload reconciliation required: %s", document_id)
            raise

    async def descargar_documento(
        self, documento_id: UUID, expediente_id: UUID, tenant_id: Optional[str] = None,
    ) -> tuple[bytes, str]:
        """Descarga un documento real de Supabase Storage, descifrando si
        es necesario. Valida que el documento pertenezca al expediente de la
        ruta (evita acceso cross-expediente por UUID conocido) Y que el
        expediente pertenezca al tenant que hace la solicitud.

        BUG ORIGINAL (x2): regresaba `contenido = b""` siempre -- un stub
        que nunca se conectó al storage (ya corregido). Y no validaba
        tenant en absoluto -- current_user se recibía en el endpoint pero
        nunca se usaba, así que cualquier tenant con un documento_id +
        expediente_id válidos de OTRO tenant podía descargarlo y
        descifrarlo (la KEK se deriva del tenant del expediente, no de
        quien pide la descarga).
        """
        documento = await self.get(documento_id, tenant_id=tenant_id)
        if not documento or str(documento.expediente_id) != str(expediente_id):
            raise MegalodonException(
                ErrorCode.DOCUMENTO_NO_ENCONTRADO,
                f"Documento {documento_id} no encontrado en el expediente {expediente_id}",
            )

        expediente = await self.db.get(ExpedienteObra, documento.expediente_id)
        if not expediente or (tenant_id is not None and str(expediente.tenant_id) != str(tenant_id)):
            raise MegalodonException(
                ErrorCode.DOCUMENTO_NO_ENCONTRADO,
                f"Documento {documento_id} no encontrado en el expediente {expediente_id}",
            )

        storage = storage_documentos()
        contenido = await storage.descargar(documento.storage_path)

        if documento.cifrado and documento.nonce_cifrado and documento.tag_cifrado:
            if not documento.encryption_key_enc:
                raise MegalodonException(
                    ErrorCode.ARCHIVO_ERROR,
                    "Documento marcado como cifrado pero sin DEK almacenada "
                    "(cifrado con versión anterior al sistema de envelope encryption). "
                    "Contacte a soporte.",
                )
            # Obtener tenant_id desde el expediente para derivar la KEK
            # (ya lo tenemos arriba de la validación de tenant).
            contenido = descifrar_sobre(
                contenido,
                nonce=bytes.fromhex(documento.nonce_cifrado),
                tag=bytes.fromhex(documento.tag_cifrado),
                encrypted_dek_hex=documento.encryption_key_enc,
                tenant_id=str(expediente.tenant_id),
            )

        return contenido, documento.nombre

    async def listar_por_expediente(
        self,
        expediente_id: UUID,
        tipo_documental: Optional[str] = None,
        tenant_id: Optional[str] = None,
        skip: int = 0,
        limit: int = 100,
    ) -> List[Documento]:
        """Lista documentos de un expediente.

        BUG ORIGINAL: no validaba que el expediente perteneciera al tenant
        de quien pregunta -- listaba documentos de cualquier expediente
        con solo conocer su UUID, sin importar el tenant."""
        tenant_id = tenant_id or self.tenant_id
        if tenant_id is None:
            raise MegalodonException(ErrorCode.VALIDACION_FALLIDA, "Se requiere organización para listar documentos", 403)
        if tenant_id is not None:
            exp_result = await self.db.execute(
                select(ExpedienteObra).where(
                    ExpedienteObra.id == expediente_id, ExpedienteObra.tenant_id == tenant_id,
                )
            )
            if exp_result.scalar_one_or_none() is None:
                raise MegalodonException(
                    ErrorCode.DOCUMENTO_NO_ENCONTRADO,
                    f"Expediente {expediente_id} no encontrado",
                    404,
                )

        query = select(Documento).where(Documento.expediente_id == expediente_id)
        if tipo_documental:
            query = query.where(Documento.tipo_documental == tipo_documental)
        query = query.order_by(Documento.created_at.desc(), Documento.id).offset(skip).limit(limit)

        result = await self.db.execute(query)
        return result.scalars().all()
