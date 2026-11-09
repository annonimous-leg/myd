# Copyright © 2026 Cristian Rodriguez
# All rights reserved.
# Unauthorized copying, modification, distribution, or use is prohibited
# without prior written permission.

"""
OCRService - Orquestación del motor OCR con persistencia.
"""
from typing import Optional, Dict, Any
from uuid import UUID

from sqlalchemy.ext.asyncio import AsyncSession

from app.engines.ia.ocr_metrados import MotorOCRMetrados, ResultadoOCR
from app.services.base import BaseService
from app.core.errors import MegalodonException, ErrorCode


class OCRService:
    """Servicio de extracción de metrados mediante OCR."""

    def __init__(self, db: AsyncSession, tenant_id: Optional[UUID] = None):
        self.db = db
        self.tenant_id = tenant_id
        self.motor = MotorOCRMetrados()

    async def extraer_metrados(
        self,
        *,
        file_bytes: bytes,
        filename: str,
        documento_id: str,
        presupuesto_id: Optional[UUID] = None,
    ) -> ResultadoOCR:
        """
        Extrae metrados de un documento y opcionalmente los asocia a un presupuesto.
        """
        # Procesar con motor OCR
        resultado = self.motor.procesar_documento(file_bytes, filename, documento_id)

        # Si hay presupuesto, crear partidas sugeridas
        if presupuesto_id and resultado.metrados:
            await self._crear_partidas_sugeridas(presupuesto_id, resultado)

        return resultado

    async def _crear_partidas_sugeridas(
        self,
        presupuesto_id: UUID,
        resultado: ResultadoOCR,
        *,
        auto_commit: bool = True,
    ) -> None:
        """Crea partidas sugeridas en un presupuesto desde metrados OCR.

        IMPORTANTE: presupuesto_id llega desde afuera (usuario/worker) sin
        validar; antes se usaba tal cual, así que cualquier tenant podía
        inyectar partidas en el presupuesto de otro tenant con solo
        adivinar/probar un UUID. Ahora se exige tenant_id y se verifica
        pertenencia antes de escribir.
        """
        from app.models.presupuesto import Partida, Presupuesto, EstadoPresupuesto
        from app.core.errors import MegalodonException, ErrorCode
        from sqlalchemy import select

        if self.tenant_id is None:
            raise MegalodonException(
                ErrorCode.AUTH_ERROR,
                "Contexto tenant requerido para persistir partidas OCR",
                status_code=403,
            )

        presupuesto = await self.db.scalar(
            select(Presupuesto)
            .where(
                Presupuesto.id == presupuesto_id,
                Presupuesto.tenant_id == self.tenant_id,
            )
            .with_for_update().execution_options(populate_existing=True)
        )
        if presupuesto is None:
            raise MegalodonException(
                ErrorCode.DOCUMENTO_NO_ENCONTRADO,
                f"Presupuesto {presupuesto_id} no encontrado",
            )

        if presupuesto.estado in {EstadoPresupuesto.VALIDADO.value, EstadoPresupuesto.APROBADO.value}:
            raise MegalodonException(
                ErrorCode.CONFLICT,
                "El presupuesto validado o aprobado requiere una revisión antes de agregar metrados OCR.",
                status_code=409,
            )
        # New unpriced suggestions invalidate the previous calculated coverage.
        presupuesto.estado = EstadoPresupuesto.BORRADOR.value

        # Obtener siguiente número de partida
        result = await self.db.execute(
            select(Partida).where(Partida.presupuesto_id == presupuesto_id)
        )
        existing = result.scalars().all()
        next_num = max([p.numero for p in existing] or [0]) + 1

        for i, metrado in enumerate(resultado.metrados):
            partida = Partida(
                tenant_id=self.tenant_id,
                presupuesto_id=presupuesto_id,
                numero=next_num + i,
                descripcion=metrado.descripcion,
                unidad=metrado.unidad,
                cantidad=metrado.cantidad,
                precio_unitario=0.0,  # Se llena manualmente
                importe=0.0,
                metadatos={
                    "fuente": "OCR",
                    "confianza": metrado.confianza,
                    "pagina": metrado.pagina,
                    "texto_original": metrado.texto_original,
                },
            )
            self.db.add(partida)

        if auto_commit:
            await self.db.commit()
        else:
            await self.db.flush()

    async def validar_metrados(
        self,
        metrados: list,
        umbral_confianza: float = 60.0,
    ) -> Dict[str, Any]:
        """
        Valida metrados extraídos por OCR.
        Filtra los de baja confianza y detecta anomalías.
        """
        validados = []
        rechazados = []
        advertencias = []

        for m in metrados:
            if m.confianza < umbral_confianza:
                rechazados.append({
                    "concepto": m.concepto,
                    "confianza": m.confianza,
                    "razon": "Confianza por debajo del umbral",
                })
                continue

            # Validar cantidad razonable
            if m.cantidad <= 0:
                rechazados.append({
                    "concepto": m.concepto,
                    "cantidad": m.cantidad,
                    "razon": "Cantidad no válida",
                })
                continue

            if m.cantidad > 1_000_000:
                advertencias.append({
                    "concepto": m.concepto,
                    "cantidad": m.cantidad,
                    "advertencia": "Cantidad muy alta, verificar",
                })

            validados.append(m.to_dict())

        return {
            "validados": validados,
            "rechazados": rechazados,
            "advertencias": advertencias,
            "total": len(metrados),
            "aceptados": len(validados),
            "tasa_aceptacion": len(validados) / len(metrados) if metrados else 0.0,
        }
