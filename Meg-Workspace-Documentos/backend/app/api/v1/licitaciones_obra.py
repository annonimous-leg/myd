# Copyright © 2026 Cristian Rodriguez
# All rights reserved.

"""
Router MPPL — Motor de Prevención y Pre-Evaluación Licitatoria

Megalodon NO sustituye a Compras MX. NO adjudica. NO publica. NO emite fallo oficial.

Lo que SÍ hace:
- Parsear convocatoria a reglas estructuradas
- Validar completitud documental de proposiciones
- Ejecutar evaluación técnica y económica determinista
- Simular resultado preliminar (pre-fallo)
- Proponer correcciones con workflow de aprobación del usuario
- Generar trazabilidad, evidencia y versionado

La convocante conserva SIEMPRE la decisión final.
"""

from typing import Optional, List, Dict, Any
from uuid import UUID
from datetime import date
from fastapi import APIRouter, Depends, HTTPException, status, Body
from pydantic import BaseModel, Field
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, delete

from app.core.deps import require_mutation_access, get_db, get_current_user
from app.core.rate_limit import rate_limit_standard, rate_limit_strict
from app.models.user import User
from app.models.proveedor import Proveedor
from app.models.contrato import Contrato, EstadoContrato, EntregableContrato
from app.schemas.contrato import ContratoCreate, EntregableCreate, FiniquitoCreate
from app.services.contrato_service import ContratoService
from app.services.licitacion_service import LicitacionService
from app.models.licitacion import TipoProcedimiento, Licitacion, Proposicion, EstadoLicitacion, EvaluacionLicitacion, TipoEvaluacion, ResultadoEvaluacion
from app.core.errors import handle_megalodon_errors, MegalodonException, ErrorCode
from app.schemas.licitacion import JurisdictionCode, LicitacionCreate, LicitacionUpdate, EvaluacionCreate, TransicionEstadoCreate, EvaluacionWorkspaceInput

from app.engines.licitacion.domain import (
    ConvocatoriaEstructurada, RequisitoEstructurado, CriterioTecnico, CriterioEconomico,
    TipoRequisito, PreFallResult, PropuestaCorreccion, EstadoSolvencia
)
from app.engines.licitacion.prefall_engine import PreFallEngine
from app.engines.licitacion.completeness_engine import DocumentComplianceEngine
from app.engines.licitacion.technical_engine import TechnicalEvaluationEngine
from app.engines.licitacion.economic_engine import EconomicEvaluationEngine
from app.services.correction_service import CorrectionService

router = APIRouter(dependencies=[Depends(require_mutation_access)], tags=["MPPL — Prevención y Pre-Evaluación Licitatoria"])
correction_svc = CorrectionService()


# ═══════════════════════════════════════════════════════════════════════════
# 1. PARSING DE CONVOCATORIA
# ═══════════════════════════════════════════════════════════════════════════

@router.post("/{licitacion_id}/convocatoria/parse")
@handle_megalodon_errors
async def parsear_convocatoria(
    licitacion_id: UUID,
    convocatoria_raw: Dict[str, Any] = Body(...),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
    _rate_limit: bool = Depends(rate_limit_standard),
):
    """
    Parsea convocatoria en reglas estructuradas.

    Input: texto/JSON de convocatoria.
    Output: requisitos, criterios técnicos, criterios económicos, causales de desechamiento.
    """
    result = await db.execute(select(Licitacion).where(Licitacion.id == licitacion_id, Licitacion.tenant_id == current_user.tenant_id))
    lic = result.scalar_one_or_none()
    if not lic:
        raise HTTPException(status_code=404, detail="Licitación no encontrada")

    # Extraer requisitos de la convocatoria
    requisitos = []
    bases = convocatoria_raw.get("bases", lic.bases or {})

    if isinstance(bases, dict):
        for i, (key, req_data) in enumerate(bases.get("requisitos", {}).items(), 1):
            requisitos.append(RequisitoEstructurado(
                codigo=f"REQ-{i:03d}",
                categoria=TipoRequisito(req_data.get("categoria", "ADMINISTRATIVO")),
                obligatorio=req_data.get("obligatorio", True),
                descripcion=req_data.get("descripcion", key),
                evidencia_requerida=req_data.get("evidencia", []),
                criterio_evaluacion=req_data.get("criterio", "Cumplimiento binario"),
                causal_desechamiento=req_data.get("causal_desechamiento"),
                fundamento_legal=req_data.get("fundamento", ""),
                seccion_origen=req_data.get("seccion", "Bases"),
                ponderacion=req_data.get("ponderacion")
            ))

    # Extraer criterios técnicos
    criterios_tecnicos = []
    matriz = convocatoria_raw.get("matriz_evaluacion", lic.matriz_evaluacion or {})
    if isinstance(matriz, dict):
        for i, (key, crit) in enumerate(matriz.get("tecnico", {}).items(), 1):
            criterios_tecnicos.append(CriterioTecnico(
                codigo=f"TEC-{i:03d}",
                descripcion=crit.get("descripcion", key),
                puntaje_maximo=crit.get("puntaje_maximo", 100.0),
                rubrica=crit.get("rubrica", {"minimo": crit.get("minimo", 0)}),
                ponderacion=crit.get("ponderacion"),
            ))

    # Extraer criterios económicos
    criterios_economicos = []
    if isinstance(matriz, dict):
        for i, (key, crit) in enumerate(matriz.get("economico", {}).items(), 1):
            criterios_economicos.append(CriterioEconomico(
                codigo=f"ECO-{i:03d}",
                descripcion=crit.get("descripcion", key),
                formula=crit.get("formula", "directa"),
                ponderacion=crit.get("ponderacion", 0.0),
                umbral_aceptable=crit.get("umbral")
            ))

    conv_estructurada = ConvocatoriaEstructurada(
        licitacion_id=licitacion_id,
        objeto=lic.objeto or convocatoria_raw.get("objeto", ""),
        tipo_procedimiento=TipoProcedimiento(lic.tipo_procedimiento).value if lic.tipo_procedimiento else "LICITACION_PUBLICA",
        monto_estimado=float(lic.monto_estimado or convocatoria_raw.get("monto_estimado", 0)),
        plazo_dias=lic.plazo_dias or convocatoria_raw.get("plazo_dias", 0),
        requisitos=requisitos,
        criterios_tecnicos=criterios_tecnicos,
        criterios_economicos=criterios_economicos,
        causales_desechamiento=bases.get("causales_desechamiento", []) if isinstance(bases, dict) else [],
        ponderacion_tecnica=(matriz.get("ponderacion_tecnica") if isinstance(matriz, dict) else None),
        ponderacion_economica=(matriz.get("ponderacion_economica") if isinstance(matriz, dict) else None),
        reglas_economicas=(matriz.get("reglas_economicas", {}) if isinstance(matriz, dict) else {}),
    )

    return {
        "licitacion_id": str(licitacion_id),
        "convocatoria_parseada": conv_estructurada.model_dump(),
        "requisitos_count": len(requisitos),
        "criterios_tecnicos_count": len(criterios_tecnicos),
        "criterios_economicos_count": len(criterios_economicos),
        "mensaje": "Convocatoria convertida a reglas estructuradas. Listo para validar proposiciones."
    }


