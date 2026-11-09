# Copyright © 2026 Cristian Rodriguez
# All rights reserved.
# Unauthorized copying, modification, distribution, or use is prohibited
# without prior written permission.

"""
Dashboard / Analytics API.
Estadísticas reales del sistema FILTRADAS POR TENANT.

INVARIANTE: Ninguna query en este módulo ejecuta sin filtro de tenant_id.
El current_user.tenant_id es OBLIGATORIO para TODAS las agregaciones.
"""
from app.core.rate_limit import rate_limit_standard, rate_limit_strict
from typing import List, Optional
from datetime import datetime, timedelta

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select, func, desc, and_
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.deps import get_current_user, get_db
from app.models.user import User
from app.models.expediente import ExpedienteObra, EstadoExpediente
from app.models.presupuesto import Presupuesto, EstadoPresupuesto
from app.models.licitacion import Licitacion
from app.models.contrato import Contrato, EstadoContrato
from app.models.documento import DocumentoCDE, EstadoDocumento
from app.models.proveedor import Proveedor
from app.models.audit_ledger import AuditLedger
from app.schemas.dashboard import DashboardStats, KPIData, DashboardResponse

router = APIRouter()


@router.get("/stats")
async def get_dashboard_stats(
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
    _rate_limit: bool = Depends(rate_limit_standard),
):
    """Retorna estadísticas reales del dashboard FILTRADAS POR TENANT."""

    tenant_id = current_user.tenant_id
    if not tenant_id:
        raise HTTPException(status_code=403, detail="Usuario sin tenant asignado")

    # ── Expedientes (filtrados por tenant) ──
    total_exp = await db.execute(
        select(func.count(ExpedienteObra.id))
        .where(ExpedienteObra.tenant_id == tenant_id)
    )
    estados_activos = [
        EstadoExpediente.INICIADO,
        EstadoExpediente.EN_TRAMITE,
        EstadoExpediente.PENDIENTE_DOCUMENTACION,
        EstadoExpediente.EN_FIRMA,
        EstadoExpediente.EN_INTEROPERABILIDAD,
    ]
    estados_cerrados = [EstadoExpediente.ARCHIVADO, EstadoExpediente.CERRADO]
    activos_exp = await db.execute(
        select(func.count(ExpedienteObra.id))
        .where(ExpedienteObra.tenant_id == tenant_id)
        .where(ExpedienteObra.estado.in_(estados_activos))
    )
    archivados_exp = await db.execute(
        select(func.count(ExpedienteObra.id))
        .where(ExpedienteObra.tenant_id == tenant_id)
        .where(ExpedienteObra.estado.in_(estados_cerrados))
    )

    # ── Presupuestos (join con Expediente para filtrar por tenant) ──
    total_pres = await db.execute(
        select(func.count(Presupuesto.id))
        .join(ExpedienteObra, Presupuesto.expediente_id == ExpedienteObra.id)
        .where(ExpedienteObra.tenant_id == tenant_id)
    )
    monto_total = await db.execute(
        select(func.coalesce(func.sum(Presupuesto.monto_total), 0.0))
        .join(ExpedienteObra, Presupuesto.expediente_id == ExpedienteObra.id)
        .where(ExpedienteObra.tenant_id == tenant_id)
    )

    # ── Licitaciones (filtradas por tenant) ──
    total_lic = await db.execute(
        select(func.count(Licitacion.id))
        .where(Licitacion.tenant_id == tenant_id)
    )
    lic_en_proceso = await db.execute(
        select(func.count(Licitacion.id))
        .where(Licitacion.tenant_id == tenant_id)
        .where(Licitacion.estado.in_(['PUBLICADA', 'EN_EVALUACION']))
    )

    # ── Contratos (filtrados por tenant) ──
    total_con = await db.execute(
        select(func.count(Contrato.id))
        .where(Contrato.tenant_id == tenant_id)
    )
    contratos_vigentes = await db.execute(
        select(func.count(Contrato.id))
        .where(Contrato.tenant_id == tenant_id)
        .where(Contrato.estado == EstadoContrato.VIGENTE)
    )

    # ── Proveedores (filtrados por tenant) ──
    total_prov = await db.execute(
        select(func.count(Proveedor.id))
        .where(Proveedor.tenant_id == tenant_id)
    )
    prov_activos = await db.execute(
        select(func.count(Proveedor.id))
        .where(Proveedor.tenant_id == tenant_id)
        .where(Proveedor.estado == 'ACTIVO')
    )

    # ── Documentos (join con Expediente para filtrar por tenant) ──
    total_docs = await db.execute(
        select(func.count(DocumentoCDE.id))
        .join(ExpedienteObra, DocumentoCDE.expediente_id == ExpedienteObra.id)
        .where(ExpedienteObra.tenant_id == tenant_id)
    )
    docs_pendientes = await db.execute(
        select(func.count(DocumentoCDE.id))
        .join(ExpedienteObra, DocumentoCDE.expediente_id == ExpedienteObra.id)
        .where(ExpedienteObra.tenant_id == tenant_id)
        .where(DocumentoCDE.estado == EstadoDocumento.EN_REVISION)
    )

    # ── Actividad reciente (filtrada por tenant) ──
    actividad_result = await db.execute(
        select(AuditLedger)
        .where(AuditLedger.tenant_id == tenant_id)
        .order_by(desc(AuditLedger.created_at))
        .limit(10)
    )
    actividad = actividad_result.scalars().all()

    # ── KPIs calculados ──
    kpis = []
    total_exp_val = total_exp.scalar()
    monto_total_val = float(monto_total.scalar() or 0)
    docs_pendientes_val = docs_pendientes.scalar()

    # KPI: Tasa de finalización
    finalizados = await db.execute(
        select(func.count(ExpedienteObra.id))
        .where(ExpedienteObra.tenant_id == tenant_id)
        .where(ExpedienteObra.estado.in_(estados_cerrados))
    )
    finalizados_val = finalizados.scalar()
    tasa_finalizacion = (finalizados_val / total_exp_val * 100) if total_exp_val > 0 else 0
    kpis.append(KPIData(
        label="Tasa de Finalización",
        value=round(tasa_finalizacion, 1),
    ))

    # KPI: Monto promedio por expediente
    monto_promedio = (monto_total_val / total_exp_val) if total_exp_val > 0 else 0
    kpis.append(KPIData(
        label="Monto Promedio",
        value=round(monto_promedio, 2),
    ))

    # KPI: Tiempo promedio de ciclo (real, calculado desde expedientes cerrados)
    ciclo_promedio = await db.execute(
        select(
            func.coalesce(
                func.avg(
                    func.extract("epoch", ExpedienteObra.updated_at - ExpedienteObra.created_at)
                ) / 86400.0,
                0.0,
            )
        )
        .where(ExpedienteObra.tenant_id == tenant_id)
        .where(ExpedienteObra.estado.in_(estados_cerrados))
        .where(ExpedienteObra.updated_at.isnot(None))
    )
    kpis.append(KPIData(
        label="Días Promedio Ciclo",
        value=round(float(ciclo_promedio.scalar() or 0.0), 1),
    ))

    # KPI: Documentos pendientes
    kpis.append(KPIData(
        label="Documentos Pendientes",
        value=docs_pendientes_val,
    ))

    stats = DashboardStats(
        total_expedientes=total_exp_val,
        expedientes_activos=activos_exp.scalar(),
        expedientes_archivados=archivados_exp.scalar(),
        total_presupuestos=total_pres.scalar(),
        monto_total_comprometido=monto_total_val,
        total_licitaciones=total_lic.scalar(),
        licitaciones_en_proceso=lic_en_proceso.scalar(),
        total_contratos=total_con.scalar(),
        contratos_vigentes=contratos_vigentes.scalar(),
        total_proveedores=total_prov.scalar(),
        proveedores_activos=prov_activos.scalar(),
        total_documentos=total_docs.scalar(),
        documentos_pendientes_firma=docs_pendientes_val,
    )

    return DashboardResponse(
        stats=stats,
        kpis=kpis,
        recent_activity=[
            {
                "id": str(a.id),
                "accion": a.accion.value if hasattr(a.accion, 'value') else str(a.accion),
                "entidad": f"{a.entidad_tipo} #{a.entidad_id}",
                "usuario": a.user_email or "Sistema",
                "fecha": a.created_at.isoformat() if a.created_at else None,
            }
            for a in actividad
        ],
    )


