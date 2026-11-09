from __future__ import annotations

from dataclasses import dataclass
from typing import Any


class ContractPolicyError(ValueError):
    """Raised when the economic model violates the selected contract basis."""


@dataclass(frozen=True)
class ContractPolicyResult:
    contract_type: str
    required_components: tuple[str, ...]
    notes: tuple[str, ...]


def validate_contract_model(contract_type: str | None, economic: dict[str, Any], schedule: dict[str, Any], facts: dict[str, Any]) -> ContractPolicyResult:
    """Validate the selected payment basis against the canonical economic model.

    The policy mirrors the current federal public-works contract bases: unit prices,
    lump sum, and mixed. Jurisdiction-specific rules remain authoritative and can
    impose stricter requirements; this function only enforces invariant structure.
    """
    c = str(contract_type or "").upper()
    if not c:
        raise ContractPolicyError("El tipo de contrato es obligatorio antes del cálculo económico.")
    if c not in {"UNIT_PRICES", "LUMP_SUM", "MIXED"}:
        raise ContractPolicyError(f"Tipo de contrato no soportado: {c}")
    activities = schedule.get("activities") or []
    if not activities:
        raise ContractPolicyError("El modelo de programa no contiene actividades; la propuesta no puede cerrar de forma reproducible.")

    if c == "UNIT_PRICES":
        partidas = economic.get("partidas") or []
        if not partidas:
            raise ContractPolicyError("Precios unitarios exige catálogo de conceptos cuantificado.")
        has_apu = any(p.get("conceptos") for p in partidas)
        if not has_apu:
            raise ContractPolicyError("Precios unitarios exige análisis de precios unitarios por concepto.")
        missing = [name for name in ("factor_indirecto", "factor_utilidad") if name not in economic]
        if missing:
            raise ContractPolicyError(f"Precios unitarios exige trazabilidad de: {', '.join(missing)}; no se admiten porcentajes implícitos.")
        if not economic.get("indirect_costs"):
            raise ContractPolicyError("Precios unitarios exige memoria de costos indirectos; un factor aislado no es suficiente.")
        if not economic.get("financing"):
            raise ContractPolicyError("Precios unitarios exige memoria de financiamiento basada en flujo de efectivo.")
        if not economic.get("profit_detail"):
            raise ContractPolicyError("Precios unitarios exige memoria de utilidad y base de cálculo.")
        return ContractPolicyResult(c, ("APU", "DIRECT_COST", "INDIRECT_COST", "FINANCING", "PROFIT", "SCHEDULE"), ())

    if c == "LUMP_SUM":
        lump_activities = economic.get("lump_sum_activities") or activities
        if len(lump_activities) < 5:
            raise ContractPolicyError("Precio alzado exige desglosar la proposición en al menos cinco actividades principales.")
        if not economic.get("lump_sum_total") and not economic.get("budget_total"):
            raise ContractPolicyError("Precio alzado exige monto total determinable y trazable.")
        if (economic.get("factor_indirecto") or economic.get("factor_utilidad")) and not economic.get("cost_build_up"):
            raise ContractPolicyError("Precio alzado no acepta factores económicos aislados; requiere memoria de integración.")
        if not economic.get("cost_build_up") and not economic.get("lump_sum_cost_detail"):
            raise ContractPolicyError("Precio alzado exige desglose de costos/actividades suficiente para auditoría de la propuesta.")
        return ContractPolicyResult(c, ("LUMP_SUM_TOTAL", "MIN_5_MAIN_ACTIVITIES", "WBS", "SCHEDULE"), ())

    components = economic.get("mixed_components") or []
    if not components:
        raise ContractPolicyError("Contrato mixto exige identificar qué partidas son a precios unitarios y cuáles a precio alzado.")
    kinds = {str(x.get("basis", "")).upper() for x in components}
    if not {"UNIT_PRICES", "LUMP_SUM"}.issubset(kinds):
        raise ContractPolicyError("Contrato mixto exige al menos un componente a precios unitarios y otro a precio alzado.")
    unit_parts = [x for x in components if str(x.get("basis", "")).upper() == "UNIT_PRICES"]
    lump_parts = [x for x in components if str(x.get("basis", "")).upper() == "LUMP_SUM"]
    if not unit_parts or not any(x.get("partidas") for x in unit_parts):
        raise ContractPolicyError("La parte a precios unitarios del contrato mixto requiere partidas y APUs reales.")
    if not lump_parts or not any(len(x.get("activities") or []) >= 5 for x in lump_parts):
        raise ContractPolicyError("La parte a precio alzado del contrato mixto requiere al menos cinco actividades principales.")
    return ContractPolicyResult(c, ("MIXED_COMPONENTS", "APU_FOR_UNIT_PRICE_PARTS", "MIN_5_MAIN_ACTIVITIES_FOR_LUMP_SUM_PARTS", "SCHEDULE"), ())
