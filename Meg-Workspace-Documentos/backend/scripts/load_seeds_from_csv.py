#!/usr/bin/env python3
"""Carga CSV de app/data/seeds/ hacia procedure_thresholds, legal_rules y
jurisdiction_profiles.

Idempotente (upsert). tenant_id=NULL (global).

Uso:
  python -m scripts.load_seeds_from_csv
  python -m scripts.load_seeds_from_csv --only thresholds
  python -m scripts.load_seeds_from_csv --dry-run
"""
from __future__ import annotations

import argparse
import asyncio
import csv
import sys
from pathlib import Path
from uuid import uuid4

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
SEEDS = ROOT / "app" / "data" / "seeds"

from sqlalchemy import select
from app.models.base import AsyncSessionLocal
from app.models.procurement import CatalogTerm, JurisdictionProfile, LegalRule, ProcedureThreshold


def _empty(v: str | None) -> bool:
    return v is None or str(v).strip() == ""


def _f(v: str | None) -> float | None:
    if _empty(v):
        return None
    return float(v)


def _b(v: str | None) -> bool:
    return str(v or "").strip().lower() in {"1", "true", "yes", "y", "si", "sí"}


async def load_thresholds(*, dry_run: bool) -> dict[str, int]:
    path = SEEDS / "procedure_thresholds.csv"
    if not path.exists():
        raise FileNotFoundError(f"Falta {path}; corre export_procedure_seed_csv.py primero")
    stats = {"insert": 0, "update": 0}
    async with AsyncSessionLocal() as db:
        with path.open(encoding="utf-8") as f:
            for row in csv.DictReader(f):
                code = row["jurisdiction_code"].strip().upper()
                tipo = row["tipo_contratacion"].strip().upper()
                ej = int(row["ejercicio_fiscal"])
                pmin = float(row["presupuesto_min_miles"])
                existing = await db.scalar(
                    select(ProcedureThreshold).where(
                        ProcedureThreshold.tenant_id.is_(None),
                        ProcedureThreshold.jurisdiction_code == code,
                        ProcedureThreshold.tipo_contratacion == tipo,
                        ProcedureThreshold.ejercicio_fiscal == ej,
                        ProcedureThreshold.presupuesto_min_miles == pmin,
                    )
                )
                payload = dict(
                    government_level=row["government_level"],
                    matter=row["matter"],
                    presupuesto_max_miles=_f(row.get("presupuesto_max_miles")),
                    adjudicacion_directa_miles=float(row["adjudicacion_directa_miles"]),
                    invitacion_restringida_miles=float(row["invitacion_restringida_miles"]),
                    adjudicacion_directa_servicio_miles=_f(
                        row.get("adjudicacion_directa_servicio_miles")
                    ),
                    invitacion_restringida_servicio_miles=_f(
                        row.get("invitacion_restringida_servicio_miles")
                    ),
                    ley=row["ley"],
                    articulo_referencia=row["articulo_referencia"],
                    fuente=row["fuente"],
                    fecha_publicacion=row.get("fecha_publicacion") or None,
                    estado_dato=row["estado_dato"].upper(),
                    notas=row.get("notas") or None,
                    active=_b(row.get("active") or "true"),
                )
                if existing is None:
                    stats["insert"] += 1
                    if not dry_run:
                        db.add(
                            ProcedureThreshold(
                                id=uuid4(),
                                tenant_id=None,
                                jurisdiction_code=code,
                                tipo_contratacion=tipo,
                                ejercicio_fiscal=ej,
                                presupuesto_min_miles=pmin,
                                **payload,
                            )
                        )
                else:
                    stats["update"] += 1
                    if not dry_run:
                        for k, v in payload.items():
                            setattr(existing, k, v)
        if not dry_run:
            await db.commit()
    return stats


