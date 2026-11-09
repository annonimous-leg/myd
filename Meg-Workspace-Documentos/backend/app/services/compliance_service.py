# Copyright © 2026 Cristian Rodriguez
"""Servicio de compliance — Reglas, inconformidades, sanciones y evaluación automática."""
from typing import Optional, List
from uuid import UUID
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, func, and_
from sqlalchemy.orm import selectinload
from app.models.compliance import (
    ReglaCumplimiento, Inconformidad, Sancion, EvaluacionCompliance,
    EstadoInconformidad, TipoSancion, EstadoRegla,
)
from app.models.expediente import ExpedienteObra
from app.models.user import User
from app.schemas.compliance import (
    ReglaCumplimientoCreate, InconformidadCreate, InconformidadUpdate,
    SancionCreate, EvaluacionComplianceCreate,
)
from app.core.errors import MegalodonException, ErrorCode
from app.engines.compliance.motor_compliance import MotorCompliance

class ComplianceService:
    async def crear_regla(self, db: AsyncSession, data: ReglaCumplimientoCreate, current_user: User) -> ReglaCumplimiento:
        r = ReglaCumplimiento(
            nombre=data.nombre, descripcion=data.descripcion,
            tipo_procedimiento=data.tipo_procedimiento, etapa=data.etapa,
            requisitos=data.requisitos, obligatorio=data.obligatorio, activa=data.activa,
            condicion_evaluacion=data.condicion_evaluacion,
            tenant_id=current_user.tenant_id, creado_por_id=current_user.id)
        db.add(r); await db.commit(); await db.refresh(r); return r

    async def listar_reglas(self, db: AsyncSession, current_user: User,
                            tipo_procedimiento=None, etapa=None, activa=None, skip=0, limit=50) -> dict:
        q = select(ReglaCumplimiento).where(ReglaCumplimiento.tenant_id == current_user.tenant_id)
        if tipo_procedimiento: q = q.where(ReglaCumplimiento.tipo_procedimiento == tipo_procedimiento)
        if etapa: q = q.where(ReglaCumplimiento.etapa == etapa)
        if activa is not None: q = q.where(ReglaCumplimiento.activa == activa)
        total = await db.scalar(select(func.count()).select_from(q.subquery())) or 0
        items = (await db.execute(q.offset(skip).limit(limit).order_by(
            ReglaCumplimiento.etapa, ReglaCumplimiento.nombre))).scalars().all()
        return {"total": total, "items": items}

    async def obtener_regla(self, db: AsyncSession, regla_id: UUID, current_user: User) -> ReglaCumplimiento:
        r = (await db.execute(select(ReglaCumplimiento).where(and_(
            ReglaCumplimiento.id == regla_id,
            ReglaCumplimiento.tenant_id == current_user.tenant_id)))).scalar_one_or_none()
        if not r: raise MegalodonException(ErrorCode.NOT_FOUND, f"Regla '{regla_id}' no encontrada.", status_code=404)
        return r

    async def actualizar_regla(self, db: AsyncSession, regla_id: UUID, data: ReglaCumplimientoCreate, current_user: User) -> ReglaCumplimiento:
        r = await self.obtener_regla(db, regla_id, current_user)
        r.nombre=data.nombre; r.descripcion=data.descripcion; r.tipo_procedimiento=data.tipo_procedimiento
        r.etapa=data.etapa; r.requisitos=data.requisitos; r.obligatorio=data.obligatorio; r.activa=data.activa
        r.condicion_evaluacion=data.condicion_evaluacion; r.actualizado_por_id=current_user.id
        await db.commit(); await db.refresh(r); return r

    async def eliminar_regla(self, db: AsyncSession, regla_id: UUID, current_user: User) -> None:
        r = await self.obtener_regla(db, regla_id, current_user)
        await db.delete(r); await db.commit()

    async def crear_inconformidad(self, db: AsyncSession, data: InconformidadCreate, current_user: User) -> Inconformidad:
        # CORREGIDO (F-02): severidad/regla_id/asignado_a/fecha_limite no
        # existían ni en el modelo ni en el schema -- el ORM tronaba en cada
        # alta. Se agregaron como columnas reales en Inconformidad (ver
        # models/compliance.py) en vez de quitarle la funcionalidad al
        # servicio. EstadoInconformidad.ABIERTA tampoco existía en el enum;
        # REGISTRADA ya es el estado inicial correcto del ciclo de vida
        # (REGISTRADA -> EN_ANALISIS -> RESPONDIDA -> RESUELTA/ARCHIVADA).
        i = Inconformidad(
            expediente_id=data.expediente_id, licitacion_id=data.licitacion_id,
            contrato_id=data.contrato_id, titulo=data.titulo, descripcion=data.descripcion,
            severidad=data.severidad, estado=EstadoInconformidad.REGISTRADA,
            regla_id=data.regla_id, asignado_a=data.asignado_a,
            fecha_limite=data.fecha_limite, evidencia=data.evidencia,
            tenant_id=current_user.tenant_id, creado_por_id=current_user.id)
        db.add(i); await db.commit(); await db.refresh(i); return i

    async def listar_inconformidades(self, db: AsyncSession, current_user: User,
                                     estado=None, severidad=None, expediente_id=None, skip=0, limit=50) -> dict:
        q = select(Inconformidad).where(Inconformidad.tenant_id == current_user.tenant_id)
        if estado: q = q.where(Inconformidad.estado == estado)
        if severidad: q = q.where(Inconformidad.severidad == severidad)
        if expediente_id: q = q.where(Inconformidad.expediente_id == expediente_id)
        total = await db.scalar(select(func.count()).select_from(q.subquery())) or 0
        items = (await db.execute(q.offset(skip).limit(limit).order_by(
            Inconformidad.created_at.desc()))).scalars().all()
        return {"total": total, "items": items}

    async def obtener_inconformidad(self, db: AsyncSession, inconformidad_id: UUID, current_user: User) -> Inconformidad:
        i = (await db.execute(select(Inconformidad).where(and_(
            Inconformidad.id == inconformidad_id,
            Inconformidad.tenant_id == current_user.tenant_id)))).scalar_one_or_none()
        if not i: raise MegalodonException(ErrorCode.NOT_FOUND, f"Inconformidad '{inconformidad_id}' no encontrada.", status_code=404)
        return i

    async def actualizar_inconformidad(self, db: AsyncSession, inconformidad_id: UUID,
                                       data: InconformidadUpdate, current_user: User) -> Inconformidad:
        i = await self.obtener_inconformidad(db, inconformidad_id, current_user)
        # CORREGIDO (contra-auditoría V9): InconformidadUpdate acepta
        # 'respuesta'/'dictamen'/'fecha_dictamen' (siempre los aceptó, desde
        # antes de esta sesión), pero este loop nunca los incluía -- el
        # PATCH pasaba la validación de Pydantic y devolvía 200, pero esos
        # 3 campos nunca llegaban a la BD. Regresión real, no introducida
        # por las correcciones de F-02 (esas solo tocaron severidad/
        # regla_id/asignado_a/fecha_limite), pero sí en el mismo método.
        for field in ['titulo','descripcion','severidad','estado','asignado_a','fecha_limite',
                      'resolucion','evidencia','respuesta','dictamen','fecha_dictamen']:
            val = getattr(data, field, None)
            if val is not None: setattr(i, field, val)
        i.actualizado_por_id= current_user.id; await db.commit(); await db.refresh(i); return i

    async def crear_sancion(self, db: AsyncSession, data: SancionCreate, current_user: User) -> Sancion:
        # CORREGIDO (F-03): usaba data.monto/data.descripcion/data.fundamento_legal,
        # que no existen en SancionCreate ni en el modelo Sancion (que sí
        # tienen monto_multa/motivo/expediente_sancionador/hechos/pruebas/
        # audiencia_fecha/resolucion/vigencia_inicio/vigencia_fin -- ver
        # schemas/compliance.py). Además fijaba estado="ACTIVA" mientras el
        # modelo declara default "VIGENTE"; ahora coincide.
        s = Sancion(
            proveedor_id=data.proveedor_id, expediente_id=data.expediente_id,
            licitacion_id=data.licitacion_id, tipo=data.tipo, motivo=data.motivo,
            monto_multa=data.monto_multa, expediente_sancionador=data.expediente_sancionador,
            hechos=data.hechos, pruebas=data.pruebas, audiencia_fecha=data.audiencia_fecha,
            resolucion=data.resolucion, vigencia_inicio=data.vigencia_inicio,
            vigencia_fin=data.vigencia_fin, estado="VIGENTE",
            tenant_id=current_user.tenant_id, creado_por_id=current_user.id)
        db.add(s); await db.commit(); await db.refresh(s); return s

    async def listar_sanciones(self, db: AsyncSession, current_user: User,
                               proveedor_id=None, tipo=None, skip=0, limit=50) -> dict:
        q = select(Sancion).where(Sancion.tenant_id == current_user.tenant_id)
        if proveedor_id: q = q.where(Sancion.proveedor_id == proveedor_id)
        if tipo: q = q.where(Sancion.tipo == tipo)
        total = await db.scalar(select(func.count()).select_from(q.subquery())) or 0
        items = (await db.execute(q.offset(skip).limit(limit).order_by(
            Sancion.created_at.desc()))).scalars().all()
        return {"total": total, "items": items}

    async def obtener_sancion(self, db: AsyncSession, sancion_id: UUID, current_user: User) -> Sancion:
        s = (await db.execute(select(Sancion).where(and_(
            Sancion.id == sancion_id, Sancion.tenant_id == current_user.tenant_id)))).scalar_one_or_none()
        if not s: raise MegalodonException(ErrorCode.NOT_FOUND, f"Sancion '{sancion_id}' no encontrada.", status_code=404)
        return s

    async def evaluar_expediente(self, db: AsyncSession, expediente_id: str, current_user: User) -> dict:
        """
        CORREGIDO (F-04): la versión anterior NUNCA cargaba el expediente.
        Solo tomaba las reglas activas del tenant y clasificaba cada una en
        cumplidas/incumplidas según si TENÍA una condición o no -- sin mirar
        estado del expediente, licitación, contrato, documentos ni fechas.
        Dos expedientes del mismo tenant (uno completo, otro vacío) daban
        exactamente el mismo score. Ahora carga el expediente real con sus
        relaciones y delega en MotorCompliance.evaluar_expediente(), que
        evalúa condición por condición contra ese estado real -- el mismo
        motor que ya evalúa licitaciones y contratos.
        """
        expediente = (await db.execute(
            select(ExpedienteObra)
            .options(
                selectinload(ExpedienteObra.licitaciones),
                selectinload(ExpedienteObra.contratos),
                selectinload(ExpedienteObra.documentos),
            )
            .where(and_(
                ExpedienteObra.id == expediente_id,
                ExpedienteObra.tenant_id == current_user.tenant_id,
            ))
        )).scalar_one_or_none()
        if expediente is None:
            raise MegalodonException(
                ErrorCode.NOT_FOUND, f"Expediente '{expediente_id}' no encontrado.", status_code=404,
            )

        reglas = (await db.execute(select(ReglaCumplimiento).where(and_(
            ReglaCumplimiento.tenant_id == current_user.tenant_id,
            ReglaCumplimiento.activa == True)))).scalars().all()

        resultados = MotorCompliance().evaluar_expediente(expediente, list(reglas))

        cumplidas = [r for r in resultados if r.estado == EstadoRegla.CUMPLIDA]
        incumplidas = [r for r in resultados if r.estado == EstadoRegla.NO_CUMPLIDA]
        pendientes = [r for r in resultados if r.estado == EstadoRegla.PENDIENTE]
        no_aplica = [r for r in resultados if r.estado == EstadoRegla.NO_APLICA]

        # El score solo considera reglas efectivamente evaluadas (CUMPLIDA/
        # NO_CUMPLIDA). PENDIENTE (condición no evaluable/ausente, requiere
        # revisión manual) y NO_APLICA no cuentan ni a favor ni en contra --
        # antes "cumplidas" incluía por error toda regla sin condición.
        evaluadas = len(cumplidas) + len(incumplidas)
        score = (len(cumplidas) / evaluadas * 100) if evaluadas else 0.0

        detalle = lambda rs: [
            {"regla_id": r.regla_id, "nombre": r.nombre, "observaciones": r.observaciones}
            for r in rs
        ]

        return {
            "expediente_id": expediente_id,
            "total_reglas": len(reglas),
            "cumplidas": len(cumplidas),
            "incumplidas": len(incumplidas),
            "pendientes_revision_manual": len(pendientes),
            "no_aplica": len(no_aplica),
            "score": round(score, 2),
            "detalle_cumplidas": detalle(cumplidas),
            "detalle_incumplidas": detalle(incumplidas),
            "detalle_pendientes": detalle(pendientes),
        }
