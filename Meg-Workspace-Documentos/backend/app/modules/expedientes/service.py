# Copyright © 2026 Cristian Rodriguez
# All rights reserved.
# Unauthorized copying, modification, distribution, or use is prohibited
# without prior written permission.

"""
ExpedienteModuleService - Servicio de gestión de expedientes.
Relacionador, timeline, resumen ejecutivo y control de estados.
"""
from typing import List, Optional, Dict, Any
from uuid import UUID
from datetime import datetime

from sqlalchemy import select, and_, desc, func, or_
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.expediente import ExpedienteObra, EstadoExpediente
from app.models.documento import DocumentoCDE
from app.models.presupuesto import Presupuesto
from app.models.programacion import ProgramaObra
from app.models.bim import ModeloBIM
from app.models.contrato import Contrato
from app.models.licitacion import Licitacion
from app.models.compliance import Inconformidad, Sancion
from app.models.topografia import Levantamiento
from app.models.workflow import TareaWorkflow
from app.services.expediente_service import ExpedienteService
from app.services.base import BaseService
from app.core.errors import MegalodonException, ErrorCode


class ExpedienteModuleService:
    """Servicio de gestión avanzada de expedientes.

    Relaciona todos los artefactos de un expediente y provee
    vistas consolidadas para reporting y control.
    """

    def __init__(self, db: AsyncSession, tenant_id: Optional[UUID] = None):
        self.db = db
        self.base_service = ExpedienteService(db, tenant_id) if tenant_id is not None else None

    async def obtener_resumen_completo(
        self,
        expediente_id: UUID,
        *,
        tenant_id: UUID,
    ) -> Dict[str, Any]:
        """Obtiene un resumen completo de un expediente con todos sus artefactos relacionados."""
        expediente = await self.base_service.get(expediente_id, tenant_id=tenant_id)
        if not expediente:
            raise MegalodonException(
                ErrorCode.DOCUMENTO_NO_ENCONTRADO,
                f"Expediente {expediente_id} no encontrado",
            )

        # Cargar artefactos relacionados
        documentos_result = await self.db.execute(
            select(func.count(DocumentoCDE.id)).where(DocumentoCDE.expediente_id == expediente_id)
        )
        num_documentos = documentos_result.scalar()

        presupuestos_result = await self.db.execute(
            select(Presupuesto).join(ExpedienteObra, Presupuesto.expediente_id == ExpedienteObra.id).where(Presupuesto.expediente_id == expediente_id, ExpedienteObra.tenant_id == tenant_id)
        )
        presupuestos = presupuestos_result.scalars().all()

        programas_result = await self.db.execute(
            select(ProgramaObra).join(ExpedienteObra, ProgramaObra.expediente_id == ExpedienteObra.id).where(ProgramaObra.expediente_id == expediente_id, ExpedienteObra.tenant_id == tenant_id)
        )
        programas = programas_result.scalars().all()

        modelos_result = await self.db.execute(
            select(ModeloBIM).join(ExpedienteObra, ModeloBIM.expediente_id == ExpedienteObra.id).where(ModeloBIM.expediente_id == expediente_id, ExpedienteObra.tenant_id == tenant_id)
        )
        modelos_bim = modelos_result.scalars().all()

        contratos_result = await self.db.execute(
            select(Contrato).join(ExpedienteObra, Contrato.expediente_id == ExpedienteObra.id).where(Contrato.expediente_id == expediente_id, ExpedienteObra.tenant_id == tenant_id)
        )
        contratos = contratos_result.scalars().all()

        licitaciones_result = await self.db.execute(
            select(Licitacion).join(ExpedienteObra, Licitacion.expediente_id == ExpedienteObra.id).where(Licitacion.expediente_id == expediente_id, ExpedienteObra.tenant_id == tenant_id)
        )
        licitaciones = licitaciones_result.scalars().all()

        inconformidades_result = await self.db.execute(
            select(func.count(Inconformidad.id)).where(Inconformidad.expediente_id == expediente_id)
        )
        num_inconformidades = inconformidades_result.scalar()

        sanciones_result = await self.db.execute(
            select(func.count(Sancion.id)).where(Sancion.expediente_id == expediente_id)
        )
        num_sanciones = sanciones_result.scalar()

        levantamientos_result = await self.db.execute(
            select(Levantamiento).join(ExpedienteObra, Levantamiento.expediente_id == ExpedienteObra.id).where(Levantamiento.expediente_id == expediente_id, ExpedienteObra.tenant_id == tenant_id)
        )
        levantamientos = levantamientos_result.scalars().all()

        return {
            "expediente": {
                "id": str(expediente.id),
                "identificador": expediente.identificador,
                "titulo": expediente.titulo,
                "estado": expediente.estado.value if hasattr(expediente.estado, 'value') else str(expediente.estado),
                "monto_contrato": expediente.monto_contrato,
                "plazo_dias": expediente.plazo_dias,
                "created_at": expediente.created_at.isoformat() if expediente.created_at else None,
            },
            "artefactos": {
                "documentos": num_documentos,
                "presupuestos": [
                    {"id": str(p.id), "identificador": p.identificador, "estado": p.estado.value if hasattr(p.estado, 'value') else str(p.estado)}
                    for p in presupuestos
                ],
                "programas": [
                    {"id": str(p.id), "nombre": p.nombre, "avance_fisico": p.avance_fisico}
                    for p in programas
                ],
                "modelos_bim": [
                    {"id": str(m.id), "nombre": m.nombre, "estado": m.estado_procesamiento}
                    for m in modelos_bim
                ],
                "contratos": [
                    {"id": str(c.id), "numero": c.numero_contrato, "estado": c.estado.value if hasattr(c.estado, 'value') else str(c.estado)}
                    for c in contratos
                ],
                "licitaciones": [
                    {"id": str(l.id), "numero": l.numero_licitacion, "estado": l.estado}
                    for l in licitaciones
                ],
                "inconformidades": num_inconformidades,
                "sanciones": num_sanciones,
                "levantamientos": [
                    {"id": str(l.id), "tipo": l.tipo, "fecha": l.fecha_levantamiento.isoformat() if l.fecha_levantamiento else None}
                    for l in levantamientos
                ],
            },
            "completeness": self._calcular_completeness(
                num_documentos, len(presupuestos), len(programas),
                len(modelos_bim), len(contratos), len(licitaciones)
            ),
        }

    def _calcular_completeness(
        self,
        num_docs: int,
        num_presupuestos: int,
        num_programas: int,
        num_bim: int,
        num_contratos: int,
        num_licitaciones: int,
    ) -> Dict[str, Any]:
        """Calcula el porcentaje de completitud del expediente."""
        requisitos = {
            "documentos": (num_docs > 0, 15),
            "presupuesto": (num_presupuestos > 0, 20),
            "programa": (num_programas > 0, 15),
            "bim": (num_bim > 0, 15),
            "contrato": (num_contratos > 0, 20),
            "licitacion": (num_licitaciones > 0, 15),
        }

        puntos = sum(peso for cumple, peso in requisitos.values() if cumple)

        return {
            "porcentaje": puntos,
            "requisitos": {
                k: {"cumple": v[0], "peso": v[1]}
                for k, v in requisitos.items()
            },
            "estado": "COMPLETO" if puntos >= 90 else "INCOMPLETO" if puntos < 50 else "PARCIAL",
        }

    async def obtener_timeline(
        self,
        expediente_id: UUID,
        *,
        skip: int = 0,
        limit: int = 100,
    ) -> List[Dict[str, Any]]:
        """Obtiene la línea de tiempo de un expediente ordenada cronológicamente.

        Combina: cambios de estado, documentos, presupuestos, programas, etc.
        """
        from app.models.audit_ledger import AuditLedger

        result = await self.db.execute(
            select(AuditLedger)
            .where(
                and_(
                    AuditLedger.entidad_id == str(expediente_id),
                    AuditLedger.entidad_tipo.in_([
                        "EXPEDIENTE", "DOCUMENTO", "PRESUPUESTO", 
                        "PROGRAMA", "CONTRATO", "LICITACION", "BIM"
                    ])
                )
            )
            .order_by(desc(AuditLedger.created_at))
            .offset(skip)
            .limit(limit)
        )
        eventos = result.scalars().all()

        timeline = []
        for e in eventos:
            timeline.append({
                "id": str(e.id),
                "fecha": e.created_at.isoformat() if e.created_at else None,
                "tipo": e.entidad_tipo,
                "accion": e.accion.value if hasattr(e.accion, 'value') else str(e.accion),
                "descripcion": e.descripcion,
                "usuario": e.user_email,
                "datos": e.datos_nuevos,
            })

        return timeline

    async def buscar_expedientes(
        self,
        *,
        query: Optional[str] = None,
        estado: Optional[EstadoExpediente] = None,
        tipo_contrato: Optional[str] = None,
        fecha_inicio: Optional[datetime] = None,
        fecha_fin: Optional[datetime] = None,
        monto_min: Optional[float] = None,
        monto_max: Optional[float] = None,
        tenant_id: Optional[UUID] = None,
        skip: int = 0,
        limit: int = 100,
    ) -> Dict[str, Any]:
        """Búsqueda avanzada de expedientes con múltiples filtros."""
        sql_query = select(ExpedienteObra)
        filters = []

        if query:
            filters.append(
                or_(
                    ExpedienteObra.titulo.ilike(f"%{query}%"),
                    ExpedienteObra.identificador.ilike(f"%{query}%"),
                    ExpedienteObra.descripcion.ilike(f"%{query}%"),
                )
            )

        if estado:
            filters.append(ExpedienteObra.estado == estado)

        if tipo_contrato:
            filters.append(ExpedienteObra.tipo_contrato == tipo_contrato)

        if fecha_inicio:
            filters.append(ExpedienteObra.created_at >= fecha_inicio)

        if fecha_fin:
            filters.append(ExpedienteObra.created_at <= fecha_fin)

        if monto_min is not None:
            filters.append(ExpedienteObra.monto_contrato >= monto_min)

        if monto_max is not None:
            filters.append(ExpedienteObra.monto_contrato <= monto_max)

        if tenant_id:
            filters.append(ExpedienteObra.tenant_id == tenant_id)

        if filters:
            sql_query = sql_query.where(and_(*filters))

        # Count
        count_result = await self.db.execute(
            select(func.count(ExpedienteObra.id)).where(and_(*filters) if filters else True)
        )
        total = count_result.scalar()

        sql_query = sql_query.order_by(desc(ExpedienteObra.created_at)).offset(skip).limit(limit)
        result = await self.db.execute(sql_query)
        expedientes = result.scalars().all()

        return {
            "total": total,
            "skip": skip,
            "limit": limit,
            "resultados": [
                {
                    "id": str(e.id),
                    "identificador": e.identificador,
                    "titulo": e.titulo,
                    "estado": e.estado.value if hasattr(e.estado, 'value') else str(e.estado),
                    "monto_contrato": e.monto_contrato,
                    "plazo_dias": e.plazo_dias,
                    "created_at": e.created_at.isoformat() if e.created_at else None,
                }
                for e in expedientes
            ],
        }

    async def cambiar_estado_expediente(
        self,
        expediente_id: UUID,
        nuevo_estado: EstadoExpediente,
        *,
        motivo: Optional[str] = None,
        actualizado_por_id: Optional[UUID] = None,
    ) -> ExpedienteObra:
        """Use the same transactional command as the standard HTTP adapter."""
        if self.base_service is None:
            raise MegalodonException(ErrorCode.PERMISO_DENEGADO, 'Organización requerida', status_code=403)
        return await self.base_service.cambiar_estado(
            expediente_id, nuevo_estado, self.base_service.tenant_id,
            observacion=motivo, actualizado_por_id=actualizado_por_id,
        )
