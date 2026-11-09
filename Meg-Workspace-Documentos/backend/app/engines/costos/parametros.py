# Copyright © 2026 Cristian Rodriguez
# All rights reserved.

"""Snapshot inmutable y verificable de parámetros económicos de costeo."""
from __future__ import annotations

import hashlib
import json
from collections.abc import Mapping
from dataclasses import dataclass, field
from datetime import date
from decimal import Decimal, InvalidOperation
from enum import StrEnum
from types import MappingProxyType
from typing import Any

FOUR_DECIMALS = Decimal("0.0001")


class FuenteParametrosCosteo(StrEnum):
    CAPTURA_USUARIO = "CAPTURA_USUARIO"
    CONTRATO = "CONTRATO"
    PERFIL_TENANT = "PERFIL_TENANT"
    CONVOCATORIA = "CONVOCATORIA"
    TENDER_SNAPSHOT = "TENDER_SNAPSHOT"


def _decimal(value: Decimal | int | float | str) -> Decimal:
    return value if isinstance(value, Decimal) else Decimal(str(value))


def _freeze_json(value: Any) -> Any:
    if isinstance(value, Mapping):
        if any(not isinstance(key, str) for key in value):
            raise ValueError("las claves de evidencia deben ser texto")
        return MappingProxyType({key: _freeze_json(item) for key, item in value.items()})
    if isinstance(value, (list, tuple)):
        return tuple(_freeze_json(item) for item in value)
    if value is None or isinstance(value, (str, int, float, bool)):
        return value
    raise ValueError("evidencia debe contener exclusivamente valores JSON")


def _thaw_json(value: Any) -> Any:
    if isinstance(value, Mapping):
        return {key: _thaw_json(item) for key, item in value.items()}
    if isinstance(value, tuple):
        return [_thaw_json(item) for item in value]
    return value


@dataclass(frozen=True)
class ParametrosCosteoSnapshot:
    factor_indirecto: Decimal
    factor_utilidad: Decimal
    factor_impuesto: Decimal
    factor_riesgo: Decimal
    fuente: FuenteParametrosCosteo
    referencia: str
    factor_financiamiento: Decimal = Decimal("0")
    factor_cargos_adicionales: Decimal = Decimal("0")
    vigencia: date | None = None
    jurisdiccion: str | None = None
    evidencia: Mapping[str, Any] = field(default_factory=dict)

    def __post_init__(self) -> None:
        for nombre in (
            "factor_indirecto",
            "factor_financiamiento",
            "factor_utilidad",
            "factor_cargos_adicionales",
            "factor_impuesto",
            "factor_riesgo",
        ):
            try:
                valor = _decimal(getattr(self, nombre))
                if not valor.is_finite():
                    raise ValueError
                cuantizado = valor.quantize(FOUR_DECIMALS)
            except (InvalidOperation, ValueError) as exc:
                raise ValueError(f"{nombre} no es un decimal válido") from exc
            if valor < 0 or valor > 1:
                raise ValueError(f"{nombre} debe estar entre 0 y 1")
            if cuantizado != valor:
                raise ValueError(f"{nombre} admite máximo 4 decimales")
            object.__setattr__(self, nombre, cuantizado)
        referencia = self.referencia.strip()
        if not referencia:
            raise ValueError("referencia es obligatoria para parámetros de costeo")
        object.__setattr__(self, "referencia", referencia)
        object.__setattr__(self, "evidencia", _freeze_json(self.evidencia))

    def to_dict(self) -> dict[str, Any]:
        payload: dict[str, Any] = {
            "factor_indirecto": str(self.factor_indirecto),
            "factor_financiamiento": str(self.factor_financiamiento),
            "factor_utilidad": str(self.factor_utilidad),
            "factor_cargos_adicionales": str(self.factor_cargos_adicionales),
            "factor_impuesto": str(self.factor_impuesto),
            "factor_riesgo": str(self.factor_riesgo),
            "fuente": self.fuente.value,
            "referencia": self.referencia,
            "vigencia": self.vigencia.isoformat() if self.vigencia else None,
            "jurisdiccion": self.jurisdiccion,
            "evidencia": _thaw_json(self.evidencia),
        }
        canonical = json.dumps(payload, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
        payload["sha256"] = hashlib.sha256(canonical.encode("utf-8")).hexdigest()
        return payload

    @classmethod
    def from_dict(cls, payload: Mapping[str, Any]) -> ParametrosCosteoSnapshot:
        vigencia = payload.get("vigencia")
        fuente_raw = payload["fuente"]
        fuente = fuente_raw if isinstance(fuente_raw, FuenteParametrosCosteo) else FuenteParametrosCosteo(str(fuente_raw))
        return cls(
            factor_indirecto=_decimal(payload["factor_indirecto"]),
            factor_utilidad=_decimal(payload["factor_utilidad"]),
            factor_impuesto=_decimal(payload["factor_impuesto"]),
            factor_riesgo=_decimal(payload["factor_riesgo"]),
            fuente=fuente,
            referencia=str(payload["referencia"]),
            factor_financiamiento=_decimal(payload.get("factor_financiamiento", "0")),
            factor_cargos_adicionales=_decimal(payload.get("factor_cargos_adicionales", "0")),
            vigencia=date.fromisoformat(str(vigencia)) if vigencia else None,
            jurisdiccion=str(payload["jurisdiccion"]) if payload.get("jurisdiccion") else None,
            evidencia=payload.get("evidencia") or {},
        )


def verificar_snapshot_almacenado(
    payload: Mapping[str, Any] | None,
    factores_persistidos: tuple[Decimal | int | float | str | None, ...],
) -> ParametrosCosteoSnapshot:
    if not payload:
        raise ValueError("falta el snapshot de parámetros de costeo")
    almacenado = dict(payload)
    huella = almacenado.pop("sha256", None)
    canonical = json.dumps(almacenado, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
    if hashlib.sha256(canonical.encode("utf-8")).hexdigest() != huella:
        raise ValueError("la huella del snapshot no coincide")
    parametros = ParametrosCosteoSnapshot.from_dict(payload)
    if len(factores_persistidos) not in (4, 6) or any(value is None for value in factores_persistidos):
        raise ValueError("faltan columnas persistidas de parámetros de costeo")
    try:
        normalizados = tuple(_decimal(value).quantize(FOUR_DECIMALS) for value in factores_persistidos)
    except (InvalidOperation, ValueError) as exc:
        raise ValueError("las columnas de factores contienen valores inválidos") from exc
    if len(normalizados) == 4:
        # Snapshots históricos no almacenaban financiamiento/cargos; ambos
        # quedan en cero y su huella original se conserva verificable.
        esperados = (
            parametros.factor_indirecto,
            parametros.factor_utilidad,
            parametros.factor_impuesto,
            parametros.factor_riesgo,
        )
        if parametros.factor_financiamiento or parametros.factor_cargos_adicionales:
            raise ValueError("el snapshot declara factores que el esquema histórico no podía persistir")
    else:
        esperados = (
            parametros.factor_indirecto,
            parametros.factor_financiamiento,
            parametros.factor_utilidad,
            parametros.factor_cargos_adicionales,
            parametros.factor_impuesto,
            parametros.factor_riesgo,
        )
    if normalizados != esperados:
        raise ValueError("las columnas de factores no coinciden con el snapshot firmado")
    return parametros
