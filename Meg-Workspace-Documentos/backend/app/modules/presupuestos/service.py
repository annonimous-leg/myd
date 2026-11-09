# Copyright © 2026 Cristian Rodriguez
# All rights reserved.
# Unauthorized copying, modification, distribution, or use is prohibited
# without prior written permission.

"""
PresupuestoModuleService - Servicio de gestión de presupuestos programables.
Control de costos, análisis de variaciones, proyecciones y reporting.
"""
from datetime import datetime
from decimal import Decimal
from typing import Any, Dict, Optional
from uuid import UUID

from sqlalchemy import select, func
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.core.errors import MegalodonException, ErrorCode
from app.models.expediente import ExpedienteObra
from app.models.programacion import ProgramaObra, ActividadPrograma
from app.models.presupuesto import Presupuesto, Partida, Concepto, ZonaEconomica
from app.services.presupuesto_service import PresupuestoService


class PresupuestoModuleService:
    """Servicio de gestión avanzada de presupuestos."""

    def __init__(self, db: AsyncSession, tenant_id: Optional[UUID] = None):
        self.db = db
        self.base_service = PresupuestoService(db, tenant_id) if tenant_id is not None else None

    async def _obtener_presupuesto(self, presupuesto_id: UUID, tenant_id: Optional[UUID]) -> Presupuesto:
        query = (
            select(Presupuesto)
            .options(
                selectinload(Presupuesto.partidas)
                .selectinload(Partida.conceptos)
                .selectinload(Concepto.insumos)
            )
            .where(Presupuesto.id == presupuesto_id)
        )
        if tenant_id is not None:
            query = query.join(ExpedienteObra, Presupuesto.expediente_id == ExpedienteObra.id)
            query = query.where(ExpedienteObra.tenant_id == tenant_id)
        result = await self.db.execute(query)
        presupuesto = result.scalar_one_or_none()
        if not presupuesto:
            raise MegalodonException(ErrorCode.PRESUPUESTO_ERROR, f"Presupuesto {presupuesto_id} no encontrado")
        return presupuesto

    async def _obtener_programa(self, expediente_id: UUID, tenant_id: Optional[UUID]) -> Optional[ProgramaObra]:
        query = select(ProgramaObra).where(ProgramaObra.expediente_id == expediente_id)
        if tenant_id is not None:
            query = query.join(ExpedienteObra, ProgramaObra.expediente_id == ExpedienteObra.id)
            query = query.where(ExpedienteObra.tenant_id == tenant_id)
        result = await self.db.execute(query.order_by(ProgramaObra.created_at.desc()).limit(1))
        return result.scalar_one_or_none()

    async def _avance_programa(self, programa_id: UUID, tenant_id: Optional[UUID]) -> float:
        query = select(ActividadPrograma.porcentaje_avance, ActividadPrograma.costo_presupuestado).where(
            ActividadPrograma.programa_id == programa_id
        )
        if tenant_id is not None:
            query = query.join(ProgramaObra, ActividadPrograma.programa_id == ProgramaObra.id)
            query = query.join(ExpedienteObra, ProgramaObra.expediente_id == ExpedienteObra.id)
            query = query.where(ExpedienteObra.tenant_id == tenant_id)
        result = await self.db.execute(query)
        actividades = result.all()
        if not actividades:
            return 0.0
        peso_total = 0.0
        avance_ponderado = 0.0
        for porcentaje, costo in actividades:
            peso = float(costo or 0)
            peso_total += peso
            avance_ponderado += float(porcentaje or 0) * peso
        if peso_total <= 0:
            return sum(float(p or 0) for p, _ in actividades) / len(actividades)
        return avance_ponderado / peso_total

    async def analisis_variacion_costos(
        self,
        presupuesto_id: UUID,
        tenant_id: Optional[UUID] = None,
    ) -> Dict[str, Any]:
        presupuesto = await self._obtener_presupuesto(presupuesto_id, tenant_id)

        variaciones = []
        total_planeado = Decimal("0")
        total_real = Decimal("0")

        for partida in presupuesto.partidas:
            planeado = Decimal(str(partida.importe or 0))
            costo_desglose = Decimal("0")
            for concepto in partida.conceptos:
                costo_desglose += Decimal(str(concepto.costo_directo_unitario or 0)) * Decimal(str(concepto.cantidad or 0))
            real = planeado
            variacion = real - costo_desglose
            porcentaje = (variacion / costo_desglose * 100) if costo_desglose > 0 else Decimal("0")

            total_planeado += costo_desglose
            total_real += real
            variaciones.append({
                "partida_id": str(partida.id),
                "numero": partida.numero,
                "descripcion": partida.descripcion,
                "planeado": float(costo_desglose),
                "real": float(real),
                "variacion": float(variacion),
                "porcentaje_variacion": float(porcentaje),
                "estado": "SOBRECOSTO" if variacion > 0 else "AHORRO" if variacion < 0 else "NEUTRO",
            })

        variacion_total = total_real - total_planeado
        porcentaje_total = (variacion_total / total_planeado * 100) if total_planeado > 0 else Decimal("0")

        return {
            "presupuesto_id": str(presupuesto_id),
            "total_planeado": float(total_planeado),
            "total_real": float(total_real),
            "variacion_total": float(variacion_total),
            "porcentaje_variacion": float(porcentaje_total),
            "estado_global": "SOBRECOSTO" if variacion_total > 0 else "AHORRO" if variacion_total < 0 else "NEUTRO",
            "partidas": sorted(variaciones, key=lambda x: abs(x["variacion"]), reverse=True),
        }

    async def proyeccion_final(
        self,
        presupuesto_id: UUID,
        *,
        metodo: str = "lineal",
        tenant_id: Optional[UUID] = None,
    ) -> Dict[str, Any]:
        presupuesto = await self._obtener_presupuesto(presupuesto_id, tenant_id)
        programa = await self._obtener_programa(presupuesto.expediente_id, tenant_id)
        avance = await self._avance_programa(programa.id, tenant_id) if programa else 0.0

        total = Decimal(str(presupuesto.monto_total or 0))
        avance_ratio = Decimal(str(max(0.0, min(avance, 100.0)))) / Decimal("100")
        devengado = total * avance_ratio

        if metodo == "lineal":
            factor = Decimal("1.00")
        elif metodo == "curva_s":
            factor = Decimal("1.05")
        elif metodo == "exponencial":
            factor = Decimal("1.08")
        else:
            factor = Decimal("1.00")

        proyeccion = total * factor
        variacion = proyeccion - total

        return {
            "presupuesto_id": str(presupuesto_id),
            "metodo": metodo,
            "avance_actual": float(avance),
            "total_presupuestado": float(total),
            "devengado_actual": float(devengado),
            "proyeccion_final": float(proyeccion),
            "variacion_proyectada": float(variacion),
            "porcentaje_variacion": float((variacion / total * 100) if total > 0 else 0),
        }

    async def flujo_caja(
        self,
        presupuesto_id: UUID,
        *,
        num_periodos: int = 12,
        tenant_id: Optional[UUID] = None,
    ) -> Dict[str, Any]:
        presupuesto = await self._obtener_presupuesto(presupuesto_id, tenant_id)
        total = Decimal(str(presupuesto.monto_total or 0))

        periodos = []
        acumulado = Decimal("0")
        for i in range(1, num_periodos + 1):
            x = Decimal(str(i)) / Decimal(str(num_periodos))
            distribucion = Decimal("3") * x * x - Decimal("2") * x * x * x
            periodo_anterior = acumulado
            acumulado = total * distribucion
            periodo_valor = acumulado - periodo_anterior
            periodos.append({
                "periodo": i,
                "valor": float(periodo_valor),
                "acumulado": float(acumulado),
                "porcentaje_acumulado": float((acumulado / total * 100) if total > 0 else 0),
            })

        return {
            "presupuesto_id": str(presupuesto_id),
            "total": float(total),
            "num_periodos": num_periodos,
            "periodos": periodos,
        }

    async def comparativo_precios(
        self,
        concepto_clave: str,
        *,
        zona_economica: Optional[ZonaEconomica] = None,
        tenant_id: Optional[UUID] = None,
    ) -> Dict[str, Any]:
        query = (
            select(Concepto, Partida, Presupuesto)
            .join(Partida, Concepto.partida_id == Partida.id)
            .join(Presupuesto, Partida.presupuesto_id == Presupuesto.id)
            .where(Concepto.clave == concepto_clave)
        )
        if zona_economica is not None:
            query = query.where(Presupuesto.zona_economica == zona_economica.value if hasattr(zona_economica, 'value') else zona_economica)
        if tenant_id is not None:
            query = query.join(ExpedienteObra, Presupuesto.expediente_id == ExpedienteObra.id)
            query = query.where(ExpedienteObra.tenant_id == tenant_id)

        result = await self.db.execute(query)
        filas = result.all()
        precios = []
        for concepto, partida, presupuesto in filas:
            precios.append({
                "presupuesto_id": str(presupuesto.id),
                "partida_id": str(partida.id),
                "concepto_id": str(concepto.id),
                "precio_unitario": float(concepto.costo_directo_unitario or 0),
                "cantidad": float(concepto.cantidad or 0),
                "importe": float((concepto.costo_directo_unitario or 0) * (concepto.cantidad or 0)),
                "zona_economica": presupuesto.zona_economica.value if hasattr(presupuesto.zona_economica, 'value') else str(presupuesto.zona_economica),
                "fecha_creacion": concepto.created_at.isoformat() if getattr(concepto, 'created_at', None) else None,
            })

        precios_ordenados = sorted(precios, key=lambda x: x["precio_unitario"])
        return {
            "concepto_clave": concepto_clave,
            "total_registros": len(precios_ordenados),
            "precios": precios_ordenados,
        }

    async def reprogramar_presupuesto(
        self,
        presupuesto_id: UUID,
        *,
        nuevo_monto: Optional[float] = None,
        nuevo_plazo: Optional[int] = None,
        motivo: str,
        creado_por_id: Optional[UUID] = None,
        tenant_id: Optional[UUID] = None,
    ) -> Dict[str, Any]:
        presupuesto = await self._obtener_presupuesto(presupuesto_id, tenant_id)
        datos_anteriores = {
            "monto": float(presupuesto.monto_total or 0),
            "plazo": presupuesto.plazo_dias,
        }

        if nuevo_monto is not None:
            presupuesto.monto_total = nuevo_monto
        if nuevo_plazo is not None:
            presupuesto.plazo_dias = nuevo_plazo

        historial = list((presupuesto.metadatos or {}).get("reprogramaciones", []))
        historial.append({
            "fecha": datetime.utcnow().isoformat(),
            "motivo": motivo,
            "datos_anteriores": datos_anteriores,
            "datos_nuevos": {
                "monto": float(presupuesto.monto_total or 0),
                "plazo": presupuesto.plazo_dias,
            },
            "creado_por_id": str(creado_por_id) if creado_por_id else None,
        })
        presupuesto.metadatos = {**(presupuesto.metadatos or {}), "reprogramaciones": historial}

        await self.db.commit()
        await self.db.refresh(presupuesto)
        return {
            "presupuesto_id": str(presupuesto.id),
            "monto_total": float(presupuesto.monto_total or 0),
            "plazo_dias": presupuesto.plazo_dias,
            "motivo": motivo,
            "reprogramaciones": historial,
        }
