from __future__ import annotations

from decimal import Decimal, InvalidOperation
from typing import Any


def money(value: Any) -> Decimal:
    try:
        return Decimal(str(value or 0)).quantize(Decimal("0.01"))
    except (InvalidOperation, ValueError, TypeError) as exc:
        raise ValueError(f"Valor monetario inválido: {value!r}") from exc


class ProcurementConsistencyEngine:
    """Cross-model invariants for a reproducible tender package."""

    def validate(self, model: dict[str, Any]) -> list[dict[str, Any]]:
        findings: list[dict[str, Any]] = []
        economic = model.get("economic", {})
        partidas = economic.get("partidas") or []
        computed_total = sum((money(p.get("importe", money(p.get("cantidad")) * money(p.get("precio_unitario")))) for p in partidas), Decimal("0"))
        if not partidas and economic.get("budget_total") is not None and economic.get("catalog_total") is not None and money(economic["budget_total"]) != money(economic["catalog_total"]):
            findings.append(self._blocker("ECON-CATALOG-TOTAL", f"El total del presupuesto ({economic['budget_total']}) no coincide con el total declarado del catálogo ({economic['catalog_total']})."))
        direct_cost = economic.get('direct_cost')
        line_target = direct_cost if direct_cost is not None else economic.get('budget_total')
        if partidas and line_target is not None and money(line_target) != computed_total:
            findings.append(self._blocker("ECON-CATALOG-TOTAL", f"El costo directo ({line_target}) no coincide con la suma de partidas ({computed_total})."))
        components = ('direct_cost', 'indirect_cost', 'profit', 'risk', 'tax')
        if economic.get('budget_total') is not None and all(economic.get(k) is not None for k in components):
            total = sum((money(economic[k]) for k in components), Decimal('0'))
            if money(economic['budget_total']) != total:
                findings.append(self._blocker('ECON-BUDGET-COMPONENTS', 'El total presupuestado no cierra con costo directo, indirectos, utilidad, riesgo e impuestos.'))

        if economic.get("catalog_total") is not None and money(economic["catalog_total"]) != computed_total:
            findings.append(self._blocker("ECON-CATALOG-DECLARED", f"El total declarado del catálogo ({economic['catalog_total']}) no coincide con la suma calculada ({computed_total})."))

        program_total = economic.get("program_total")
        schedule = model.get("schedule", {})
        activities = schedule.get("activities") or []
        if program_total is not None and activities:
            activity_total = sum((money(a.get("budget")) for a in activities), Decimal("0"))
            if money(program_total) != activity_total:
                findings.append(self._blocker("ECON-PROGRAM-TOTAL", f"El total programado ({program_total}) no coincide con las actividades ({activity_total})."))
        elif activities and partidas:
            activity_total = sum((money(a.get("budget")) for a in activities), Decimal("0"))
            if activity_total != computed_total:
                findings.append(self._blocker("ECON-PROGRAM-IMPLICT", f"Las actividades programadas ({activity_total}) no coinciden con el presupuesto ({computed_total})."))

        letter_total = economic.get("letter_total")
        proposal_total = money(economic['budget_total']) if economic.get('budget_total') is not None else computed_total
        if letter_total is not None and money(letter_total) != proposal_total:
            findings.append(self._blocker("ECON-LETTER-TOTAL", f"La carta económica ({letter_total}) no coincide con el presupuesto ({computed_total})."))

        technical = model.get("technical", {})
        concepts = {str(c.get("code")): c for c in (technical.get("concepts") or [])}
        for quantity in technical.get("quantities", []) or []:
            code = str(quantity.get("concept_code"))
            if code not in concepts:
                findings.append(self._blocker("TECH-ORPHAN-QUANTITY", f"Cantidad sin concepto: {code}"))
            if money(quantity.get("value")) < 0:
                findings.append(self._blocker("TECH-NEGATIVE-QUANTITY", f"Cantidad negativa: {code}"))

        for activity in technical.get("activities", []) or []:
            if not activity.get("concept_codes"):
                findings.append(self._high("SCHED-ACTIVITY-NO-CONCEPT", f"Actividad sin conceptos: {activity.get('code')}"))

        for partida in partidas:
            for concept in partida.get("conceptos", []) or []:
                direct = money(concept.get("costo_directo_unitario"))
                components = sum((money(item.get("importe", money(item.get("cantidad")) * money(item.get("precio_unitario")))) for item in concept.get("insumos", []) or []), Decimal("0"))
                if components and direct != components:
                    findings.append(self._blocker("APU-DIRECT-COST", f"El costo directo de {concept.get('clave')} ({direct}) no coincide con sus insumos ({components})."))

        documents = model.get("documents", []) or []
        for document in documents:
            if document.get("required") and not document.get("artifact_id"):
                findings.append(self._blocker("DOC-REQUIRED-MISSING", f"Falta artefacto requerido: {document.get('code')}"))
        return findings

    @staticmethod
    def _blocker(code: str, message: str) -> dict[str, Any]:
        return {"code": code, "severity": "BLOCKER", "message": message}

    @staticmethod
    def _high(code: str, message: str) -> dict[str, Any]:
        return {"code": code, "severity": "HIGH", "message": message}
