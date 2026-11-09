from __future__ import annotations

import hashlib
import json
from datetime import datetime, timezone
from typing import Any, Protocol
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.engines.procurement.consistency import ProcurementConsistencyEngine
from app.engines.procurement.materializer import ProcurementMaterializer
from app.engines.procurement.contract_policy import validate_contract_model, ContractPolicyError
from app.engines.procurement.lifecycle import TenderLifecycle, InvalidTenderTransition
from app.engines.procurement.rules import (
    DeterministicRuleRuntime,
    DeterministicRuleCompiler,
    RuleCompilationError,
    CompiledDecisionTable,
)
from app.engines.riesgo.monte_carlo import MotorMonteCarlo, VariableRiesgo
from app.services.procurement.artifact_policy import artifact_submission_eligible

from app.models.procurement import (
    RequirementStatus,
    SubmissionPackage,
    TenderArtifact,
    TenderEvidenceLink,
    TenderPackage,
    TenderRequirement,
    TenderState,
    TenderValidationRun,
    TenderValidationEvidenceLink,
    TenderEvidence,
    TenderRuleDefinition,
    TenderRuleExecution,
)


class _StageTracker(Protocol):
    async def begin_stage(self, stage: str, *, input_refs: dict | None = None, rule_version: str | None = None, engine_version: str | None = None) -> Any: ...
    async def finish_stage(self, *, status: str, output_refs: dict | None = None, error_code: str | None = None, error_detail: str | None = None) -> None: ...


