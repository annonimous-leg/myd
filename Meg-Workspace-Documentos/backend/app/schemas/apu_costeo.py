"""Validated quantities and prices at the APU input seam."""
from decimal import Decimal

from pydantic import BaseModel, ConfigDict, Field, model_validator

from app.schemas.indices_costos import ActualizacionPrecioInput


class InsumoCosteoInput(BaseModel):
    model_config = ConfigDict(extra='forbid', str_strip_whitespace=True)
    clave: str = Field('', max_length=50)
    descripcion: str = ''
    tipo: str = Field('MATERIAL', max_length=50)
    unidad: str = Field('', max_length=20)
    cantidad: Decimal = Field(gt=0, max_digits=20, decimal_places=6, allow_inf_nan=False)
    precio_unitario: Decimal | None = Field(None, ge=0, max_digits=18, decimal_places=2, allow_inf_nan=False)
    rendimiento: Decimal = Field(Decimal('1'), gt=0, max_digits=8, decimal_places=4, allow_inf_nan=False)
    actualizacion_precio: ActualizacionPrecioInput | None = None

    @model_validator(mode='after')
    def requiere_precio(self):
        if self.precio_unitario is None and self.actualizacion_precio is None:
            raise ValueError('El insumo requiere precio o una referencia de actualización')
        return self


class ConceptoCosteoInput(BaseModel):
    model_config = ConfigDict(extra='forbid')
    clave: str = Field('', max_length=50)
    descripcion: str = ''
    unidad: str = Field('', max_length=20)
    cantidad: Decimal = Field(Decimal('1'), gt=0, max_digits=18, decimal_places=4, allow_inf_nan=False)
    insumos: list[InsumoCosteoInput] = Field(min_length=1)
