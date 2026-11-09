"""Versioned TIN quantity evidence. Hashes establish provenance, not authenticity."""
from copy import deepcopy
from datetime import datetime, timezone
from decimal import Decimal
import hashlib
import json

from app.core.errors import ErrorCode, MegalodonException


def huella(payload: dict) -> str:
    canonical = json.dumps(payload, sort_keys=True, separators=(",", ":"), ensure_ascii=False, allow_nan=False)
    return hashlib.sha256(canonical.encode()).hexdigest()


def fuente(superficie, crs) -> dict:
    return {
        "superficie_id": str(superficie.id), "levantamiento_id": str(superficie.levantamiento_id),
        "crs": crs.to_string(),
        "malla_sha256": huella({"vertices": superficie.malla_vertices, "caras": superficie.malla_caras}),
    }


def cantidad(value) -> str:
    return str(Decimal(str(value)).quantize(Decimal("0.001")))


def crear(calculo, resultado, existente: dict, proyecto: dict | None, tenant_id) -> dict:
    payload = {
        "version": 1, "algoritmo": "TIN_OVERLAY_LINEAR_V1", "calculo_id": str(calculo.id),
        "expediente_id": str(calculo.expediente_id), "tenant_id": str(tenant_id),
        "usuario_id": str(calculo.creado_por_id) if calculo.creado_por_id else None,
        "calculado_en": datetime.now(timezone.utc).isoformat(),
        "unidades": {"area": "m2", "volumen": "m3", "elevacion": "m"},
        "existente": existente, "proyecto": proyecto,
        "elevacion_referencia": calculo.elevacion_referencia,
        "resultados": {name: cantidad(getattr(calculo, name)) for name in (
            "volumen_corte_m3", "volumen_terraplen_m3", "volumen_neto_m3", "area_analizada_m2")},
        "cobertura": deepcopy(resultado.cobertura),
    }
    return {**payload, "sha256": huella(payload)}


def verificar(calculo, tenant_id) -> dict:
    payload = deepcopy(calculo.evidencia or {})
    digest = payload.pop("sha256", None)
    if not payload or payload.get("version") != 1 or digest != huella(payload):
        raise MegalodonException(ErrorCode.TOPOGRAFIA_ERROR, "El cálculo carece de evidencia verificable; vuelva a calcular el volumen")
    expected = {
        "calculo_id": str(calculo.id), "expediente_id": str(calculo.expediente_id), "tenant_id": str(tenant_id),
        "resultados": {name: cantidad(getattr(calculo, name)) for name in (
            "volumen_corte_m3", "volumen_terraplen_m3", "volumen_neto_m3", "area_analizada_m2")},
    }
    if any(payload.get(name) != value for name, value in expected.items()):
        raise MegalodonException(ErrorCode.TOPOGRAFIA_ERROR, "Los resultados cambiaron después del cálculo; vuelva a calcular el volumen")
    return {**payload, "sha256": digest}


def partidas_coinciden(presupuesto) -> bool:
    """A changed/deleted measured line cannot retain a complete source claim."""
    metadata = getattr(presupuesto, "metadatos", None) or {}
    snapshot = metadata.get("topografia_evidencia")
    if snapshot is None:
        return not (metadata.get('topografia_cobertura') is not None
                    or any((getattr(p, 'metadatos', None) or {}).get('topografia') for p in presupuesto.partidas))
    payload = deepcopy(snapshot)
    digest = payload.pop("sha256", None)
    if digest != huella(payload) or payload.get("cobertura") != metadata.get("topografia_cobertura"):
        return False
    expected = {key: Decimal(payload['resultados'][field]) for key, field in (
        ('CORTE', 'volumen_corte_m3'), ('TERRAPLEN', 'volumen_terraplen_m3'))
        if Decimal(payload['resultados'][field]) > 0}
    seen = set()
    for partida in presupuesto.partidas:
        origin = (partida.metadatos or {}).get('topografia')
        if not origin:
            continue
        kind = origin.get('tipo')
        if (kind not in expected or kind in seen or partida.unidad != 'm3'
                or Decimal(str(partida.cantidad)) != expected[kind]
                or origin.get('calculo_id') != payload.get('calculo_id')
                or origin.get('evidencia_sha256') != digest):
            return False
        seen.add(kind)
    return seen == set(expected)