# ═══════════════════════════════════════════════════════════════════════════
# 2. VALIDACIÓN DE PROPOSICIONES
# ═══════════════════════════════════════════════════════════════════════════

@router.post("/{licitacion_id}/proposiciones/{proposicion_id}/validar")
@handle_megalodon_errors
async def validar_proposicion(
    licitacion_id: UUID,
    proposicion_id: UUID,
    documentos: Dict[str, Any] = Body(..., description="Documentos de la proposición"),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
    _rate_limit: bool = Depends(rate_limit_standard),
):
    """
    Valida completitud documental de una proposición.

    Verifica: existencia, vigencia, firmas, RFC, montos, fechas,
    correspondencia entre documentos, anexos, formatos, inconsistencias, duplicados.
    """
    result = await db.execute(select(Licitacion).where(Licitacion.id == licitacion_id, Licitacion.tenant_id == current_user.tenant_id))
    lic = result.scalar_one_or_none()
    if not lic:
        raise HTTPException(status_code=404, detail="Licitación no encontrada")

    # Reconstruir requisitos desde la convocatoria
    bases = lic.bases or {}
    requisitos = []
    if isinstance(bases, dict):
        for i, (key, req_data) in enumerate(bases.get("requisitos", {}).items(), 1):
            requisitos.append(RequisitoEstructurado(
                codigo=f"REQ-{i:03d}",
                categoria=TipoRequisito(req_data.get("categoria", "ADMINISTRATIVO")),
                obligatorio=req_data.get("obligatorio", True),
                descripcion=req_data.get("descripcion", key),
                evidencia_requerida=req_data.get("evidencia", []),
                criterio_evaluacion=req_data.get("criterio", "Cumplimiento binario"),
                fundamento_legal=req_data.get("fundamento", ""),
                seccion_origen=req_data.get("seccion", "Bases")
            ))

    engine = DocumentComplianceEngine(requisitos)
    hallazgos = engine.validar(documentos)

    return {
        "licitacion_id": str(licitacion_id),
        "proposicion_id": str(proposicion_id),
        "hallazgos_count": len(hallazgos),
        "hallazgos": [h.model_dump() for h in hallazgos],
        "estado_preliminar": "NO_SOLVENTE" if any(h.nivel_riesgo.value == "CRITICO" for h in hallazgos) else "PENDIENTE_EVALUACION",
        "mensaje": "Validación documental completada. Revisar hallazgos antes de evaluación técnica/económica."
    }


# ═══════════════════════════════════════════════════════════════════════════
# 3. EVALUACIÓN TÉCNICA
# ═══════════════════════════════════════════════════════════════════════════

@router.post("/{licitacion_id}/evaluacion/tecnica")
@handle_megalodon_errors
async def evaluar_tecnica(
    licitacion_id: UUID,
    proposicion_tecnica: Dict[str, Any] = Body(..., description="Datos técnicos de la proposición"),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
    _rate_limit: bool = Depends(rate_limit_standard),
):
    """
    Ejecuta evaluación técnica determinista.

    Aplica exclusivamente los criterios técnicos establecidos en la convocatoria.
    Produce: cumple/no cumple con puntaje por criterio.
    """
    result = await db.execute(select(Licitacion).where(Licitacion.id == licitacion_id, Licitacion.tenant_id == current_user.tenant_id))
    lic = result.scalar_one_or_none()
    if not lic:
        raise HTTPException(status_code=404, detail="Licitación no encontrada")

    # Extraer criterios técnicos
    criterios = []
    matriz = lic.matriz_evaluacion or {}
    if isinstance(matriz, dict):
        for i, (key, crit) in enumerate(matriz.get("tecnico", {}).items(), 1):
            criterios.append(CriterioTecnico(
                codigo=f"TEC-{i:03d}",
                descripcion=crit.get("descripcion", key),
                puntaje_maximo=crit.get("puntaje_maximo", 100.0),
                rubrica=crit.get("rubrica", {"minimo": crit.get("minimo", 0)}),
                ponderacion=crit.get("ponderacion"),
            ))

    engine = TechnicalEvaluationEngine(criterios)
    resultados = engine.evaluar(proposicion_tecnica)
    hallazgos = engine.generar_hallazgos(resultados)

    puntaje_total = sum(r.puntaje_obtenido for r in resultados)
    puntaje_max = sum(r.puntaje_maximo for r in resultados)

    return {
        "licitacion_id": str(licitacion_id),
        "criterios_evaluados": len(resultados),
        "puntaje_total": puntaje_total,
        "puntaje_maximo": puntaje_max,
        "porcentaje": round(puntaje_total / puntaje_max * 100, 2) if puntaje_max > 0 else 0,
        "resultados": [r.model_dump() for r in resultados],
        "hallazgos": [h.model_dump() for h in hallazgos],
        "mensaje": "Evaluación técnica completada. Criterios aplicados según convocatoria."
    }


