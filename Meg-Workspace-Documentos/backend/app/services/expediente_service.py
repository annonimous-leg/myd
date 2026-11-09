# Copyright © 2026 Cristian Rodriguez
# All rights reserved.
# Unauthorized copying, modification, distribution, or use is prohibited
# without prior written permission.

"""
ExpedienteService - Gestión de expedientes electrónicos.
"""
from datetime import datetime
from typing import List, Optional
from uuid import UUID, uuid4

from sqlalchemy import select, func
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.models.expediente import ExpedienteObra, Documento, EstadoExpediente
from app.models.user import User
from app.services.base import BaseService
from app.core.errors import MegalodonException, ErrorCode
from app.core.crypto import calcular_merkle_root
from app.core.authorization import authorize_by_id


class ExpedienteService(BaseService[ExpedienteObra]):
    """Servicio de gestión de expedientes electrónicos."""

    def __init__(self, db: AsyncSession, tenant_id: UUID | None = None):
        super().__init__(ExpedienteObra, db, tenant_id=tenant_id, tenant_required=True)

    async def get_with_relations(self, id: UUID, tenant_id: UUID) -> Optional[ExpedienteObra]:
        """Obtiene expediente con documentos y presupuestos, filtrando por tenant
        para que un usuario no pueda leer expedientes de otro tenant con un UUID
        conocido."""
        result = await self.db.execute(
            select(ExpedienteObra)
            .where(ExpedienteObra.id == id)
            .where(ExpedienteObra.tenant_id == tenant_id)
            .options(selectinload(ExpedienteObra.documentos))
            .options(selectinload(ExpedienteObra.presupuestos))
        )
        return result.scalar_one_or_none()

    async def create_expediente(
        self,
        *,
        titulo: str,
        organo: str,
        unidad_administrativa: str,
        serie_documental: str,
        subserie_documental: str,
        tenant_id: UUID,
        descripcion: Optional[str] = None,
        proyecto_nombre: Optional[str] = None,
        ubicacion_obra: Optional[str] = None,
        monto_contrato: Optional[float] = None,
        plazo_dias: Optional[int] = None,
        tipo_contrato: str = "PRECIOS_UNITARIOS",
        responsable_tecnico: Optional[str] = None,
        responsable_ejecutivo: Optional[str] = None,
        responsable_id: Optional[UUID] = None,
        creado_por_id: Optional[UUID] = None,
    ) -> ExpedienteObra:
        """Crea un nuevo expediente con identificador único."""
        await authorize_by_id(self.db, creado_por_id, tenant_id)

        # Generar identificador: EXP-YYYY-NNNN
        year = datetime.now().year
        count = await self.count(tenant_id=tenant_id) + 1
        identificador = f"EXP-{year}-{count:04d}"

        data = {
            "id": uuid4(),
            "identificador": identificador,
            "titulo": titulo,
            "descripcion": descripcion,
            "organo": organo,
            "unidad_administrativa": unidad_administrativa,
            "serie_documental": serie_documental,
            "subserie_documental": subserie_documental,
            "tenant_id": tenant_id,
            "proyecto_nombre": proyecto_nombre,
            "ubicacion_obra": ubicacion_obra,
            "monto_contrato": monto_contrato,
            "plazo_dias": plazo_dias,
            "tipo_contrato": tipo_contrato,
            "responsable_tecnico": responsable_tecnico,
            "responsable_ejecutivo": responsable_ejecutivo,
            "responsable_id": responsable_id,
            "estado": EstadoExpediente.INICIADO,
            "metadatos": {
                "fecha_creacion_iso": datetime.now().isoformat(),
                "sistema": "Megalodon v4",
                "version_normativa": "2026",
            },
        }

        return await self.create(data, creado_por_id=creado_por_id, tenant_id=tenant_id)

    async def cambiar_estado(
        self,
        expediente_id: UUID,
        nuevo_estado: EstadoExpediente,
        tenant_id: UUID,
        observacion: Optional[str] = None,
        actualizado_por_id: Optional[UUID] = None,
    ) -> ExpedienteObra:
        """Cambia el estado de un expediente con trazabilidad, validando
        que el expediente pertenezca al tenant del usuario."""
        action = 'approve' if nuevo_estado == EstadoExpediente.CERRADO else 'write'
        await authorize_by_id(self.db, actualizado_por_id, tenant_id, action)
        result = await self.db.execute(
            select(ExpedienteObra)
            .where(ExpedienteObra.id == expediente_id)
            .where(ExpedienteObra.tenant_id == tenant_id)
            .with_for_update().execution_options(populate_existing=True)
        )
        expediente = result.scalar_one_or_none()
        if not expediente:
            raise MegalodonException(
                ErrorCode.DOCUMENTO_NO_ENCONTRADO,
                f"Expediente {expediente_id} no encontrado",
            )

        estado_anterior = expediente.estado

        # Validar transición de estado
        transiciones_validas = self._transiciones_validas(estado_anterior)
        if nuevo_estado not in transiciones_validas:
            raise MegalodonException(
                ErrorCode.NORMATIVO_GENERICO,
                f"Transición de estado inválida: {estado_anterior} -> {nuevo_estado}",
                details={"transiciones_permitidas": [t.value for t in transiciones_validas]},
            )

        # Actualizar
        metadatos = dict(expediente.metadatos or {})
        historial = metadatos.get("historial_estados", [])
        historial.append({
            "estado_anterior": estado_anterior,
            "estado_nuevo": nuevo_estado.value,
            "fecha": datetime.now().isoformat(),
            "observacion": observacion,
            "actor_id": str(actualizado_por_id),
        })
        metadatos["historial_estados"] = historial

        updated = await self.update(
            expediente_id,
            {"estado": nuevo_estado, "metadatos": metadatos},
            actualizado_por_id=actualizado_por_id,
            tenant_id=tenant_id,
        )

        return updated

    def _transiciones_validas(self, estado_actual: EstadoExpediente) -> List[EstadoExpediente]:
        """Define máquina de estados del expediente."""
        maquina = {
            EstadoExpediente.INICIADO: [
                EstadoExpediente.EN_TRAMITE,
                EstadoExpediente.ARCHIVADO,
            ],
            EstadoExpediente.EN_TRAMITE: [
                EstadoExpediente.PENDIENTE_DOCUMENTACION,
                EstadoExpediente.EN_FIRMA,
                EstadoExpediente.EN_INTEROPERABILIDAD,
                EstadoExpediente.ARCHIVADO,
            ],
            EstadoExpediente.PENDIENTE_DOCUMENTACION: [
                EstadoExpediente.EN_TRAMITE,
                EstadoExpediente.ARCHIVADO,
            ],
            EstadoExpediente.EN_FIRMA: [
                EstadoExpediente.CERRADO,
                EstadoExpediente.ARCHIVADO,
            ],
            EstadoExpediente.EN_INTEROPERABILIDAD: [
                EstadoExpediente.CERRADO,
                EstadoExpediente.ARCHIVADO,
            ],
            EstadoExpediente.CERRADO: [EstadoExpediente.ARCHIVADO],
            EstadoExpediente.ARCHIVADO: [],
        }
        return maquina.get(estado_actual, [])

    async def buscar_expedientes(
        self,
        *,
        tenant_id: UUID,
        query: Optional[str] = None,
        estado: Optional[str] = None,
        organo: Optional[str] = None,
        fecha_desde: Optional[datetime] = None,
        fecha_hasta: Optional[datetime] = None,
        skip: int = 0,
        limit: int = 20,
    ) -> tuple[List[ExpedienteObra], int]:
        """Búsqueda full-text de expedientes."""

        base_query = select(ExpedienteObra).where(ExpedienteObra.tenant_id == tenant_id)
        count_query = select(func.count(ExpedienteObra.id)).where(ExpedienteObra.tenant_id == tenant_id)

        if estado:
            base_query = base_query.where(ExpedienteObra.estado == estado)
            count_query = count_query.where(ExpedienteObra.estado == estado)

        if organo:
            base_query = base_query.where(ExpedienteObra.organo.ilike(f"%{organo}%"))
            count_query = count_query.where(ExpedienteObra.organo.ilike(f"%{organo}%"))

        if fecha_desde:
            base_query = base_query.where(ExpedienteObra.created_at >= fecha_desde)
            count_query = count_query.where(ExpedienteObra.created_at >= fecha_desde)

        if fecha_hasta:
            base_query = base_query.where(ExpedienteObra.created_at <= fecha_hasta)
            count_query = count_query.where(ExpedienteObra.created_at <= fecha_hasta)

        if query:
            # Búsqueda con pg_trgm
            from sqlalchemy import text
            base_query = base_query.where(
                text("expedientes_obra.titulo % :query OR expedientes_obra.identificador % :query")
            ).params(query=query)
            count_query = count_query.where(
                text("expedientes_obra.titulo % :query OR expedientes_obra.identificador % :query")
            ).params(query=query)

        base_query = base_query.order_by(ExpedienteObra.created_at.desc())
        base_query = base_query.offset(skip).limit(limit)

        result = await self.db.execute(base_query)
        count_result = await self.db.execute(count_query)

        return result.scalars().all(), count_result.scalar()

    async def calcular_merkle_root(self, expediente_id: UUID, tenant_id: Optional[UUID] = None) -> str:
        """Calcula Merkle root de todos los documentos del expediente."""
        from app.models.expediente import Documento, ExpedienteObra

        query = select(Documento.hash_sha256).where(Documento.expediente_id == expediente_id)
        if tenant_id is not None:
            query = query.join(ExpedienteObra, Documento.expediente_id == ExpedienteObra.id)
            query = query.where(ExpedienteObra.tenant_id == tenant_id)
        query = query.order_by(Documento.created_at)
        result = await self.db.execute(query)
        hashes = [row[0] for row in result.all() if row[0]]

        if not hashes:
            return ""

        merkle_root = calcular_merkle_root(hashes)

        # Guardar en expediente
        await self.update(expediente_id, {"merkle_root": merkle_root}, tenant_id=tenant_id)

        return merkle_root
