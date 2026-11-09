from __future__ import annotations

from datetime import datetime, timedelta, timezone
from hashlib import sha256
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.exc import IntegrityError

from app.config import get_settings
from app.models.base import AsyncSessionLocal
from app.models.procurement_jobs import ProcurementStorageIntent
from app.integrations.supabase_storage import storage_documentos, storage_exportaciones


class ProcurementStorageGuard:
    def __init__(self, *, session_factory=None):
        self.session_factory = session_factory or AsyncSessionLocal

    async def _prepare(self, *, tenant_id: UUID, job_id: UUID | None, bucket: str, path: str, content_hash: str, content_type: str, size_bytes: int, entity_type: str) -> UUID:
        async with self.session_factory() as db:
            existing = await db.scalar(select(ProcurementStorageIntent).where(
                ProcurementStorageIntent.tenant_id == tenant_id,
                ProcurementStorageIntent.bucket == bucket,
                ProcurementStorageIntent.storage_path == path,
                ProcurementStorageIntent.content_hash == content_hash,
            ).with_for_update().execution_options(populate_existing=True))
            if existing is not None:
                # ERROR/STALE are retryable observations, not a new identity.
                return existing.id
            row = ProcurementStorageIntent(
                tenant_id=tenant_id,
                job_id=job_id,
                bucket=bucket,
                storage_path=path,
                content_hash=content_hash,
                content_type=content_type,
                size_bytes=size_bytes,
                state="PENDING",
                entity_type=entity_type,
            )
            db.add(row)
            try:
                await db.commit()
            except IntegrityError:
                await db.rollback()
                existing = await db.scalar(select(ProcurementStorageIntent).where(
                    ProcurementStorageIntent.tenant_id == tenant_id,
                    ProcurementStorageIntent.bucket == bucket,
                    ProcurementStorageIntent.storage_path == path,
                    ProcurementStorageIntent.content_hash == content_hash,
                ))
                if existing is None:
                    raise
                return existing.id
            return row.id

    async def _set_state(self, intent_id: UUID, state: str, *, tenant_id: UUID, verified: bool = False, entity_id: UUID | None = None, error: str | None = None) -> None:
        async with self.session_factory() as db:
            row = await db.scalar(select(ProcurementStorageIntent).where(ProcurementStorageIntent.id == intent_id, ProcurementStorageIntent.tenant_id == tenant_id))
            if row is None:
                return
            row.state = state
            row.verified = verified
            if entity_id is not None:
                row.entity_id = entity_id
            row.error_message = error
            await db.commit()

    async def upload_verified(self, *, tenant_id: UUID, job_id: UUID | None, bucket_name: str, path: str, content: bytes, content_type: str, entity_type: str, entity_id: UUID | None = None) -> str:
        digest = sha256(content).hexdigest()
        intent_id = await self._prepare(tenant_id=tenant_id, job_id=job_id, bucket=bucket_name, path=path, content_hash=digest, content_type=content_type, size_bytes=len(content), entity_type=entity_type)
        await self._set_state(intent_id, "UPLOADING", tenant_id=tenant_id)
        settings = get_settings()
        if bucket_name == settings.SUPABASE_BUCKET_DOCUMENTOS:
            bucket = storage_documentos()
        elif bucket_name == settings.SUPABASE_BUCKET_EXPORTS:
            bucket = storage_exportaciones()
        else:
            raise RuntimeError(f"Bucket de Procurement no permitido: {bucket_name}")
        try:
            await bucket.subir(path, content, content_type)
            stored = await bucket.descargar(path)
            stored_hash = sha256(stored).hexdigest()
            if stored_hash != digest:
                await self._set_state(intent_id, "ERROR", tenant_id=tenant_id, error="Storage hash mismatch after upload.")
                raise RuntimeError("El hash del objeto en storage no coincide después de la subida.")
            await self._set_state(intent_id, "VERIFIED", tenant_id=tenant_id, verified=True, entity_id=entity_id)
            return path
        except Exception as exc:
            await self._set_state(intent_id, "ERROR", tenant_id=tenant_id, error=str(exc)[:4000])
            raise

    async def reconcile(self, *, tenant_id: UUID | None = None, max_rows: int = 100) -> dict:
        async with self.session_factory() as db:
            query = select(ProcurementStorageIntent).where(ProcurementStorageIntent.state.in_(["PENDING", "UPLOADING", "VERIFIED"]))
            if tenant_id is not None:
                query = query.where(ProcurementStorageIntent.tenant_id == tenant_id)
            rows = (await db.execute(query.order_by(ProcurementStorageIntent.created_at).limit(max_rows))).scalars().all()
        checked = verified = missing = stale = 0
        now = datetime.now(timezone.utc)
        for row in rows:
            checked += 1
            try:
                settings = get_settings()
                if row.bucket == settings.SUPABASE_BUCKET_DOCUMENTOS:
                    bucket = storage_documentos()
                elif row.bucket == settings.SUPABASE_BUCKET_EXPORTS:
                    bucket = storage_exportaciones()
                else:
                    await self._set_state(row.id, "ERROR", tenant_id=row.tenant_id, error=f"Bucket no permitido: {row.bucket}")
                    missing += 1
                    continue
                data = await bucket.descargar(row.storage_path)
                if sha256(data).hexdigest() == row.content_hash:
                    await self._set_state(row.id, "VERIFIED", tenant_id=row.tenant_id, verified=True)
                    verified += 1
                else:
                    await self._set_state(row.id, "ERROR", tenant_id=row.tenant_id, error="Reconciliation hash mismatch.")
                    missing += 1
            except Exception as exc:
                age = now - (row.created_at or now)
                if age > timedelta(hours=1):
                    await self._set_state(row.id, "STALE", tenant_id=row.tenant_id, error=str(exc)[:4000])
                    stale += 1
        return {"checked": checked, "verified": verified, "missing": missing, "stale": stale}
