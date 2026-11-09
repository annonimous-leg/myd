# Copyright © 2026 Cristian Rodriguez
# All rights reserved.
# Unauthorized copying, modification, distribution, or use is prohibited
# without prior written permission.

"""
ClashService - Corre el motor de clash detection sobre un ModeloBIM ya
procesado y persiste los resultados.

FIX P0 auditoría BIM 2026-09-14: hasta ahora ejecutar_analisis() era
síncrono dentro del propio request HTTP (el propio código lo admitía en
un comentario: "Síncrono por ahora... ver ROADMAP.md"). Con un modelo de
miles de elementos de malla densa, la narrow-phase Möller-Trumbore puede
tardar segundos-a-minutos -- eso bloquea el worker HTTP y arriesga
timeout, exactamente como ya se había resuelto para procesar_ifc()
moviéndolo a Celery (ver bim_tasks.py). Ahora el mismo patrón: el
endpoint solo crea el AnalisisClash en PENDIENTE (rápido) y encola
app.workers.bim_tasks.analizar_clash; el cómputo real vive en
ejecutar_analisis_worker(), que corre dentro del worker Celery.
"""
import time
from typing import List, Optional
from uuid import UUID, uuid4

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.bim import (
    ModeloBIM, ElementoBIM, AnalisisClash, ClashResult,
    EstadoAnalisisClash, EstadoClash,
)
from app.engines.bim.clash.motor_clash import MotorClash, ElementoParaClash
from app.core.errors import MegalodonException, ErrorCode