# ═══════════════════════════════════════════════════════════════════════════
# 4. EVALUACIÓN ECONÓMICA
# ═══════════════════════════════════════════════════════════════════════════

@router.post("/{licitacion_id}/evaluacion/economica")
@handle_megalodon_errors
async def evaluar_economica(
    licitacion_id: UUID,
    proposicion_economica: Dict[str, Any] = Body(..., description="Datos económicos de la proposición"),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
    _rate_limit: bool = Depends(rate_limit_standard),
):
    """
    Ejecuta evaluación económica determinista.

    Valida: suma de partidas, indirectos, utilidad, IVA, precios unitarios,
    cantidades, subtotales, discrepancias, comparación contra investigación de mercado,
    consistencia entre catálogo de conceptos y oferta.
    """
    result = await db.execute(select(Licitacion).where(Licitacion.id == licitacion_id, Licitacion.tenant_id == current_user.tenant_id))
    lic = result.scalar_one_or_none()
    if not lic:
        raise HTTPException(status_code=404, detail="Licitación no encontrada")

    # Extraer criterios económicos
    criterios = []
    matriz = lic.matriz_evaluacion or {}
    if isinstance(matriz, dict):
        for i, (key, crit) in enumerate(matriz.get("economico", {}).items(), 1):
            criterios.append(CriterioEconomico(
                codigo=f"ECO-{i:03d}",
                descripcion=crit.get("descripcion", key),
                formula=crit.get("formula", "directa"),
                ponderacion=crit.get("ponderacion", 0.0),
                umbral_aceptable=crit.get("umbral")
            ))

    monto_referencia = float(lic.monto_estimado) if lic.monto_estimado else None
    engine = EconomicEvaluationEngine(criterios, monto_referencia=monto_referencia)
    resultados = engine.evaluar(proposicion_economica)
    hallazgos = engine.generar_hallazgos(resultados)

    consistentes = sum(1 for r in resultados if r.consistente)

    return {
        "licitacion_id": str(licitacion_id),
        "criterios_evaluados": len(resultados),
        "consistentes": consistentes,
        "inconsistentes": len(resultados) - consistentes,
        "resultados": [r.model_dump() for r in resultados],
        "hallazgos": [h.model_dump() for h in hallazgos],
        "mensaje": "Evaluación económica completada. Validación de sumas, indirectos, IVA y consistencia."
    }


# ═══════════════════════════════════════════════════════════════════════════
# 5. SIMULACIÓN PRE-FALLO
# ═══════════════════════════════════════════════════════════════════════════

