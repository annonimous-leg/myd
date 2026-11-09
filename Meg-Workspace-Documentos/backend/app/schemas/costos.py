# Copyright © 2026 Cristian Rodriguez
# All rights reserved.

"""Contratos HTTP para parámetros económicos explícitos y trazables."""
from datetime import date
from decimal import Decimal
from typing import Any

from pydantic import BaseModel, Field, field_validator

from app.engines.costos.parametros import FuenteParametrosCosteo, ParametrosCosteoSnapshot


class ParametrosCosteoInput(BaseModel):
    factor_indirecto: Decimal = Field(..., ge=0, le=1, decimal_places=4)
    factor_financiamiento: Decimal = Field(Decimal("0"), ge=0, le=1, decimal_places=4)
    factor_utilidad: Decimal = Field(..., ge=0, le=1, decimal_places=4)
    factor_cargos_adicionales: Decimal = Field(Decimal("0"), ge=0, le=1, decimal_places=4)
    factor_impuesto: Decimal = Field(..., ge=0, le=1, decimal_places=4)
    factor_riesgo: Decimal = Field(..., ge=0, le=1, decimal_places=4)
    fuente: FuenteParametrosCosteo
    referencia: str = Field(..., min_length=1, max_length=500)
    vigencia: date | None = None
    jurisdiccion: str | None = Field(None, max_length=100)
    evidencia: dict[str, Any] = Field(default_factory=dict)

    @field_validator("referencia")
    @classmethod
    def validar_referencia(cls, value: str) -> str:
        value = value.strip()
        if not value:
            raise ValueError("referencia no puede estar vacía")
        return value

    def to_domain(self) -> ParametrosCosteoSnapshot:
        return ParametrosCosteoSnapshot.from_dict(self.model_dump())

