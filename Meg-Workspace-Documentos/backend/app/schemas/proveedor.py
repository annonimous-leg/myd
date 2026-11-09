"""Tenant-owned supplier registry; identity is not a compliance attestation."""
from typing import Annotated
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, StringConstraints, field_validator

from app.models.proveedor import TipoPersona


class ProveedorCreate(BaseModel):
    model_config = ConfigDict(extra="forbid")
    tipo_persona: TipoPersona
    rfc: Annotated[str, StringConstraints(pattern=r"^[A-ZÑ&]{3,4}[0-9]{6}[A-Z0-9]{3}$")]
    razon_social: Annotated[str, StringConstraints(strip_whitespace=True, min_length=2, max_length=500)]

    @field_validator("rfc", mode="before")
    @classmethod
    def normalize_rfc(cls, value):
        return value.strip().upper() if isinstance(value, str) else value


class ProveedorOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: UUID
    tipo_persona: TipoPersona
    rfc: str
    razon_social: str
    estado: str


class ProveedorList(BaseModel):
    total: int
    items: list[ProveedorOut]