@router.post("/{licitacion_id}/prefallo/simular")
@handle_megalodon_errors
async def simular_prefallo(
    licitacion_id: UUID,
    proposicion_id: UUID,
    payload: Dict[str, Any] = Body(...),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
    _rate_limit: bool = Depends(rate_limit_strict),
):
    """
    Simula resultado preliminar del procedimiento.

    NO es fallo oficial. Es simulación determinista.

    Dice: "Aplicando exclusivamente los criterios publicados en la convocatoria
    y las evidencias cargadas, esta proposición resulta preliminarmente
    solvente/no solvente y obtiene X puntos."
    """
    result = await db.execute(select(Licitacion).where(Licitacion.id == licitacion_id, Licitacion.tenant_id == current_user.tenant_id))
    lic = result.scalar_one_or_none()
    if not lic:
        raise HTTPException(status_code=404, detail="Licitación no encontrada")

    prop_result = await db.execute(select(Proposicion).where(
        Proposicion.id == proposicion_id,
        Proposicion.licitacion_id == licitacion_id,
        Proposicion.tenant_id == current_user.tenant_id,
    ))
    prop = prop_result.scalar_one_or_none()
    if prop is None:
        raise HTTPException(status_code=404, detail="Proposición no encontrada")

    # El pre-fallo es una capa aislada: si existe el TenderPackage canónico del
    # mismo expediente, su dependencia debe coincidir; nunca se usa para
    # alterar el canonical_model ni los artefactos de elaboración.
    from app.models.procurement import TenderPackage
    canonical_tender = await db.scalar(select(TenderPackage).where(
        TenderPackage.expediente_id == lic.expediente_id,
        TenderPackage.tenant_id == current_user.tenant_id,
    ).order_by(TenderPackage.updated_at.desc()))
    if canonical_tender is not None and (canonical_tender.jurisdiction_code or '').upper() != (lic.jurisdiction_code or '').upper():
        raise HTTPException(status_code=409, detail="El pre-fallo aislado no puede usar una dependencia distinta del expediente canónico.")

    # Reconstruir convocatoria estructurada
    bases = lic.bases or {}
    requisitos = []
    if isinstance(bases, dict):
        for i, (key, req_data) in enumerate(bases.get("requisitos", {}).items(), 1):
            requisitos.append(RequisitoEstructurado(
                codigo=f"REQ-{i:03d}",
                categoria=TipoRequisito(req_data.get("categoria", "ADMINISTRATIVO")),
                obligatorio=req_data.get("obligatorio", True),
                descripcion=req_data.get("descripcion", key),
                evidencia_requerida=req_data.get("evidencia", []),
                criterio_evaluacion=req_data.get("criterio", "Cumplimiento binario"),
                fundamento_legal=req_data.get("fundamento", ""),
                seccion_origen=req_data.get("seccion", "Bases")
            ))

    criterios_tecnicos = []
    criterios_economicos = []
    matriz = lic.matriz_evaluacion or {}
    if isinstance(matriz, dict):
        for i, (key, crit) in enumerate(matriz.get("tecnico", {}).items(), 1):
            criterios_tecnicos.append(CriterioTecnico(
                codigo=f"TEC-{i:03d}",
                descripcion=crit.get("descripcion", key),
                puntaje_maximo=crit.get("puntaje_maximo", 100.0),
                rubrica=crit.get("rubrica", {})
            ))
        for i, (key, crit) in enumerate(matriz.get("economico", {}).items(), 1):
            criterios_economicos.append(CriterioEconomico(
                codigo=f"ECO-{i:03d}",
                descripcion=crit.get("descripcion", key),
                formula=crit.get("formula", "directa"),
                ponderacion=crit.get("ponderacion", 1.0)
            ))

    conv = ConvocatoriaEstructurada(
        licitacion_id=licitacion_id,
        jurisdiction_code=lic.jurisdiction_code,
        objeto=lic.objeto or "",
        tipo_procedimiento=TipoProcedimiento(lic.tipo_procedimiento).value if lic.tipo_procedimiento else "LICITACION_PUBLICA",
        monto_estimado=float(lic.monto_estimado or 0),
        plazo_dias=lic.plazo_dias or 0,
        requisitos=requisitos,
        criterios_tecnicos=criterios_tecnicos,
        criterios_economicos=criterios_economicos,
        ponderacion_tecnica=(matriz.get("ponderacion_tecnica") if isinstance(matriz, dict) else None),
        ponderacion_economica=(matriz.get("ponderacion_economica") if isinstance(matriz, dict) else None),
        reglas_economicas=(matriz.get("reglas_economicas", {}) if isinstance(matriz, dict) else {}),
    )

    historical_patterns = payload.get("historical_patterns") or {}
    engine = PreFallEngine(conv, historical_patterns=historical_patterns)
    resultado = engine.simular(
        proposicion_id=proposicion_id,
        licitante_nombre=payload.get("licitante_nombre", "Sin nombre"),
        documentos=payload.get("documentos", {}),
        prop_tecnica=payload.get("proposicion_tecnica", {}),
        prop_economica=payload.get("proposicion_economica", {})
    )

    prop.sobres_digitales = {
        **(prop.sobres_digitales or {}),
        "prefall_result": resultado.model_dump(mode="json"),
        "prefall_revision": int((prop.sobres_digitales or {}).get("prefall_revision", 0)) + 1,
    }
    await db.commit()

    return {
        "licitacion_id": str(licitacion_id),
        "proposicion_id": str(proposicion_id),
        "simulacion": resultado.model_dump(),
        "disclaimer": "Este es un resultado PRELIMINAR de simulación. NO es fallo oficial. La convocante conserva la decisión final.",
        "mensaje": "Simulación de pre-fallo completada. Revisar hallazgos, riesgos y trazabilidad."
    }


# ═══════════════════════════════════════════════════════════════════════════
# 6. CORRECCIONES — WORKFLOW DE APROBACIÓN
# ═══════════════════════════════════════════════════════════════════════════

@router.post("/{licitacion_id}/proposiciones/{proposicion_id}/correcciones/proponer")
@handle_megalodon_errors
async def proponer_correccion(
    licitacion_id: UUID,
    proposicion_id: UUID,
    hallazgo: Dict[str, Any] = Body(...),
    cambio: Dict[str, Any] = Body(...),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
    _rate_limit: bool = Depends(rate_limit_standard),
):
    """
    Megalodon detecta error y propone corrección concreta.

    La corrección NO se aplica automáticamente. El usuario debe decidir.
    """
    lic = await db.scalar(select(Licitacion).where(
        Licitacion.id == licitacion_id, Licitacion.tenant_id == current_user.tenant_id
    ))
    if lic is None:
        raise HTTPException(status_code=404, detail="Licitación no encontrada")
    prop = await db.scalar(select(Proposicion).where(
        Proposicion.id == proposicion_id,
        Proposicion.licitacion_id == licitacion_id,
        Proposicion.tenant_id == current_user.tenant_id,
    ))
    if prop is None:
        raise HTTPException(status_code=404, detail="Proposición no encontrada")

    from app.engines.licitacion.domain import Hallazgo as HallazgoDomain

    h = HallazgoDomain(**hallazgo)
    propuesta = await correction_svc.proponer_correccion(proposicion_id, h, cambio)

    return {
        "licitacion_id": str(licitacion_id),
        "proposicion_id": str(proposicion_id),
        "correccion_id": propuesta.id,
        "estado": propuesta.estado,
        "descripcion_original": propuesta.descripcion_original,
        "descripcion_propuesta": propuesta.descripcion_propuesta,
        "cambio": propuesta.cambio,
        "mensaje": "Corrección propuesta. El usuario debe revisar y decidir (ACEPTAR o RECHAZAR)."
    }


