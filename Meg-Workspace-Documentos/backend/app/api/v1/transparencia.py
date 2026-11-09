# Copyright © 2026 Cristian Rodriguez
# All rights reserved.
# Unauthorized copying, modification, distribution, or use is prohibited
# without prior written permission.

"""
API de transparencia — Expediente público, bitácora de cambios, línea de tiempo.
"""
from app.core.rate_limit import rate_limit_standard, rate_limit_strict
from typing import Optional, List
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, func, and_

from app.core.deps import get_db, get_current_user
from app.models.user import User
from app.models.expediente import ExpedienteObra, ClasificacionSeguridad
from app.models.licitacion import Licitacion
from app.models.contrato import Contrato
from app.models.compliance import Inconformidad, Sancion

router = APIRouter()


@router.get("/expedientes-publicos")
async def listar_expedientes_publicos(
    q: Optional[str] = None,
    estado: Optional[str] = None,
    skip: int = Query(0, ge=0),
    limit: int = Query(100, ge=1, le=500),
    db: AsyncSession = Depends(get_db), _rate_limit: bool = Depends(rate_limit_standard),
):
    """Lista expedientes de clasificación PUBLICO para el portal de
    transparencia (sin auth). Antes no existía -- el frontend llamaba a
    esta ruta y siempre recibía 404, así que en la práctica sólo se veían
    los 3 expedientes de demo hardcodeados en el fallback del componente."""
    query = select(ExpedienteObra).where(ExpedienteObra.clasificacion == ClasificacionSeguridad.PUBLICO)
    if q:
        query = query.where(
            (ExpedienteObra.titulo.ilike(f"%{q}%")) | (ExpedienteObra.identificador.ilike(f"%{q}%"))
        )
    if estado:
        query = query.where(ExpedienteObra.estado == estado)

    count_query = select(func.count()).select_from(query.subquery())
    total = await db.scalar(count_query) or 0

    query = query.offset(skip).limit(limit).order_by(ExpedienteObra.created_at.desc())
    result = await db.execute(query)
    items = result.scalars().all()

    return {
        "total": total,
        "resultados": [
            {
                "id": str(e.id),
                "identificador": e.identificador,
                "titulo": e.titulo,
                "estado": e.estado,
                "monto_contrato": float(e.monto_contrato) if e.monto_contrato else None,
                "organo": e.organo,
                "created_at": e.created_at,
            }
            for e in items
        ],
    }


@router.get("/expediente/{expediente_id}")
async def expediente_publico(
    expediente_id: str,
    db: AsyncSession = Depends(get_db), _rate_limit: bool = Depends(rate_limit_standard),
):
    """Obtiene la vista pública de un expediente (sin auth requerida)."""
    result = await db.execute(
        select(ExpedienteObra).where(
            ExpedienteObra.id == expediente_id,
            ExpedienteObra.clasificacion == ClasificacionSeguridad.PUBLICO,
        )
    )
    expediente = result.scalar_one_or_none()
    if not expediente:
        raise HTTPException(status_code=404, detail="Expediente no encontrado")

    # Obtener licitaciones públicas
    lic_result = await db.execute(
        select(Licitacion).where(
            and_(Licitacion.expediente_id == expediente_id, Licitacion.estado.notin_(["PLANEACION"]))
        )
    )
    licitaciones = lic_result.scalars().all()

    # Obtener contratos públicos
    cont_result = await db.execute(
        select(Contrato).where(Contrato.expediente_id == expediente_id)
    )
    contratos = cont_result.scalars().all()

    return {
        "expediente": {
            "id": str(expediente.id),
            "nombre": expediente.titulo,
            "descripcion": expediente.descripcion,
            "estado": expediente.estado,
            "created_at": expediente.created_at,
        },
        "licitaciones": [
            {
                "id": str(l.id),
                "folio": l.folio,
                "tipo_procedimiento": l.tipo_procedimiento,
                "estado": l.estado,
                "objeto": l.objeto,
                "monto_estimado": float(l.monto_estimado) if l.monto_estimado else None,
                "fecha_convocatoria": l.fecha_convocatoria,
                "fecha_fallo": l.fecha_fallo,
            }
            for l in licitaciones
        ],
        "contratos": [
            {
                "id": str(c.id),
                "numero_contrato": c.numero_contrato,
                "estado": c.estado,
                "objeto": c.objeto,
                "monto_total": float(c.monto_total) if c.monto_total else None,
                "fecha_firma": c.fecha_firma,
                "avance_fisico": float(c.avance_fisico) if c.avance_fisico else None,
            }
            for c in contratos
        ],
    }


