# Copyright © 2026 Cristian Rodriguez
# All rights reserved.
# Unauthorized copying, modification, distribution, or use is prohibited
# without prior written permission.

"""
Trazabilidad / Audit Ledger — Bitácora inmutable con Hash Chain.
Registro de acciones: quién hizo qué, cuándo, sobre qué expediente.
"""
import hashlib
import json
from typing import Optional, List, Dict, Any
from datetime import datetime

from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, desc, and_

from app.models.audit_ledger import AuditLedger, TipoAccion
from app.core.errors import MegalodonException


class TrazabilidadError(MegalodonException):
    """Error en el sistema de trazabilidad."""


class LedgerService:
    """
    Servicio de bitácora inmutable con Hash Chain (Merkle light).
    Cada registro incluye el hash del registro anterior, formando una cadena
    criptográfica que permite detectar alteraciones.
    """

    def __init__(self, db: AsyncSession):
        self.db = db

    def _calcular_hash(
        self,
        entidad_tipo: str,
        entidad_id: str,
        accion: str,
        datos_anteriores: Optional[Dict],
        datos_nuevos: Optional[Dict],
        timestamp: str,
        hash_previo: Optional[str] = None,
    ) -> str:
        """
        Calcula el hash SHA-256 de un registro de auditoría.
        El hash incluye el hash_previo, formando una cadena inmutable.
        """
        data = {
            "entidad_tipo": entidad_tipo,
            "entidad_id": entidad_id,
            "accion": accion,
            "datos_anteriores": datos_anteriores or {},
            "datos_nuevos": datos_nuevos or {},
            "timestamp": timestamp,
            "hash_previo": hash_previo or "0" * 64,
        }

        # Serializar de forma determinística
        json_str = json.dumps(data, sort_keys=True, ensure_ascii=False)
        return hashlib.sha256(json_str.encode("utf-8")).hexdigest()

    async def registrar_accion(
        self,
        tenant_id: str,
        user_id: Optional[str],
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
    ) -> AuditLedger:
        """
        Registra una acción en la bitácora inmutable.
        Calcula el hash del registro incluyendo el hash previo.
        """
        # Obtener el hash previo del mismo tipo de entidad
        query = select(AuditLedger).where(
            and_(
                AuditLedger.entidad_tipo == entidad_tipo,
                AuditLedger.entidad_id == entidad_id,
            )
        ).order_by(desc(AuditLedger.created_at)).limit(1)

        result = await self.db.execute(query)
        registro_previo = result.scalar_one_or_none()
        hash_previo = registro_previo.hash_registro if registro_previo else None

        # Calcular hash del nuevo registro
        timestamp = datetime.utcnow().isoformat()
        hash_registro = self._calcular_hash(
            entidad_tipo=entidad_tipo,
            entidad_id=entidad_id,
            accion=accion.value,
            datos_anteriores=datos_anteriores,
            datos_nuevos=datos_nuevos,
            timestamp=timestamp,
            hash_previo=hash_previo,
        )

        # Crear registro
        registro = AuditLedger(
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
            hash_registro=hash_registro,
            hash_previo=hash_previo,
            ip_address=ip_address,
            user_agent=user_agent,
        )

        self.db.add(registro)
        await self.db.commit()
        await self.db.refresh(registro)

        return registro

    async def verificar_integridad(
        self,
        entidad_tipo: str,
        entidad_id: str,
    ) -> Dict[str, Any]:
        """
        Verifica la integridad de la cadena de hashes para una entidad.
        Recalcula los hashes y detecta cualquier alteración.

        Returns:
            Dict con resultado de verificación
        """
        query = select(AuditLedger).where(
            and_(
                AuditLedger.entidad_tipo == entidad_tipo,
                AuditLedger.entidad_id == entidad_id,
            )
        ).order_by(AuditLedger.created_at)

        result = await self.db.execute(query)
        registros = result.scalars().all()

        if not registros:
            return {"valido": True, "registros": 0, "errores": []}

        errores = []
        hash_previo_esperado = None

        for i, reg in enumerate(registros):
            # Verificar que el hash_previo coincida con el hash del registro anterior
            if i > 0:
                if reg.hash_previo != registros[i - 1].hash_registro:
                    errores.append({
                        "registro_id": str(reg.id),
                        "error": "Hash previo no coincide con registro anterior",
                        "hash_previo_registrado": reg.hash_previo,
                        "hash_previo_esperado": registros[i - 1].hash_registro,
                    })

            # Recalcular hash y verificar
            hash_recalculado = self._calcular_hash(
                entidad_tipo=reg.entidad_tipo,
                entidad_id=reg.entidad_id,
                accion=reg.accion,
                datos_anteriores=reg.datos_anteriores,
                datos_nuevos=reg.datos_nuevos,
                timestamp=reg.created_at.isoformat() if reg.created_at else datetime.utcnow().isoformat(),
                hash_previo=reg.hash_previo,
            )

            if hash_recalculado != reg.hash_registro:
                errores.append({
                    "registro_id": str(reg.id),
                    "error": "Hash recalculado no coincide",
                    "hash_registrado": reg.hash_registro,
                    "hash_recalculado": hash_recalculado,
                })

        return {
            "valido": len(errores) == 0,
            "registros": len(registros),
            "errores": errores,
        }

    async def obtener_historial(
        self,
        entidad_tipo: str,
        entidad_id: str,
        skip: int = 0,
        limit: int = 100,
    ) -> List[Dict[str, Any]]:
        """Obtiene el historial completo de una entidad."""
        query = select(AuditLedger).where(
            and_(
                AuditLedger.entidad_tipo == entidad_tipo,
                AuditLedger.entidad_id == entidad_id,
            )
        ).order_by(desc(AuditLedger.created_at)).offset(skip).limit(limit)

        result = await self.db.execute(query)
        registros = result.scalars().all()

        return [
            {
                "id": str(r.id),
                "user_email": r.user_email,
                "user_role": r.user_role,
                "accion": r.accion,
                "descripcion": r.descripcion,
                "datos_anteriores": r.datos_anteriores,
                "datos_nuevos": r.datos_nuevos,
                "hash_registro": r.hash_registro,
                "hash_previo": r.hash_previo,
                "ip_address": r.ip_address,
                "created_at": r.created_at.isoformat() if r.created_at else None,
            }
            for r in registros
        ]

    async def exportar_para_auditoria(
        self,
        entidad_tipo: str,
        entidad_id: str,
    ) -> Dict[str, Any]:
        """
        Exporta el historial completo de una entidad para auditoría.
        Incluye verificación de integridad.
        """
        historial = await self.obtener_historial(entidad_tipo, entidad_id, limit=10000)
        verificacion = await self.verificar_integridad(entidad_tipo, entidad_id)

        return {
            "entidad_tipo": entidad_tipo,
            "entidad_id": entidad_id,
            "fecha_exportacion": datetime.utcnow().isoformat(),
            "integridad_verificada": verificacion["valido"],
            "registros_totales": verificacion["registros"],
            "errores_detectados": verificacion["errores"],
            "historial": historial,
        }
