# Copyright © 2026 Cristian Rodriguez
# All rights reserved.
# Unauthorized copying, modification, distribution, or use is prohibited
# without prior written permission.

"""
BaseService - CRUD genérico async para todos los servicios.
"""
from typing import TypeVar, Generic, Type, List, Optional, Any
from uuid import UUID

from sqlalchemy import select, update, delete
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.base import Base

ModelType = TypeVar("ModelType", bound=Base)


class BaseService(Generic[ModelType]):
    """Servicio base con operaciones CRUD async."""

    def __init__(self, model: Type[ModelType], db: AsyncSession, *, tenant_id: Optional[UUID] = None, tenant_required: bool = False):
        self.model = model
        self.db = db
        self.tenant_id = tenant_id
        self.tenant_required = tenant_required
        # A tenant-required service must never silently degrade to a global
        # query just because a future model forgot TenantMixin. Fail at
        # construction time, before any read/write can occur.
        if self.tenant_required and not self._has_tenant_id():
            raise TypeError(
                f"{self.model.__name__} requiere tenant_id porque el servicio "
                "está configurado con tenant_required=True"
            )

    def _effective_tenant(self, tenant_id: Optional[UUID]) -> Optional[UUID]:
        effective = tenant_id if tenant_id is not None else self.tenant_id
        if self.tenant_required and effective is None:
            raise ValueError(f"{self.model.__name__} requiere tenant_id en el contexto de servicio")
        return effective

    def _has_tenant_id(self) -> bool:
        return hasattr(self.model, "tenant_id")

    def _apply_tenant_filter(self, query, tenant_id: Optional[UUID]):
        if tenant_id is not None and self._has_tenant_id():
            return query.where(self.model.tenant_id == tenant_id)
        return query

    async def get(self, id: UUID, tenant_id: Optional[UUID] = None) -> Optional[ModelType]:
        """Obtiene una entidad por ID, opcionalmente restringida al tenant."""
        query = select(self.model).where(self.model.id == id)
        query = self._apply_tenant_filter(query, self._effective_tenant(tenant_id))
        result = await self.db.execute(query)
        return result.scalar_one_or_none()

    async def get_multi(
        self,
        *,
        skip: int = 0,
        limit: int = 100,
        tenant_id: Optional[UUID] = None,
        filters: Optional[dict] = None,
    ) -> List[ModelType]:
        """Lista entidades con paginación y filtros."""
        query = select(self.model)

        tenant_id = self._effective_tenant(tenant_id)
        if tenant_id is not None and self._has_tenant_id():
            query = query.where(self.model.tenant_id == tenant_id)

        if filters:
            for key, value in filters.items():
                if hasattr(self.model, key) and value is not None:
                    query = query.where(getattr(self.model, key) == value)

        query = query.offset(skip).limit(limit)
        result = await self.db.execute(query)
        return result.scalars().all()

    async def create(
        self,
        obj_in: dict,
        *,
        creado_por_id: Optional[UUID] = None,
        tenant_id: Optional[UUID] = None,
    ) -> ModelType:
        """Crea una nueva entidad.

        Si el modelo tiene TenantMixin, el tenant se puede fijar de forma
        explícita con tenant_id o venir ya embebido en obj_in. Si ambos se
        dan, deben coincidir.
        """
        if "created_by" in obj_in and "creado_por_id" not in obj_in:
            obj_in = {**obj_in, "creado_por_id": obj_in.pop("created_by")}
        if "updated_by" in obj_in and "actualizado_por_id" not in obj_in:
            obj_in = {**obj_in, "actualizado_por_id": obj_in.pop("updated_by")}
        if creado_por_id is not None and hasattr(self.model, "creado_por_id"):
            obj_in = {**obj_in, "creado_por_id": creado_por_id, "actualizado_por_id": creado_por_id}
        tenant_id = self._effective_tenant(tenant_id)
        if tenant_id is not None and self._has_tenant_id():
            if "tenant_id" in obj_in and obj_in["tenant_id"] is not None and str(obj_in["tenant_id"]) != str(tenant_id):
                raise ValueError("tenant_id inconsistente entre el payload y el contexto")
            obj_in = {**obj_in, "tenant_id": tenant_id}
        db_obj = self.model(**obj_in)
        self.db.add(db_obj)
        await self.db.commit()
        await self.db.refresh(db_obj)
        return db_obj

    async def update(
        self,
        id: UUID,
        obj_in: dict,
        *,
        actualizado_por_id: Optional[UUID] = None,
        tenant_id: Optional[UUID] = None,
    ) -> Optional[ModelType]:
        """Actualiza una entidad existente."""
        if "updated_by" in obj_in and "actualizado_por_id" not in obj_in:
            obj_in = {**obj_in, "actualizado_por_id": obj_in.pop("updated_by")}
        if actualizado_por_id is not None and hasattr(self.model, "actualizado_por_id"):
            obj_in = {**obj_in, "actualizado_por_id": actualizado_por_id}

        query = update(self.model).where(self.model.id == id)
        query = self._apply_tenant_filter(query, self._effective_tenant(tenant_id))
        result = await self.db.execute(query.values(**obj_in))
        await self.db.commit()
        return await self.get(id, tenant_id=self._effective_tenant(tenant_id)) if result.rowcount else None

    async def delete(self, id: UUID, tenant_id: Optional[UUID] = None) -> bool:
        """Elimina una entidad."""
        query = delete(self.model).where(self.model.id == id)
        query = self._apply_tenant_filter(query, self._effective_tenant(tenant_id))
        result = await self.db.execute(query)
        await self.db.commit()
        return result.rowcount > 0

    async def count(self, tenant_id: Optional[UUID] = None) -> int:
        """Cuenta entidades."""
        from sqlalchemy import func
        query = select(func.count(self.model.id))
        tenant_id = self._effective_tenant(tenant_id)
        if tenant_id is not None and self._has_tenant_id():
            query = query.where(self.model.tenant_id == tenant_id)
        result = await self.db.execute(query)
        return int(result.scalar() or 0)
