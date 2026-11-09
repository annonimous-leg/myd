"""Single decision policy for workspace, reviewed layers and adjudication.

The caller owns the transaction and locks the licitation before reading a
proposal. This module never commits. Historical decisions remain append-only;
only the latest layer with the exact current evidence can admit a proposal.
"""
from copy import deepcopy
from dataclasses import asdict
from hashlib import sha256
import json

from sqlalchemy import select

from app.core.errors import ErrorCode, MegalodonException
from app.engines.juridico.motor_evaluacion import MotorEvaluacion
from app.models.licitacion import EvaluacionLicitacion, ResultadoEvaluacion, TipoEvaluacion


LEGAL_FLAGS = ("firma_valida", "integridad_valida", "cumplimiento_documental")
LAYERS = frozenset(layer.value for layer in TipoEvaluacion)


def conflict(message):
    raise MegalodonException(ErrorCode.VALIDACION_FALLIDA, message, 409)


def digest(value):
    try:
        encoded = json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False, allow_nan=False)
    except (TypeError, ValueError) as exc:
        raise MegalodonException(ErrorCode.VALIDACION_FALLIDA, "La evidencia no es JSON canónico válido.", 409) from exc
    return sha256(encoded.encode()).hexdigest()


def context(lic, *, require_frozen=True):
    if not lic.jurisdiction_code or not lic.bases or (require_frozen and not lic.bases_congeladas):
        conflict("La evaluación requiere dependencia, bases y matriz congeladas.")
    motor = MotorEvaluacion(lic.matriz_evaluacion)
    motor.validar_matriz_completa()
    return {
        "jurisdiction_code": lic.jurisdiction_code,
        "evaluation_matrix": deepcopy(lic.matriz_evaluacion),
        "bases_version": lic.bases_version,
        "bases_sha256": digest(lic.bases),
    }


def evidence(prop):
    envelopes = {k: v for k, v in (prop.sobres_digitales or {}).items()
                 if k not in {"prefall_result", "prefall_revision"}}
    return {
        "proposicion_sha256": digest({
            "sobres": envelopes, "monto": str(prop.monto), "plazo_dias": prop.plazo_dias,
            **{flag: getattr(prop, flag) for flag in LEGAL_FLAGS},
            "verificacion_documental": prop.verificacion_documental,
        })
    }


def snapshot(lic, prop):
    return {**context(lic), **evidence(prop)}


def legal_verified(prop):
    verification = prop.verificacion_documental or {}
    return (verification.get("metodo") == "ATESTACION_DOCUMENTAL"
            and bool(verification.get("documentos")) and bool(verification.get("autor_id"))
            and all(getattr(prop, flag) is True and verification.get(flag) is True for flag in LEGAL_FLAGS))


async def current_layers(db, lic, prop, tenant_id):
    rows = (await db.scalars(select(EvaluacionLicitacion).where(
        EvaluacionLicitacion.licitacion_id == lic.id,
        EvaluacionLicitacion.proposicion_id == prop.id,
        EvaluacionLicitacion.tenant_id == tenant_id,
    ).order_by(EvaluacionLicitacion.revision.desc(), EvaluacionLicitacion.created_at.desc(),
               EvaluacionLicitacion.id.desc()))).all()
    latest = {}
    for row in rows:
        latest.setdefault(TipoEvaluacion(row.tipo).value, row)
    expected = snapshot(lic, prop)
    return {kind: row for kind, row in latest.items()
            if all((row.criterios or {}).get(k) == v for k, v in expected.items())}


async def update_admission(db, lic, prop, tenant_id):
    layers = await current_layers(db, lic, prop, tenant_id)
    approved = (set(layers) == LAYERS and legal_verified(prop)
                and all(row.resultado == ResultadoEvaluacion.APROBADA for row in layers.values()))
    rejected = (not legal_verified(prop) or any(
        row.resultado != ResultadoEvaluacion.APROBADA for row in layers.values()))
    prop.estado = "ADMITIDA" if approved else "DESECHADA" if rejected else "RECIBIDA"
    prop.motivo_desecho = (
        "No satisface todas las capas vigentes y las verificaciones de firma, integridad y documentación."
        if rejected else None
    )
    return layers


async def require_adjudicable(db, lic, prop, tenant_id):
    if prop.estado != "ADMITIDA" or not legal_verified(prop):
        conflict("La proposición no está admitida con firma, integridad y documentación verificadas.")
    layers = await current_layers(db, lic, prop, tenant_id)
    if set(layers) != LAYERS or any(row.resultado != ResultadoEvaluacion.APROBADA for row in layers.values()):
        conflict("El fallo requiere evaluaciones legal, técnica y económica aprobadas con las bases y evidencia vigentes.")
    from app.services.proposicion_verification import require_current
    await require_current(db, lic, prop)
    return layers


async def require_awarded(db, lic, prop, tenant_id):
    layers = await require_adjudicable(db, lic, prop, tenant_id)
    award = lic.fallo_snapshot or {}
    expected = {**snapshot(lic, prop), "proposicion_id": str(prop.id),
                "proveedor_id": str(prop.proveedor_id), "monto": str(prop.monto),
                "plazo_dias": prop.plazo_dias,
                "evaluaciones": {kind: str(row.id) for kind, row in layers.items()}}
    if any(award.get(key) != value for key, value in expected.items()):
        conflict("La proposición o su evidencia no corresponden al fallo registrado.")


def evaluate_layer(lic, prop, kind, data, *, precio_referencia=None):
    context(lic)
    motor = MotorEvaluacion(lic.matriz_evaluacion)
    if kind == TipoEvaluacion.LEGAL:
        # Verified domain facts override submitted copies of these fields.
        result = motor.evaluar_legal(str(prop.id), {
            **data, **{flag: getattr(prop, flag) for flag in LEGAL_FLAGS},
        })
        if not legal_verified(prop):
            result.resultado = ResultadoEvaluacion.RECHAZADA
            result.puntaje_total = 0
            result.dictamen = "Firma, integridad o cumplimiento documental no acreditados."
        return result
    if kind == TipoEvaluacion.TECNICA:
        return motor.evaluar_tecnica(str(prop.id), data.get("criterios_tecnicos", data))
    if kind == TipoEvaluacion.ECONOMICA:
        if lic.matriz_evaluacion.get("variacion_mercado_max") is not None and (
            precio_referencia is None or precio_referencia <= 0
        ):
            conflict("La regla de mercado requiere un precio de referencia positivo en las bases.")
        return motor.evaluar_economica(str(prop.id), {
            **data.get("criterios_economicos", data), "precio_total": prop.monto,
        },
                                      precio_referencia=precio_referencia)
    conflict("Tipo de evaluación no soportado.")


def begin_revision(lic):
    # The licitation is locked by the caller. Its optimistic version provides
    # a monotonic sequence independent of timestamps or application clocks.
    lic.row_version += 1


def evaluation_row(lic, prop, user, result, *, inputs):
    return EvaluacionLicitacion(
        licitacion_id=lic.id, proposicion_id=prop.id, tipo=result.tipo,
        resultado=result.resultado, puntaje=result.puntaje_total, dictamen=result.dictamen,
        criterios={**snapshot(lic, prop), "datos": deepcopy(inputs),
                   "detalle": [asdict(c) for c in result.criterios]},
        revision=lic.row_version,
        evaluador_id=user.id, tenant_id=user.tenant_id,
        creado_por_id=user.id, actualizado_por_id=user.id,
    )
