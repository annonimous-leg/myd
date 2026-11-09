# Copyright © 2026 Cristian Rodriguez
# All rights reserved.
"""Servicio de catálogo de Análisis de Precios Unitarios (APU)."""
from typing import Optional, List
from uuid import UUID
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, func, and_, or_
from app.models.catalogo_apu import CatalogoAPU, PrecioUnitarioAsignado
from app.models.user import User
from app.schemas.catalogo_apu import CatalogoAPUCreate, CatalogoAPUOut, CatalogoAPUList
from app.core.authorization import authorize_by_id
from app.core.errors import MegalodonException, ErrorCode

class CatalogoAPUService:
    async def crear(self, db: AsyncSession, data: CatalogoAPUCreate, current_user: User) -> CatalogoAPU:
        await authorize_by_id(db, current_user.id, current_user.tenant_id, 'write')
        stmt = select(CatalogoAPU).where(and_(
            CatalogoAPU.clave == data.clave,
            CatalogoAPU.fuente == data.fuente,
            CatalogoAPU.zona_economica == data.zona_economica,
            CatalogoAPU.tenant_id == current_user.tenant_id,
        ))
        if (await db.execute(stmt)).scalar_one_or_none():
            raise MegalodonException(ErrorCode.CONFLICT,
                f"Concepto APU '{data.clave}'+fuente+'{data.zona_economica}' ya existe.")
        concepto = CatalogoAPU(
            clave=data.clave, descripcion=data.descripcion, tipo=data.tipo.value,
            unidad=data.unidad.value, precio_unitario=data.precio_unitario,
            fuente=data.fuente, zona_economica=data.zona_economica,
            estado=data.estado, incluye_iva=data.incluye_iva, desglose=data.desglose,
            tenant_id=current_user.tenant_id, creado_por_id=current_user.id,
        )
        db.add(concepto); await db.commit(); await db.refresh(concepto)
        return concepto

    async def listar(self, db: AsyncSession, current_user: User, skip=0, limit=100,
                     fuente=None, zona=None, tipo=None, q=None) -> CatalogoAPUList:
        query = select(CatalogoAPU).where(CatalogoAPU.tenant_id == current_user.tenant_id)
        if fuente: query = query.where(CatalogoAPU.fuente.ilike(f"%{fuente}%"))
        if zona: query = query.where(CatalogoAPU.zona_economica.ilike(f"%{zona}%"))
        if tipo: query = query.where(CatalogoAPU.tipo == tipo)
        if q:
            search = f"%{q}%"
            query = query.where(or_(
                CatalogoAPU.clave.ilike(search),
                CatalogoAPU.descripcion.ilike(search),
                CatalogoAPU.fuente.ilike(search),
            ))
        total = await db.scalar(select(func.count()).select_from(query.subquery())) or 0
        query = query.offset(skip).limit(limit).order_by(CatalogoAPU.clave)
        items = (await db.execute(query)).scalars().all()
        return CatalogoAPUList(total=total, items=items)

    async def obtener(self, db: AsyncSession, concepto_id: UUID, current_user: User) -> CatalogoAPU:
        stmt = select(CatalogoAPU).where(and_(
            CatalogoAPU.id == concepto_id, CatalogoAPU.tenant_id == current_user.tenant_id))
        c = (await db.execute(stmt)).scalar_one_or_none()
        if not c: raise MegalodonException(ErrorCode.NOT_FOUND, f"Concepto '{concepto_id}' no encontrado.")
        return c

    async def actualizar(self, db: AsyncSession, concepto_id: UUID, data: CatalogoAPUCreate, current_user: User) -> CatalogoAPU:
        await authorize_by_id(db, current_user.id, current_user.tenant_id, 'write')
        c = await self.obtener(db, concepto_id, current_user)
        if c.registro_importado_id:
            raise MegalodonException(ErrorCode.CONFLICT, "La edición importada es inmutable; importe una nueva versión con su evidencia", status_code=409)
        c.descripcion=data.descripcion; c.tipo=data.tipo.value; c.unidad=data.unidad.value
        c.precio_unitario=data.precio_unitario; c.fuente=data.fuente
        c.zona_economica=data.zona_economica; c.estado=data.estado
        c.incluye_iva=data.incluye_iva; c.desglose=data.desglose; c.actualizado_por_id=current_user.id
        await db.commit(); await db.refresh(c); return c

    async def eliminar(self, db: AsyncSession, concepto_id: UUID, current_user: User) -> None:
        await authorize_by_id(db, current_user.id, current_user.tenant_id, 'write')
        c = await self.obtener(db, concepto_id, current_user)
        if c.registro_importado_id:
            raise MegalodonException(ErrorCode.CONFLICT, "La edición importada conserva la trazabilidad de los presupuestos", status_code=409)
        await db.delete(c); await db.commit()

    async def obtener_precio_con_iva(self, db: AsyncSession, concepto_id: UUID,
                                     tasa_iva=0.16, current_user=None) -> dict:
        c = await self.obtener(db, concepto_id, current_user)
        base = float(c.precio_unitario)
        if c.incluye_iva:
            sin_iva = base / (1 + tasa_iva); con_iva = base
        else:
            sin_iva = base; con_iva = base * (1 + tasa_iva)
        return {
            "concepto_id": str(c.id), "clave": c.clave, "descripcion": c.descripcion,
            "precio_base": round(base,4), "precio_sin_iva": round(sin_iva,4),
            "precio_con_iva": round(con_iva,4), "tasa_iva_aplicada": tasa_iva,
            "incluye_iva_original": c.incluye_iva, "fuente": c.fuente,
        }