@router.post("/{licitacion_id}/proposiciones/{proposicion_id}/correcciones/{correccion_id}/decidir")
@handle_megalodon_errors
async def decidir_correccion(
    licitacion_id: UUID,
    proposicion_id: UUID,
    correccion_id: str,
    decision: str = Body(..., embed=True),  # ACEPTADA o RECHAZADA
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
    _rate_limit: bool = Depends(rate_limit_standard),
):
    """
    Usuario revisa y decide sobre corrección propuesta.

    Si ACEPTA → Megalodon aplica → recalcula → nueva versión.
    Si RECHAZA → se mantiene versión actual.
    """
    if decision.upper() not in ("ACEPTADA", "RECHAZADA"):
        raise HTTPException(status_code=400, detail="Decisión debe ser ACEPTADA o RECHAZADA")
    lic = await db.scalar(select(Licitacion).where(
        Licitacion.id == licitacion_id, Licitacion.tenant_id == current_user.tenant_id
    ))
    if lic is None:
        raise HTTPException(status_code=404, detail="Licitación no encontrada")
    prop = await db.scalar(select(Proposicion).where(
        Proposicion.id == proposicion_id,
        Proposicion.licitacion_id == licitacion_id,
        Proposicion.tenant_id == current_user.tenant_id,
    ))
    if prop is None:
        raise HTTPException(status_code=404, detail="Proposición no encontrada")

    propuesta = await correction_svc.decidir_correccion(
        proposicion_id, correccion_id, decision, current_user.email
    )

    return {
        "licitacion_id": str(licitacion_id),
        "proposicion_id": str(proposicion_id),
        "correccion_id": correccion_id,
        "decision": propuesta.estado,
        "usuario": propuesta.usuario_decision,
        "fecha_decision": propuesta.fecha_decision.isoformat() if propuesta.fecha_decision else None,
        "mensaje": f"Corrección {propuesta.estado}. {'Se generará nueva versión al recalcular.' if propuesta.estado == 'ACEPTADA' else 'Versión actual se mantiene.'}"
    }


# ═══════════════════════════════════════════════════════════════════════════
# 7. VERSIONADO DE PROPOSICIONES
# ═══════════════════════════════════════════════════════════════════════════

@router.get("/{licitacion_id}/proposiciones/{proposicion_id}/versiones")
@handle_megalodon_errors
async def listar_versiones(
    licitacion_id: UUID,
    proposicion_id: UUID,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
    _rate_limit: bool = Depends(rate_limit_standard),
):
    """Lista versiones de una proposición con trazabilidad completa."""
    lic = await db.scalar(select(Licitacion).where(
        Licitacion.id == licitacion_id, Licitacion.tenant_id == current_user.tenant_id
    ))
    if lic is None:
        raise HTTPException(status_code=404, detail="Licitación no encontrada")
    prop = await db.scalar(select(Proposicion).where(
        Proposicion.id == proposicion_id,
        Proposicion.licitacion_id == licitacion_id,
        Proposicion.tenant_id == current_user.tenant_id,
    ))
    if prop is None:
        raise HTTPException(status_code=404, detail="Proposición no encontrada")
    versiones = await correction_svc.listar_versiones(proposicion_id)

    return {
        "licitacion_id": str(licitacion_id),
        "proposicion_id": str(proposicion_id),
        "versiones_count": len(versiones),
        "versiones": [v.model_dump() for v in versiones],
        "mensaje": "Versionado completo. Cada versión conserva hallazgos, correcciones y pre-fallo."
    }


# ═══════════════════════════════════════════════════════════════════════════
# 8. RESUMEN PRE-FALLO (comparativo)
# ═══════════════════════════════════════════════════════════════════════════

@router.get("/{licitacion_id}/prefallo/resumen")
@handle_megalodon_errors
async def resumen_prefallo(
    licitacion_id: UUID,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
    _rate_limit: bool = Depends(rate_limit_standard),
):
    """
    Resumen comparativo preliminar de TODAS las proposiciones de la licitación.

    Muestra: estado, solvencia, puntaje, ranking preliminar, riesgos críticos.
    NO adjudica. Es una evaluación preliminar basada en reglas y evidencia persistidas.
    """
    result = await db.execute(
        select(Proposicion).where(
            Proposicion.licitacion_id == licitacion_id,
            Proposicion.tenant_id == current_user.tenant_id,
        )
    )
    proposiciones = result.scalars().all()

    resultados = []
    pendientes = []
    for prop in proposiciones:
        raw = (prop.sobres_digitales or {}).get("prefall_result")
        if raw:
            try:
                resultados.append(PreFallResult(**raw))
            except Exception as exc:
                raise HTTPException(status_code=409, detail=f"La evaluación almacenada de {prop.id} no es consistente: {exc}") from exc
        else:
            pendientes.append(prop)

    ranked = PreFallEngine.rank_results(resultados) if resultados else []
    resumen = [{
        "proposicion_id": str(res.proposicion_id),
        "licitante": res.licitante_nombre,
        "estado_preliminar": res.estado_general.value,
        "monto": next((float(p.monto) for p in proposiciones if p.id == res.proposicion_id), None),
        "plazo": next((p.plazo_dias for p in proposiciones if p.id == res.proposicion_id), None),
        "ranking_preliminar": res.ranking_preliminar,
        "puntaje_total": res.puntaje_total,
        "riesgos_criticos": res.riesgos_criticos,
        "advertencias": res.advertencias,
    } for res in ranked]
    for prop in pendientes:
        resumen.append({
            "proposicion_id": str(prop.id),
            "licitante": str(prop.proveedor_id),
            "estado_preliminar": prop.estado or "PENDIENTE",
            "monto": float(prop.monto) if prop.monto else None,
            "plazo": prop.plazo_dias,
            "ranking_preliminar": None,
            "puntaje_total": None,
            "riesgos_criticos": None,
            "advertencias": None,
        })

    return {
        "licitacion_id": str(licitacion_id),
        "proposiciones_count": len(proposiciones),
        "resumen": resumen,
        "disclaimer": "Ranking preliminar basado en simulación. NO es fallo oficial.",
        "mensaje": "Resumen comparativo preliminar. La convocante conserva la decisión final."
    }


