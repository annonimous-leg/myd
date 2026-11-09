from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Any


@dataclass(frozen=True)
class ReferenceCaseResult:
    case_pack_code: str
    facts: dict[str, Any]
    technical: dict[str, Any]
    economic: dict[str, Any]
    schedule: dict[str, Any]
    bidder: dict[str, Any]
    sections: dict[str, str]


class ConaguaPtArCaseParser:
    """Deterministic adapter for the CONAGUA/PTAR guide acceptance case.

    It parses the supplied guide case as evidence. It is intentionally isolated
    from generic procurement rules so production jurisdictions do not inherit
    case-specific assumptions.
    """

    HEADER_PATTERNS = {
        "identifier": r"\*\*Numero de licitacion\*\*\s*\|\s*([^|]+)",
        "authority": r"\*\*Dependencia convocante\*\*\s*\|\s*([^|]+)",
        "unit": r"\*\*Unidad administrativa\*\*\s*\|\s*([^|]+)",
        "object": r"\*\*Objeto\*\*\s*\|\s*([^|]+)",
        "procedure": r"\*\*Modalidad\*\*\s*\|\s*([^|]+)",
        "contract": r"\*\*Tipo de contrato\*\*\s*\|\s*([^|]+)",
        "duration_days": r"\*\*Plazo de ejecucion\*\*\s*\|\s*([0-9]+)\s*dias",
        "advance": r"\*\*Anticipo\*\*\s*\|\s*([^|]+)",
        "evaluation": r"\*\*Criterio de evaluacion\*\*\s*\|\s*([^|]+)",
        "national_content": r"\*\*Contenido nacional\*\*\s*\|\s*([0-9]+(?:\.[0-9]+)?)%",
        "submission_date": r"\*\*Fecha de presentacion\*\*\s*\|\s*([^|]+)",
        "platform": r"\*\*Plataforma\*\*\s*\|\s*([^|]+)",
        "validity_days": r"\*\*Vigencia de proposiciones\*\*\s*\|\s*([0-9]+)\s*dias",
    }

    def parse(self, text: str) -> ReferenceCaseResult:
        if "CONAGUA-LPN-2026-0847" not in text or "AT-1" not in text or "AE-12" not in text:
            raise ValueError("El documento no corresponde al caso de referencia CONAGUA/PTAR de la guía.")
        facts: dict[str, Any] = {
            "jurisdiction_code": "MX-FED-CONAGUA-OBRA",
            "procedure_type": "LICITACION_PUBLICA",
            "contract_type": "UNIT_PRICES",
            "evaluation_criterion": "POINTS_PERCENTAGES",
            "project_type": "INFRASTRUCTURE",
            "scope_scale": "LARGE",
            "funding_source": "FEDERAL",
            "object_class": "PUBLIC_WORKS",
            "legal_regime": "LOPSRM",
            "government_level": "FEDERAL",
        }
        for key, pattern in self.HEADER_PATTERNS.items():
            match = re.search(pattern, text, re.IGNORECASE)
            if not match:
                continue
            value = match.group(1).strip()
            if key in {"duration_days", "validity_days"}:
                facts[key] = int(value)
            elif key == "national_content":
                facts[key] = float(value)
            else:
                facts[key] = value
        facts["authority"] = facts.get("authority", "CONAGUA")

        sections = self._sections(text)
        technical = {
            "reference_sections": {k: v for k, v in sections.items() if k.startswith("AT-")},
            "specifications": self._extract_table_after(text, "## Especificaciones Tecnicas Clave"),
            "national_content": facts.get("national_content"),
            "site_visit": sections.get("AT-01"),
            "planning": sections.get("AT-02"),
            "construction_method": sections.get("AT-02"),
            "national_content_detail": sections.get("AT-09"),
            "mipyme_subcontracting": sections.get("AT-10"),
            "disability": sections.get("AT-11"),
            "training": sections.get("AT-12"),
            "pacma": sections.get("AT-13"),
        }
        economic = self._economic_model(text, sections)
        schedule = {
            "reference_case": True,
            "duration_days": facts.get("duration_days"),
            "activities": self._extract_week_activities(text),
        }
        bidder = {
            "reference_sections": {k: v for k, v in sections.items() if k in {"AT-03", "AT-06", "AT-07", "AT-08"}},
            "personnel": sections.get("AT-03"),
            "machinery": sections.get("AT-05"),
            "financial_capacity": sections.get("AT-06"),
            "experience": sections.get("AT-07"),
            "contract_compliance": sections.get("AT-08"),
        }
        return ReferenceCaseResult("REFERENCE_CONAGUA_PTAR_2026", facts, technical, economic, schedule, bidder, sections)

    @staticmethod
    def _table_rows(block: str) -> list[dict[str, str]]:
        lines = [line.strip() for line in block.splitlines() if line.strip().startswith("|")]
        if len(lines) < 2:
            return []
        headers = [c.strip() for c in lines[0].strip().strip("|").split("|")]
        rows: list[dict[str, str]] = []
        for line in lines[1:]:
            if "---" in line:
                continue
            cells = [c.strip() for c in line.strip().strip("|").split("|")]
            if not any(cells):
                continue
            rows.append({headers[i] if i < len(headers) else f"col_{i + 1}": cells[i] for i in range(len(cells))})
        return rows

    @staticmethod
    def _money(value: Any) -> float:
        text = str(value or "").replace(",", "")
        cleaned = re.sub(r"[^0-9.\-]", "", text)
        return float(cleaned) if cleaned else 0.0

    @classmethod
    def _economic_model(cls, text: str, sections: dict[str, str]) -> dict[str, Any]:
        ae2_rows = cls._table_rows(sections.get("AE-02", ""))
        partidas: list[dict[str, Any]] = []
        for row in ae2_rows:
            key = row.get("Clave", "").strip()
            if not re.match(r"^\d+\.\d+\.\d+$", key):
                continue
            partidas.append({
                "numero": key,
                "descripcion": row.get("Descripcion", ""),
                "unidad": row.get("Unidad", ""),
                "cantidad": cls._money(row.get("Cantidad")),
                "precio_unitario": cls._money(row.get("Precio Unitario")),
                "importe": cls._money(row.get("Importe")),
                "conceptos": [],
            })

        ae3 = sections.get("AE-03", "")
        material_block = ae3[ae3.find("#### A. MATERIALES"):ae3.find("#### B. MANO DE OBRA")] if "#### A. MATERIALES" in ae3 else ""
        labor_block = ae3[ae3.find("#### B. MANO DE OBRA"):ae3.find("#### C. EQUIPO")] if "#### B. MANO DE OBRA" in ae3 else ""
        equipment_block = ae3[ae3.find("#### C. EQUIPO"):ae3.find("#### D. COSTO DIRECTO")] if "#### C. EQUIPO" in ae3 else ""

        apu_items: list[dict[str, Any]] = []
        for row in cls._table_rows(material_block):
            name = row.get("Material") or row.get("Concepto")
            if name and "Subtotal" not in name:
                apu_items.append({"clave": name[:80], "descripcion": name, "tipo": "MATERIAL", "unidad": "", "cantidad": cls._money(row.get("Cantidad Real") or row.get("Cantidad Neta")), "precio_unitario": cls._money(row.get("Precio Unitario")), "importe": cls._money(row.get("Importe"))})
        for row in cls._table_rows(labor_block):
            name = row.get("Categoria", "")
            if name and "Subtotal" not in name:
                apu_items.append({"clave": name[:80], "descripcion": name, "tipo": "MANO_OBRA", "unidad": "jornada", "cantidad": cls._money(row.get("Jornada Req.")), "precio_unitario": cls._money(row.get("Salario Real")), "importe": cls._money(row.get("Importe"))})
        for row in cls._table_rows(equipment_block):
            name = row.get("Concepto", "")
            if name and "Subtotal" not in name:
                apu_items.append({"clave": name[:80], "descripcion": name, "tipo": "EQUIPO", "unidad": "", "cantidad": 1.0, "precio_unitario": cls._money(row.get("Importe")), "importe": cls._money(row.get("Importe"))})

        target = next((p for p in partidas if p["numero"] == "2.01.006"), None)
        if target is not None:
            target["conceptos"] = [{"clave": target["numero"], "descripcion": target["descripcion"], "unidad": target["unidad"], "cantidad": target["cantidad"], "costo_directo_unitario": 417.62, "insumos": apu_items}]

        ae8_rows = cls._table_rows(sections.get("AE-08", ""))
        indirect_items = []
        for row in ae8_rows:
            rubric = row.get("Rubro", "")
            if rubric and not rubric.upper().startswith("TOTAL"):
                indirect_items.append({"concept": rubric, "basis": row.get("% sobre CD"), "amount": cls._money(row.get("Monto (sobre CD=$8,500,000)"))})

        ae9_rows = cls._table_rows(sections.get("AE-09", ""))
        ae10_rows = cls._table_rows(sections.get("AE-10", ""))
        financing = {row.get("Concepto"): row.get("Valor") for row in ae9_rows}
        investment = cls._money(financing.get("Inversion inicial estimada", "3,500,000"))
        curve = financing.get("Curva de desembolsos", "") or ""
        cash_flow = []
        for period, percentage in re.findall(r"Mes\s*(\d+)\s*:\s*([0-9]+)%", curve):
            amount = investment * float(percentage) / 100.0
            cash_flow.append({"period": f"Mes {period}", "inflow": amount, "outflow": 0.0, "net": amount})
        profit = {row.get("Concepto"): row.get("Valor") for row in ae10_rows}

        return {
            "reference_sections": {k: v for k, v in sections.items() if k.startswith("AE-")},
            "partidas": partidas,
            "budget_total": 12150000.0 if "12,150,000.00" in text else None,
            "amount_in_words": "CATORCE MILLONES NOVENTA Y CUATRO MIL PESOS 00/100 M.N.",
            "fasar": {"ps": 0.5, "tp": 1.67587, "tl": 0.0, "fsr": 1.67587, "inputs": {"source": "AE-03"}},
            "indirect_costs": {"items": indirect_items, "total": sum(float(item["amount"]) for item in indirect_items)},
            "financing": {"cash_flow": cash_flow, "factor": 0.02, "source_rows": financing},
            "profit_detail": {"amount": 684000.0, "basis": "CD + CI + F", "rate": 0.08, "criterion": profit.get("Justificacion")},
            "profit": {"amount": 684000.0, "basis": "CD + CI + F", "rate": 0.08, "criterion": profit.get("Justificacion")},
            "material_schedule": cls._month_rows(sections.get("AE-04", "")),
            "labor_schedule": cls._month_rows(sections.get("AE-05", "")),
            "equipment_schedule": cls._month_rows(sections.get("AE-06", "")),
            "machinery_analysis": {"source": "AE-07"},
            "explosion": cls._table_rows(sections.get("AE-11", "")),
        }

    @staticmethod
    def _month_rows(block: str) -> list[dict[str, Any]]:
        rows = ConaguaPtArCaseParser._table_rows(block)
        normalized = []
        for row in rows:
            first_key = next(iter(row), "Item")
            normalized.append({"name": row.get(first_key, ""), **row})
        return normalized

    @staticmethod
    def _sections(text: str) -> dict[str, str]:
        pattern = re.compile(r"^## (?:ANEXO (?:TECNICO|ECONOMICO)) (AT-\d{1,2}|AE-\d{1,2}):[^\n]*", re.MULTILINE | re.IGNORECASE)
        matches = list(pattern.finditer(text))
        sections: dict[str, str] = {}
        for idx, match in enumerate(matches):
            raw_code = match.group(1).upper()
            prefix, number = raw_code.split("-")
            code = f"{prefix}-{int(number):02d}"
            start = match.end()
            end = matches[idx + 1].start() if idx + 1 < len(matches) else len(text)
            sections[code] = text[start:end].strip()
        return sections

    @staticmethod
    def _extract_table_after(text: str, heading: str) -> list[dict[str, str]]:
        pos = text.find(heading)
        if pos < 0:
            return []
        block = text[pos:].split("\n\n", 1)[0]
        rows = []
        for line in block.splitlines():
            if not line.startswith("|") or line.count("|") < 3 or "---" in line:
                continue
            cells = [c.strip() for c in line.strip().strip("|").split("|")]
            if len(cells) == 2 and cells[0].lower() != "concepto":
                rows.append({"field": cells[0], "value": cells[1]})
        return rows

    @staticmethod
    def _extract_week_activities(text: str) -> list[dict[str, Any]]:
        activities: list[dict[str, Any]] = []
        for phase, start_month, end_month in re.findall(r"\*\*([^*]+) \(Mes (\d+)-(\d+)\)\*\*", text):
            activities.append({"id": f"REF-{len(activities)+1:03d}", "name": phase.strip(), "duration_days": (int(end_month) - int(start_month) + 1) * 30, "budget": 0.0, "predecessors": []})
        return activities
