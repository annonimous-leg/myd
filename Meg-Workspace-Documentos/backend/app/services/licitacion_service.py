# Copyright © 2026 Cristian Rodriguez
"""Servicio de licitaciones — Máquina de estados legal completa."""
from __future__ import annotations

from datetime import datetime, timezone
from typing import Optional, List, Dict, Any
from uuid import UUID

from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, func, and_

from app.core.authorization import authorize_by_id
from app.core.errors import MegalodonException, ErrorCode
from app.models.expediente import ExpedienteObra
from app.models.proveedor import Proveedor
from app.models.licitacion import (
    Licitacion,
    EstadoLicitacion,
    TipoProcedimiento,
    JuntaAclaracion,
    Proposicion,
    EvaluacionLicitacion,
    TipoEvaluacion,
    ResultadoEvaluacion,
)
from app.models.user import User
from app.schemas.licitacion import (
    LicitacionCreate, LicitacionUpdate, JuntaAclaracionCreate,
    ProposicionCreate, EvaluacionCreate, EvaluacionAutomaticaCreate, TransicionEstadoCreate,
)
from app.services import licitacion_evaluation as evaluation_policy


class LicitacionService:
    TRANSICIONES = {
        EstadoLicitacion.PLANEACION: [EstadoLicitacion.INVESTIGACION_MERCADO, EstadoLicitacion.SELECCION_PROCEDIMIENTO, EstadoLicitacion.CANCELADA],
        EstadoLicitacion.INVESTIGACION_MERCADO: [EstadoLicitacion.SELECCION_PROCEDIMIENTO, EstadoLicitacion.CONVOCATORIA, EstadoLicitacion.CANCELADA],
        EstadoLicitacion.SELECCION_PROCEDIMIENTO: [EstadoLicitacion.CONVOCATORIA, EstadoLicitacion.CANCELADA],
        EstadoLicitacion.CONVOCATORIA: [EstadoLicitacion.JUNTA_ACLARACIONES, EstadoLicitacion.CANCELADA],
        EstadoLicitacion.JUNTA_ACLARACIONES: [EstadoLicitacion.RECEPCION_PROPUESTAS, EstadoLicitacion.CANCELADA],
        EstadoLicitacion.RECEPCION_PROPUESTAS: [EstadoLicitacion.APERTURA, EstadoLicitacion.DESIERTA, EstadoLicitacion.CANCELADA],
        EstadoLicitacion.APERTURA: [EstadoLicitacion.EVALUACION, EstadoLicitacion.DESIERTA, EstadoLicitacion.CANCELADA],
        EstadoLicitacion.EVALUACION: [EstadoLicitacion.FALLO, EstadoLicitacion.DESIERTA, EstadoLicitacion.CANCELADA],
        EstadoLicitacion.FALLO: [EstadoLicitacion.ADJUDICACION, EstadoLicitacion.DESIERTA],
        EstadoLicitacion.ADJUDICACION: [EstadoLicitacion.CONTRATO],
        EstadoLicitacion.CONTRATO: [EstadoLicitacion.CERRADA],
        EstadoLicitacion.DESIERTA: [],
        EstadoLicitacion.CANCELADA: [],
        EstadoLicitacion.CERRADA: [],
    }

    async def _obtener_licitacion(self, db: AsyncSession, licitacion_id: UUID, current_user: User, *, bloquear: bool = False) -> Licitacion:
        query = (
            select(Licitacion)
            .join(ExpedienteObra, Licitacion.expediente_id == ExpedienteObra.id)
            .where(Licitacion.id == licitacion_id)
            .where(ExpedienteObra.tenant_id == current_user.tenant_id)
        )
        if bloquear:
            query = query.with_for_update(of=Licitacion).execution_options(populate_existing=True)
        result = await db.execute(query)
        lic = result.scalar_one_or_none()
        if not lic:
            raise MegalodonException(ErrorCode.NOT_FOUND, f"Licitación '{licitacion_id}' no encontrada.")
        return lic

    async def _obtener_proposicion_en_licitacion(self, db: AsyncSession, proposicion_id: UUID, licitacion_id: UUID, current_user: User, *, bloquear: bool = False) -> Proposicion:
        query = (
            select(Proposicion)
            .join(Licitacion, Proposicion.licitacion_id == Licitacion.id)
            .join(ExpedienteObra, Licitacion.expediente_id == ExpedienteObra.id)
            .where(Proposicion.id == proposicion_id, Proposicion.licitacion_id == licitacion_id,
                   Proposicion.tenant_id == current_user.tenant_id,
                   ExpedienteObra.tenant_id == current_user.tenant_id)
        )
        if bloquear:
            query = query.with_for_update(of=Proposicion).execution_options(populate_existing=True)
        result = await db.execute(query)
        proposicion = result.scalar_one_or_none()
        if not proposicion:
            raise MegalodonException(ErrorCode.NOT_FOUND, "Proposición no encontrada")
        return proposicion

    async def crear(self, db: AsyncSession, data: LicitacionCreate, current_user: User) -> Licitacion:
        await authorize_by_id(db, current_user.id, current_user.tenant_id, 'write')
        expediente = await db.execute(
            select(ExpedienteObra)
            .where(ExpedienteObra.id == data.expediente_id)
            .where(ExpedienteObra.tenant_id == current_user.tenant_id)
        )
        if expediente.scalar_one_or_none() is None:
            raise MegalodonException(ErrorCode.NOT_FOUND, f"Expediente '{data.expediente_id}' no encontrado")

        jurisdiction_code = data.jurisdiction_code.strip().upper()
        if not jurisdiction_code:
            raise MegalodonException(ErrorCode.PARAMETRO_INVALIDO, "Debe seleccionar la dependencia convocante.", 422)
        lic = Licitacion(
            expediente_id=data.expediente_id,
            folio=data.folio,
            jurisdiction_code=jurisdiction_code,
            tipo_procedimiento=data.tipo_procedimiento,
            estado=EstadoLicitacion.PLANEACION,
            objeto=data.objeto,
            monto_estimado=data.monto_estimado,
            plazo_dias=data.plazo_dias,
            fecha_convocatoria=data.fecha_convocatoria,
            reglas_participacion=data.reglas_participacion,
            bases=data.bases,
            matriz_evaluacion=data.matriz_evaluacion,
            presupuesto_dependencia_miles=data.presupuesto_dependencia_miles,
            tenant_id=current_user.tenant_id,
            creado_por_id=current_user.id,
            actualizado_por_id=current_user.id,
        )
        db.add(lic)
        await db.commit()
        await db.refresh(lic)
        return lic

    async def listar(
        self,
        db: AsyncSession,
        current_user: User,
        estado=None,
        tipo_procedimiento=None,
        expediente_id=None,
        skip: int = 0,
        limit: int = 50,
    ) -> dict:
        query = select(Licitacion).where(Licitacion.tenant_id == current_user.tenant_id)
        if estado is not None:
            query = query.where(Licitacion.estado == estado)
        if tipo_procedimiento is not None:
            query = query.where(Licitacion.tipo_procedimiento == tipo_procedimiento)
        if expediente_id is not None:
            query = query.where(Licitacion.expediente_id == expediente_id)
        total = await db.scalar(select(func.count()).select_from(query.subquery())) or 0
        items = (await db.execute(query.order_by(Licitacion.created_at.desc()).offset(skip).limit(limit))).scalars().all()
        return {"total": total, "items": items}

    async def obtener(self, db: AsyncSession, licitacion_id: UUID, current_user: User) -> Licitacion:
        return await self._obtener_licitacion(db, licitacion_id, current_user)

    async def actualizar(self, db: AsyncSession, licitacion_id: UUID, data: LicitacionUpdate, current_user: User) -> Licitacion:
        await authorize_by_id(db, current_user.id, current_user.tenant_id, 'write')
        lic = await self._obtener_licitacion(db, licitacion_id, current_user, bloquear=True)
        if data.version_esperada is not None and data.version_esperada != lic.row_version:
            evaluation_policy.conflict('La licitación cambió; actualice antes de guardar las bases.')
        if lic.estado not in [EstadoLicitacion.PLANEACION, EstadoLicitacion.INVESTIGACION_MERCADO, EstadoLicitacion.SELECCION_PROCEDIMIENTO, EstadoLicitacion.CONVOCATORIA]:
            raise MegalodonException(ErrorCode.BAD_REQUEST, f"No se puede editar licitación en estado '{EstadoLicitacion(lic.estado).value}'.")
        changes_policy = any(getattr(data, field) is not None and getattr(data, field) != getattr(lic, field)
                             for field in {'bases', 'matriz_evaluacion', 'jurisdiction_code'} & data.model_fields_set)
        if lic.bases_congeladas and changes_policy:
            raise MegalodonException(ErrorCode.BAD_REQUEST, 'Las bases están congeladas; registre una nueva versión documental', 409)
        if changes_policy:
            lic.bases_version += 1
        for field in [
            'folio', 'objeto', 'tipo_procedimiento', 'reglas_participacion',
            'jurisdiction_code', 'monto_estimado', 'plazo_dias', 'fecha_convocatoria', 'fecha_junta_aclaraciones',
            'fecha_apertura', 'matriz_evaluacion', 'bases', 'justificacion_procedimiento', 'investigacion_mercado',
        ]:
            val = getattr(data, field, None)
            if val is not None:
                setattr(lic, field, val)
        lic.actualizado_por_id = current_user.id
        await db.commit()
        await db.refresh(lic)
        return lic

    async def transicionar_estado(self, db: AsyncSession, licitacion_id: UUID, data: TransicionEstadoCreate, current_user: User) -> Licitacion:
        decision = data.nuevo_estado in {EstadoLicitacion.EVALUACION, EstadoLicitacion.FALLO,
                                        EstadoLicitacion.ADJUDICACION, EstadoLicitacion.CONTRATO}
        await authorize_by_id(db, current_user.id, current_user.tenant_id, 'approve' if decision else 'write')
        lic = await self._obtener_licitacion(db, licitacion_id, current_user, bloquear=True)
        nuevo = data.nuevo_estado
        permitidos = self.TRANSICIONES.get(lic.estado, [])
        if nuevo not in permitidos:
            raise MegalodonException(ErrorCode.BAD_REQUEST, f"Transición de '{EstadoLicitacion(lic.estado).value}' a '{nuevo.value}' no permitida.")
        if nuevo == EstadoLicitacion.CONVOCATORIA and (not lic.folio or not lic.bases):
            raise MegalodonException(ErrorCode.BAD_REQUEST, "Requiere folio y bases para convocatoria.")
        if nuevo in {EstadoLicitacion.JUNTA_ACLARACIONES, EstadoLicitacion.RECEPCION_PROPUESTAS}:
            evaluation_policy.context(lic)
        # La junta de aclaraciones ocurre fuera de Megalodon.
        # El usuario incorpora sus actas/modificaciones como documentación oficial
        # del expediente; Megalodon no exige ni crea una junta para avanzar.
        if nuevo == EstadoLicitacion.APERTURA:
            count = await db.scalar(select(func.count()).where(Proposicion.licitacion_id == licitacion_id)) or 0
            if count == 0:
                raise MegalodonException(ErrorCode.BAD_REQUEST, "No hay proposiciones registradas.")
        if nuevo == EstadoLicitacion.EVALUACION:
            proposals = await self.listar_proposiciones(db, licitacion_id, current_user)
            if not proposals:
                evaluation_policy.conflict("No hay proposiciones evaluadas.")
            for prop in proposals:
                layers = await evaluation_policy.current_layers(db, lic, prop, current_user.tenant_id)
                if set(layers) != evaluation_policy.LAYERS:
                    evaluation_policy.conflict("Todas las proposiciones requieren las tres capas vigentes.")
        if nuevo == EstadoLicitacion.FALLO:
            evaluation_policy.conflict("Emita el fallo mediante el comando con proposición ganadora explícita.")
        if nuevo in {EstadoLicitacion.ADJUDICACION, EstadoLicitacion.CONTRATO}:
            if not lic.fallo_snapshot:
                evaluation_policy.conflict("Se requiere fallo trazable antes de adjudicar o contratar.")
            prop = await self._obtener_proposicion_en_licitacion(
                db, UUID(lic.fallo_snapshot["proposicion_id"]), lic.id, current_user, bloquear=True)
            await evaluation_policy.require_awarded(db, lic, prop, current_user.tenant_id)
            if nuevo == EstadoLicitacion.CONTRATO:
                from app.models.contrato import Contrato
                if not await db.scalar(select(Contrato.id).where(Contrato.licitacion_id == lic.id,
                                                               Contrato.tenant_id == current_user.tenant_id)):
                    evaluation_policy.conflict("La transición requiere un contrato persistido.")
        lic.estado = nuevo
        if data.justificacion:
            lic.justificacion_procedimiento = data.justificacion
        lic.actualizado_por_id = current_user.id
        await db.commit()
        await db.refresh(lic)
        return lic

    async def listar_juntas(self, db: AsyncSession, licitacion_id: UUID, current_user: User) -> List[JuntaAclaracion]:
        await self._obtener_licitacion(db, licitacion_id, current_user)
        result = await db.execute(
            select(JuntaAclaracion)
            .join(Licitacion, JuntaAclaracion.licitacion_id == Licitacion.id)
            .where(JuntaAclaracion.licitacion_id == licitacion_id)
            .where(Licitacion.tenant_id == current_user.tenant_id)
            .order_by(JuntaAclaracion.created_at.desc())
        )
        return result.scalars().all()

    async def registrar_junta(
        self,
        db: AsyncSession,
        licitacion_id: UUID,
        data: JuntaAclaracionCreate,
        current_user: User,
    ) -> JuntaAclaracion:
        """Registra el acta oficial de una junta ya celebrada externamente."""
        await authorize_by_id(db, current_user.id, current_user.tenant_id, 'write')
        await self._obtener_licitacion(db, licitacion_id, current_user)
        junta = JuntaAclaracion(
            licitacion_id=licitacion_id,
            tenant_id=current_user.tenant_id,
            creado_por_id=current_user.id,
            actualizado_por_id=current_user.id,
            **data.model_dump(),
        )
        db.add(junta)
        await db.commit()
        await db.refresh(junta)
        return junta

    async def registrar_proposicion(self, db: AsyncSession, licitacion_id: UUID, data: ProposicionCreate, current_user: User) -> Proposicion:
        await authorize_by_id(db, current_user.id, current_user.tenant_id, 'write')
        lic = await self._obtener_licitacion(db, licitacion_id, current_user, bloquear=True)
        if lic.estado not in [EstadoLicitacion.JUNTA_ACLARACIONES, EstadoLicitacion.RECEPCION_PROPUESTAS]:
            raise MegalodonException(ErrorCode.BAD_REQUEST, f"No se puede registrar proposición en estado '{EstadoLicitacion(lic.estado).value}'.")
        proveedor = await db.execute(
            select(Proveedor)
            .where(Proveedor.id == data.proveedor_id)
            .where(Proveedor.tenant_id == current_user.tenant_id)
        )
        if proveedor.scalar_one_or_none() is None:
            raise MegalodonException(ErrorCode.NOT_FOUND, f"Proveedor '{data.proveedor_id}' no encontrado")
        dup = await db.execute(
            select(Proposicion)
            .where(Proposicion.licitacion_id == licitacion_id)
            .where(Proposicion.proveedor_id == data.proveedor_id)
        )
        if dup.scalar_one_or_none() is not None:
            raise MegalodonException(ErrorCode.CONFLICT, "El proveedor ya presentó una proposición en esta licitación.")
        evaluation_policy.context(lic)
        proposicion = Proposicion(
            licitacion_id=licitacion_id,
            proveedor_id=data.proveedor_id,
            monto=data.monto,
            plazo_dias=data.plazo_dias,
            sobres_digitales=data.sobres_digitales,
            tenant_id=current_user.tenant_id,
            creado_por_id=current_user.id,
            actualizado_por_id=current_user.id,
        )
        db.add(proposicion)
        lic.row_version += 1
        lic.actualizado_por_id = current_user.id
        if lic.estado == EstadoLicitacion.JUNTA_ACLARACIONES:
            lic.estado = EstadoLicitacion.RECEPCION_PROPUESTAS
            lic.actualizado_por_id = current_user.id
        await db.commit()
        await db.refresh(proposicion)
        return proposicion

    async def listar_proposiciones(self, db: AsyncSession, licitacion_id: UUID, current_user: User) -> List[Proposicion]:
        await self._obtener_licitacion(db, licitacion_id, current_user)
        result = await db.execute(
            select(Proposicion)
            .join(Licitacion, Proposicion.licitacion_id == Licitacion.id)
            .where(Proposicion.licitacion_id == licitacion_id)
            .where(Licitacion.tenant_id == current_user.tenant_id)
            .order_by(Proposicion.created_at.desc())
        )
        return result.scalars().all()

    async def congelar_bases(self, db, licitacion_id, current_user, *, version_esperada=None):
        await authorize_by_id(db, current_user.id, current_user.tenant_id, 'approve')
        try:
            lic = await self._obtener_licitacion(db, licitacion_id, current_user, bloquear=True)
            if version_esperada is not None and lic.row_version != version_esperada:
                evaluation_policy.conflict('Las bases cambiaron; revise la versión actual antes de aprobar.')
            if lic.estado not in {EstadoLicitacion.PLANEACION, EstadoLicitacion.INVESTIGACION_MERCADO,
                                  EstadoLicitacion.SELECCION_PROCEDIMIENTO, EstadoLicitacion.CONVOCATORIA}:
                evaluation_policy.conflict("Las bases deben aprobarse antes de recibir proposiciones.")
            evaluation_policy.context(lic, require_frozen=False)
            lic.bases_congeladas = True
            lic.actualizado_por_id = current_user.id
            await db.commit()
            await db.refresh(lic)
            return lic
        except BaseException:
            await db.rollback()
            raise

    async def _evaluation_target(self, db, licitacion_id, proposicion_id, current_user, *, allow_reception=False):
        await authorize_by_id(db, current_user.id, current_user.tenant_id, 'approve')
        lic = await self._obtener_licitacion(db, licitacion_id, current_user, bloquear=True)
        allowed = {EstadoLicitacion.APERTURA, EstadoLicitacion.EVALUACION}
        if allow_reception:
            allowed.add(EstadoLicitacion.RECEPCION_PROPUESTAS)
        if lic.estado not in allowed:
            evaluation_policy.conflict("La evaluación requiere apertura o evaluación en curso.")
        prop = await self._obtener_proposicion_en_licitacion(
            db, proposicion_id, licitacion_id, current_user, bloquear=True)
        evaluation_policy.context(lic)
        return lic, prop

    async def revisar_documentacion(self, db, licitacion_id, proposicion_id, data, current_user):
        """Persist a review attestation and independently hash its stored support."""
        from app.services.proposicion_verification import attest
        try:
            lic, prop = await self._evaluation_target(db, licitacion_id, proposicion_id, current_user,
                                                       allow_reception=True)
            await attest(db, lic, prop, current_user, data)
            evaluation_policy.begin_revision(lic)
            await db.commit()
            return prop
        except BaseException:
            await db.rollback()
            raise

    async def crear_evaluacion(self, db: AsyncSession, licitacion_id: UUID, data: EvaluacionCreate, current_user: User) -> EvaluacionLicitacion:
        """Review a layer using the same engine and frozen evidence as workspace.

        A reviewer may reject/observe an otherwise passing layer, but may not
        turn a failed computation or missing legal verification into approval.
        """
        try:
            lic, prop = await self._evaluation_target(db, licitacion_id, data.proposicion_id, current_user)
            inputs = (data.criterios or {}).get("datos")
            if not isinstance(inputs, dict):
                evaluation_policy.conflict("El dictamen requiere evidencia por criterio en criterios.datos.")
            result = evaluation_policy.evaluate_layer(lic, prop, data.tipo, inputs,
                                                       precio_referencia=lic.monto_estimado)
            if data.resultado == ResultadoEvaluacion.APROBADA and result.resultado != ResultadoEvaluacion.APROBADA:
                evaluation_policy.conflict("Un dictamen manual no puede aprobar una capa que incumple las bases.")
            result.resultado = data.resultado
            result.dictamen = data.dictamen or result.dictamen
            evaluation_policy.begin_revision(lic)
            row = evaluation_policy.evaluation_row(lic, prop, current_user, result, inputs=inputs)
            db.add(row)
            await db.flush()
            await evaluation_policy.update_admission(db, lic, prop, current_user.tenant_id)
            prop.actualizado_por_id = current_user.id
            await db.commit()
            return row
        except BaseException:
            await db.rollback()
            raise

    async def evaluar_proposicion_automatica(self, db: AsyncSession, licitacion_id: UUID, data: EvaluacionAutomaticaCreate, current_user: User) -> EvaluacionLicitacion:
        try:
            lic, prop = await self._evaluation_target(db, licitacion_id, data.proposicion_id, current_user)
            result = evaluation_policy.evaluate_layer(lic, prop, data.tipo, data.datos,
                                                       precio_referencia=lic.monto_estimado)
            evaluation_policy.begin_revision(lic)
            row = evaluation_policy.evaluation_row(lic, prop, current_user, result, inputs=data.datos)
            db.add(row)
            await db.flush()
            await evaluation_policy.update_admission(db, lic, prop, current_user.tenant_id)
            prop.actualizado_por_id = current_user.id
            await db.commit()
            return row
        except BaseException:
            await db.rollback()
            raise

    async def evaluar_workspace(self, db, licitacion_id, current_user, *, review=None):
        """One lock, one policy, one commit for every layer and state change."""
        await authorize_by_id(db, current_user.id, current_user.tenant_id, 'approve')
        try:
            lic = await self._obtener_licitacion(db, licitacion_id, current_user, bloquear=True)
            if review is not None and review.revision_esperada != lic.row_version:
                evaluation_policy.conflict('La licitación cambió; actualice los insumos antes de evaluar.')
            if lic.estado not in {EstadoLicitacion.RECEPCION_PROPUESTAS, EstadoLicitacion.APERTURA,
                                  EstadoLicitacion.EVALUACION}:
                evaluation_policy.conflict("La licitación no está disponible para evaluación.")
            evaluation_policy.context(lic)
            proposals = (await db.scalars(select(Proposicion).where(
                Proposicion.licitacion_id == lic.id, Proposicion.tenant_id == current_user.tenant_id
            ).order_by(Proposicion.id).with_for_update().execution_options(populate_existing=True))).all()
            if not proposals:
                evaluation_policy.conflict("No hay proposiciones recibidas para evaluar.")
            if review is not None and set(review.insumos) != {prop.id for prop in proposals}:
                evaluation_policy.conflict('Los insumos deben corresponder a todas las proposiciones de esta licitación.')
            created, results = 0, []
            kinds = ((TipoEvaluacion.LEGAL, 'legal'), (TipoEvaluacion.TECNICA, 'tecnico'),
                     (TipoEvaluacion.ECONOMICA, 'economico'))
            for prop in proposals:
                layers = await evaluation_policy.current_layers(db, lic, prop, current_user.tenant_id)
                envelopes = review.insumos[prop.id].model_dump() if review is not None else prop.sobres_digitales or {}
                changed_inputs = review is not None and any(
                    kind.value not in layers or (layers[kind.value].criterios or {}).get('datos') != envelopes[key]
                    for kind, key in kinds)
                if set(layers) != evaluation_policy.LAYERS or changed_inputs:
                    evaluation_policy.begin_revision(lic)
                    for kind, key in kinds:
                        inputs = envelopes.get(key)
                        if not isinstance(inputs, dict):
                            evaluation_policy.conflict(f"Falta evidencia de la capa {key} en una proposición.")
                        result = evaluation_policy.evaluate_layer(lic, prop, kind, inputs,
                                                                   precio_referencia=lic.monto_estimado)
                        db.add(evaluation_policy.evaluation_row(lic, prop, current_user, result, inputs=inputs))
                        created += 1
                    await db.flush()
                layers = await evaluation_policy.update_admission(db, lic, prop, current_user.tenant_id)
                prop.actualizado_por_id = current_user.id
                results.append({"proposicion_id": str(prop.id), "estado": prop.estado,
                                **{str(kind).lower(): row.resultado == ResultadoEvaluacion.APROBADA
                                   for kind, row in layers.items()}})
            lic.estado = EstadoLicitacion.EVALUACION
            lic.actualizado_por_id = current_user.id
            await db.commit()
            return {"licitacion_id": str(lic.id), "estado": lic.estado,
                    "proposiciones_evaluadas": len(proposals), "evaluaciones_creadas": created,
                    "resultados": results}
        except BaseException:
            await db.rollback()
            raise

    async def emitir_fallo(self, db: AsyncSession, licitacion_id: UUID, proposicion_ganadora_id: UUID, current_user: User) -> Licitacion:
        await authorize_by_id(db, current_user.id, current_user.tenant_id, 'approve')
        try:
            lic = await self._obtener_licitacion(db, licitacion_id, current_user, bloquear=True)
            prop = await self._obtener_proposicion_en_licitacion(db, proposicion_ganadora_id,
                                                               licitacion_id, current_user, bloquear=True)
            layers = await evaluation_policy.require_adjudicable(db, lic, prop, current_user.tenant_id)
            if lic.estado == EstadoLicitacion.FALLO:
                if (lic.fallo_snapshot or {}).get("proposicion_id") != str(prop.id):
                    evaluation_policy.conflict("El fallo ya fue emitido para otra proposición o requiere revisión histórica.")
                await evaluation_policy.require_awarded(db, lic, prop, current_user.tenant_id)
                return lic
            if lic.estado not in {EstadoLicitacion.APERTURA, EstadoLicitacion.EVALUACION}:
                evaluation_policy.conflict("No se puede emitir fallo en el estado actual.")
            signed_at = datetime.now(timezone.utc)
            lic.fallo_snapshot = {
                **evaluation_policy.snapshot(lic, prop), "proposicion_id": str(prop.id),
                "proveedor_id": str(prop.proveedor_id), "monto": str(prop.monto), "plazo_dias": prop.plazo_dias,
                "evaluaciones": {str(kind): str(row.id) for kind, row in layers.items()},
                "autor_id": str(current_user.id), "fecha": signed_at.isoformat(),
            }
            lic.estado = EstadoLicitacion.FALLO
            lic.dictamen = f"Proposición ganadora: {prop.id}"
            lic.fecha_fallo = signed_at.date().isoformat()
            lic.actualizado_por_id = current_user.id
            await db.commit()
            return lic
        except BaseException:
            await db.rollback()
            raise

    async def resumen_licitacion(self, db: AsyncSession, licitacion_id: UUID, current_user: User) -> Dict[str, Any]:
        lic = await self._obtener_licitacion(db, licitacion_id, current_user)
        juntas = await db.scalar(select(func.count()).where(JuntaAclaracion.licitacion_id == licitacion_id)) or 0
        proposiciones = await db.scalar(select(func.count()).where(Proposicion.licitacion_id == licitacion_id)) or 0
        evaluaciones = await db.scalar(select(func.count()).where(EvaluacionLicitacion.licitacion_id == licitacion_id)) or 0
        return {
            "licitacion_id": str(lic.id),
            "folio": lic.folio,
            "estado": EstadoLicitacion(lic.estado).value if hasattr(lic.estado, 'value') else str(lic.estado),
            "tipo_procedimiento": TipoProcedimiento(lic.tipo_procedimiento).value if hasattr(lic.tipo_procedimiento, 'value') else str(lic.tipo_procedimiento),
            "objeto": lic.objeto,
            "monto_estimado": float(lic.monto_estimado or 0),
            "plazo_dias": lic.plazo_dias,
            "juntas_aclaraciones": int(juntas),
            "proposiciones": int(proposiciones),
            "evaluaciones": int(evaluaciones),
            "bases_congeladas": bool(lic.bases_congeladas),
        }
