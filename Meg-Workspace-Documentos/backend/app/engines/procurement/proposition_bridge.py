# Copyright © 2026 Cristian Rodriguez
"""Puente licitación/tender ↔ presupuesto programable.

Hidrata el modelo canónico del tender con datos reales del Presupuesto
(MotorCosteo / PresupuestoService) del mismo expediente. No inventa una
calculadora: reutiliza montos, partidas y factores ya calculados.

Uso típico (modo LICITANTE):
  model = await hydrate_canonical_from_presupuesto(db, tender, presupuesto_id=...)
  tender.canonical_model = model  → compile_artifacts
"""
from __future__ import annotations

from decimal import Decimal
from typing import Any
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.core.errors import ErrorCode, MegalodonException
from app.engines.costos.parametros import verificar_snapshot_almacenado

# Model imports are local to DB helpers to keep pure builders import-light.


def _f(value: Any) -> float:
    if value is None:
        return 0.0
    if isinstance(value, Decimal):
        return float(value)
    try:
        return float(value)
    except (TypeError, ValueError):
        return 0.0


def _partidas_from_presupuesto(presupuesto: Any) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for partida in sorted(presupuesto.partidas or [], key=lambda p: p.numero or 0):
        conceptos: list[dict[str, Any]] = []
        for concepto in partida.conceptos or []:
            insumos = [
                {
                    "clave": i.clave,
                    "descripcion": i.descripcion,
                    "tipo": i.tipo,
                    "unidad": i.unidad,
                    "cantidad": _f(i.cantidad),
                    "precio_unitario": _f(i.precio_unitario),
                    "rendimiento": _f(getattr(i, "rendimiento", 1) or 1),
                    "importe": _f(i.cantidad) * _f(i.precio_unitario),
                }
                for i in (concepto.insumos or [])
            ]
            cd = sum(x["importe"] for x in insumos)
            conceptos.append(
                {
                    "clave": concepto.clave,
                    "descripcion": concepto.descripcion,
                    "unidad": concepto.unidad,
                    "cantidad": _f(getattr(concepto, "cantidad", 1) or 1),
                    "insumos": insumos,
                    "costo_directo_unitario": cd,
                }
            )
        cantidad = _f(partida.cantidad)
        # Prefer stored precio; else sum conceptos
        if getattr(partida, "precio_unitario", None) is not None:
            pu = _f(partida.precio_unitario)
        elif conceptos:
            pu = sum(c["costo_directo_unitario"] * c["cantidad"] for c in conceptos)
        else:
            pu = 0.0
        importe = _f(getattr(partida, "importe", None)) or (cantidad * pu)
        rows.append(
            {
                "numero": partida.numero,
                "descripcion": partida.descripcion,
                "unidad": partida.unidad,
                "cantidad": cantidad,
                "precio_unitario": pu,
                "precio_unitario_manual": pu if not conceptos else None,
                "importe": importe,
                "conceptos": conceptos,
            }
        )
    return rows


