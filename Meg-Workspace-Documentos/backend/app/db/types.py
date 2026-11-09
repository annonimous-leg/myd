# Copyright © 2026 Cristian Rodriguez
# All rights reserved.

"""Tipos ORM portables para SQLite y PostgreSQL.

La base de tests usa SQLite, pero la producción usa PostgreSQL.
Este módulo expone alias estables para que los modelos no dependan
直接 de `sqlalchemy.dialects.postgresql` y sigan compilando en ambos
entornos sin stubs ni mocks.
"""
from __future__ import annotations

from sqlalchemy import JSON, Uuid
from sqlalchemy.dialects.postgresql import UUID as PGUUID

from app.config import settings

DATABASE_IS_POSTGRESQL = settings.database_async_url.startswith(("postgresql://", "postgresql+"))

# UUID: el mismo contrato de columna, distinto backend físico.
UUID = PGUUID if DATABASE_IS_POSTGRESQL else Uuid

# JSONB: en SQLite no existe JSONB; usamos JSON nativo con la misma
# semántica de serialización para listas/dicts del dominio.
JSONB = JSON if not DATABASE_IS_POSTGRESQL else __import__("sqlalchemy.dialects.postgresql", fromlist=["JSONB"]).JSONB

