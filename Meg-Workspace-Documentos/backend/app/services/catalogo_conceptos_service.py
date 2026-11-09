# Copyright © 2026 Cristian Rodriguez
"""Servicio de catálogos de conceptos reales (CFE, CMIC, CONAGA, SCT, PEMEX, CUSTOM)."""
from typing import Optional, List
from decimal import Decimal
from uuid import UUID
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, func, and_, or_
from app.models.catalogo_conceptos import CatalogoFuente, ConceptoCatalogo, InsumoCatalogo
from app.models.user import User
from app.schemas.catalogo_conceptos import (
    CatalogoFuenteCreate, ConceptoCatalogoCreate, ConceptoCatalogoOut,
    ConceptoCatalogoList, InsumoCatalogoCreate, InsumoCatalogoOut,
)
from app.core.errors import MegalodonException, ErrorCode

class CatalogoConceptosService:
    # ─── FUENTES ───
    async def crear_fuente(self, db: AsyncSession, data: CatalogoFuenteCreate, current_user: User) -> CatalogoFuente:
        stmt = select(CatalogoFuente).where(and_(
            CatalogoFuente.nombre == data.nombre,
            CatalogoFuente.tipo == data.tipo.value,
        ))
        if (await db.execute(stmt)).scalar_one_or_none():
            raise MegalodonException(ErrorCode.CONFLICT, f"Fuente '{data.nombre}' ya existe.")
        f = CatalogoFuente(nombre=data.nombre, tipo=data.tipo.value,
            vigencia_inicio=data.vigencia_inicio, vigencia_fin=data.vigencia_fin,
            descripcion=data.descripcion, url_fuente=data.url_fuente, moneda=data.moneda, creado_por_id=current_user.id)
        db.add(f); await db.commit(); await db.refresh(f); return f

    async def listar_fuentes(self, db: AsyncSession, activo=None) -> List[CatalogoFuente]:
        q = select(CatalogoFuente)
        if activo is not None: q = q.where(CatalogoFuente.activo == activo)
        return (await db.execute(q.order_by(CatalogoFuente.nombre))).scalars().all()

    async def obtener_fuente(self, db: AsyncSession, fuente_id: UUID) -> CatalogoFuente:
        f = (await db.execute(select(CatalogoFuente).where(CatalogoFuente.id == fuente_id))).scalar_one_or_none()
        if not f: raise MegalodonException(ErrorCode.NOT_FOUND, f"Fuente '{fuente_id}' no encontrada.")
        return f

    # ─── CONCEPTOS ───
    async def crear_concepto(self, db: AsyncSession, data: ConceptoCatalogoCreate, current_user: User) -> ConceptoCatalogo:
        await self.obtener_fuente(db, data.fuente_id)
        stmt = select(ConceptoCatalogo).where(and_(
            ConceptoCatalogo.clave == data.clave,
            ConceptoCatalogo.fuente_id == data.fuente_id,
            ConceptoCatalogo.zona_economica == data.zona_economica,
        ))
        if (await db.execute(stmt)).scalar_one_or_none():
            raise MegalodonException(ErrorCode.CONFLICT, f"Concepto '{data.clave}' ya existe.")
        c = ConceptoCatalogo(
            fuente_id=data.fuente_id, clave=data.clave, descripcion=data.descripcion,
            descripcion_larga=data.descripcion_larga, unidad=data.unidad,
            precio_unitario=data.precio_unitario, zona_economica=data.zona_economica,
            estado=data.estado, region=data.region, incluye_iva=data.incluye_iva,
            desglose=data.desglose, creado_por_id=current_user.id)
        db.add(c); await db.commit(); await db.refresh(c); return c

    async def actualizar_concepto(self, db, concepto_id, data, current_user):
        c = await self.obtener_concepto(db, concepto_id)
        await self.obtener_fuente(db, data.fuente_id)
        duplicate = await db.scalar(select(ConceptoCatalogo.id).where(
            ConceptoCatalogo.id != concepto_id,
            ConceptoCatalogo.fuente_id == data.fuente_id,
            ConceptoCatalogo.clave == data.clave,
            ConceptoCatalogo.zona_economica == data.zona_economica,
        ))
        if duplicate:
            raise MegalodonException(ErrorCode.CONFLICT, "Concepto duplicado en la fuente y zona")
        for key, value in data.model_dump().items():
            setattr(c, key, value)
        c.actualizado_por_id = current_user.id
        await db.commit()
        await db.refresh(c)
        return c

    async def listar_conceptos(self, db: AsyncSession, skip=0, limit=100,
                               fuente_id=None, zona=None, estado=None, q=None) -> ConceptoCatalogoList:
        query = select(ConceptoCatalogo).where(ConceptoCatalogo.activo == True)
        if fuente_id: query = query.where(ConceptoCatalogo.fuente_id == fuente_id)
        if zona: query = query.where(ConceptoCatalogo.zona_economica.ilike(f"%{zona}%"))
        if estado: query = query.where(ConceptoCatalogo.estado.ilike(f"%{estado}%"))
        if q:
            search = f"%{q}%"
            query = query.where(or_(
                ConceptoCatalogo.clave.ilike(search),
                ConceptoCatalogo.descripcion.ilike(search),
                ConceptoCatalogo.descripcion_larga.ilike(search),
            ))
        total = await db.scalar(select(func.count()).select_from(query.subquery())) or 0
        items = (await db.execute(query.offset(skip).limit(limit).order_by(ConceptoCatalogo.clave))).scalars().all()
        return ConceptoCatalogoList(total=total, items=items)

    async def obtener_concepto(self, db: AsyncSession, concepto_id: UUID) -> ConceptoCatalogo:
        c = (await db.execute(select(ConceptoCatalogo).where(ConceptoCatalogo.id == concepto_id))).scalar_one_or_none()
        if not c: raise MegalodonException(ErrorCode.NOT_FOUND, f"Concepto '{concepto_id}' no encontrado.")
        return c

    # ─── INSUMOS ───
    async def crear_insumo(self, db: AsyncSession, data: InsumoCatalogoCreate, current_user: User) -> InsumoCatalogo:
        await self.obtener_fuente(db, data.fuente_id)
        stmt = select(InsumoCatalogo).where(and_(
            InsumoCatalogo.clave == data.clave,
            InsumoCatalogo.fuente_id == data.fuente_id,
            InsumoCatalogo.zona_economica == data.zona_economica,
            InsumoCatalogo.tipo == data.tipo,
        ))
        if (await db.execute(stmt)).scalar_one_or_none():
            raise MegalodonException(ErrorCode.CONFLICT, f"Insumo '{data.clave}' ya existe.")
        i = InsumoCatalogo(
            fuente_id=data.fuente_id, clave=data.clave, descripcion=data.descripcion,
            tipo=data.tipo, unidad=data.unidad, precio_unitario=data.precio_unitario,
            categoria=data.categoria, subcategoria=data.subcategoria,
            zona_economica=data.zona_economica, estado=data.estado,
            incluye_iva=data.incluye_iva, creado_por_id=current_user.id)
        db.add(i); await db.commit(); await db.refresh(i); return i

    async def listar_insumos(self, db: AsyncSession, skip=0, limit=100,
                             fuente_id=None, tipo=None, categoria=None) -> List[InsumoCatalogo]:
        q = select(InsumoCatalogo).where(InsumoCatalogo.activo == True)
        if fuente_id: q = q.where(InsumoCatalogo.fuente_id == fuente_id)
        if tipo: q = q.where(InsumoCatalogo.tipo == tipo)
        if categoria: q = q.where(InsumoCatalogo.categoria.ilike(f"%{categoria}%"))
        return (await db.execute(q.offset(skip).limit(limit).order_by(InsumoCatalogo.clave))).scalars().all()

    async def calcular_costo_desglosado(self, db: AsyncSession, concepto_id: UUID,
                                        cantidad=1.0, tasa_iva=0.16) -> dict:
        c = await self.obtener_concepto(db, concepto_id)
        cantidad, tasa_iva = Decimal(str(cantidad)), Decimal(str(tasa_iva))
        if (not cantidad.is_finite() or cantidad <= 0 or not tasa_iva.is_finite()
                or not 0 <= tasa_iva <= 1):
            raise MegalodonException(ErrorCode.BAD_REQUEST, "Cantidad o impuesto inválido")
        if not c.activo or c.unidad.strip().lower() in {"%", "iva"}:
            raise MegalodonException(ErrorCode.BAD_REQUEST, "Concepto inactivo o porcentual")
        d = c.desglose or {}
        def subtotal(group):
            return sum((Decimal(str(m.get("cantidad", 0))) * Decimal(str(m.get("precio", 0)))
                        for m in d.get(group, [])), Decimal(0))
        mats, mo, maq, ind = (subtotal(group) for group in
                              ("materiales", "mano_obra", "maquinaria", "indirectos"))
        tiene_desglose = any(d.get(group) for group in
                            ("materiales", "mano_obra", "maquinaria", "indirectos"))
        sub = mats + mo + maq + ind if tiene_desglose else Decimal(str(c.precio_unitario))
        if c.incluye_iva:
            sin_iva = sub/(1+tasa_iva); iva = sub - sin_iva; total = sub
        else:
            iva = sub*tasa_iva; total = sub+iva; sin_iva = sub
        return {
            "concepto_id": str(c.id), "clave": c.clave, "descripcion": c.descripcion,
            "cantidad": cantidad, "origen_calculo": "DESGLOSE" if tiene_desglose else "PRECIO_CATALOGO",
            "desglose": {
                "materiales":{"items":len(d.get("materiales",[])),"subtotal":round(mats,4)},
                "mano_obra":{"items":len(d.get("mano_obra",[])),"subtotal":round(mo,4)},
                "maquinaria":{"items":len(d.get("maquinaria",[])),"subtotal":round(maq,4)},
                "indirectos":{"items":len(d.get("indirectos",[])),"subtotal":round(ind,4)},
            },
            "subtotal": round(sub*cantidad,4), "total_sin_iva": round(sin_iva*cantidad,4),
            "iva": round(iva*cantidad,4), "total": round(total*cantidad,4),
            "tasa_iva_aplicada": tasa_iva, "unidad": c.unidad,
        }