# ============================================================================
# SaaS workspace bridge: frontend-facing orchestration over existing domains.
# These endpoints do not replace /licitaciones or /contratos; they expose a
# tenant-scoped business workspace using those real services/models.
# ============================================================================

class PlaneacionWorkspaceCreate(BaseModel):
    jurisdiction_code: JurisdictionCode
    folio: str = Field(..., min_length=1, max_length=100)
    tipo_procedimiento: str
    objeto: str = Field(..., min_length=1)
    monto_estimado: float | None = Field(default=None, ge=0)
    plazo_dias: int | None = Field(default=None, gt=0)
    fecha_convocatoria: str | None = None
    tipo_obra: str | None = None
    fuente_financiamiento: str | None = None


class EvaluacionWorkspaceResult(BaseModel):
    licitacion_id: str
    estado: str
    proposiciones_evaluadas: int
    evaluaciones_creadas: int
    resultados: list[dict]


class FalloWorkspaceCreate(BaseModel):
    proposicion_id: UUID


class ContratoWorkspaceCreate(BaseModel):
    proposicion_id: UUID
    numero_contrato: str = Field(..., min_length=1, max_length=100)
    fecha_firma: str | None = None
    fecha_inicio: str | None = None
    fecha_termino: str | None = None
    clausulas: dict | None = None
    obligaciones: dict | None = None


async def _workspace_licitacion(db: AsyncSession, expediente_id: UUID, current_user: User) -> Licitacion:
    result = await db.execute(
        select(Licitacion)
        .where(Licitacion.expediente_id == expediente_id)
        .where(Licitacion.tenant_id == current_user.tenant_id)
        .order_by(Licitacion.created_at.desc())
    )
    lic = result.scalars().first()
    if not lic:
        raise HTTPException(status_code=404, detail="No existe una licitación para el expediente activo.")
    return lic


async def _workspace_payload(db: AsyncSession, expediente_id: UUID, current_user: User) -> dict:
    lic = await _workspace_licitacion(db, expediente_id, current_user)
    propuestas = await LicitacionService().listar_proposiciones(db, lic.id, current_user)
    eval_result = await db.execute(
        select(EvaluacionLicitacion)
        .where(EvaluacionLicitacion.licitacion_id == lic.id)
        .where(EvaluacionLicitacion.tenant_id == current_user.tenant_id)
        .order_by(EvaluacionLicitacion.created_at.desc())
    )
    evaluaciones = eval_result.scalars().all()
    contrato_result = await db.execute(
        select(Contrato)
        .where(Contrato.licitacion_id == lic.id)
        .where(Contrato.tenant_id == current_user.tenant_id)
        .order_by(Contrato.created_at.desc())
    )
    contrato = contrato_result.scalars().first()

    proveedores = {}
    if propuestas:
        prov_ids = {UUID(str(p.proveedor_id)) for p in propuestas}
        prov_result = await db.execute(select(Proveedor).where(Proveedor.id.in_(prov_ids), Proveedor.tenant_id == current_user.tenant_id))
        proveedores = {str(p.id): p for p in prov_result.scalars().all()}

    return {
        "licitacion": {
            "id": str(lic.id), "folio": lic.folio, "estado": EstadoLicitacion(lic.estado).value,
            "jurisdiction_code": lic.jurisdiction_code,
            "tipo_procedimiento": TipoProcedimiento(lic.tipo_procedimiento).value,
            "objeto": lic.objeto, "monto_estimado": float(lic.monto_estimado or 0),
            "plazo_dias": lic.plazo_dias, "fecha_convocatoria": lic.fecha_convocatoria,
            "bases_congeladas": bool(lic.bases_congeladas),
            "bases": lic.bases, "bases_version": lic.bases_version, "row_version": lic.row_version,
            "matriz_evaluacion": lic.matriz_evaluacion,
            "transiciones_disponibles": [state.value for state in LicitacionService.TRANSICIONES.get(lic.estado, [])
                if state in {EstadoLicitacion.INVESTIGACION_MERCADO, EstadoLicitacion.SELECCION_PROCEDIMIENTO,
                             EstadoLicitacion.CONVOCATORIA, EstadoLicitacion.JUNTA_ACLARACIONES,
                             EstadoLicitacion.RECEPCION_PROPUESTAS, EstadoLicitacion.APERTURA}],
            "proposicion_ganadora_id": (lic.fallo_snapshot or {}).get("proposicion_id"),
            "justificacion_procedimiento": lic.justificacion_procedimiento,
            "presupuesto_dependencia_miles": float(lic.presupuesto_dependencia_miles or 0),
            "planeacion": lic.reglas_participacion.get("workspace", {}) if isinstance(lic.reglas_participacion, dict) else {},
        },
        "proposiciones": [
            {
                "id": str(p.id), "proveedor_id": str(p.proveedor_id),
                "proveedor": {
                    "razon_social": proveedores.get(str(p.proveedor_id)).razon_social if proveedores.get(str(p.proveedor_id)) else None,
                    "rfc": proveedores.get(str(p.proveedor_id)).rfc if proveedores.get(str(p.proveedor_id)) else None,
                },
                "monto": float(p.monto), "plazo_dias": p.plazo_dias, "estado": p.estado,
                "firma_valida": p.firma_valida, "integridad_valida": p.integridad_valida,
                "cumplimiento_documental": p.cumplimiento_documental,
                "verificacion_documental": p.verificacion_documental,
            }
            for p in propuestas
        ],
        "evaluaciones": [
            {"id": str(e.id), "proposicion_id": str(e.proposicion_id), "tipo": TipoEvaluacion(e.tipo).value,
             "resultado": ResultadoEvaluacion(e.resultado).value, "puntaje": float(e.puntaje) if e.puntaje is not None else None,
             "dictamen": e.dictamen, "revision": e.revision, "criterios": e.criterios, "created_at": e.created_at.isoformat()}
            for e in evaluaciones
        ],
        "contrato": ({"id": str(contrato.id), "numero_contrato": contrato.numero_contrato,
                      "estado": EstadoContrato(contrato.estado).value, "monto_total": float(contrato.monto_total),
                      "plazo_dias": contrato.plazo_dias, "proveedor_id": str(contrato.proveedor_id),
                      "avance_fisico": float(contrato.avance_fisico or 0),
                      "avance_financiero": float(contrato.avance_financiero or 0),
                      "fecha_finiquito": contrato.fecha_finiquito,
                      "monto_finiquito": float(contrato.monto_finiquito) if contrato.monto_finiquito is not None else None}
                     if contrato else None),
        "summary": {
            "estado": EstadoLicitacion(lic.estado).value,
            "proposiciones": len(propuestas),
            "evaluaciones": len(evaluaciones),
            "contrato": bool(contrato),
        },
    }