async def load_exceptions(*, dry_run: bool) -> dict[str, int]:
    path = SEEDS / "procedure_exceptions.csv"
    if not path.exists():
        raise FileNotFoundError(f"Falta {path}")
    stats = {"insert": 0, "update": 0}
    async with AsyncSessionLocal() as db:
        with path.open(encoding="utf-8") as f:
            for row in csv.DictReader(f):
                rule_id = row["rule_id"].strip()
                version = int(row.get("rule_version") or 1)
                existing = await db.scalar(
                    select(LegalRule).where(
                        LegalRule.tenant_id.is_(None),
                        LegalRule.rule_id == rule_id,
                        LegalRule.rule_version == version,
                    )
                )
                requisitos = [
                    x.strip() for x in (row.get("requisitos") or "").split("|") if x.strip()
                ]
                requirement = {
                    "fundamento": row["fundamento"],
                    "citation": row.get("citation") or "",
                    "ley": row.get("ley") or "",
                    "articulo": row.get("articulo") or "",
                    "requisitos": requisitos,
                    "requiere_investigacion_mercado": _b(
                        row.get("requiere_investigacion_mercado") or "true"
                    ),
                    "riesgo_compliance": row.get("riesgo_compliance") or "ALTO",
                }
                if existing is None:
                    stats["insert"] += 1
                    if not dry_run:
                        db.add(
                            LegalRule(
                                id=uuid4(),
                                tenant_id=None,
                                rule_id=rule_id,
                                jurisdiction_code=row["jurisdiction_code"].strip().upper(),
                                domain="PROCEDURE_EXCEPTION",
                                procedure_type=row.get("procedure_type") or "ADJUDICACION",
                                source_version=row.get("source_version") or None,
                                condition={"kind": "EXCEPTION_INVOKED", "rule_id": rule_id},
                                requirement=requirement,
                                validation={"min_justificacion_chars": 50},
                                severity="BLOCKER",
                                rule_version=version,
                                active=_b(row.get("active") or "true"),
                            )
                        )
                else:
                    stats["update"] += 1
                    if not dry_run:
                        existing.jurisdiction_code = row["jurisdiction_code"].strip().upper()
                        existing.domain = "PROCEDURE_EXCEPTION"
                        existing.procedure_type = row.get("procedure_type") or "ADJUDICACION"
                        existing.source_version = row.get("source_version") or None
                        existing.requirement = requirement
                        existing.validation = {"min_justificacion_chars": 50}
                        existing.active = _b(row.get("active") or "true")
        if not dry_run:
            await db.commit()
    return stats


async def load_profiles(*, dry_run: bool) -> dict[str, int]:
    path = SEEDS / "jurisdiction_profiles.csv"
    if not path.exists():
        raise FileNotFoundError(f"Falta {path}")
    stats = {"insert": 0, "update": 0}
    async with AsyncSessionLocal() as db:
        with path.open(encoding="utf-8") as f:
            for row in csv.DictReader(f):
                code = row["code"].strip().upper()
                existing = await db.scalar(
                    select(JurisdictionProfile).where(
                        JurisdictionProfile.tenant_id.is_(None),
                        JurisdictionProfile.code == code,
                    )
                )
                inherits_raw = [
                    x.strip().upper()
                    for x in (row.get("inherits_from") or "").split("|")
                    if x.strip()
                ]
                # Si no hay umbrales locales sembrados, heredar federales por materia
                # para que ThresholdResolver encuentre procedure_thresholds.
                thr_code = (row.get("threshold_jurisdiction_code") or code).strip().upper()
                if not inherits_raw and thr_code != code:
                    inherits_raw = [thr_code]
                level = (row.get("government_level") or "").upper()
                matter = (row.get("matter") or "").upper()
                if not inherits_raw and level not in {"FEDERAL", ""}:
                    if matter in {"PUBLIC_WORKS", "OBRA", ""}:
                        inherits_raw = ["MX-FED-OBRA"]
                    elif matter in {"ACQUISITION", "ADQ", "PROCUREMENT"}:
                        inherits_raw = ["MX-FED-ADQ"]
                ruleset = {
                    "regime_family": row.get("regime_family") or "",
                    "selection_label": row.get("selection_label") or "",
                    "inherits_from": inherits_raw,
                    "allowed_procedures": [
                        x for x in (row.get("allowed_procedures") or "").split("|") if x
                    ],
                    "allowed_contract_types": [
                        x for x in (row.get("allowed_contract_types") or "").split("|") if x
                    ],
                    "allowed_evaluation_criteria": [
                        x
                        for x in (row.get("allowed_evaluation_criteria") or "").split("|")
                        if x
                    ],
                    "allowed_funding_sources": [
                        x for x in (row.get("allowed_funding_sources") or "").split("|") if x
                    ],
                    "allowed_legal_regimes": [
                        x for x in (row.get("allowed_legal_regimes") or "").split("|") if x
                    ],
                    "legal_sources": [
                        x for x in (row.get("legal_sources") or "").split("|") if x
                    ],
                    "threshold_jurisdiction_code": thr_code,
                    "threshold_estado_dato": row.get("threshold_estado_dato") or "",
                    "requires_official_entity_pack": _b(
                        row.get("requires_official_entity_pack")
                    ),
                    "notes": row.get("notes") or "",
                }
                if existing is None:
                    stats["insert"] += 1
                    if not dry_run:
                        db.add(
                            JurisdictionProfile(
                                id=uuid4(),
                                tenant_id=None,
                                code=code,
                                authority=row["authority"],
                                government_level=row["government_level"],
                                matter=row["matter"],
                                portal_code=row.get("portal_code") or None,
                                profile_version=1,
                                ruleset=ruleset,
                                templates={"case_packs": []},
                                active=_b(row.get("active") or "true"),
                            )
                        )
                else:
                    stats["update"] += 1
                    if not dry_run:
                        merged = dict(existing.ruleset or {})
                        merged.update(ruleset)
                        existing.ruleset = merged
                        existing.authority = row["authority"]
                        existing.government_level = row["government_level"]
                        existing.matter = row["matter"]
                        existing.portal_code = row.get("portal_code") or None
                        existing.active = _b(row.get("active") or "true")
        if not dry_run:
            await db.commit()
    return stats


