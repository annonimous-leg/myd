"""PostgreSQL E2E gate for durable StageRun + validation evidence + tenant A/B.

Requires a migrated PostgreSQL database and the normal Megalodon environment.
Run explicitly with:
    pytest -m postgres backend/tests/e2e/test_procurement_stage_trace_postgres.py -q
"""
from __future__ import annotations

import json
import asyncio
import os
from pathlib import Path
from uuid import uuid4
from decimal import Decimal

import pytest
from sqlalchemy import delete, select

pytestmark = pytest.mark.postgres

FIXTURE = Path(__file__).resolve().parents[2] / ".." / "reference" / "expediente_inbal_n3_2026_CONTROL.json"


@pytest.mark.asyncio
async def test_inbal_stage_trace_postgres_tenant_a_b():
    if not os.getenv("DATABASE_URL", "").startswith(("postgresql://", "postgresql+")):
        pytest.skip("Este gate exige PostgreSQL real; no se ejecuta sobre SQLite.")

    from app.models.base import AsyncSessionLocal
    from app.models.expediente import ExpedienteObra
    from app.models.procurement import (
        TenderEvidence,
        TenderEvidenceLink,
        TenderPackage,
        TenderPreparationRun,
        TenderPreparationStageRun,
        TenderRequirement,
        TenderState,
        TenderValidationEvidenceLink,
        TenderValidationRun,
    )
    from app.models.user import Tenant, User, UserRole
    from app.services.procurement.service import ProcurementService

    raw = json.loads(FIXTURE.read_text(encoding="utf-8"))
    synthetic = raw["synthetic_operational_input"]

    def operational_model() -> dict:
        concepts = synthetic["catalogo_conceptos"]
        partidas = [
            {
                "numero": idx + 1,
                "descripcion": row["descripcion"],
                "unidad": row["unidad"],
                "cantidad": row["cantidad"],
                "precio_unitario_manual": row["pu"],
                "conceptos": [
                    {
                        "clave": row["codigo"],
                        "descripcion": row["descripcion"],
                        "unidad": row["unidad"],
                        "cantidad": row["cantidad"],
                        "insumos": [
                            {
                                "clave": f"INS-{idx+1}",
                                "descripcion": row["descripcion"],
                                "tipo": "MATERIAL",
                                "unidad": row["unidad"],
                                "cantidad": 1,
                                "precio_unitario": row["pu"],
                                "rendimiento": 1,
                            }
                        ],
                    }
                ],
            }
            for idx, row in enumerate(concepts)
        ]
        activities = [
            {"id": "A1", "name": "Preparación", "duration_days": 10, "budget": 500000, "predecessors": []},
            {"id": "A2", "name": "Muros", "duration_days": 15, "budget": 1500000, "predecessors": ["A1"]},
            {"id": "A3", "name": "Lucernario", "duration_days": 12, "budget": 1200000, "predecessors": ["A1"]},
            {"id": "A4", "name": "Sanitarios", "duration_days": 10, "budget": 800000, "predecessors": ["A2", "A3"]},
            {"id": "A5", "name": "Complementarios", "duration_days": 13, "budget": 500000, "predecessors": ["A4"]},
        ]
        # The four priced concepts define the direct schedule allocation.
        # Closing documents are a separate zero-cost activity in this fixture.
        for activity, concept in zip(activities, concepts, strict=False):
            activity['budget'] = float(Decimal(str(concept['cantidad'])) * Decimal(str(concept['pu'])))
        activities[-1].update(name='Cierre documental', budget=0)
        return {
            "identifier": synthetic["expediente"]["identificador"],
            "title": synthetic["expediente"]["titulo"],
            "facts": {
                "authority": synthetic["expediente"]["organo"],
                "object": raw["reference"]["subject"],
                "project_type": "CONSERVATION",
                "jurisdiction_code": "FEDERAL_OBRA_PUBLICA",
                "procedure_type": "PUBLIC_TENDER",
                "contract_type": "UNIT_PRICES",
                "evaluation_criterion": "BEST_VALUE",
                "bidder": {**synthetic["proposicion"]["licitante"], "capital": 5000000},
            },
            "technical": {"concepts": [{"code": x["codigo"]} for x in concepts]},
            "economic": {
                "partidas": partidas,
                "factor_indirecto": 0.10,
                "factor_utilidad": 0.08,
                "factor_impuesto": 0.16,
                "factor_riesgo": 0,
                "source": "Caso E2E validado: modelo económico operativo",
                "indirect_costs": {"items": [{"code": "IND-01", "amount": 100}]},
                "financing": {"amount": 100},
                "profit_detail": {"amount": 100},
            },
            "schedule": {
                "start_date": "2026-03-16T08:00:00-06:00",
                "duration_days": synthetic["expediente"]["plazo_dias"],
                "activities": activities,
            },
            "documents": [],
            "bidder": {"capital": 5000000, "name": synthetic["proposicion"]["licitante"]["razon_social"]},
        }

    tenants = []
    tenders = []
    async with AsyncSessionLocal() as db:
        for suffix in ("a", "b"):
            tenant = Tenant(name=f"PRR INBAL tenant {suffix}", slug=f"prr-inbal-{suffix}-{uuid4().hex[:8]}", is_active=True)
            db.add(tenant)
            await db.flush()
            user = User(
                email=f"prr-{suffix}-{uuid4().hex[:8]}@example.mx",
                hashed_password="not-used-by-gate",
                full_name=f"PRR Tenant {suffix}",
                role=UserRole.TECNICO,
                tenant_id=tenant.id,
                is_active=True,
                is_verified=True,
            )
            db.add(user)
            await db.flush()
            expediente = ExpedienteObra(
                tenant_id=tenant.id,
                creado_por_id=user.id,
                actualizado_por_id=user.id,
                identificador=f"{synthetic['expediente']['identificador']}-{suffix.upper()}",
                titulo=synthetic["expediente"]["titulo"],
                descripcion=raw["reference"]["subject"],
                organo=synthetic["expediente"]["organo"],
                unidad_administrativa=synthetic["expediente"]["unidad_administrativa"],
                serie_documental="OBRA_PUBLICA",
                subserie_documental="LICITACION",
                proyecto_nombre=synthetic["expediente"]["titulo"],
                ubicacion_obra=synthetic["expediente"]["ubicacion_obra"],
                monto_contrato=synthetic["expediente"]["monto_estimado"],
                plazo_dias=synthetic["expediente"]["plazo_dias"],
                tipo_contrato="PRECIOS_UNITARIOS",
                responsable_id=user.id,
            )
            db.add(expediente)
            await db.flush()
            tender = TenderPackage(
                tenant_id=tenant.id,
                creado_por_id=user.id,
                actualizado_por_id=user.id,
                expediente_id=expediente.id,
                identifier=synthetic["expediente"]["identificador"],
                title=synthetic["expediente"]["titulo"],
                state=TenderState.DOCUMENTS_READY.value,
                jurisdiction_code="FEDERAL_OBRA_PUBLICA",
                procedure_type="PUBLIC_TENDER",
                contract_type="UNIT_PRICES",
                evaluation_criterion="BEST_VALUE",
                project_type="CONSERVATION",
                canonical_model=operational_model(),
                current_revision=1,
            )
            db.add(tender)
            await db.flush()
            source = TenderEvidence(
                tenant_id=tenant.id,
                creado_por_id=user.id,
                actualizado_por_id=user.id,
                tender_id=tender.id,
                kind="SOURCE_DOCUMENT",
                subject="INBAL official procedure source",
                value={"procedure_number": raw["reference"]["procedure_number"], "source_url": raw["reference"]["source_url"]},
                source_uri=raw["reference"]["source_url"],
                source_hash="0" * 64,
                source_revision=1,
                status="ACTIVE",
            )
            db.add(source)
            await db.flush()
            req = TenderRequirement(
                tenant_id=tenant.id,
                creado_por_id=user.id,
                actualizado_por_id=user.id,
                tender_id=tender.id,
                code="REQ-CAP-001",
                category="ECONOMICO",
                description="Capital contable mínimo",
                mandatory=True,
                condition={"conditions": [{"field": "bidder.capital", "op": "gte", "val": 1000000}]},
                evidence_required=[{"kind": "SOURCE_DOCUMENT"}],
                severity="BLOCKER",
            )
            db.add(req)
            await db.flush()
            db.add(TenderEvidenceLink(
                tenant_id=tenant.id, tender_id=tender.id, evidence_id=source.id,
                requirement_id=req.id, relation="SUPPORTS",
            ))
            await db.commit()
            # Use the production activation gate; a raw condition is not an
            # approved executable rule. Test both sides of its boundary.
            activation = await ProcurementService(db, user).create_requirement_rule_version(
                tender.id, req.id,
                {'id': req.code, 'conditions': [{'field': 'bidder.capital', 'op': 'gte', 'val': 1000000}]},
                test_cases=[
                    {'facts': {'bidder': {'capital': 1000000}}, 'expected': True},
                    {'facts': {'bidder': {'capital': 999999}}, 'expected': False},
                ],
            )
            assert activation['status'] == 'ACTIVE'
            tenants.append((tenant.id, user.id))
            tenders.append((tender.id, tenant.id, user.id))

        # Tenant A and B run independently. Both use the same external identifier.
        results = []
        for tender_id, tenant_id, user_id in tenders:
            user = await db.get(User, user_id)
            # Regression: a parent FOR UPDATE lock must not deadlock the
            # independent transaction that persists the preparation trace.
            result = await asyncio.wait_for(ProcurementService(db, user).run(tender_id), timeout=60)
            results.append((tender_id, tenant_id, result))

        for tender_id, tenant_id, result in results:
            runs = (await db.execute(select(TenderPreparationRun).where(
                TenderPreparationRun.tender_id == tender_id,
                TenderPreparationRun.tenant_id == tenant_id,
            ))).scalars().all()
            assert runs, "No se persistió PreparationRun"
            stages = (await db.execute(select(TenderPreparationStageRun).where(
                TenderPreparationStageRun.preparation_run_id == runs[-1].id,
                TenderPreparationStageRun.tenant_id == tenant_id,
            ))).scalars().all()
            names = {s.stage for s in stages}
            assert {"CONTRACT_POLICY", "LOAD_RULE_INPUTS", "REQUIREMENT_EVALUATION", "MATERIALIZATION", "RISK_ANALYSIS", "CROSS_CONSISTENCY", "VALIDATION_EVIDENCE", "LIFECYCLE_GATE"}.issubset(names)
            # This E2E exercises the preparation engine through its
            # cross-validation boundary. Human QA/review is a later explicit gate.
            assert result["state"] == TenderState.CROSS_VALIDATED.value, result['findings']

        # Cross-tenant lookup must fail at the service boundary.
        user_a = await db.get(User, tenders[0][2])
        service_a = ProcurementService(db, user_a)
        with pytest.raises(Exception):
            await service_a._get(tenders[1][0])

        # Clean up all records created by this test.
        for tenant_id, _, in tenants:
            await db.execute(delete(Tenant).where(Tenant.id == tenant_id))
        await db.commit()
