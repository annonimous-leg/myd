# Copyright © 2026 Cristian Rodriguez
"""Servicio de contratos — Ciclo contractual completo."""
from __future__ import annotations

from datetime import date, datetime, timedelta
from decimal import Decimal
from typing import Optional, List, Dict, Any
from uuid import UUID

from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, func, and_

from app.core.authorization import authorize_by_id
from app.core.errors import MegalodonException, ErrorCode
from app.models.expediente import ExpedienteObra
from app.models.proveedor import Proveedor
from app.models.licitacion import Licitacion, EstadoLicitacion
from app.models.contrato import (
    Contrato,
    EstadoContrato,
    ConvenioModificatorio,
    GarantiaContrato,
    EntregableContrato,
    PenalizacionContrato,
    TipoGarantia,
    TipoPenalizacion,
)
from app.models.user import User
from app.services import licitacion_evaluation as evaluation_policy
from app.schemas.contrato import (
    ContratoCreate, ContratoUpdate, ConvenioModificatorioCreate,
    GarantiaCreate, EntregableCreate, PenalizacionCreate,
)
from app.engines.juridico.motor_garantias import MotorGarantiasPenalizaciones


class ContratoService:
    TRANSICIONES = {
        EstadoContrato.EN_FIRMA: [EstadoContrato.VIGENTE, EstadoContrato.CERRADO],
        EstadoContrato.VIGENTE: [EstadoContrato.EN_MODIFICACION, EstadoContrato.SUSPENDIDO, EstadoContrato.TERMINADO, EstadoContrato.RESCINDIDO],
        EstadoContrato.EN_MODIFICACION: [EstadoContrato.VIGENTE, EstadoContrato.SUSPENDIDO, EstadoContrato.RESCINDIDO],
        EstadoContrato.SUSPENDIDO: [EstadoContrato.VIGENTE, EstadoContrato.RESCINDIDO],
        EstadoContrato.TERMINADO: [EstadoContrato.CERRADO],
        EstadoContrato.RESCINDIDO: [EstadoContrato.CERRADO],
        EstadoContrato.CERRADO: [],
    }

    async def _obtener_contrato(self, db: AsyncSession, contrato_id: UUID, current_user: User, *, bloquear: bool = False) -> Contrato:
        query = (
            select(Contrato)
            .join(ExpedienteObra, Contrato.expediente_id == ExpedienteObra.id)
            .where(Contrato.id == contrato_id)
            .where(ExpedienteObra.tenant_id == current_user.tenant_id)
        )
        if bloquear:
            query = query.with_for_update(of=Contrato).execution_options(populate_existing=True)
        result = await db.execute(query)
        contrato = result.scalar_one_or_none()
        if not contrato:
            raise MegalodonException(ErrorCode.NOT_FOUND, f"Contrato '{contrato_id}' no encontrado.")
        return contrato

    async def crear(self, db: AsyncSession, data: ContratoCreate, current_user: User) -> Contrato:
        try:
            return await self._crear_transaccion(db, data, current_user)
        except BaseException:
            await db.rollback()
            raise

    async def _crear_transaccion(self, db: AsyncSession, data: ContratoCreate, current_user: User) -> Contrato:
        await authorize_by_id(db, current_user.id, current_user.tenant_id, 'approve' if data.licitacion_id else 'write')
        expediente = await db.execute(
            select(ExpedienteObra)
            .where(ExpedienteObra.id == data.expediente_id)
            .where(ExpedienteObra.tenant_id == current_user.tenant_id)
        )
        if expediente.scalar_one_or_none() is None:
            raise MegalodonException(ErrorCode.NOT_FOUND, f"Expediente '{data.expediente_id}' no encontrado")

        proveedor = await db.execute(
            select(Proveedor)
            .where(Proveedor.id == data.proveedor_id)
            .where(Proveedor.tenant_id == current_user.tenant_id)
        )
        if proveedor.scalar_one_or_none() is None:
            raise MegalodonException(ErrorCode.NOT_FOUND, f"Proveedor '{data.proveedor_id}' no encontrado")

        lic = None
        if data.licitacion_id:
            from app.services.licitacion_service import LicitacionService
            service = LicitacionService()
            lic = await service._obtener_licitacion(db, UUID(str(data.licitacion_id)), current_user, bloquear=True)
            if str(lic.expediente_id) != str(data.expediente_id):
                evaluation_policy.conflict("El contrato pertenece a otro expediente.")
            if lic.estado not in {EstadoLicitacion.FALLO, EstadoLicitacion.ADJUDICACION, EstadoLicitacion.CONTRATO} or not lic.fallo_snapshot:
                evaluation_policy.conflict("El contrato requiere un fallo aprobado y trazable.")
            prop = await service._obtener_proposicion_en_licitacion(db,
                UUID(lic.fallo_snapshot["proposicion_id"]), lic.id, current_user, bloquear=True)
            await evaluation_policy.require_awarded(db, lic, prop, current_user.tenant_id)
            if (str(prop.proveedor_id) != str(data.proveedor_id)
                or Decimal(str(data.monto_total)) != prop.monto or data.plazo_dias != prop.plazo_dias):
                evaluation_policy.conflict("Proveedor, monto y plazo deben corresponder a la proposición ganadora.")
            existing = await db.scalar(select(Contrato).where(Contrato.licitacion_id == lic.id,
                                                            Contrato.tenant_id == current_user.tenant_id))
            if existing:
                if existing.numero_contrato != data.numero_contrato:
                    evaluation_policy.conflict("La licitación ya tiene un contrato registrado.")
                return existing
            lic.estado = EstadoLicitacion.CONTRATO
            lic.actualizado_por_id = current_user.id

        contrato = Contrato(
            expediente_id=data.expediente_id,
            licitacion_id=data.licitacion_id,
            proveedor_id=data.proveedor_id,
            numero_contrato=data.numero_contrato,
            estado=EstadoContrato.EN_FIRMA,
            objeto=data.objeto,
            monto_total=data.monto_total,
            monto_original=data.monto_total,
            plazo_dias=data.plazo_dias,
            plazo_original=data.plazo_dias,
            fecha_firma=data.fecha_firma,
            fecha_inicio=data.fecha_inicio,
            fecha_termino=data.fecha_termino,
            clausulas=data.clausulas,
            obligaciones=data.obligaciones,
            tenant_id=current_user.tenant_id,
            creado_por_id=current_user.id,
            actualizado_por_id=current_user.id,
        )
        db.add(contrato)
        await db.commit()
        await db.refresh(contrato)
        return contrato

    async def listar(
        self,
        db: AsyncSession,
        current_user: User,
        estado=None,
        expediente_id=None,
        proveedor_id=None,
        skip: int = 0,
        limit: int = 50,
    ) -> dict:
        query = select(Contrato).where(Contrato.tenant_id == current_user.tenant_id)
        if estado is not None:
            query = query.where(Contrato.estado == estado)
        if expediente_id is not None:
            query = query.where(Contrato.expediente_id == expediente_id)
        if proveedor_id is not None:
            query = query.where(Contrato.proveedor_id == proveedor_id)
        total = await db.scalar(select(func.count()).select_from(query.subquery())) or 0
        items = (await db.execute(query.order_by(Contrato.created_at.desc()).offset(skip).limit(limit))).scalars().all()
        return {"total": total, "items": items}

    async def obtener(self, db: AsyncSession, contrato_id: UUID, current_user: User) -> Contrato:
        return await self._obtener_contrato(db, contrato_id, current_user)

    async def actualizar(self, db: AsyncSession, contrato_id: UUID, data: ContratoUpdate, current_user: User) -> Contrato:
        await authorize_by_id(db, current_user.id, current_user.tenant_id, 'write')
        contrato = await self._obtener_contrato(db, contrato_id, current_user, bloquear=True)
        if contrato.estado not in [EstadoContrato.EN_FIRMA, EstadoContrato.VIGENTE, EstadoContrato.EN_MODIFICACION]:
            raise MegalodonException(ErrorCode.BAD_REQUEST, f"No se puede editar contrato en estado '{EstadoContrato(contrato.estado).value}'.")
        if contrato.estado != EstadoContrato.EN_FIRMA and {'monto_total', 'plazo_dias', 'fecha_termino'} & data.model_fields_set:
            raise MegalodonException(ErrorCode.BAD_REQUEST, 'El monto y plazo vigentes requieren convenio modificatorio', 409)
        for field in [
            'monto_total', 'plazo_dias', 'fecha_firma', 'fecha_inicio', 'fecha_termino',
        ]:
            val = getattr(data, field, None)
            if val is not None:
                setattr(contrato, field, val)
        if data.monto_total is not None:
            contrato.monto_original = contrato.monto_original or contrato.monto_total
        if data.plazo_dias is not None:
            contrato.plazo_original = contrato.plazo_original or contrato.plazo_dias
        contrato.actualizado_por_id = current_user.id
        await db.commit()
        await db.refresh(contrato)
        return contrato

    async def transicionar_estado(self, db: AsyncSession, contrato_id: UUID, nuevo_estado: EstadoContrato, current_user: User) -> Contrato:
        await authorize_by_id(db, current_user.id, current_user.tenant_id, 'approve')
        contrato = await self._obtener_contrato(db, contrato_id, current_user, bloquear=True)
        permitidos = self.TRANSICIONES.get(contrato.estado, [])
        if nuevo_estado not in permitidos:
            raise MegalodonException(ErrorCode.BAD_REQUEST, f"Transición de '{EstadoContrato(contrato.estado).value}' a '{nuevo_estado.value}' no permitida.")
        if nuevo_estado == EstadoContrato.TERMINADO:
            await self._exigir_estimaciones_aprobadas(db, contrato)
            if contrato.avance_fisico < 100 or contrato.avance_financiero < 100:
                raise MegalodonException(ErrorCode.BAD_REQUEST, 'Avance físico y financiero incompleto', 409)
        if nuevo_estado == EstadoContrato.CERRADO and contrato.estado != EstadoContrato.EN_FIRMA:
            raise MegalodonException(ErrorCode.BAD_REQUEST, 'Cierre mediante el comando de finiquito', 409)
        contrato.estado = nuevo_estado
        contrato.actualizado_por_id = current_user.id
        await db.commit()
        await db.refresh(contrato)
        return contrato

    async def _exigir_estimaciones_aprobadas(self, db: AsyncSession, contrato: Contrato):
        rows = list((await db.scalars(select(EntregableContrato).where(
            EntregableContrato.contrato_id == contrato.id,
            EntregableContrato.tenant_id == contrato.tenant_id))).all())
        if not rows or any(not row.aprobado for row in rows):
            raise MegalodonException(ErrorCode.BAD_REQUEST,
                'Registre y apruebe todas las estimaciones antes del cierre', 409)
        return rows

    async def cerrar_finiquito(self, db: AsyncSession, contrato_id: UUID,
                               fecha_finiquito: date, current_user: User) -> Contrato:
        await authorize_by_id(db, current_user.id, current_user.tenant_id, 'approve')
        contrato = await self._obtener_contrato(db, contrato_id, current_user, bloquear=True)
        if contrato.estado not in (EstadoContrato.TERMINADO, EstadoContrato.RESCINDIDO):
            raise MegalodonException(ErrorCode.BAD_REQUEST, 'El contrato debe estar terminado o rescindido', 409)
        rows = await self._exigir_estimaciones_aprobadas(db, contrato)
        montos = [Decimal(str(row.monto_ejecutado)) for row in rows]
        if any(not monto.is_finite() or monto < 0 for monto in montos):
            raise MegalodonException(ErrorCode.BAD_REQUEST, 'Existen importes históricos inválidos; revise las estimaciones', 409)
        contrato.monto_finiquito = sum(montos, Decimal('0'))
        contrato.fecha_finiquito = fecha_finiquito.isoformat()
        contrato.estado = EstadoContrato.CERRADO
        contrato.actualizado_por_id = current_user.id
        await db.commit()
        await db.refresh(contrato)
        return contrato

    async def crear_modificatorio(self, db: AsyncSession, contrato_id: UUID, data: ConvenioModificatorioCreate, current_user: User) -> ConvenioModificatorio:
        await authorize_by_id(db, current_user.id, current_user.tenant_id, 'approve')
        contrato = await self._obtener_contrato(db, contrato_id, current_user, bloquear=True)
        if contrato.estado not in (EstadoContrato.VIGENTE, EstadoContrato.EN_MODIFICACION):
            raise MegalodonException(ErrorCode.BAD_REQUEST, 'No se puede modificar un contrato fuera de ejecución', 409)
        if data.monto_anterior is not None and Decimal(str(data.monto_anterior)) != contrato.monto_total:
            raise MegalodonException(ErrorCode.BAD_REQUEST, 'El monto anterior difiere del contrato vigente', 409)
        if data.plazo_anterior is not None and data.plazo_anterior != contrato.plazo_dias:
            raise MegalodonException(ErrorCode.BAD_REQUEST, 'El plazo anterior difiere del contrato vigente', 409)
        modificatorio = ConvenioModificatorio(
            contrato_id=contrato_id,
            numero=data.numero,
            tipo=data.tipo,
            descripcion=data.descripcion,
            monto_anterior=data.monto_anterior,
            monto_nuevo=data.monto_nuevo,
            plazo_anterior=data.plazo_anterior,
            plazo_nuevo=data.plazo_nuevo,
            justificacion=data.justificacion,
            aprobado_por=current_user.id,
            fecha_aprobacion=datetime.utcnow().date().isoformat(),
            tenant_id=current_user.tenant_id,
            creado_por_id=current_user.id,
            actualizado_por_id=current_user.id,
        )
        db.add(modificatorio)
        if data.monto_nuevo is not None:
            contrato.monto_total = data.monto_nuevo
        if data.plazo_nuevo is not None:
            contrato.plazo_dias = data.plazo_nuevo
        contrato.estado = EstadoContrato.EN_MODIFICACION if contrato.estado == EstadoContrato.VIGENTE else contrato.estado
        contrato.actualizado_por_id = current_user.id
        await db.commit()
        await db.refresh(modificatorio)
        return modificatorio

    async def listar_modificatorios(self, db: AsyncSession, contrato_id: UUID, current_user: User) -> List[Dict[str, Any]]:
        await self._obtener_contrato(db, contrato_id, current_user)
        result = await db.execute(
            select(ConvenioModificatorio)
            .join(Contrato, ConvenioModificatorio.contrato_id == Contrato.id)
            .where(ConvenioModificatorio.contrato_id == contrato_id)
            .where(Contrato.tenant_id == current_user.tenant_id)
            .order_by(ConvenioModificatorio.created_at.desc())
        )
        return [
            {
                "id": str(m.id),
                "contrato_id": str(m.contrato_id),
                "numero": m.numero,
                "tipo": m.tipo.value if hasattr(m.tipo, 'value') else str(m.tipo),
                "descripcion": m.descripcion,
                "monto_anterior": float(m.monto_anterior) if m.monto_anterior is not None else None,
                "monto_nuevo": float(m.monto_nuevo) if m.monto_nuevo is not None else None,
                "plazo_anterior": m.plazo_anterior,
                "plazo_nuevo": m.plazo_nuevo,
                "justificacion": m.justificacion,
                "fecha_aprobacion": m.fecha_aprobacion,
                "created_at": m.created_at,
            }
            for m in result.scalars().all()
        ]

    async def crear_garantia(self, db: AsyncSession, contrato_id: UUID, data: GarantiaCreate, current_user: User) -> GarantiaContrato:
        await authorize_by_id(db, current_user.id, current_user.tenant_id, 'write')
        contrato = await self._obtener_contrato(db, contrato_id, current_user)
        # CONECTADO (pedido explícito 2026-09-07): MotorGarantiasPenalizaciones
        # ya calculaba el piso legal de la garantía de cumplimiento (RLOPSRM
        # Art. 91, verificado contra el texto -- ver el comentario en ese
        # archivo) pero ningún servicio lo llamaba: se podía registrar una
        # garantía de cumplimiento por debajo del 10% legal sin que el
        # sistema lo notara. Se valida aquí; no se recalcula el monto -- la
        # garantía es un dato real (la póliza que el contratista entregó),
        # no algo que el sistema deba inventar.
        if data.tipo == TipoGarantia.CUMPLIMIENTO and contrato.monto_total:
            motor = MotorGarantiasPenalizaciones()
            jurisdiction_code = getattr(contrato, "jurisdiction_code", None) or None
            minimo, decision = await motor.calcular_garantia_cumplimiento(
                db,
                float(contrato.monto_total),
                tenant_id=current_user.tenant_id,
                jurisdiction_code=jurisdiction_code,
            )
            if not decision.found:
                raise MegalodonException(
                    ErrorCode.JURIDICO_GENERICO,
                    f"No hay regla de garantía de cumplimiento en DB para validar la póliza "
                    f"({decision.error or decision.rule_id}). Carga garantias_legal_rules.csv.",
                    status_code=422,
                )
            if data.monto < minimo:
                raise MegalodonException(
                    ErrorCode.JURIDICO_GENERICO,
                    f"La garantía de cumplimiento (${data.monto:,.2f}) es menor al piso legal "
                    f"({decision.rule_id} / {decision.articulo or 'N/D'} = ${minimo:,.2f}).",
                    status_code=400,
                )
        garantia = GarantiaContrato(
            contrato_id=contrato_id,
            tipo=data.tipo,
            monto=data.monto,
            institucion=data.institucion,
            numero_poliza=data.numero_poliza,
            vigencia_inicio=data.vigencia_inicio,
            vigencia_fin=data.vigencia_fin,
            activa=True,
            liberada=False,
            ejecutada=False,
            tenant_id=current_user.tenant_id,
            creado_por_id=current_user.id,
            actualizado_por_id=current_user.id,
        )
        db.add(garantia)
        await db.commit()
        await db.refresh(garantia)
        return garantia

    async def listar_garantias(self, db: AsyncSession, contrato_id: UUID, current_user: User) -> List[Dict[str, Any]]:
        await self._obtener_contrato(db, contrato_id, current_user)
        result = await db.execute(
            select(GarantiaContrato)
            .join(Contrato, GarantiaContrato.contrato_id == Contrato.id)
            .where(GarantiaContrato.contrato_id == contrato_id)
            .where(Contrato.tenant_id == current_user.tenant_id)
            .order_by(GarantiaContrato.created_at.desc())
        )
        return [
            {
                "id": str(g.id),
                "contrato_id": str(g.contrato_id),
                "tipo": g.tipo.value if hasattr(g.tipo, 'value') else str(g.tipo),
                "monto": float(g.monto or 0),
                "institucion": g.institucion,
                "numero_poliza": g.numero_poliza,
                "vigencia_inicio": g.vigencia_inicio,
                "vigencia_fin": g.vigencia_fin,
                "activa": bool(g.activa),
                "liberada": bool(g.liberada),
                "ejecutada": bool(g.ejecutada),
                "fecha_liberacion": g.fecha_liberacion,
                "created_at": g.created_at,
            }
            for g in result.scalars().all()
        ]

    async def verificar_vigencia_garantias(self, db: AsyncSession, contrato_id: UUID, current_user: User) -> List[dict]:
        contrato = await self._obtener_contrato(db, contrato_id, current_user)
        result = await db.execute(
            select(GarantiaContrato)
            .where(GarantiaContrato.contrato_id == contrato_id)
            .order_by(GarantiaContrato.vigencia_fin.desc())
        )
        hoy = datetime.utcnow().date()
        alertas = []
        for g in result.scalars().all():
            if g.vigencia_fin:
                try:
                    fecha_fin = datetime.fromisoformat(g.vigencia_fin).date()
                except ValueError:
                    continue
                dias = (fecha_fin - hoy).days
                estado = "VENCIDA" if dias < 0 else ("PROXIMA_A_VENCER" if dias <= 30 else "VIGENTE")
                alertas.append({
                    "garantia_id": str(g.id),
                    "tipo": g.tipo.value if hasattr(g.tipo, 'value') else str(g.tipo),
                    "numero_poliza": g.numero_poliza,
                    "vigencia_inicio": g.vigencia_inicio,
                    "vigencia_fin": g.vigencia_fin,
                    "dias_restantes": dias,
                    "estado": estado,
                    "contrato_id": str(contrato.id),
                })
        return alertas

    async def aprobar_entregable(self, db: AsyncSession, contrato_id: UUID, entregable_id: UUID, current_user: User) -> EntregableContrato:
        await authorize_by_id(db, current_user.id, current_user.tenant_id, 'approve')
        contrato = await self._obtener_contrato(db, contrato_id, current_user, bloquear=True)
        if contrato.estado != EstadoContrato.VIGENTE:
            raise MegalodonException(ErrorCode.BAD_REQUEST, f"El contrato debe estar VIGENTE para aprobar una estimación; estado actual: {EstadoContrato(contrato.estado).value}.")
        result = await db.execute(
            select(EntregableContrato)
            .where(EntregableContrato.id == entregable_id)
            .where(EntregableContrato.contrato_id == contrato_id)
            .where(EntregableContrato.tenant_id == current_user.tenant_id)
        )
        entregable = result.scalar_one_or_none()
        if not entregable:
            raise MegalodonException(ErrorCode.NOT_FOUND, "Estimación no encontrada.")
        if entregable.aprobado:
            return entregable
        entregable.aprobado = True
        entregable.fecha_aprobacion = datetime.utcnow().date().isoformat()
        entregable.aprobado_por = current_user.id
        await db.flush()  # production sessions disable autoflush
        aprobados = await db.execute(
            select(EntregableContrato).where(EntregableContrato.contrato_id == contrato_id).where(EntregableContrato.tenant_id == current_user.tenant_id).where(EntregableContrato.aprobado.is_(True))
        )
        rows = aprobados.scalars().all()
        avance_fisico = max((float(r.avance_fisico or 0) for r in rows), default=0.0)
        avance_fin = max((float(r.avance_financiero or 0) for r in rows), default=0.0)
        contrato.avance_fisico = min(100.0, avance_fisico)
        contrato.avance_financiero = min(100.0, avance_fin)
        contrato.actualizado_por_id = current_user.id
        await db.commit()
        await db.refresh(entregable)
        return entregable

    async def crear_entregable(self, db: AsyncSession, contrato_id: UUID, data: EntregableCreate, current_user: User) -> EntregableContrato:
        await authorize_by_id(db, current_user.id, current_user.tenant_id, 'write')
        contrato = await self._obtener_contrato(db, contrato_id, current_user, bloquear=True)
        if contrato.estado != EstadoContrato.VIGENTE:
            raise MegalodonException(ErrorCode.BAD_REQUEST, 'Las estimaciones requieren contrato vigente', 409)
        entregable = EntregableContrato(
            contrato_id=contrato_id,
            numero_estimacion=data.numero_estimacion,
            periodo_inicio=data.periodo_inicio,
            periodo_fin=data.periodo_fin,
            monto_ejecutado=data.monto_ejecutado,
            avance_fisico=data.avance_fisico,
            avance_financiero=data.avance_financiero,
            aprobado=False,
            tenant_id=current_user.tenant_id,
            creado_por_id=current_user.id,
            actualizado_por_id=current_user.id,
        )
        db.add(entregable)
        await db.commit()
        await db.refresh(entregable)
        return entregable

    async def listar_entregables(self, db: AsyncSession, contrato_id: UUID, current_user: User) -> List[Dict[str, Any]]:
        await self._obtener_contrato(db, contrato_id, current_user)
        result = await db.execute(
            select(EntregableContrato)
            .join(Contrato, EntregableContrato.contrato_id == Contrato.id)
            .where(EntregableContrato.contrato_id == contrato_id)
            .where(Contrato.tenant_id == current_user.tenant_id)
            .order_by(EntregableContrato.numero_estimacion)
        )
        return [
            {
                "id": str(e.id),
                "contrato_id": str(e.contrato_id),
                "numero_estimacion": e.numero_estimacion,
                "periodo_inicio": e.periodo_inicio,
                "periodo_fin": e.periodo_fin,
                "monto_ejecutado": float(e.monto_ejecutado or 0),
                "avance_fisico": float(e.avance_fisico or 0),
                "avance_financiero": float(e.avance_financiero or 0),
                "aprobado": bool(e.aprobado),
                "fecha_aprobacion": e.fecha_aprobacion,
                "created_at": e.created_at,
            }
            for e in result.scalars().all()
        ]

    async def crear_penalizacion(self, db: AsyncSession, contrato_id: UUID, data: PenalizacionCreate, current_user: User) -> PenalizacionContrato:
        await authorize_by_id(db, current_user.id, current_user.tenant_id, 'approve')
        contrato = await self._obtener_contrato(db, contrato_id, current_user)
        # CONECTADO (pedido explícito 2026-09-07): antes se confiaba en
        # data.monto/data.tope_legal tal cual los mandara el cliente --
        # nada impedía un tope_legal inflado que violara el tope real de
        # ley (10% del contrato, LOPSRM/LAASSP). MotorGarantiasPenalizaciones
        # resuelve tope desde LegalRule PENALIZACIONES; el cálculo
        # automático para ATRASO, pero ningún servicio lo llamaba. Ahora
        # el tope legal SIEMPRE se recalcula en el servidor -- nunca se
        # toma del cliente -- y para ATRASO el monto también se calcula
        # aquí en vez de confiar en el que mande el cliente.
        monto_contrato = float(contrato.monto_total) if contrato.monto_total else 0.0
        motor = MotorGarantiasPenalizaciones()
        jurisdiction_code = getattr(contrato, "jurisdiction_code", None) or None
        tope_dec = await motor.resolve_tope_penas(
            db,
            tenant_id=current_user.tenant_id,
            jurisdiction_code=jurisdiction_code,
            monto_contrato=monto_contrato,
            es_obra=True,
        )
        if not tope_dec.found:
            raise MegalodonException(
                ErrorCode.JURIDICO_GENERICO,
                f"No hay regla de tope de penas en DB ({tope_dec.error or tope_dec.rule_id}). "
                f"Carga garantias_legal_rules.csv.",
                status_code=422,
            )
        tope_legal = tope_dec.monto_requerido

        if data.tipo == TipoPenalizacion.ATRASO and data.dias_atraso is not None:
            resultado = await motor.calcular_penalizacion_atraso(
                db,
                monto_contrato,
                data.dias_atraso,
                tenant_id=current_user.tenant_id,
                jurisdiction_code=jurisdiction_code,
                es_obra=True,
                porcentaje_diario=getattr(data, "porcentaje_diario", None),
            )
            if not resultado.found:
                raise MegalodonException(
                    ErrorCode.JURIDICO_GENERICO,
                    resultado.error or "No se pudo calcular penalización desde DB.",
                    status_code=422,
                )
            monto = resultado.monto_aplicado if resultado.monto_calculado else min(data.monto, tope_legal)
            dentro_tope = resultado.dentro_tope if resultado.monto_calculado else data.monto <= tope_legal
        else:
            monto = min(data.monto, tope_legal) if tope_legal else data.monto
            dentro_tope = data.monto <= tope_legal if tope_legal else True

        penalizacion = PenalizacionContrato(
            contrato_id=contrato_id,
            tipo=data.tipo,
            monto=monto,
            dias_atraso=data.dias_atraso,
            descripcion=data.descripcion,
            tope_legal=tope_legal,
            dentro_tope=dentro_tope,
            aplicada=False,
            tenant_id=current_user.tenant_id,
            creado_por_id=current_user.id,
            actualizado_por_id=current_user.id,
        )
        db.add(penalizacion)
        await db.commit()
        await db.refresh(penalizacion)
        return penalizacion

    async def listar_penalizaciones(self, db: AsyncSession, contrato_id: UUID, current_user: User) -> List[Dict[str, Any]]:
        await self._obtener_contrato(db, contrato_id, current_user)
        result = await db.execute(
            select(PenalizacionContrato)
            .join(Contrato, PenalizacionContrato.contrato_id == Contrato.id)
            .where(PenalizacionContrato.contrato_id == contrato_id)
            .where(Contrato.tenant_id == current_user.tenant_id)
            .order_by(PenalizacionContrato.created_at.desc())
        )
        return [
            {
                "id": str(p.id),
                "contrato_id": str(p.contrato_id),
                "tipo": p.tipo.value if hasattr(p.tipo, 'value') else str(p.tipo),
                "monto": float(p.monto or 0),
                "dias_atraso": p.dias_atraso,
                "descripcion": p.descripcion,
                "tope_legal": float(p.tope_legal or 0),
                "dentro_tope": bool(p.dentro_tope),
                "aplicada": bool(p.aplicada),
                "fecha_aplicacion": p.fecha_aplicacion,
                "created_at": p.created_at,
            }
            for p in result.scalars().all()
        ]

    async def resumen_contrato(self, db: AsyncSession, contrato_id: UUID, current_user: User) -> Dict[str, Any]:
        contrato = await self._obtener_contrato(db, contrato_id, current_user)
        mods = (await db.execute(select(ConvenioModificatorio).where(ConvenioModificatorio.contrato_id == contrato_id))).scalars().all()
        gars = (await db.execute(select(GarantiaContrato).where(GarantiaContrato.contrato_id == contrato_id))).scalars().all()
        ents = (await db.execute(select(EntregableContrato).where(EntregableContrato.contrato_id == contrato_id).order_by(EntregableContrato.numero_estimacion))).scalars().all()
        pens = (await db.execute(select(PenalizacionContrato).where(PenalizacionContrato.contrato_id == contrato_id))).scalars().all()

        monto_mods = 0.0
        plazo_mods = 0
        for m in mods:
            if m.monto_anterior is not None and m.monto_nuevo is not None:
                monto_mods += float(m.monto_nuevo) - float(m.monto_anterior)
            if m.plazo_anterior is not None and m.plazo_nuevo is not None:
                plazo_mods += int(m.plazo_nuevo) - int(m.plazo_anterior)

        monto_ejec = sum(float(e.monto_ejecutado or 0) for e in ents if e.aprobado)
        monto_pen = sum(float(p.monto or 0) for p in pens if p.aplicada)
        alertas = await self.verificar_vigencia_garantias(db, contrato_id, current_user)

        return {
            "contrato_id": str(contrato.id),
            "numero_contrato": contrato.numero_contrato,
            "estado": EstadoContrato(contrato.estado).value if hasattr(contrato.estado, 'value') else str(contrato.estado),
            "objeto": contrato.objeto,
            "monto_original": float(contrato.monto_original or 0),
            "monto_total": float(contrato.monto_total or 0),
            "monto_modificaciones": round(monto_mods, 4),
            "monto_ejecutado": round(monto_ejec, 4),
            "monto_pendiente": round(float(contrato.monto_total or 0) - monto_ejec, 4),
            "monto_penalizaciones": round(monto_pen, 4),
            "plazo_original": contrato.plazo_original,
            "plazo_actual": contrato.plazo_dias,
            "plazo_modificaciones": plazo_mods,
            "total_modificatorios": len(mods),
            "total_garantias": len(gars),
            "total_entregables": len(ents),
            "total_penalizaciones": len(pens),
            "alertas_garantias": alertas,
        }