async def load_garantias(*, dry_run: bool) -> dict[str, int]:
    """LegalRule GARANTIAS / PENALIZACIONES from garantias_legal_rules.csv."""
    import json

    path = SEEDS / "garantias_legal_rules.csv"
    if not path.exists():
        raise FileNotFoundError(f"Falta {path}")
    stats = {"insert": 0, "update": 0}
    async with AsyncSessionLocal() as db:
        with path.open(encoding="utf-8") as f:
            for row in csv.DictReader(f):
                rule_id = row["rule_id"].strip()
                version = int(row.get("rule_version") or 1)
                existing = await db.scalar(
                    select(LegalRule).where(
                        LegalRule.tenant_id.is_(None),
                        LegalRule.rule_id == rule_id,
                        LegalRule.rule_version == version,
                    )
                )
                params = {}
                raw_params = (row.get("params_json") or "").strip()
                if raw_params:
                    params = json.loads(raw_params)
                requirement = {
                    "fundamento": row["fundamento"],
                    "citation": row.get("citation") or "",
                    "ley": row.get("ley") or "",
                    "articulo": row.get("articulo") or "",
                    "params": params,
                }
                domain = (row.get("domain") or "GARANTIAS").strip().upper()
                if existing is None:
                    stats["insert"] += 1
                    if not dry_run:
                        db.add(
                            LegalRule(
                                id=uuid4(),
                                tenant_id=None,
                                rule_id=rule_id,
                                jurisdiction_code=(row.get("jurisdiction_code") or "").strip().upper()
                                or None,
                                domain=domain,
                                procedure_type=(row.get("procedure_type") or None) or None,
                                source_version=row.get("source_version") or None,
                                condition={"kind": "PARAMETRIC", "rule_id": rule_id},
                                requirement=requirement,
                                validation={},
                                severity="BLOCKER",
                                rule_version=version,
                                active=_b(row.get("active") or "true"),
                            )
                        )
                else:
                    stats["update"] += 1
                    if not dry_run:
                        existing.domain = domain
                        existing.jurisdiction_code = (
                            (row.get("jurisdiction_code") or "").strip().upper() or None
                        )
                        existing.source_version = row.get("source_version") or None
                        existing.requirement = requirement
                        existing.active = _b(row.get("active") or "true")
        if not dry_run:
            await db.commit()
    return stats



async def load_catalog_terms(*, dry_run: bool) -> dict[str, int]:
    path = SEEDS / "catalog_terms.csv"
    if not path.exists():
        raise FileNotFoundError(f"Falta {path}")
    stats = {"insert": 0, "update": 0}
    async with AsyncSessionLocal() as db:
        with path.open(encoding="utf-8") as f:
            for row in csv.DictReader(f):
                domain = row["domain"].strip().upper()
                code = row["code"].strip().upper()
                existing = await db.scalar(
                    select(CatalogTerm).where(
                        CatalogTerm.tenant_id.is_(None),
                        CatalogTerm.domain == domain,
                        CatalogTerm.code == code,
                    )
                )
                if existing is None:
                    stats["insert"] += 1
                    if not dry_run:
                        db.add(
                            CatalogTerm(
                                id=uuid4(),
                                tenant_id=None,
                                domain=domain,
                                code=code,
                                label=row["label"].strip(),
                                sort_order=int(row.get("sort_order") or 0),
                                active=_b(row.get("active") or "true"),
                                meta={},
                            )
                        )
                else:
                    stats["update"] += 1
                    if not dry_run:
                        existing.label = row["label"].strip()
                        existing.sort_order = int(row.get("sort_order") or 0)
                        existing.active = _b(row.get("active") or "true")
        if not dry_run:
            await db.commit()
    return stats

async def main_async(only: str | None, dry_run: bool) -> None:
    targets = {
        "thresholds": load_thresholds,
        "exceptions": load_exceptions,
        "profiles": load_profiles,
        "garantias": load_garantias,
        "catalog": load_catalog_terms,
    }
    selected = [only] if only else list(targets)
    for key in selected:
        print(f"Loading {key}...")
        stats = await targets[key](dry_run=dry_run)
        print(f"  {key}: insert={stats['insert']} update={stats['update']} dry_run={dry_run}")


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--only",
        choices=["thresholds", "exceptions", "profiles", "garantias", "catalog"],
    )
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args()
    asyncio.run(main_async(args.only, args.dry_run))


if __name__ == "__main__":
    main()