class ClashService:
    """Servicio de detección de colisiones (clash detection) entre
    elementos de un mismo modelo BIM."""

    def __init__(self, db: AsyncSession, tenant_id: UUID | None = None):
        self.db = db
        self.tenant_id = tenant_id

    def _require_tenant(self) -> UUID:
        if self.tenant_id is None:
            raise MegalodonException(ErrorCode.AUTH_ERROR, "Contexto tenant requerido para ClashService", status_code=403)
        return self.tenant_id

    async def crear_analisis_pendiente(
        self,
        *,
        modelo_id: UUID,
        expediente_id: UUID,
        tolerancia_m: float = 0.0,
        tipos_incluidos: Optional[List[str]] = None,
        tipos_excluidos: Optional[List[str]] = None,
        creado_por_id: Optional[UUID] = None,
    ) -> AnalisisClash:
        """Valida y registra el análisis en PENDIENTE -- rápido, seguro de
        llamar desde el request HTTP. El cómputo pesado NO ocurre aquí;
        lo dispara el caller (el endpoint) encolando
        app.workers.bim_tasks.analizar_clash con el id que esto retorna."""
        modelo = (await self.db.execute(select(ModeloBIM).where(ModeloBIM.id == modelo_id, ModeloBIM.expediente_id == expediente_id, ModeloBIM.tenant_id == self._require_tenant()))).scalar_one_or_none()
        if not modelo or str(modelo.expediente_id) != str(expediente_id):
            raise MegalodonException(
                ErrorCode.DOCUMENTO_NO_ENCONTRADO,
                f"Modelo BIM {modelo_id} no encontrado en el expediente {expediente_id}",
            )
        if tolerancia_m < 0:
            raise MegalodonException(ErrorCode.CLASH_DETECTION_ERROR, "tolerancia_m no puede ser negativa")

        analisis = AnalisisClash(
            id=uuid4(),
            modelo_id=modelo_id,
            tenant_id=modelo.tenant_id,
            tolerancia_m=tolerancia_m,
            tipos_incluidos=tipos_incluidos,
            tipos_excluidos=tipos_excluidos,
            estado=EstadoAnalisisClash.PENDIENTE.value,
            creado_por_id=creado_por_id,
            actualizado_por_id=creado_por_id,
        )
        self.db.add(analisis)
        from app.core.process_queue import registrar_trabajo
        registrar_trabajo(self.db, analisis, 'BIM_CLASH', {})
        await self.db.commit()
        await self.db.refresh(analisis)
        return analisis

    async def ejecutar_analisis_worker(self, analisis_id: UUID) -> AnalisisClash:
        """Cómputo real (broad+narrow phase) sobre un AnalisisClash ya
        creado por crear_analisis_pendiente(). Pensado para correr dentro
        de un worker Celery (app.workers.bim_tasks.analizar_clash), no
        dentro de un request HTTP."""
        analisis = (await self.db.execute(select(AnalisisClash).where(AnalisisClash.id == analisis_id, AnalisisClash.tenant_id == self._require_tenant()))).scalar_one_or_none()
        if not analisis:
            raise MegalodonException(ErrorCode.DOCUMENTO_NO_ENCONTRADO, f"Análisis de clash {analisis_id} no encontrado")

        modelo_id = analisis.modelo_id
        tolerancia_m = analisis.tolerancia_m
        tipos_incluidos = analisis.tipos_incluidos
        tipos_excluidos = analisis.tipos_excluidos

        analisis.estado = EstadoAnalisisClash.EN_PROCESO.value
        await self.db.commit()

        query = select(ElementoBIM).join(ModeloBIM, ModeloBIM.id == ElementoBIM.modelo_id).where(ElementoBIM.modelo_id == modelo_id, ModeloBIM.tenant_id == self._require_tenant())
        if tipos_incluidos:
            query = query.where(ElementoBIM.tipo.in_(tipos_incluidos))
        if tipos_excluidos:
            query = query.where(ElementoBIM.tipo.notin_(tipos_excluidos))
        result = await self.db.execute(query)
        elementos_bd = list(result.scalars().all())

        if len(elementos_bd) < 2:
            analisis.estado = EstadoAnalisisClash.COMPLETADO.value
            analisis.num_pares_evaluados = 0
            await self.db.commit()
            await self.db.refresh(analisis)
            return analisis

        elementos_por_id = {str(e.id): e for e in elementos_bd}
        elementos_motor = [
            ElementoParaClash(
                id=str(e.id),
                tipo=e.tipo,
                bbox=tuple(e.bbox) if e.bbox else (0, 0, 0, 0, 0, 0),
                malla_vertices=e.malla_vertices,
                malla_caras=e.malla_caras,
            )
            for e in elementos_bd
            if e.bbox  # sin bbox no hay nada que probar, ni siquiera broad phase
        ]

        try:
            t0 = time.perf_counter()
            motor = MotorClash(tolerancia_m=tolerancia_m)
            resultados = motor.detectar(elementos_motor)
            tiempo_ms = int((time.perf_counter() - t0) * 1000)

            num_duros = 0
            num_blandos = 0
            for r in resultados:
                elem_a = elementos_por_id[r.elemento_a_id]
                elem_b = elementos_por_id[r.elemento_b_id]
                if r.severidad == "DURO":
                    num_duros += 1
                else:
                    num_blandos += 1
                self.db.add(ClashResult(
                    id=uuid4(),
                    analisis_id=analisis.id,
                    modelo_id=modelo_id,
                    elemento_a_id=elem_a.id,
                    elemento_b_id=elem_b.id,
                    tipo_a=r.tipo_a,
                    tipo_b=r.tipo_b,
                    severidad=r.severidad,
                    distancia_m=r.distancia_m,
                    volumen_aproximado_m3=r.volumen_aproximado_m3,
                    punto_cercano_a=r.punto_cercano_a,
                    punto_cercano_b=r.punto_cercano_b,
                    triangulos_a=r.triangulos_a,
                    triangulos_b=r.triangulos_b,
                    estado=EstadoClash.NUEVO.value,
                ))

            analisis.estado = EstadoAnalisisClash.COMPLETADO.value
            # Pares evaluados = todos los que pasaron broad phase, no solo
            # los que terminaron siendo clash real -- útil para saber si
            # el análisis de verdad recorrió el modelo o se quedó corto
            # (ej. la mayoría de elementos sin malla).
            n = len(elementos_motor)
            analisis.num_pares_evaluados = n * (n - 1) // 2
            analisis.num_clashes_duros = num_duros
            analisis.num_clashes_blandos = num_blandos
            analisis.tiempo_calculo_ms = tiempo_ms
            await self.db.commit()
            await self.db.refresh(analisis)
            return analisis

        except Exception as e:
            analisis.estado = EstadoAnalisisClash.ERROR.value
            analisis.error = str(e)
            await self.db.commit()
            raise

    async def obtener_analisis(self, analisis_id: UUID, modelo_id: UUID) -> AnalisisClash:
        analisis = await self.db.scalar(select(AnalisisClash).where(AnalisisClash.id == analisis_id, AnalisisClash.tenant_id == self._require_tenant()))
        if not analisis or str(analisis.modelo_id) != str(modelo_id):
            raise MegalodonException(
                ErrorCode.DOCUMENTO_NO_ENCONTRADO,
                f"Análisis de clash {analisis_id} no encontrado en el modelo {modelo_id}",
            )
        return analisis

    async def listar_resultados(
        self,
        analisis_id: UUID,
        modelo_id: UUID,
        severidad: Optional[str] = None,
        estado: Optional[str] = None,
        limit: int = 200,
        offset: int = 0,
    ) -> List[ClashResult]:
        analisis = await self.db.scalar(select(AnalisisClash).where(AnalisisClash.id == analisis_id, AnalisisClash.tenant_id == self._require_tenant()))
        if not analisis or str(analisis.modelo_id) != str(modelo_id):
            raise MegalodonException(
                ErrorCode.DOCUMENTO_NO_ENCONTRADO,
                f"Análisis de clash {analisis_id} no encontrado en el modelo {modelo_id}",
            )
        query = select(ClashResult).join(AnalisisClash, AnalisisClash.id == ClashResult.analisis_id).where(ClashResult.analisis_id == analisis_id, AnalisisClash.tenant_id == self._require_tenant())
        if severidad:
            query = query.where(ClashResult.severidad == severidad)
        if estado:
            query = query.where(ClashResult.estado == estado)
        query = query.order_by(ClashResult.severidad, ClashResult.created_at).limit(limit).offset(offset)
        result = await self.db.execute(query)
        return list(result.scalars().all())

    async def actualizar_estado_resultado(self, resultado_id: UUID, nuevo_estado: str) -> ClashResult:
        if nuevo_estado not in {e.value for e in EstadoClash}:
            raise MegalodonException(
                ErrorCode.CLASH_DETECTION_ERROR,
                f"Estado inválido: {nuevo_estado}. Válidos: {[e.value for e in EstadoClash]}",
            )
        resultado = await self.db.scalar(select(ClashResult).join(AnalisisClash, AnalisisClash.id == ClashResult.analisis_id).where(ClashResult.id == resultado_id, AnalisisClash.tenant_id == self._require_tenant()))
        if not resultado:
            raise MegalodonException(ErrorCode.DOCUMENTO_NO_ENCONTRADO, f"Resultado de clash {resultado_id} no encontrado")
        resultado.estado = nuevo_estado
        await self.db.commit()
        await self.db.refresh(resultado)
        return resultado
