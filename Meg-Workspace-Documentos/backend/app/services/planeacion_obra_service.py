from __future__ import annotations

from datetime import date
from decimal import Decimal
from typing import Dict, Optional, Any
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.errors import MegalodonException, ErrorCode
from app.engines.topografia.planeacion_obra import MotorPlaneacionObraAvanzada
from app.models.catalogo_apu import CatalogoAPU


class PlaneacionObraService:
    """Planeación de terreno con tarifas APU vigentes y trazables."""

    def __init__(self, db: AsyncSession):
        self.db = db
        self.motor = MotorPlaneacionObraAvanzada()

    async def resolver_tarifas(
        self, tenant_id: UUID, claves: Dict[str, str],
        zona_economica: Optional[str] = None, estado: Optional[str] = None, fecha: Optional[date] = None,
    ) -> tuple[Dict[str, float], Dict[str, Any]]:
        required = {"corte_m3", "relleno_m3", "drenaje_m2"}
        if set(claves) != required:
            raise MegalodonException(ErrorCode.VALIDACION_FALLIDA,
                "El mapa de tarifas debe contener exactamente corte_m3, relleno_m3 y drenaje_m2.",
                details={"claves_recibidas": sorted(claves)})
        fecha = fecha or date.today()
        filtros = [CatalogoAPU.tenant_id == tenant_id, CatalogoAPU.clave.in_(list(claves.values()))]
        if zona_economica:
            filtros.append(CatalogoAPU.zona_economica == zona_economica)
        if estado:
            filtros.append(CatalogoAPU.estado == estado)
        rows = (await self.db.execute(select(CatalogoAPU).where(*filtros))).scalars().all()
        reverse = {v: k for k, v in claves.items()}
        candidates = {k: [] for k in required}
        for row in rows:
            if row.clave not in reverse: continue
            try:
                if row.vigencia_inicio and date.fromisoformat(row.vigencia_inicio) > fecha: continue
                if row.vigencia_fin and date.fromisoformat(row.vigencia_fin) < fecha: continue
            except ValueError as exc:
                raise MegalodonException(ErrorCode.VALIDACION_FALLIDA,
                    f"Vigencia inválida en catálogo APU {row.clave}.", details={"clave": row.clave}) from exc
            candidates[reverse[row.clave]].append(row)
        tarifas, evidencia = {}, {}
        for key, items in candidates.items():
            if not items:
                raise MegalodonException(ErrorCode.DOCUMENTO_NO_ENCONTRADO,
                    f"No existe tarifa APU vigente para {key}.",
                    details={"clave_catalogo": claves[key], "zona_economica": zona_economica, "estado": estado})
            items.sort(key=lambda r: ((r.vigencia_inicio or "0000-00-00"), str(r.created_at)), reverse=True)
            row = items[0]
            value = Decimal(str(row.precio_unitario))
            if value < 0:
                raise MegalodonException(ErrorCode.VALIDACION_FALLIDA,
                    f"Tarifa negativa en catálogo APU {row.clave}.", details={"valor": str(value)})
            tarifas[key] = float(value)
            evidencia[key] = {
                "catalogo_id": str(row.id), "clave": row.clave, "fuente": row.fuente,
                "vigencia_inicio": row.vigencia_inicio, "vigencia_fin": row.vigencia_fin,
                "zona_economica": row.zona_economica, "estado": row.estado,
                "precio_unitario": float(value),
                "unidad": row.unidad.value if hasattr(row.unidad, "value") else str(row.unidad),
            }
        return tarifas, evidencia

    async def generar_plan(self, tenant_id: UUID, puntos: list[tuple[float, float, float]],
                           cota_objetivo: float, salto_terrazas: float, claves_catalogo: Dict[str, str],
                           zona_economica: Optional[str] = None, estado: Optional[str] = None) -> Dict[str, Any]:
        tarifas, evidencia = await self.resolver_tarifas(tenant_id, claves_catalogo, zona_economica, estado)
        resultado = self.motor.generar_plan(puntos, cota_objetivo, salto_terrazas, tarifas=tarifas)
        resultado["tarifas_catalogo"] = evidencia
        return resultado