def build_economic_block(presupuesto: Any) -> dict[str, Any]:
    snapshot_payload = (getattr(presupuesto, "metadatos", None) or {}).get("parametros_costeo")
    try:
        parametros = verificar_snapshot_almacenado(
            snapshot_payload,
            (
                presupuesto.factor_indirecto,
                presupuesto.factor_utilidad,
                presupuesto.factor_impuesto,
                getattr(presupuesto, "factor_riesgo", None),
            ),
        )
    except (KeyError, TypeError, ValueError) as exc:
        raise MegalodonException(
            ErrorCode.PRESUPUESTO_ERROR,
            "El presupuesto no tiene parámetros económicos trazables. "
            "Regularícelo con PUT /presupuestos/{expediente_id}/presupuestos/"
            f"{{presupuesto_id}}/parametros-costeo antes de hidratar procurement: {exc}",
            422,
        ) from exc
    partidas = _partidas_from_presupuesto(presupuesto)
    return {
        "presupuesto_id": str(presupuesto.id),
        "identificador": presupuesto.identificador,
        "nombre": presupuesto.nombre,
        "partidas": partidas,
        "budget_total": _f(presupuesto.monto_total),
        "monto_directo": _f(presupuesto.monto_directo),
        "monto_indirecto": _f(presupuesto.monto_indirecto),
        "monto_utilidad": _f(presupuesto.monto_utilidad),
        "monto_riesgo": _f(getattr(presupuesto, "monto_riesgo", None)),
        "monto_impuesto": _f(presupuesto.monto_impuesto),
        "factor_indirecto": _f(parametros.factor_indirecto),
        "factor_utilidad": _f(parametros.factor_utilidad),
        "factor_impuesto": _f(parametros.factor_impuesto),
        "factor_riesgo": _f(parametros.factor_riesgo),
        "source": f"{parametros.fuente.value}:{parametros.referencia}",
        "parameter_snapshot": parametros.to_dict(),
        "plazo_dias": presupuesto.plazo_dias,
        "moneda": presupuesto.moneda or "MXN",
        "indirects": {
            "factor": _f(presupuesto.factor_indirecto),
            "amount": _f(presupuesto.monto_indirecto),
            "basis": _f(presupuesto.monto_directo),
        },
        "profit": {
            "rate": _f(presupuesto.factor_utilidad),
            "amount": _f(presupuesto.monto_utilidad),
            "basis": _f(presupuesto.monto_directo) + _f(presupuesto.monto_indirecto),
        },
    }


def merge_facts_from_licitacion(
    facts: dict[str, Any],
    licitacion: Any,
    tender: Any,
) -> dict[str, Any]:
    out = dict(facts or {})
    if licitacion is not None:
        out.setdefault("authority", out.get("authority"))
        out["object"] = out.get("object") or licitacion.objeto
        out["procedure_type"] = (
            out.get("procedure_type")
            or licitacion.tipo_procedimiento
            or tender.procedure_type
        )
        if licitacion.plazo_dias is not None:
            out.setdefault("duration_days", licitacion.plazo_dias)
        if licitacion.monto_estimado is not None and "estimated_amount" not in out:
            out["estimated_amount"] = _f(licitacion.monto_estimado)
        out.setdefault("folio", licitacion.folio)
    out.setdefault("procedure_type", tender.procedure_type)
    out.setdefault("contract_type", tender.contract_type)
    out.setdefault("evaluation_criterion", tender.evaluation_criterion)
    out.setdefault("project_type", tender.project_type)
    if tender.title and not out.get("object"):
        out["object"] = tender.title
    return out


async def load_presupuesto_for_expediente(
    db: AsyncSession,
    expediente_id: UUID,
    *,
    presupuesto_id: UUID | None = None,
    tenant_id: UUID,
) -> Any:
    """Carga el presupuesto programable del expediente (preferido o el más reciente usable)."""
    from app.models.presupuesto import Concepto, Partida, Presupuesto
    from app.models.expediente import ExpedienteObra
    q = (
        select(Presupuesto)
        .join(ExpedienteObra, Presupuesto.expediente_id == ExpedienteObra.id)
        .where(Presupuesto.expediente_id == expediente_id)
        .where(ExpedienteObra.tenant_id == tenant_id)
        .options(
            selectinload(Presupuesto.partidas)
            .selectinload(Partida.conceptos)
            .selectinload(Concepto.insumos)
        )
    )
    if presupuesto_id is not None:
        q = q.where(Presupuesto.id == presupuesto_id)
    else:
        q = q.order_by(Presupuesto.created_at.desc() if hasattr(Presupuesto, "created_at") else Presupuesto.identificador.desc())
    result = await db.execute(q)
    rows = list(result.scalars().all())
    if not rows:
        return None
    if presupuesto_id is not None:
        return rows[0]
    # Prefer non-draft with partidas
    for p in rows:
        if (p.partidas or []) and str(p.estado).upper() not in {"CANCELADO", "ANULADO"}:
            return p
    return rows[0]