@router.get("/linea-tiempo/{expediente_id}")
async def linea_tiempo(
    expediente_id: str,
    db: AsyncSession = Depends(get_db), _rate_limit: bool = Depends(rate_limit_standard),
):
    """Genera la línea de tiempo de un expediente (sin auth requerida)."""
    exp_result = await db.execute(
        select(ExpedienteObra).where(
            ExpedienteObra.id == expediente_id,
            ExpedienteObra.clasificacion == ClasificacionSeguridad.PUBLICO,
        )
    )
    if exp_result.scalar_one_or_none() is None:
        raise HTTPException(status_code=404, detail="Expediente no encontrado")

    eventos = []

    # Eventos de licitación
    lic_result = await db.execute(
        select(Licitacion).where(Licitacion.expediente_id == expediente_id)
    )
    for lic in lic_result.scalars().all():
        eventos.append({
            "fecha": lic.created_at,
            "tipo": "LICITACION",
            "titulo": f"Licitación {lic.folio}",
            "descripcion": f"Estado: {lic.estado} — {lic.objeto[:100]}",
            "estado": lic.estado,
        })

    # Eventos de contrato
    cont_result = await db.execute(
        select(Contrato).where(Contrato.expediente_id == expediente_id)
    )
    for cont in cont_result.scalars().all():
        eventos.append({
            "fecha": cont.created_at,
            "tipo": "CONTRATO",
            "titulo": f"Contrato {cont.numero_contrato}",
            "descripcion": f"Estado: {cont.estado} — {cont.objeto[:100]}",
            "estado": cont.estado,
        })

    # Ordenar por fecha
    eventos.sort(key=lambda x: x["fecha"], reverse=True)

    return {"expediente_id": expediente_id, "eventos": eventos, "total": len(eventos)}


@router.get("/sanciones-publicas")
async def sanciones_publicas(
    proveedor_id: Optional[str] = None,
    skip: int = Query(0, ge=0),
    limit: int = Query(50, ge=1, le=200),
    db: AsyncSession = Depends(get_db), _rate_limit: bool = Depends(rate_limit_standard),
):
    """Lista sanciones públicas (sin auth).

    CORREGIDO 2026-08-30: filtraba solo por estado == VIGENTE, sin
    tenant_id ni ningún campo de publicación -- devolvía sanciones de
    todos los tenants mezcladas. Ahora exige `publicada == True` además
    del estado; `publicada` nace en False por default (ver migración
    20260830_sancion_publicada_flag), así que hasta que cada tenant
    marque explícitamente qué sanciones sí van al portal público, este
    endpoint no expone nada de nadie.
    """
    query = select(Sancion).where(Sancion.estado == "VIGENTE", Sancion.publicada.is_(True))

    if proveedor_id:
        query = query.where(Sancion.proveedor_id == proveedor_id)

    count_query = select(func.count()).select_from(query.subquery())
    total = await db.scalar(count_query) or 0

    query = query.offset(skip).limit(limit).order_by(Sancion.created_at.desc())
    result = await db.execute(query)
    items = result.scalars().all()

    return {
        "total": total,
        "items": [
            {
                "id": str(s.id),
                "tipo": s.tipo,
                "motivo": s.motivo,
                "monto_multa": float(s.monto_multa) if s.monto_multa else None,
                "vigencia_inicio": s.vigencia_inicio,
                "vigencia_fin": s.vigencia_fin,
                "estado": s.estado,
            }
            for s in items
        ],
    }