@router.get("/expediente/{expediente_id}/workspace")
@handle_megalodon_errors
async def workspace(expediente_id: UUID, db: AsyncSession = Depends(get_db), current_user: User = Depends(get_current_user)):
    return await _workspace_payload(db, expediente_id, current_user)


@router.post("/expediente/{expediente_id}/planeacion", response_model=dict, status_code=201)
@handle_megalodon_errors
async def guardar_planeacion(expediente_id: UUID, data: PlaneacionWorkspaceCreate, db: AsyncSession = Depends(get_db), current_user: User = Depends(get_current_user)):
    service = LicitacionService()
    rows = await service.listar(db, current_user, expediente_id=expediente_id, skip=0, limit=1)
    from app.models.licitacion import TipoProcedimiento
    try:
        tipo = TipoProcedimiento(data.tipo_procedimiento)
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=f"Tipo de procedimiento no soportado: {data.tipo_procedimiento}") from exc
    metadata = {"tipo_obra": data.tipo_obra, "fuente_financiamiento": data.fuente_financiamiento}
    if rows["items"]:
        lic = rows["items"][0]
        if lic.estado not in [EstadoLicitacion.PLANEACION, EstadoLicitacion.INVESTIGACION_MERCADO, EstadoLicitacion.SELECCION_PROCEDIMIENTO, EstadoLicitacion.CONVOCATORIA]:
            raise HTTPException(status_code=409, detail="La planeación ya no está en un estado editable.")
        current_rules = {**(lic.reglas_participacion or {})}
        current_rules["workspace"] = metadata
        update = LicitacionUpdate(
            jurisdiction_code=data.jurisdiction_code, folio=data.folio, objeto=data.objeto,
            tipo_procedimiento=tipo, reglas_participacion=current_rules,
            monto_estimado=data.monto_estimado, plazo_dias=data.plazo_dias,
            fecha_convocatoria=data.fecha_convocatoria, bases=lic.bases,
            justificacion_procedimiento=lic.justificacion_procedimiento,
        )
        lic = await service.actualizar(db, lic.id, update, current_user)
    else:
        payload = LicitacionCreate(
            expediente_id=expediente_id, jurisdiction_code=data.jurisdiction_code, folio=data.folio, tipo_procedimiento=tipo,
            objeto=data.objeto, monto_estimado=data.monto_estimado, plazo_dias=data.plazo_dias,
            fecha_convocatoria=data.fecha_convocatoria,
            reglas_participacion={"workspace": metadata}, bases=None, matriz_evaluacion={},
        )
        lic = await service.crear(db, payload, current_user)
    return {"id": str(lic.id), "folio": lic.folio, "estado": EstadoLicitacion(lic.estado).value, "expediente_id": str(lic.expediente_id)}


@router.post("/expediente/{expediente_id}/evaluar", response_model=EvaluacionWorkspaceResult)
@handle_megalodon_errors
async def evaluar_workspace(expediente_id: UUID, data: Optional[EvaluacionWorkspaceInput] = Body(None), db: AsyncSession = Depends(get_db), current_user: User = Depends(get_current_user)):
    lic = await _workspace_licitacion(db, expediente_id, current_user)
    result = await LicitacionService().evaluar_workspace(db, lic.id, current_user, review=data)
    return EvaluacionWorkspaceResult(**result)