async def load_licitacion_for_expediente(
    db: AsyncSession,
    expediente_id: UUID,
    *,
    tenant_id: UUID,
) -> Any:
    from app.models.licitacion import Licitacion
    from app.models.expediente import ExpedienteObra
    result = await db.execute(
        select(Licitacion)
        .join(ExpedienteObra, Licitacion.expediente_id == ExpedienteObra.id)
        .where(Licitacion.expediente_id == expediente_id)
        .where(Licitacion.tenant_id == tenant_id)
        .where(ExpedienteObra.tenant_id == tenant_id)
        .order_by(Licitacion.folio.desc())
    )
    return result.scalars().first()


async def hydrate_canonical_from_presupuesto(
    db: AsyncSession,
    tender: Any,
    *,
    presupuesto_id: UUID | None = None,
    overwrite_economic: bool = True,
) -> dict[str, Any]:
    """Construye/actualiza tender.canonical_model desde el presupuesto del expediente.

    - No borra technical/legal ya cargados.
    - Si overwrite_economic=False y ya hay partidas, no toca economic.
    """
    model: dict[str, Any] = dict(tender.canonical_model or {})
    existing_economic = model.get("economic") or {}
    if (
        not overwrite_economic
        and existing_economic.get("partidas")
        and existing_economic.get("budget_total")
    ):
        return model

    presupuesto = await load_presupuesto_for_expediente(
        db, tender.expediente_id, presupuesto_id=presupuesto_id, tenant_id=tender.tenant_id
    )
    if presupuesto is None:
        # Fail soft: leave model; compile will raise if economic required
        model.setdefault("economic", existing_economic)
        model["_bridge"] = {
            "status": "NO_PRESUPUESTO",
            "expediente_id": str(tender.expediente_id),
            "message": "No hay presupuesto programable en el expediente; compile usará solo datos del canonical_model actual.",
        }
        return model

    licitacion = await load_licitacion_for_expediente(db, tender.expediente_id, tenant_id=tender.tenant_id)
    economic = build_economic_block(presupuesto)
    # Preserve optional blocks already computed (fasar, financing detail, etc.)
    for key in ("fasar", "financing", "explosion", "budget_total_words"):
        if key in existing_economic and key not in economic:
            economic[key] = existing_economic[key]

    model["economic"] = economic
    model["facts"] = merge_facts_from_licitacion(model.get("facts") or {}, licitacion, tender)
    model["_bridge"] = {
        "status": "OK",
        "presupuesto_id": str(presupuesto.id),
        "presupuesto_identificador": presupuesto.identificador,
        "partidas": len(economic["partidas"]),
        "budget_total": economic["budget_total"],
        "licitacion_folio": licitacion.folio if licitacion else None,
    }
    return model


async def missing_paths_for_formats(db: AsyncSession, model: dict[str, Any], format_codes: list[str], *, tenant_id: Any, jurisdiction_code: str) -> list[str]:
    """Lista rutas canónicas faltantes para los códigos de formato exigidos."""
    from app.engines.procurement.format_field_map import required_paths_for_codes

    def _get(path: str) -> Any:
        cur: Any = model
        for part in path.split("."):
            if not isinstance(cur, dict):
                return None
            cur = cur.get(part)
        return cur

    missing: list[str] = []
    for path in await required_paths_for_codes(db, tenant_id=tenant_id, jurisdiction_code=jurisdiction_code, codes=format_codes):
        # nested list paths like economic.partidas.conceptos
        root = path.split(".")[0]
        if path.endswith(".conceptos"):
            partidas = _get("economic.partidas") or []
            if not partidas or not any((p or {}).get("conceptos") for p in partidas):
                missing.append(path)
            continue
        val = _get(path)
        if val is None or val == "" or val == [] or val == {}:
            missing.append(path)
    return missing
