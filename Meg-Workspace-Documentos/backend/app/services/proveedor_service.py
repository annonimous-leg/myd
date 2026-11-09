"""Supplier commands and tenant isolation at the domain boundary."""
from sqlalchemy import func, or_, select
from sqlalchemy.exc import IntegrityError

from app.core.authorization import authorize_by_id
from app.core.errors import ErrorCode, MegalodonException
from app.models.proveedor import Proveedor


class ProveedorService:
    async def listar(self, db, user, *, q=None, skip=0, limit=50):
        query = select(Proveedor).where(Proveedor.tenant_id == user.tenant_id)
        if q:
            query = query.where(or_(Proveedor.rfc.icontains(q, autoescape=True),
                                    Proveedor.razon_social.icontains(q, autoescape=True)))
        total = await db.scalar(select(func.count()).select_from(query.subquery())) or 0
        rows = (await db.scalars(query.order_by(Proveedor.razon_social, Proveedor.id).offset(skip).limit(limit))).all()
        return {"total": total, "items": rows}

    async def crear(self, db, user, data):
        await authorize_by_id(db, user.id, user.tenant_id, "write")
        tenant_id = user.tenant_id
        row = Proveedor(**data.model_dump(), tenant_id=user.tenant_id,
                        creado_por_id=user.id, actualizado_por_id=user.id)
        db.add(row)
        try:
            await db.commit()
        except IntegrityError as exc:
            await db.rollback()
            duplicate = await db.scalar(select(Proveedor.id).where(
                Proveedor.tenant_id == tenant_id, Proveedor.rfc == data.rfc))
            if duplicate:
                raise MegalodonException(ErrorCode.CONFLICT, "Ya existe un proveedor con ese RFC en su organización.", 409) from exc
            raise
        await db.refresh(row)
        return row
