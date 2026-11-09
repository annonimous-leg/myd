from __future__ import annotations

from datetime import datetime
from decimal import Decimal
from typing import Any
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.core.errors import ErrorCode, MegalodonException
from app.engines.costos.motor_costeo import ConceptoCosteo, InsumoCosteo, MotorCosteo, PartidaCosteo, PresupuestoCosteo
from app.engines.costos.parametros import FuenteParametrosCosteo, ParametrosCosteoSnapshot
from app.engines.programacion.cpm import Actividad, MotorCPM, TipoActividad
from app.models.expediente import ExpedienteObra
from app.models.presupuesto import Presupuesto, Partida, Concepto, Insumo
from app.models.programacion import ActividadPrograma, ProgramaObra
from app.models.bim import ElementoBIM, ModeloBIM
from app.models.topografia import CalculoVolumen
from app.engines.procurement.domain_contracts import DomainSnapshot, make_reference, source_revision_token

_MATERIALIZER_ENGINE_VERSION = "materializer@2026-08-30"


class ProcurementMaterializer:
    """Binds Procurement's canonical model to existing production entities."""

    def __init__(self) -> None:
        self.cost_engine = MotorCosteo()
        self.cpm = MotorCPM()

    async def materialize(self, db: AsyncSession, tender_id: UUID, expediente_id: UUID, canonical: dict[str, Any], *, tenant_id: UUID) -> dict[str, Any]:
        expediente = await db.scalar(select(ExpedienteObra).where(ExpedienteObra.id == expediente_id, ExpedienteObra.tenant_id == tenant_id))
        if expediente is None:
            raise MegalodonException(ErrorCode.DOCUMENTO_NO_ENCONTRADO, "Expediente asociado no encontrado.", 404)
        canonical = await self._attach_quantification_sources(db, expediente_id, canonical, tenant_id=tenant_id)
        if canonical.get("economic", {}).get("partidas"):
            budget = await self._materialize_budget(db, expediente, tender_id, canonical, tenant_id=tenant_id)
            canonical.setdefault("integration", {})["presupuesto_id"] = str(budget.id)
        schedule = canonical.get("schedule", {})
        if schedule.get("activities"):
            program = await self._materialize_schedule(db, expediente, tender_id, canonical, tenant_id=tenant_id)
            canonical.setdefault("integration", {})["programa_id"] = str(program.id)
        return canonical

    async def _attach_quantification_sources(self, db: AsyncSession, expediente_id: UUID, canonical: dict[str, Any], *, tenant_id: UUID) -> dict[str, Any]:
        technical = dict(canonical.get("technical", {}))
        sources = []
        # DomainSnapshot por recurso origen (uno por ModeloBIM, uno por
        # CalculoVolumen) -- ver domain_contracts.py. Vive junto a
        # `quantification_sources` (que no se toca, nada más lo consume
        # hoy fuera de este método) en vez de reemplazarlo, para no
        # arriesgar un consumidor que no haya encontrado con grep.
        snapshots: list[dict[str, Any]] = []

        bim_model_id = technical.get("bim_model_id")
        if bim_model_id:
            try:
                bim_uuid = UUID(str(bim_model_id))
            except ValueError as exc:
                raise MegalodonException(ErrorCode.PARAMETRO_INVALIDO, "technical.bim_model_id no es un UUID válido.", 422) from exc
            modelo = await db.scalar(
                select(ModeloBIM).where(ModeloBIM.id == bim_uuid, ModeloBIM.tenant_id == tenant_id)
            )
            elements = (await db.execute(
                select(ElementoBIM)
                .join(ModeloBIM, ElementoBIM.modelo_id == ModeloBIM.id)
                .where(ElementoBIM.modelo_id == bim_uuid)
                .where(ModeloBIM.expediente_id == expediente_id)
                .where(ModeloBIM.tenant_id == tenant_id)
            )).scalars().all()
            if not elements:
                raise MegalodonException(ErrorCode.BIM_ERROR, "El Modelo BIM indicado no contiene elementos cuantificados.", 422)
            bim_snapshot_rows = []
            for element in elements:
                quantity = element.volumen if element.volumen is not None else element.area
                if quantity is None:
                    quantity = element.longitud
                if quantity is None:
                    continue
                row = {
                    "provider": "BIM", "element_id": str(element.id), "global_id": element.global_id,
                    "type": element.tipo, "quantity": float(quantity), "unit": element.unidad,
                    "source": element.fuente_volumen if element.volumen is not None else element.fuente_area,
                    "partida_id": str(element.partida_id) if element.partida_id else None,
                }
                sources.append(row)
                bim_snapshot_rows.append(row)
            if bim_snapshot_rows:
                snapshots.append(DomainSnapshot(
                    source=make_reference(
                        "BIM_MODEL", bim_uuid, tenant_id,
                        revision=source_revision_token(modelo.updated_at, modelo.version_ifc) if modelo else None,
                        content_hash=None,  # ModeloBIM no calcula un hash de contenido todavía
                    ),
                    snapshot={"elements": bim_snapshot_rows},
                    engine_version=_MATERIALIZER_ENGINE_VERSION,
                ).to_dict())

        volume_ids = technical.get("calculo_volumen_ids", [])
        if volume_ids:
            parsed = []
            for value in volume_ids:
                try:
                    parsed.append(UUID(str(value)))
                except ValueError as exc:
                    raise MegalodonException(ErrorCode.PARAMETRO_INVALIDO, "calculo_volumen_ids contiene un UUID inválido.", 422) from exc
            volumes = (await db.execute(
                select(CalculoVolumen).where(
                    CalculoVolumen.id.in_(parsed),
                    CalculoVolumen.expediente_id == expediente_id,
                    CalculoVolumen.expediente_id.in_(select(ExpedienteObra.id).where(ExpedienteObra.id == expediente_id, ExpedienteObra.tenant_id == tenant_id)),
                )
            )).scalars().all()
            if len(volumes) != len(parsed):
                raise MegalodonException(ErrorCode.TOPOGRAFIA_ERROR, "Uno o más cálculos de volumen no pertenecen al expediente.", 422)
            for volume in volumes:
                row = {
                    "provider": "TOPOGRAFIA", "calculo_volumen_id": str(volume.id),
                    "corte_m3": float(volume.volumen_corte_m3), "terraplen_m3": float(volume.volumen_terraplen_m3),
                    "neto_m3": float(volume.volumen_neto_m3), "area_m2": float(volume.area_analizada_m2),
                    "partida_id": str(volume.partida_id) if volume.partida_id else None,
                }
                sources.append(row)
                snapshots.append(DomainSnapshot(
                    source=make_reference(
                        "TOPOGRAFIA_VOLUMEN",
                        volume.id,
                        tenant_id,
                        revision=source_revision_token(volume.updated_at),
                        content_hash=None,
                    ),
                    snapshot=row,
                    engine_version=_MATERIALIZER_ENGINE_VERSION,
                ).to_dict())

        if sources:
            canonical.setdefault("technical", {})["quantification_sources"] = sources
        if snapshots:
            canonical.setdefault("technical", {})["snapshots"] = snapshots
        return canonical

    def _cost_model(self, canonical: dict[str, Any]) -> PresupuestoCosteo:
        economic = canonical.get("economic", {})
        if economic.get("partidas"):
            required = ("factor_indirecto", "factor_utilidad", "factor_impuesto", "factor_riesgo", "source")
            missing = [key for key in required if economic.get(key) is None]
            if not str(economic.get("source") or "").strip():
                missing = sorted(set([*missing, "source"]))
            if missing:
                raise MegalodonException(
                    ErrorCode.PARAMETRO_INVALIDO,
                    "El modelo económico tiene partidas sin parámetros trazables: " + ", ".join(missing),
                    422,
                )
        partidas: list[PartidaCosteo] = []
        for row in economic.get("partidas", []):
            concepts: list[ConceptoCosteo] = []
            for concept in row.get("conceptos", []):
                insumos = [
                    InsumoCosteo(
                        clave=str(item["clave"]),
                        descripcion=str(item["descripcion"]),
                        tipo=str(item["tipo"]),
                        unidad=str(item["unidad"]),
                        cantidad=Decimal(str(item["cantidad"])),
                        precio_unitario=Decimal(str(item["precio_unitario"])),
                        rendimiento=Decimal(str(item.get("rendimiento", 1))),
                    )
                    for item in concept.get("insumos", [])
                ]
                concepts.append(
                    ConceptoCosteo(
                        clave=str(concept["clave"]),
                        descripcion=str(concept["descripcion"]),
                        unidad=str(concept["unidad"]),
                        cantidad=Decimal(str(concept.get("cantidad", 1))),
                        insumos=insumos,
                    )
                )
            partidas.append(
                PartidaCosteo(
                    numero=int(row["numero"]),
                    descripcion=str(row["descripcion"]),
                    unidad=str(row["unidad"]),
                    cantidad=Decimal(str(row["cantidad"])),
                    conceptos=concepts,
                    precio_unitario_manual=(
                        Decimal(str(row["precio_unitario_manual"]))
                        if row.get("precio_unitario_manual") is not None else None
                    ),
                )
            )
        return PresupuestoCosteo(
            identificador=str(canonical["identifier"]),
            nombre=str(canonical["title"]),
            partidas=partidas,
            parametros=ParametrosCosteoSnapshot(
                factor_indirecto=Decimal(str(economic["factor_indirecto"])),
                factor_utilidad=Decimal(str(economic["factor_utilidad"])),
                factor_impuesto=Decimal(str(economic["factor_impuesto"])),
                factor_riesgo=Decimal(str(economic["factor_riesgo"])),
                fuente=FuenteParametrosCosteo.TENDER_SNAPSHOT,
                referencia=f"{canonical['identifier']}:{economic['source']}",
                jurisdiccion=canonical.get("jurisdiction_code"),
                evidencia={"economic_source": economic["source"]},
            ),
        )

    async def _materialize_budget(self, db: AsyncSession, expediente: ExpedienteObra, tender_id: UUID, canonical: dict[str, Any], *, tenant_id: UUID) -> Presupuesto:
        model = self._cost_model(canonical)
        self.cost_engine.calcular_presupuesto(model)
        identifier = f"LIC-{canonical['identifier']}"
        budget = await db.scalar(
            select(Presupuesto)
            .where(Presupuesto.expediente_id == expediente.id, Presupuesto.identificador == identifier)
            .join(ExpedienteObra, Presupuesto.expediente_id == ExpedienteObra.id)
            .where(ExpedienteObra.tenant_id == tenant_id)
            .options(selectinload(Presupuesto.partidas).selectinload(Partida.conceptos).selectinload(Concepto.insumos))
        )
        if budget is None:
            budget = Presupuesto(
                tenant_id=tenant_id,
                identificador=identifier,
                nombre=str(canonical["title"]),
                expediente_id=expediente.id,
                estado="CALCULADO",
                factor_indirecto=model.factor_indirecto,
                factor_utilidad=model.factor_utilidad,
                factor_impuesto=model.factor_impuesto,
                factor_riesgo=model.factor_riesgo,
                metadatos={"parametros_costeo": model.parametros.to_dict()},
                partidas=[],
            )
            db.add(budget)
            await db.flush()
        budget.partidas.clear()
        for p in model.partidas:
            partida = Partida(
                tenant_id=tenant_id,
                numero=p.numero, descripcion=p.descripcion, unidad=p.unidad,
                cantidad=p.cantidad, precio_unitario=p.precio_unitario, importe=p.importe,
                presupuesto=budget,
            )
            for c in p.conceptos:
                concepto = Concepto(
                    tenant_id=tenant_id,
                    clave=c.clave, descripcion=c.descripcion, unidad=c.unidad, cantidad=c.cantidad,
                    costo_directo_unitario=c.costo_directo_unitario, partida=partida,
                )
                for item in c.insumos:
                    concepto.insumos.append(Insumo(
                        tenant_id=tenant_id,
                        clave=item.clave, descripcion=item.descripcion, tipo=item.tipo, unidad=item.unidad,
                        cantidad=item.cantidad, precio_unitario=item.precio_unitario, importe=item.importe,
                        rendimiento=item.rendimiento, concepto=concepto,
                    ))
                partida.conceptos.append(concepto)
            budget.partidas.append(partida)
        budget.monto_directo = model.monto_directo
        budget.monto_indirecto = model.monto_indirecto
        budget.monto_utilidad = model.monto_utilidad
        budget.monto_riesgo = model.monto_riesgo
        budget.monto_impuesto = model.monto_impuesto
        budget.monto_total = model.monto_total
        budget.factor_indirecto = model.factor_indirecto
        budget.factor_utilidad = model.factor_utilidad
        budget.factor_impuesto = model.factor_impuesto
        budget.factor_riesgo = model.factor_riesgo
        budget.plazo_dias = canonical.get("schedule", {}).get("duration_days")
        budget.metadatos = {
            "procurement": {"tender_id": str(tender_id)},
            "parametros_costeo": model.parametros.to_dict(),
        }
        budget.resultado_determinista = {
            "tender_id": str(tender_id),
            "engine": "MotorCosteo",
            "model": model.to_dict(),
        }
        economic = canonical.setdefault("economic", {})
        economic.update({
            "budget_total": float(model.monto_total),
            "direct_cost": float(model.monto_directo),
            "indirect_cost": float(model.monto_indirecto),
            "profit": float(model.monto_utilidad),
            "risk": float(model.monto_riesgo),
            "tax": float(model.monto_impuesto),
            "partidas": model.to_dict().get("partidas", []),
        })
        return budget

    async def _materialize_schedule(self, db: AsyncSession, expediente: ExpedienteObra, tender_id: UUID, canonical: dict[str, Any], *, tenant_id: UUID) -> ProgramaObra:
        schedule = canonical["schedule"]
        start = datetime.fromisoformat(str(schedule["start_date"]).replace("Z", "+00:00"))
        identifier = f"LIC-{canonical['identifier']}"
        program = await db.scalar(select(ProgramaObra).join(ExpedienteObra, ProgramaObra.expediente_id == ExpedienteObra.id).where(ProgramaObra.expediente_id == expediente.id, ProgramaObra.identificador == identifier, ExpedienteObra.tenant_id == tenant_id).options(selectinload(ProgramaObra.actividades)))
        if program is None:
            program = ProgramaObra(
                tenant_id=tenant_id,
                identificador=identifier,
                nombre=str(canonical["title"]),
                expediente_id=expediente.id,
                fecha_inicio_plan=start,
                estado="PLANIFICADO",
                actividades=[],
            )
            db.add(program)
            await db.flush()
        # Replace the schedule projection atomically within the same transaction.
        program.actividades.clear()
        cpm = MotorCPM()
        for item in schedule["activities"]:
            activity = Actividad(
                id=str(item["id"]),
                nombre=str(item["name"]),
                descripcion=str(item.get("description", "")),
                duracion=float(item["duration_days"]),
                predecesoras=[str(v) for v in item.get("predecessors", [])],
                costo_presupuestado=float(item.get("budget", 0)),
                tipo=TipoActividad(str(item.get("type", TipoActividad.CONSTRUCCION.value))),
                wbs_codigo=str(item.get("wbs_code", "")),
                wbs_nivel=int(item.get("wbs_level", 0)),
                metadatos={"tender_id": str(tender_id)},
            )
            cpm.agregar_actividad(activity)
        result = cpm.calcular_cpm(start, usar_calendario=True)
        program.fecha_fin_plan = result.ruta_critica.fecha_fin
        program.duracion_plan_dias = int(result.duracion_total)
        program.resultado_cpm = result.to_dict()
        for activity in result.actividades.values():
            row = ActividadPrograma(
                tenant_id=tenant_id,
                identificador=activity.id,
                nombre=activity.nombre,
                descripcion=activity.descripcion,
                wbs_codigo=activity.wbs_codigo,
                wbs_nivel=activity.wbs_nivel,
                duracion=activity.duracion,
                tipo=activity.tipo.value,
                costo_presupuestado=activity.costo_presupuestado,
                predecesoras=activity.predecesoras,
                inicio_temprano=activity.inicio_temprano,
                fin_temprano=activity.fin_temprano,
                inicio_tardio=activity.inicio_tardio,
                fin_tardio=activity.fin_tardio,
                holgura_total=activity.holgura_total,
                holgura_libre=activity.holgura_libre,
                en_ruta_critica=activity.en_ruta_critica,
                metadatos={"tender_id": str(tender_id)},
            )
            program.actividades.append(row)
        canonical.setdefault("schedule", {})["duration_days"] = result.duracion_total
        canonical["schedule"]["cpm"] = result.to_dict()
        return program