@router.post("/expediente/{expediente_id}/fallo")
@handle_megalodon_errors
async def emitir_fallo_workspace(expediente_id: UUID, data: FalloWorkspaceCreate, db: AsyncSession = Depends(get_db), current_user: User = Depends(get_current_user)):
    lic = await _workspace_licitacion(db, expediente_id, current_user)
    lic = await LicitacionService().emitir_fallo(db, lic.id, data.proposicion_id, current_user)
    return await _workspace_payload(db, expediente_id, current_user)


@router.post("/expediente/{expediente_id}/contrato")
@handle_megalodon_errors
async def crear_contrato_workspace(expediente_id: UUID, data: ContratoWorkspaceCreate, db: AsyncSession = Depends(get_db), current_user: User = Depends(get_current_user)):
    lic = await _workspace_licitacion(db, expediente_id, current_user)
    prop = await LicitacionService()._obtener_proposicion_en_licitacion(db, data.proposicion_id, lic.id, current_user)
    if (lic.fallo_snapshot or {}).get("proposicion_id") != str(prop.id):
        raise HTTPException(status_code=409, detail="El contrato requiere la proposición ganadora del fallo registrado.")
    contrato_service = ContratoService()
    payload = ContratoCreate(expediente_id=str(expediente_id), licitacion_id=str(lic.id), proveedor_id=str(prop.proveedor_id), numero_contrato=data.numero_contrato, objeto=lic.objeto, monto_total=float(prop.monto), plazo_dias=prop.plazo_dias, fecha_firma=data.fecha_firma, fecha_inicio=data.fecha_inicio, fecha_termino=data.fecha_termino, clausulas=data.clausulas, obligaciones=data.obligaciones)
    contrato = await contrato_service.crear(db, payload, current_user)
    return await _workspace_payload(db, expediente_id, current_user)


@router.get("/expediente/{expediente_id}/estimaciones")
@handle_megalodon_errors
async def listar_estimaciones_workspace(expediente_id: UUID, db: AsyncSession = Depends(get_db), current_user: User = Depends(get_current_user)):
    payload = await _workspace_payload(db, expediente_id, current_user)
    if not payload["contrato"]:
        return {"contrato": None, "estimaciones": []}
    rows = await ContratoService().listar_entregables(db, UUID(payload["contrato"]["id"]), current_user)
    return {"contrato": payload["contrato"], "estimaciones": rows}


@router.post("/expediente/{expediente_id}/estimaciones", response_model=dict, status_code=201)
@handle_megalodon_errors
async def crear_estimacion_workspace(expediente_id: UUID, data: EntregableCreate, db: AsyncSession = Depends(get_db), current_user: User = Depends(get_current_user)):
    payload = await _workspace_payload(db, expediente_id, current_user)
    if not payload["contrato"]:
        raise HTTPException(status_code=409, detail="No existe contrato para registrar una estimación.")
    row = await ContratoService().crear_entregable(db, UUID(payload["contrato"]["id"]), data, current_user)
    return {"id": str(row.id), "numero_estimacion": row.numero_estimacion, "periodo_inicio": row.periodo_inicio, "periodo_fin": row.periodo_fin, "monto_ejecutado": float(row.monto_ejecutado or 0), "avance_fisico": float(row.avance_fisico or 0), "avance_financiero": float(row.avance_financiero or 0), "aprobado": row.aprobado}


@router.post("/expediente/{expediente_id}/contrato/terminar")
@handle_megalodon_errors
async def terminar_contrato_workspace(
    expediente_id: UUID,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
    _rate_limit: bool = Depends(rate_limit_strict),
):
    """Marca la terminación contractual sólo cuando el avance y las estimaciones aprobadas lo permiten."""
    workspace = await _workspace_payload(db, expediente_id, current_user)
    contrato_data = workspace.get("contrato")
    if not contrato_data:
        raise HTTPException(status_code=404, detail="No existe contrato para el expediente")
    contrato_id = UUID(str(contrato_data["id"]))
    contrato_actualizado = await ContratoService().transicionar_estado(db, contrato_id, EstadoContrato.TERMINADO, current_user)
    return {
        "contrato_id": str(contrato_actualizado.id),
        "estado": EstadoContrato(contrato_actualizado.estado).value,
        "avance_fisico": float(contrato_actualizado.avance_fisico or 0),
        "avance_financiero": float(contrato_actualizado.avance_financiero or 0),
    }

@router.post("/expediente/{expediente_id}/finiquito")
@handle_megalodon_errors
async def cerrar_finiquito_workspace(expediente_id: UUID, data: FiniquitoCreate, db: AsyncSession = Depends(get_db), current_user: User = Depends(get_current_user)):
    payload = await _workspace_payload(db, expediente_id, current_user)
    if not payload["contrato"]:
        raise HTTPException(status_code=409, detail="No existe contrato para cerrar.")
    contrato_id = UUID(payload["contrato"]["id"])
    contrato_service = ContratoService()
    contrato = await contrato_service.cerrar_finiquito(db, contrato_id, data.fecha_finiquito, current_user)
    monto_ejecutado = float(contrato.monto_finiquito)
    return {"contrato_id": str(contrato.id), "numero_contrato": contrato.numero_contrato, "estado": EstadoContrato(contrato.estado).value, "fecha_finiquito": contrato.fecha_finiquito, "monto_finiquito": float(contrato.monto_finiquito or 0), "monto_total_contrato": float(contrato.monto_total), "monto_total_ejecutado": monto_ejecutado}