@router.get("/kpis")
async def get_kpis_detallados(
    periodo: str = "mensual",
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
    _rate_limit: bool = Depends(rate_limit_standard),
):
    """KPIs detallados por periodo FILTRADOS POR TENANT."""

    tenant_id = current_user.tenant_id
    if not tenant_id:
        raise HTTPException(status_code=403, detail="Usuario sin tenant asignado")

    estados_cerrados = [EstadoExpediente.ARCHIVADO, EstadoExpediente.CERRADO]

    hoy = datetime.utcnow()
    if periodo == "mensual":
        inicio = hoy - timedelta(days=30)
    elif periodo == "trimestral":
        inicio = hoy - timedelta(days=90)
    else:
        inicio = hoy - timedelta(days=365)

    # Expedientes creados en el periodo (por tenant)
    exp_nuevos = await db.execute(
        select(func.count(ExpedienteObra.id))
        .where(ExpedienteObra.tenant_id == tenant_id)
        .where(ExpedienteObra.created_at >= inicio)
    )

    # Expedientes finalizados en el periodo (por tenant)
    exp_finalizados = await db.execute(
        select(func.count(ExpedienteObra.id))
        .where(ExpedienteObra.tenant_id == tenant_id)
        .where(ExpedienteObra.estado.in_(estados_cerrados))
        .where(ExpedienteObra.updated_at >= inicio)
    )

    # Monto adjudicado en el periodo (por tenant)
    monto_adjudicado = await db.execute(
        select(func.coalesce(func.sum(Contrato.monto_total), 0.0))
        .where(Contrato.tenant_id == tenant_id)
        .where(Contrato.created_at >= inicio)
    )

    ciclo_promedio = await db.execute(
        select(
            func.coalesce(
                func.avg(
                    func.extract("epoch", ExpedienteObra.updated_at - ExpedienteObra.created_at)
                ) / 86400.0,
                0.0,
            )
        )
        .where(ExpedienteObra.tenant_id == tenant_id)
        .where(ExpedienteObra.estado.in_(estados_cerrados))
        .where(ExpedienteObra.updated_at.isnot(None))
    )

    return {
        "periodo": periodo,
        "fecha_inicio": inicio.isoformat(),
        "fecha_fin": hoy.isoformat(),
        "expedientes_nuevos": exp_nuevos.scalar(),
        "expedientes_finalizados": exp_finalizados.scalar(),
        "monto_adjudicado": float(monto_adjudicado.scalar()),
        "promedio_dias_ciclo": round(float(ciclo_promedio.scalar() or 0.0), 1),
    }