class TenderOrchestrator:
    """Deterministic lifecycle engine for tender preparation.

    Every meaningful phase can optionally emit a durable PreparationStageRun.
    The tracker is infrastructure-only; it never owns procurement-domain state.
    """

    ENGINE_VERSION = "tender-orchestrator-v2"
    RULE_VERSION = "procurement-rules-v2"

    def __init__(self) -> None:
        self.rules = DeterministicRuleRuntime()
        self.rule_compiler = DeterministicRuleCompiler(self.rules)
        self.consistency = ProcurementConsistencyEngine()
        self.materializer = ProcurementMaterializer()
        # OpenL-style compile-once/reuse semantics. The DB stores the source
        # definition + compiled hash; the orchestrator keeps bounded process-local
        # execution plans so requests do not rebuild the same decision table.
        self._compiled_rule_cache: dict[str, Any] = {}

    @staticmethod
    def canonical_hash(model: dict[str, Any]) -> str:
        payload = model
        technical = model.get("technical") if isinstance(model, dict) else None
        if isinstance(technical, dict) and isinstance(technical.get("snapshots"), list):
            payload = dict(model)
            payload["technical"] = dict(technical)
            payload["technical"]["snapshots"] = [
                ({k: v for k, v in snapshot.items() if k != "captured_at"} if isinstance(snapshot, dict) else snapshot)
                for snapshot in technical["snapshots"]
            ]
        data = json.dumps(payload, sort_keys=True, separators=(",", ":"), default=str).encode()
        return hashlib.sha256(data).hexdigest()

    def _compile_rule_definition(self, definition: dict[str, Any], version: int):
        """Compile the correct executable artifact for simple rules or tables."""
        if definition.get("rows") is not None:
            return self.rule_compiler.compile_decision_table(definition, version=version)
        return self.rule_compiler.compile(definition, version=version)

    @staticmethod
    def _serialize_rule_result(result: Any) -> dict[str, Any]:
        if result is None:
            return {}
        payload: dict[str, Any] = {}
        for key in ("rule_id", "table_id", "version", "matched", "message", "error", "selected_row_ids", "actions", "evaluated_conditions", "evaluated_rows"):
            if hasattr(result, key):
                value = getattr(result, key)
                if isinstance(value, tuple):
                    value = list(value)
                payload[key] = value
        return payload

    async def _stage_begin(self, tracker: _StageTracker | None, stage: str, **refs: Any) -> None:
        if tracker is not None:
            await tracker.begin_stage(
                stage,
                input_refs=refs,
                rule_version=self.RULE_VERSION,
                engine_version=self.ENGINE_VERSION,
            )

    async def _stage_pass(self, tracker: _StageTracker | None, **refs: Any) -> None:
        if tracker is not None:
            await tracker.finish_stage(status="PASS", output_refs=refs)

    async def _stage_fail(self, tracker: _StageTracker | None, *, code: str, detail: str) -> None:
        if tracker is not None:
            await tracker.finish_stage(status="FAILED", error_code=code, error_detail=detail)

    async def run(
        self,
        db: AsyncSession,
        tender: TenderPackage,
        *,
        tracker: _StageTracker | None = None,
    ) -> dict[str, Any]:
        model = dict(tender.canonical_model or {})
        facts = model.get("facts", {})
        model_hash_before = self.canonical_hash(model)

        # Stage 1: contract configuration / policy.
        await self._stage_begin(tracker, "CONTRACT_POLICY", tender_id=str(tender.id), revision=tender.current_revision, model_hash=model_hash_before)
        try:
            try:
                policy = validate_contract_model(
                    tender.contract_type,
                    model.get("economic", {}),
                    model.get("schedule", {}),
                    facts,
                )
            except ContractPolicyError as exc:
                policy = None
                findings_seed = [{"code": "CONTRACT_POLICY", "severity": "BLOCKER", "message": str(exc)}]
            else:
                findings_seed = []
            await self._stage_pass(tracker, policy=policy.contract_type if policy else None, blocking_seed_count=len(findings_seed))
        except Exception as exc:
            await self._stage_fail(tracker, code=type(exc).__name__, detail=str(exc))
            raise

        # Stage 2: load requirements + evidence, tenant-scoped at every query.
        await self._stage_begin(tracker, "LOAD_RULE_INPUTS", tender_id=str(tender.id), revision=tender.current_revision)
        try:
            requirements = (
                await db.execute(
                    select(TenderRequirement).where(
                        TenderRequirement.tender_id == tender.id,
                        TenderRequirement.tenant_id == tender.tenant_id,
                    )
                )
            ).scalars().all()
            links = (
                await db.execute(
                    select(TenderEvidenceLink).where(
                        TenderEvidenceLink.tender_id == tender.id,
                        TenderEvidenceLink.tenant_id == tender.tenant_id,
                    )
                )
            ).scalars().all()
            evidence_rows = (
                await db.execute(
                    select(TenderEvidence).where(
                        TenderEvidence.tender_id == tender.id,
                        TenderEvidence.tenant_id == tender.tenant_id,
                        TenderEvidence.status == "ACTIVE",
                    )
                )
            ).scalars().all()
            evidence_by_id = {str(row.id): row for row in evidence_rows}
            links_by_requirement: dict[str, list[Any]] = {}
            for link in links:
                if link.requirement_id:
                    links_by_requirement.setdefault(str(link.requirement_id), []).append(link)
            await self._stage_pass(
                tracker,
                requirement_count=len(requirements),
                evidence_count=len(evidence_rows),
                requirement_link_count=len(links),
            )
        except Exception as exc:
            await self._stage_fail(tracker, code=type(exc).__name__, detail=str(exc))
            raise

        findings: list[dict[str, Any]] = list(findings_seed)
        now = datetime.now(timezone.utc).isoformat()
        model["requirements"] = []
        if policy is not None:
            model.setdefault("economic", {})["contract_policy"] = {
                "type": policy.contract_type,
                "required_components": list(policy.required_components),
            }

        # Stage 3: evaluate deterministic requirements and their evidence.
        await self._stage_begin(tracker, "REQUIREMENT_EVALUATION", requirement_count=len(requirements))
        try:
            requirement_results: list[dict[str, Any]] = []
            rule_executions: list[dict[str, Any]] = []
            facts_hash = self.canonical_hash(facts)
            for req in requirements:
                condition = req.condition or {}
                result = None
                rule_definition = None
                execution_status = "BLOCKED"
                execution_error = None
                if condition.get("conditions") or condition.get("rows"):
                    try:
                        rule_definition = await self._ensure_rule_definition(db, tender, req, condition)
                        compiled = self._compile_rule_definition(rule_definition.definition, rule_definition.version)
                        if rule_definition.compiled_hash != compiled.compiled_hash:
                            execution_error = "RULE-HASH-MISMATCH"
                            findings.append({
                                "code": f"RULE-HASH-MISMATCH:{req.code}",
                                "requirement_id": str(req.id),
                                "severity": "BLOCKER",
                                "message": f"La definición de {req.code} v{rule_definition.version} no coincide con su hash compilado; requiere nueva versión.",
                            })
                        elif rule_definition.status != "ACTIVE":
                            execution_error = "RULE-NOT-ACTIVE"
                            findings.append({
                                "code": f"RULE-NOT-ACTIVE:{req.code}",
                                "requirement_id": str(req.id),
                                "severity": "BLOCKER",
                                "message": f"La regla {req.code} v{rule_definition.version} no está activa; debe pasar su gate de pruebas.",
                            })
                        else:
                            result = self._evaluate_compiled_definition(
                                compiled.source_definition if isinstance(compiled, CompiledDecisionTable) else compiled.definition,
                                compiled.compiled_hash,
                                facts,
                            )
                            execution_status = "PASS" if getattr(result, "matched", False) else "FAIL"
                            if getattr(result, "error", None):
                                execution_error = "DECISION_CONFLICT" if str(result.error).startswith("DECISION_CONFLICT") else "DECISION_MISS" if str(result.error).startswith("DECISION_MISS") else str(result.error)
                                execution_status = "CONFLICT" if execution_error == "DECISION_CONFLICT" else "NO_MATCH" if execution_error == "DECISION_MISS" else "ERROR"
                    except (RuleCompilationError, ValueError, TypeError) as exc:
                        execution_error = "RULE-RUNTIME"
                        execution_status = "ERROR"
                        findings.append({
                            "code": f"RULE-RUNTIME:{req.code}",
                            "requirement_id": str(req.id),
                            "severity": "BLOCKER",
                            "message": str(exc),
                        })

                if condition.get("conditions") or condition.get("rows"):
                    result_payload = self._serialize_rule_result(result)
                    rule_executions.append({
                        "requirement_id": req.id,
                        "rule_definition_id": rule_definition.id if rule_definition else None,
                        "rule_code": req.code,
                        "rule_version": rule_definition.version if rule_definition else None,
                        "compiled_hash": rule_definition.compiled_hash if rule_definition else None,
                        "source_reference": rule_definition.source_reference if rule_definition else {},
                        "execution_status": execution_status,
                        "matched": getattr(result, "matched", None),
                        "input_facts_hash": facts_hash,
                        "input_facts": facts,
                        "hit_policy": rule_definition.definition.get("hit_policy") if rule_definition else None,
                        "selected_row_ids": result_payload.get("selected_row_ids", []),
                        "evaluated_conditions": result_payload.get("evaluated_conditions", result_payload.get("evaluated_rows", [])),
                        "actions": result_payload.get("actions", []),
                        "result_payload": result_payload,
                        "error_code": execution_error,
                        "revision": tender.current_revision,
                        "executed_at": now,
                    })
                linked_evidence_ids = [
                    str(link.evidence_id)
                    for link in links_by_requirement.get(str(req.id), [])
                    if str(link.evidence_id) in evidence_by_id
                ]
                evidence_ok, evidence_message = self._validate_evidence_requirement(
                    req,
                    links_by_requirement.get(str(req.id), []),
                    evidence_by_id,
                )
                rule_blocked = bool(execution_error) or (rule_definition is not None and rule_definition.status != "ACTIVE")
                result_matched = bool(result.matched) if result is not None else False
                passed = result_matched and evidence_ok and not rule_blocked
                req.evaluated_at = now
                if passed:
                    req.status = RequirementStatus.PASS.value
                elif req.mandatory:
                    req.status = RequirementStatus.FAIL.value
                    if result is not None and hasattr(result, "message"):
                        message = result.message
                    elif result is not None and getattr(result, "error", None):
                        message = result.error
                    elif execution_error:
                        message = f"Ejecución de regla bloqueada: {execution_error}."
                    else:
                        message = evidence_message or "El requisito no pudo demostrar cumplimiento."
                    findings.append({
                        "code": req.code,
                        "requirement_id": str(req.id),
                        "severity": req.severity,
                        "message": message,
                        "evidence_ids": linked_evidence_ids,
                    })
                else:
                    req.status = RequirementStatus.UNKNOWN.value
                model["requirements"].append(
                    {
                        "id": str(req.id),
                        "code": req.code,
                        "category": req.category,
                        "mandatory": req.mandatory,
                        "status": req.status,
                    }
                )
                requirement_results.append({"code": req.code, "status": req.status, "evidence_ids": linked_evidence_ids})

            project_type = str(facts.get("project_type") or tender.project_type or "").upper()
            if project_type == "REMODELING":
                remodel = facts.get("remodeling", {})
                if remodel.get("separate_acquisitions") is True and not remodel.get("classification_basis"):
                    findings.append({
                        "code": "REMODELING-CLASSIFICATION",
                        "severity": "BLOCKER",
                        "message": "La remodelación declara adquisiciones separadas pero no aporta fundamento de clasificación jurídica; debe determinarse el régimen aplicable antes de continuar.",
                    })
                elif not remodel.get("existing_conditions_source"):
                    findings.append({
                        "code": "REMODELING-EXISTING-CONDITIONS",
                        "severity": "BLOCKER",
                        "message": "La remodelación requiere evidencia de condiciones existentes (levantamiento, planos, diagnóstico o fuente equivalente) antes de cerrar cuantificación y programa.",
                    })
            await self._stage_pass(tracker, evaluated=requirement_results, findings_added=len(findings) - len(findings_seed))
        except Exception as exc:
            await self._stage_fail(tracker, code=type(exc).__name__, detail=str(exc))
            raise

        # Stage 4: materialization of linked domain data.
        if policy is not None:
            await self._stage_begin(tracker, "MATERIALIZATION", tender_id=str(tender.id), expediente_id=str(tender.expediente_id))
            try:
                # CORREGIDO 2026-08-30 (verificado antes de tocar: materialize()
                # exige tenant_id como keyword-only en materializer.py:29, esta
                # llamada no lo pasaba -- TypeError garantizado en cualquier
                # ejecución real que llegue a esta etapa con policy configurada.
                # El test estático test_materializer_requires_tenant_context()
                # solo comprueba que el texto "tenant_id: UUID" aparece en
                # materializer.py -- nunca cruza eso contra esta llamada, por
                # eso pasaba en verde con el bug presente.
                model = await self.materializer.materialize(
                    db, tender.id, tender.expediente_id, model, tenant_id=tender.tenant_id,
                )
                await self._stage_pass(tracker, model_hash=self.canonical_hash(model))
            except Exception as exc:
                await self._stage_fail(tracker, code=type(exc).__name__, detail=str(exc))
                raise

        # Stage 5: deterministic risk analysis when configured.
        risk = model.get("risk")
        await self._stage_begin(tracker, "RISK_ANALYSIS", enabled=bool(risk))
        try:
            if risk:
                variables = [VariableRiesgo(**v) for v in risk.get("variables", [])]
                if variables and risk.get("seed") is None:
                    findings.append({
                        "code": "RISK-SEED-REQUIRED",
                        "severity": "BLOCKER",
                        "message": "Los escenarios de riesgo requieren una semilla explícita para garantizar reproducibilidad.",
                    })
                if variables and risk.get("seed") is not None:
                    simulation = MotorMonteCarlo(
                        seed=risk.get("seed"),
                        chunk_size=int(risk.get("chunk_size", 50_000)),
                    ).simular_presupuesto(
                        presupuesto_base=float(model.get("economic", {}).get("budget_total", 0)),
                        variables=variables,
                        iteraciones=int(risk.get("iterations", 10_000)),
                        presupuesto_maximo=risk.get("budget_maximum"),
                        plazo_base=model.get("schedule", {}).get("duration_days"),
                        plazo_maximo=risk.get("schedule_maximum_days"),
                        confidence_level=float(risk.get("confidence_level", 0.95)),
                        correlaciones=risk.get("correlations"),
                    )
                    model["risk"]["simulation"] = simulation.to_dict()
            await self._stage_pass(tracker, simulated=bool(risk and model.get("risk", {}).get("simulation")))
        except Exception as exc:
            await self._stage_fail(tracker, code=type(exc).__name__, detail=str(exc))
            raise

        # Stage 6: cross-domain consistency engine.
        await self._stage_begin(tracker, "CROSS_CONSISTENCY", model_hash=self.canonical_hash(model))
        try:
            consistency_findings = self.consistency.validate(model)
            findings.extend(consistency_findings)
            await self._stage_pass(
                tracker,
                model_hash=self.canonical_hash(model),
                findings_count=len(consistency_findings),
                blocking_count=sum(1 for f in consistency_findings if f.get("severity") in {"BLOCKER", "P0"}),
            )
        except Exception as exc:
            await self._stage_fail(tracker, code=type(exc).__name__, detail=str(exc))
            raise

        # Persist one forensic execution record per deterministic rule before
        # validation findings; validation_run_id is linked after the finding row exists.
        execution_rows: list[tuple[Any, dict[str, Any]]] = []
        for execution in rule_executions:
            row = TenderRuleExecution(
                tender_id=tender.id,
                tenant_id=tender.tenant_id,
                requirement_id=execution["requirement_id"],
                rule_definition_id=execution["rule_definition_id"],
                rule_code=execution["rule_code"],
                rule_version=execution["rule_version"],
                compiled_hash=execution["compiled_hash"],
                source_reference=execution["source_reference"],
                engine_version=self.RULE_VERSION,
                execution_status=execution["execution_status"],
                matched=execution["matched"],
                input_facts_hash=execution["input_facts_hash"],
                input_facts=execution["input_facts"],
                hit_policy=execution["hit_policy"],
                selected_row_ids=execution["selected_row_ids"],
                evaluated_conditions=execution["evaluated_conditions"],
                actions=execution["actions"],
                result_payload=execution["result_payload"],
                error_code=execution["error_code"],
                revision=execution["revision"],
                executed_at=execution["executed_at"],
                creado_por_id=tender.creado_por_id,
                actualizado_por_id=tender.actualizado_por_id,
            )
            db.add(row)
            execution_rows.append((row, execution))
        if execution_rows:
            await db.flush()

        # Stage 7: persist validation runs and concrete evidence links.
        revision = tender.current_revision
        model_hash = self.canonical_hash(model)
        await self._stage_begin(tracker, "VALIDATION_EVIDENCE", finding_count=len(findings), revision=revision)
        try:
            validation_run_ids: list[str] = []
            for finding in findings:
                evidence_ids = [str(x) for x in finding.get("evidence_ids", [])]
                if not evidence_ids:
                    evidence = await self._get_or_create_validation_evidence(
                        db,
                        tender=tender,
                        revision=revision,
                        model_hash=model_hash,
                        finding=finding,
                    )
                    evidence_ids = [str(evidence.id)]
                validation = TenderValidationRun(
                    tender_id=tender.id,
                    engine="procurement_orchestrator",
                    status="FAIL",
                    severity=finding["severity"],
                    rule_id=finding["code"],
                    message=finding["message"],
                    evidence={"revision": revision, "model_hash": model_hash, "evidence_ids": evidence_ids},
                    revision=revision,
                    tenant_id=tender.tenant_id,
                    creado_por_id=tender.creado_por_id,
                    actualizado_por_id=tender.actualizado_por_id,
                )
                db.add(validation)
                await db.flush()
                finding_requirement_id = finding.get("requirement_id")
                if finding_requirement_id:
                    for execution_row, execution in execution_rows:
                        if str(execution["requirement_id"]) == str(finding_requirement_id):
                            execution_row.validation_run_id = validation.id
                            break
                for evidence_id in evidence_ids:
                    db.add(TenderValidationEvidenceLink(
                        validation_run_id=validation.id,
                        evidence_id=UUID(evidence_id),
                        relation="SUPPORTS",
                        tenant_id=tender.tenant_id,
                    ))
                validation_run_ids.append(str(validation.id))
            await db.flush()
            await self._stage_pass(tracker, validation_run_ids=validation_run_ids, evidence_count=sum(len(f.get("evidence_ids", [])) or 1 for f in findings))
        except Exception as exc:
            await self._stage_fail(tracker, code=type(exc).__name__, detail=str(exc))
            raise

        # Stage 8: domain lifecycle gate. This intentionally does not replace the service's own state machine.
        await self._stage_begin(tracker, "LIFECYCLE_GATE", current_state=tender.state, finding_count=len(findings))
        try:
            tender.canonical_model = model
            if findings:
                try:
                    tender.state = TenderLifecycle.transition(tender.state, TenderState.BLOCKED.value)
                except InvalidTenderTransition:
                    if tender.state not in {
                        TenderState.QA_READY.value, TenderState.READY_FOR_HUMAN_REVIEW.value,
                        TenderState.HUMAN_APPROVAL.value, TenderState.SIGNED.value,
                        TenderState.SUBMISSION_READY.value, TenderState.SUBMITTED.value,
                        TenderState.ARCHIVED.value, TenderState.BLOCKED.value,
                    }:
                        raise
            elif tender.state == TenderState.DOCUMENTS_READY.value:
                tender.state = TenderLifecycle.transition(tender.state, TenderState.CROSS_VALIDATED.value)
            elif tender.state == TenderState.CROSS_VALIDATED.value:
                tender.state = tender.state
            elif tender.state == TenderState.QA_READY.value:
                tender.state = TenderLifecycle.transition(tender.state, TenderState.READY_FOR_HUMAN_REVIEW.value)
            elif tender.state == TenderState.READY_FOR_HUMAN_REVIEW.value:
                tender.state = tender.state
            await self._stage_pass(tracker, resulting_state=tender.state, model_hash=model_hash)
        except Exception as exc:
            await self._stage_fail(tracker, code=type(exc).__name__, detail=str(exc))
            raise

        return {
            "state": tender.state,
            "revision": revision,
            "findings": findings,
            "model_hash": model_hash,
        }

    def _evaluate_compiled_definition(self, definition: dict[str, Any], compiled_hash: str, facts: dict[str, Any]):
        """Evaluate a compiled definition through the same cached executable plan.

        The database remains the source of truth; this cache is only an execution
        optimization and is keyed by the immutable compiled hash.
        """
        plan = self._compiled_rule_cache.get(compiled_hash)
        if plan is None:
            if definition.get("rows"):
                plan = self.rule_compiler.compile_decision_table(
                    definition, version=int(definition.get("version", 1))
                )
            else:
                plan = self.rule_compiler.compile(
                    definition, version=int(definition.get("version", 1))
                )
            if len(self._compiled_rule_cache) >= 256:
                # Bounded cache: compilation is cheap compared with retaining an
                # unbounded number of tenant/user supplied rule plans.
                self._compiled_rule_cache.clear()
            self._compiled_rule_cache[compiled_hash] = plan

        if isinstance(plan, CompiledDecisionTable):
            decision = self.rules.evaluate_decision_table(plan, facts)
            return decision
        return self.rules.evaluate(plan.definition, facts)

    async def _ensure_rule_definition(self, db: AsyncSession, tender: TenderPackage, req: TenderRequirement, condition: dict[str, Any]) -> TenderRuleDefinition:
        current = None
        if req.rule_definition_id:
            current = await db.scalar(select(TenderRuleDefinition).where(
                TenderRuleDefinition.id == req.rule_definition_id,
                TenderRuleDefinition.tenant_id == tender.tenant_id,
                TenderRuleDefinition.tender_id == tender.id,
            ))
        if current is not None:
            return current
        definition = {
            "id": req.code,
            "message": condition.get("message", req.description),
            "severity": req.severity,
            "logic": condition.get("logic", "ALL"),
            "conditions": condition.get("conditions", []),
        }
        if condition.get("rows"):
            definition = {
                "id": req.code,
                "version": 1,
                "hit_policy": condition.get("hit_policy", "FIRST"),
                "rows": condition.get("rows", []),
            }
            compiled = self.rule_compiler.compile_decision_table(definition, version=1)
            compiled_definition = compiled.source_definition
        else:
            compiled = self.rule_compiler.compile(definition, version=1)
            compiled_definition = compiled.definition
        row = TenderRuleDefinition(
            tender_id=tender.id, tenant_id=tender.tenant_id, requirement_id=req.id, code=req.code, version=1,
            status="DRAFT", definition=compiled_definition, test_cases=[], compiled_hash=compiled.compiled_hash,
            source_reference=req.source_reference or {}, creado_por_id=tender.creado_por_id, actualizado_por_id=tender.actualizado_por_id,
        )
        db.add(row)
        await db.flush()
        req.rule_definition_id = row.id
        return row

    @staticmethod
    async def _get_or_create_validation_evidence(
        db: AsyncSession,
        *,
        tender: TenderPackage,
        revision: int,
        model_hash: str,
        finding: dict[str, Any],
    ) -> TenderEvidence:
        subject = f"VALIDATION:{finding['code']}@r{revision}"
        existing = await db.scalar(select(TenderEvidence).where(
            TenderEvidence.tender_id == tender.id,
            TenderEvidence.tenant_id == tender.tenant_id,
            TenderEvidence.kind == "CALCULATION",
            TenderEvidence.subject == subject,
            TenderEvidence.source_hash == model_hash,
            TenderEvidence.status == "ACTIVE",
        ))
        if existing is not None:
            return existing
        evidence = TenderEvidence(
            tender_id=tender.id,
            tenant_id=tender.tenant_id,
            kind="CALCULATION",
            subject=subject,
            value={
                "engine": "TenderOrchestrator",
                "finding_code": finding["code"],
                "severity": finding["severity"],
                "message": finding["message"],
                "model_hash": model_hash,
                "revision": revision,
            },
            source_hash=model_hash,
            source_revision=revision,
            creado_por_id=tender.creado_por_id,
            actualizado_por_id=tender.actualizado_por_id,
        )
        db.add(evidence)
        await db.flush()
        return evidence

    @staticmethod
    def _validate_evidence_requirement(req: Any, links: list[Any], evidence_by_id: dict[str, Any]) -> tuple[bool, str]:
        specifications = req.evidence_required or []
        if not specifications:
            return True, ""
        linked = [evidence_by_id.get(str(link.evidence_id)) for link in links]
        linked = [item for item in linked if item is not None]
        for specification in specifications:
            if isinstance(specification, str):
                match = any(
                    item.kind == specification or item.subject == specification or specification.lower() in item.subject.lower()
                    for item in linked
                )
            else:
                kind = specification.get("kind")
                subject = specification.get("subject")
                match = any(
                    (kind is None or item.kind == kind) and
                    (subject is None or subject.lower() in item.subject.lower())
                    for item in linked
                )
            if not match:
                return False, f"Falta evidencia requerida para {req.code}: {specification}"
        return True, ""

    async def build_submission(self, db: AsyncSession, tender: TenderPackage) -> SubmissionPackage:
        if tender.state not in {
            TenderState.CROSS_VALIDATED.value,
            TenderState.QA_READY.value,
            TenderState.HUMAN_APPROVAL.value,
        }:
            raise ValueError("El expediente no ha superado validación cruzada.")
        artifacts_all = (
            await db.execute(
                select(TenderArtifact).where(
                    TenderArtifact.tender_id == tender.id,
                    TenderArtifact.tenant_id == tender.tenant_id,
                    TenderArtifact.status != "SUPERSEDED",
                )
            )
        ).scalars().all()
        artifacts = [artifact for artifact in artifacts_all if artifact_submission_eligible(artifact)]
        if not artifacts:
            raise ValueError("No existen artefactos elegibles para construir el paquete de presentación.")
        manifest = {
            "tender_id": str(tender.id),
            "revision": tender.current_revision,
            "artifacts": [
                {
                    "code": artifact.artifact_code,
                    "version": artifact.version,
                    "hash": artifact.content_hash,
                    "path": artifact.storage_path,
                }
                for artifact in artifacts
            ],
            "canonical_model_hash": self.canonical_hash(tender.canonical_model),
        }
        package_hash = hashlib.sha256(
            json.dumps(manifest, sort_keys=True, separators=(",", ":")).encode()
        ).hexdigest()
        submission = SubmissionPackage(
            tender_id=tender.id,
            revision=tender.current_revision,
            manifest=manifest,
            package_hash=package_hash,
            status="READY",
            tenant_id=tender.tenant_id,
            creado_por_id=tender.creado_por_id,
            actualizado_por_id=tender.actualizado_por_id,
        )
        db.add(submission)
        return submission
