# Copyright © 2026 Cristian Rodriguez
# All rights reserved.
# Unauthorized copying, modification, distribution, or use is prohibited
# without prior written permission.

"""
AuditService - Servicio de auditoría y bitácora inmutable.
Consultas, reportes y verificación de integridad del audit ledger.
"""
from typing import List, Optional, Dict, Any
from uuid import UUID
from datetime import datetime, timezone, timedelta

from sqlalchemy import select, and_, desc, text
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.audit_ledger import AuditLedger, TipoAccion
from app.services.base import BaseService
from app.core.errors import MegalodonException, ErrorCode


class AuditService(BaseService[AuditLedger]):
    """Servicio de auditoría con consultas avanzadas y reportes."""

    def __init__(self, db: AsyncSession):
        super().__init__(AuditLedger, db)

    @staticmethod
    def _require_scope(tenant_id: Optional[UUID], global_scope: bool, operation: str) -> None:
        if global_scope and tenant_id is not None:
            raise MegalodonException(
                ErrorCode.VALIDACION_FALLIDA,
                f"El alcance global de {operation} no acepta tenant_id.",
                status_code=400,
            )
        if not global_scope and tenant_id is None:
            raise MegalodonException(
                ErrorCode.VALIDACION_FALLIDA,
                f"{operation} requiere tenant_id explícito o autorización global explícita.",
                status_code=403,
            )

    @staticmethod
    def _payload_hash_v2(
        *,
        tenant_id: UUID,
        user_id: Optional[UUID],
        user_email: Optional[str],
        user_role: Optional[str],
        entidad_tipo: str,
        entidad_id: str,
        accion: TipoAccion,
        descripcion: Optional[str],
        datos_anteriores: Optional[Dict],
        datos_nuevos: Optional[Dict],
        ip_address: Optional[str],
        user_agent: Optional[str],
        timestamp: datetime,
        hash_previo: Optional[str],
    ) -> str:
        import hashlib
        import json

        payload = {
            "hash_version": 2,
            "tenant_id": str(tenant_id),
            "user_id": str(user_id) if user_id else None,
            "user_email": user_email,
            "user_role": user_role,
            "entidad_tipo": entidad_tipo,
            "entidad_id": entidad_id,
            "accion": accion.value,
            "descripcion": descripcion,
            "datos_anteriores": datos_anteriores,
            "datos_nuevos": datos_nuevos,
            "ip_address": ip_address,
            "user_agent": user_agent,
            "timestamp": timestamp.isoformat(),
            "hash_previo": hash_previo,
        }
        return hashlib.sha256(
            json.dumps(payload, sort_keys=True, default=str).encode()
        ).hexdigest()

    async def registrar_accion(
        self,
        *,
        user_id: Optional[UUID],
        user_email: Optional[str],
        user_role: Optional[str],
        entidad_tipo: str,
        entidad_id: str,
        accion: TipoAccion,
        descripcion: Optional[str] = None,
        datos_anteriores: Optional[Dict] = None,
        datos_nuevos: Optional[Dict] = None,
        ip_address: Optional[str] = None,
        user_agent: Optional[str] = None,
        hash_previo: Optional[str] = None,
        tenant_id: Optional[UUID] = None,
        commit: bool = True,
    ) -> AuditLedger:
        if tenant_id is None:
            raise MegalodonException(
                ErrorCode.VALIDACION_FALLIDA,
                "La bitácora requiere tenant_id explícito.",
                status_code=400,
            )

        entidad_tipo = entidad_tipo.strip().upper()
        entidad_id = str(entidad_id).strip()
        if not entidad_tipo or not entidad_id:
            raise MegalodonException(
                ErrorCode.VALIDACION_FALLIDA,
                "La cadena de auditoría requiere tipo e id de entidad.",
                status_code=400,
            )

        # PostgreSQL serializes writers of the same tenant/entity chain even
        # when the chain is still empty. The DB INSERT trigger repeats this
        # guard, so direct writers cannot fork a chain either.
        bind = self.db.get_bind()
        if bind.dialect.name == "postgresql":
            chain_key = f"{tenant_id}|{entidad_tipo}|{entidad_id}"
            await self.db.execute(
                text("SELECT pg_advisory_xact_lock(hashtextextended(:key, 0))"),
                {"key": chain_key},
            )

        previous = await self.db.scalar(
            select(AuditLedger)
            .where(
                AuditLedger.tenant_id == tenant_id,
                AuditLedger.entidad_tipo == entidad_tipo,
                AuditLedger.entidad_id == entidad_id,
            )
            .order_by(AuditLedger.created_at.desc(), AuditLedger.id.desc())
            .limit(1)
        )
        actual_previo = previous.hash_registro if previous else None

        # Backward-compatible parameter: callers may assert the predecessor,
        # but they can no longer choose it. A stale expected value fails
        # instead of producing a fork.
        if hash_previo is not None and hash_previo != actual_previo:
            raise MegalodonException(
                ErrorCode.CONFLICT,
                "La bitácora avanzó concurrentemente; reintenta la operación.",
                status_code=409,
            )
        hash_previo = actual_previo
        timestamp = datetime.now(timezone.utc)
        if timestamp.tzinfo is None:
            timestamp = timestamp.replace(tzinfo=timezone.utc)
        if previous is not None:
            previous_timestamp = previous.created_at
            if previous_timestamp.tzinfo is None:
                previous_timestamp = previous_timestamp.replace(tzinfo=timezone.utc)
            else:
                previous_timestamp = previous_timestamp.astimezone(timezone.utc)
            # Wall-clock resolution/adjustment must not collapse two chain events.
            if timestamp <= previous_timestamp:
                timestamp = previous_timestamp + timedelta(microseconds=1)
        hash_registro = self._payload_hash_v2(
            tenant_id=tenant_id,
            user_id=user_id,
            user_email=user_email,
            user_role=user_role,
            entidad_tipo=entidad_tipo,
            entidad_id=entidad_id,
            accion=accion,
            descripcion=descripcion,
            datos_anteriores=datos_anteriores,
            datos_nuevos=datos_nuevos,
            ip_address=ip_address,
            user_agent=user_agent,
            timestamp=timestamp,
            hash_previo=hash_previo,
        )

        registro = AuditLedger(
            tenant_id=tenant_id,
            created_at=timestamp,
            user_id=user_id,
            user_email=user_email,
            user_role=user_role,
            entidad_tipo=entidad_tipo,
            entidad_id=entidad_id,
            accion=accion,
            descripcion=descripcion,
            datos_anteriores=datos_anteriores,
            datos_nuevos=datos_nuevos,
            hash_registro=hash_registro,
            hash_previo=hash_previo,
            hash_version=2,
            ip_address=ip_address,
            user_agent=user_agent,
        )
        self.db.add(registro)
        await self.db.flush()
        if commit:
            await self.db.commit()
            await self.db.refresh(registro)
        return registro

    async def obtener_historial_expediente(
        self,
        expediente_id: str,
        *,
        skip: int = 0,
        limit: int = 100,
        tenant_id: UUID,
    ) -> List[AuditLedger]:
        query = select(AuditLedger).where(
            and_(
                AuditLedger.tenant_id == tenant_id,
                AuditLedger.entidad_tipo == "EXPEDIENTE",
                AuditLedger.entidad_id == str(expediente_id),
            )
        )
        result = await self.db.execute(
            query.order_by(desc(AuditLedger.created_at)).offset(skip).limit(limit)
        )
        return result.scalars().all()

    async def obtener_historial_documento(
        self,
        documento_id: str,
        *,
        skip: int = 0,
        limit: int = 100,
        tenant_id: UUID,
    ) -> List[AuditLedger]:
        query = select(AuditLedger).where(
            and_(
                AuditLedger.tenant_id == tenant_id,
                AuditLedger.entidad_tipo == "DOCUMENTO",
                AuditLedger.entidad_id == str(documento_id),
            )
        )
        result = await self.db.execute(
            query.order_by(desc(AuditLedger.created_at)).offset(skip).limit(limit)
        )
        return result.scalars().all()

    async def verificar_integridad_cadena(
        self,
        entidad_tipo: str,
        entidad_id: str,
        tenant_id: Optional[UUID] = None,
        *,
        global_scope: bool = False,
    ) -> Dict[str, Any]:
        self._require_scope(tenant_id, global_scope, "verificación de integridad")
        import hashlib
        import json

        query = select(AuditLedger).where(
            and_(
                AuditLedger.entidad_tipo == entidad_tipo,
                AuditLedger.entidad_id == str(entidad_id),
            )
        )
        if tenant_id is not None:
            query = query.where(AuditLedger.tenant_id == tenant_id)
        ordering = (
            (AuditLedger.tenant_id, AuditLedger.created_at, AuditLedger.id)
            if global_scope
            else (AuditLedger.created_at, AuditLedger.id)
        )
        result = await self.db.execute(query.order_by(*ordering))
        registros = result.scalars().all()

        if not registros:
            return {"valido": True, "registros": 0, "errores": []}

        # Entity IDs are not globally unique across tenants. Global verification
        # must validate each tenant's independent hash chain rather than merging
        # records with the same external entity identifier into one false chain.
        cadenas: Dict[UUID, List[AuditLedger]] = {}
        for registro in registros:
            cadenas.setdefault(registro.tenant_id, []).append(registro)

        errores = []
        for tenant_actual, registros_cadena in cadenas.items():
            hash_previo_esperado = None
            for indice, reg in enumerate(registros_cadena):
                timestamp = (
                    reg.created_at.replace(tzinfo=timezone.utc)
                    if reg.created_at.tzinfo is None
                    else reg.created_at.astimezone(timezone.utc)
                )
                if getattr(reg, "hash_version", 1) == 2:
                    hash_recomputado = self._payload_hash_v2(
                        tenant_id=reg.tenant_id,
                        user_id=reg.user_id,
                        user_email=reg.user_email,
                        user_role=reg.user_role,
                        entidad_tipo=reg.entidad_tipo,
                        entidad_id=reg.entidad_id,
                        accion=TipoAccion(reg.accion),
                        descripcion=reg.descripcion,
                        datos_anteriores=reg.datos_anteriores,
                        datos_nuevos=reg.datos_nuevos,
                        ip_address=reg.ip_address,
                        user_agent=reg.user_agent,
                        timestamp=timestamp,
                        hash_previo=reg.hash_previo,
                    )
                else:
                    # Historical v1 contract is preserved exactly; migration never
                    # rewrites or pretends stronger evidence existed in the past.
                    payload = {
                        "user_id": str(reg.user_id) if reg.user_id else None,
                        "entidad_tipo": reg.entidad_tipo,
                        "entidad_id": reg.entidad_id,
                        "accion": reg.accion.value if hasattr(reg.accion, "value") else reg.accion,
                        "descripcion": reg.descripcion,
                        "datos_nuevos": reg.datos_nuevos,
                        "timestamp": timestamp.isoformat(),
                        "hash_previo": reg.hash_previo,
                    }
                    hash_recomputado = hashlib.sha256(
                        json.dumps(payload, sort_keys=True, default=str).encode()
                    ).hexdigest()

                context: Dict[str, Any] = {"indice": indice, "registro_id": str(reg.id)}
                if global_scope:
                    context["tenant_id"] = str(tenant_actual)

                if hash_recomputado != reg.hash_registro:
                    errores.append({
                        **context,
                        "hash_almacenado": reg.hash_registro,
                        "hash_recomputado": hash_recomputado,
                        "tipo_error": "HASH_NO_COINCIDE",
                    })
                if reg.hash_previo != hash_previo_esperado:
                    errores.append({
                        **context,
                        "hash_previo_almacenado": reg.hash_previo,
                        "hash_previo_esperado": hash_previo_esperado,
                        "tipo_error": "CADENA_ROTA" if indice else "GENESIS_INVALIDA",
                    })
                hash_previo_esperado = reg.hash_registro

        return {
            "valido": len(errores) == 0,
            "registros": len(registros),
            "errores": errores,
        }

    async def reporte_actividad_usuario(
        self,
        user_id: UUID,
        fecha_inicio: Optional[datetime] = None,
        fecha_fin: Optional[datetime] = None,
        tenant_id: Optional[UUID] = None,
        *,
        global_scope: bool = False,
    ) -> Dict[str, Any]:
        self._require_scope(tenant_id, global_scope, "reporte de actividad de usuario")
        query = select(AuditLedger).where(AuditLedger.user_id == user_id)
        if tenant_id is not None:
            query = query.where(AuditLedger.tenant_id == tenant_id)
        if fecha_inicio:
            query = query.where(AuditLedger.created_at >= fecha_inicio)
        if fecha_fin:
            query = query.where(AuditLedger.created_at <= fecha_fin)

        result = await self.db.execute(query)
        registros = result.scalars().all()

        acciones = {}
        entidades = {}
        for r in registros:
            accion_key = r.accion.value if hasattr(r.accion, 'value') else str(r.accion)
            acciones[accion_key] = acciones.get(accion_key, 0) + 1
            entidades[r.entidad_tipo] = entidades.get(r.entidad_tipo, 0) + 1

        return {
            "user_id": str(user_id),
            "total_registros": len(registros),
            "periodo": {
                "inicio": fecha_inicio.isoformat() if fecha_inicio else None,
                "fin": fecha_fin.isoformat() if fecha_fin else None,
            },
            "acciones": acciones,
            "entidades_afectadas": entidades,
            "registros": [
                {
                    "id": str(r.id),
                    "accion": r.accion.value if hasattr(r.accion, 'value') else str(r.accion),
                    "entidad_tipo": r.entidad_tipo,
                    "entidad_id": r.entidad_id,
                    "descripcion": r.descripcion,
                    "created_at": r.created_at.isoformat() if r.created_at else None,
                }
                for r in registros
            ],
        }

    async def reporte_actividad_sistema(
        self,
        fecha_inicio: Optional[datetime] = None,
        fecha_fin: Optional[datetime] = None,
        tenant_id: Optional[UUID] = None,
        *,
        global_scope: bool = False,
    ) -> Dict[str, Any]:
        self._require_scope(tenant_id, global_scope, "reporte de actividad del sistema")
        query = select(AuditLedger)
        if tenant_id is not None:
            query = query.where(AuditLedger.tenant_id == tenant_id)
        if fecha_inicio:
            query = query.where(AuditLedger.created_at >= fecha_inicio)
        if fecha_fin:
            query = query.where(AuditLedger.created_at <= fecha_fin)

        result = await self.db.execute(query)
        registros = result.scalars().all()

        usuarios = {}
        acciones = {}
        for r in registros:
            if r.user_email:
                usuarios[r.user_email] = usuarios.get(r.user_email, 0) + 1
            accion_key = r.accion.value if hasattr(r.accion, 'value') else str(r.accion)
            acciones[accion_key] = acciones.get(accion_key, 0) + 1

        return {
            "total_registros": len(registros),
            "periodo": {
                "inicio": fecha_inicio.isoformat() if fecha_inicio else None,
                "fin": fecha_fin.isoformat() if fecha_fin else None,
            },
            "top_usuarios": sorted(usuarios.items(), key=lambda x: x[1], reverse=True)[:10],
            "acciones": acciones,
        }
