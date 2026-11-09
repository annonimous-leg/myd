# Copyright © 2026 Cristian Rodriguez
# All rights reserved.
# Unauthorized copying, modification, distribution, or use is prohibited
# without prior written permission.

"""
ValidadorService - Orquestación de la validación completa de propuestas
de licitación, con persistencia de la bitácora para auditoría.
"""
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional
from uuid import UUID, uuid4

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.engines.validadores.motor_validador import MotorDeterministaLicitaciones, MotorValidador
from app.engines.validadores.motor_expediente import MotorValidacionExpediente, CHECKS_DEFAULT
from app.models.expediente import ExpedienteObra
from app.models.licitacion import Licitacion, Proposicion
from app.models.validador import ValidacionPropuesta, ValidacionExpediente, CheckValidacion
from app.core.errors import MegalodonException, ErrorCode
from app.core.authorization import authorize_by_id


class ValidadorService:
    """Servicio de validación de propuestas de licitación."""

    def __init__(self, db: AsyncSession):
        self.db = db
        self.motor_rfc = MotorValidador()

    async def evaluar_propuesta_completa(
        self,
        *,
        tenant_id: UUID,
        expediente_id: UUID,
        datos_propuesta: Dict[str, Any],
        creado_por_id: Optional[UUID] = None,
        proposicion_id: Optional[UUID] = None,
    ) -> ValidacionPropuesta:
        """Persist a diagnostic of declared inputs, without issuing legal facts.

        The optional proposition link only associates the diagnostic with the
        same tenant and expediente. Formal review is a separate approve command.
        """
        await authorize_by_id(self.db, creado_por_id, tenant_id, "write")
        result = await self.db.execute(
            select(ExpedienteObra).where(
                ExpedienteObra.id == expediente_id,
                ExpedienteObra.tenant_id == tenant_id,
            )
        )
        if not result.scalar_one_or_none():
            raise MegalodonException(ErrorCode.DOCUMENTO_NO_ENCONTRADO, f"Expediente {expediente_id} no encontrado")

        if proposicion_id is not None:
            linked = await self.db.scalar(select(Proposicion.id).join(
                Licitacion, Proposicion.licitacion_id == Licitacion.id,
            ).where(
                Proposicion.id == proposicion_id, Proposicion.tenant_id == tenant_id,
                Licitacion.tenant_id == tenant_id, Licitacion.expediente_id == expediente_id,
            ))
            if linked is None:
                raise MegalodonException(ErrorCode.DOCUMENTO_NO_ENCONTRADO,
                    "Proposición no encontrada en el expediente")

        motor = MotorDeterministaLicitaciones()
        reporte = motor.procesar_propuesta(datos_propuesta)

        validacion = ValidacionPropuesta(
            id=uuid4(),
            tenant_id=tenant_id,
            expediente_id=expediente_id,
            proposicion_id=proposicion_id,
            rfc_empresa=reporte.get("rfc_empresa"),
            estado=reporte["estado"],
            bitacora_evaluacion=reporte["bitacora_evaluacion"],
            datos_entrada=datos_propuesta,
            creado_por_id=creado_por_id,
            actualizado_por_id=creado_por_id,
        )
        self.db.add(validacion)

        await self.db.commit()
        await self.db.refresh(validacion)
        return validacion

    async def historial(self, expediente_id: UUID, tenant_id: UUID, limit: int = 50) -> List[ValidacionPropuesta]:
        result = await self.db.execute(
            select(ValidacionPropuesta)
            .where(
                ValidacionPropuesta.expediente_id == expediente_id,
                ValidacionPropuesta.tenant_id == tenant_id,
            )
            .order_by(ValidacionPropuesta.created_at.desc())
            .limit(limit)
        )
        return list(result.scalars().all())

    async def obtener(self, validacion_id: UUID, expediente_id: UUID, tenant_id: UUID) -> ValidacionPropuesta:
        """Valida que la validación pertenezca al expediente de la URL Y al
        tenant del usuario -- antes no se validaba ninguna de las dos cosas
        (mismo patrón de fuga cross-expediente/cross-tenant que ya se
        corrigió para BIM/topografía/presupuestos/programación)."""
        validacion = await self.db.get(ValidacionPropuesta, validacion_id)
        if (
            not validacion
            or str(validacion.expediente_id) != str(expediente_id)
            or str(validacion.tenant_id) != str(tenant_id)
        ):
            raise MegalodonException(
                ErrorCode.DOCUMENTO_NO_ENCONTRADO,
                f"Validación {validacion_id} no encontrada en el expediente {expediente_id}",
            )
        return validacion

    # ─── Compatibilidad retro: validaciones rápidas por RFC (formato,
    # NO es una consulta real al SAT/IMSS/INFONAVIT -- ver motor_validador.py) ───
    async def validar_completo_rfc(self, rfc: str, fsr: float = 1.0) -> Dict[str, Any]:
        resultados = self.motor_rfc.validar_completo(rfc, fsr)
        return {
            "rfc": rfc,
            "fsr": fsr,
            "aprobado": all(r.valido for r in resultados),
            "validaciones": [
                {
                    "entidad": r.entidad,
                    "valido": r.valido,
                    "estado": r.estado,
                    "mensaje": r.mensaje,
                }
                for r in resultados
            ],
        }


class ValidadorExpedienteService:
    """Servicio de validación documental/normativa de expedientes.

    Complementa a ValidadorService (que valida propuestas de licitación):
    este servicio corre el catálogo de CheckValidacion contra un
    ExpedienteObra completo -- documentos requeridos, montos, plazos,
    campos obligatorios, catálogos permitidos -- usando el motor de
    app.engines.validadores.motor_expediente.

    ANTES: ValidacionExpediente y CheckValidacion existían como modelos
    (con imports/tipos rotos) pero no había ningún servicio ni endpoint
    que los usara -- este servicio es esa pieza faltante.
    """

    def __init__(self, db: AsyncSession):
        self.db = db
        self.motor = MotorValidacionExpediente()

    async def _obtener_expediente_con_documentos(self, expediente_id: UUID, tenant_id: UUID) -> ExpedienteObra:
        result = await self.db.execute(
            select(ExpedienteObra)
            .options(
                selectinload(ExpedienteObra.documentos_cde),
                selectinload(ExpedienteObra.documentos),
            )
            .where(ExpedienteObra.id == expediente_id, ExpedienteObra.tenant_id == tenant_id)
        )
        expediente = result.scalar_one_or_none()
        if expediente is None:
            raise MegalodonException(ErrorCode.DOCUMENTO_NO_ENCONTRADO, f"Expediente {expediente_id} no encontrado")
        return expediente

    async def ejecutar(
        self,
        *,
        tenant_id: UUID,
        expediente_id: UUID,
        tipo: str,
        nombre: str,
        descripcion: Optional[str] = None,
        categoria: Optional[str] = None,
        check_codigos: Optional[List[str]] = None,
        ejecutado_por_id: Optional[UUID] = None,
    ) -> ValidacionExpediente:
        """Ejecuta el catálogo de checks activos (opcionalmente filtrado por
        categoría o por una lista explícita de códigos) contra el
        expediente, y persiste el resultado."""
        expediente = await self._obtener_expediente_con_documentos(expediente_id, tenant_id)

        query = select(CheckValidacion).where(
            CheckValidacion.tenant_id == tenant_id,
            CheckValidacion.activo.is_(True),
        )
        if categoria:
            query = query.where(CheckValidacion.categoria == categoria)
        if check_codigos:
            query = query.where(CheckValidacion.codigo.in_(check_codigos))
        checks = list((await self.db.execute(query)).scalars().all())

        reporte = self.motor.ejecutar(expediente, checks)

        validacion = ValidacionExpediente(
            id=uuid4(),
            tenant_id=tenant_id,
            expediente_id=expediente_id,
            tipo=tipo,
            nombre=nombre,
            descripcion=descripcion,
            estado=reporte.estado,
            resultados=reporte.to_dict()["resultados"],
            score=reporte.score,
            ejecutado_por_id=ejecutado_por_id,
            fecha_ejecucion=datetime.now(timezone.utc),
        )
        self.db.add(validacion)
        await self.db.commit()
        await self.db.refresh(validacion)
        return validacion

    async def historial(self, expediente_id: UUID, tenant_id: UUID, limit: int = 50) -> List[ValidacionExpediente]:
        result = await self.db.execute(
            select(ValidacionExpediente)
            .where(
                ValidacionExpediente.expediente_id == expediente_id,
                ValidacionExpediente.tenant_id == tenant_id,
            )
            .order_by(ValidacionExpediente.created_at.desc())
            .limit(limit)
        )
        return list(result.scalars().all())

    async def obtener(self, validacion_id: UUID, expediente_id: UUID, tenant_id: UUID) -> ValidacionExpediente:
        validacion = await self.db.get(ValidacionExpediente, validacion_id)
        if (
            not validacion
            or str(validacion.expediente_id) != str(expediente_id)
            or str(validacion.tenant_id) != str(tenant_id)
        ):
            raise MegalodonException(
                ErrorCode.DOCUMENTO_NO_ENCONTRADO,
                f"Validación {validacion_id} no encontrada en el expediente {expediente_id}",
            )
        return validacion

    # ─── Catálogo de checks reutilizables ──────────────────────────────

    async def listar_checks(
        self, tenant_id: UUID, categoria: Optional[str] = None, solo_activos: bool = False
    ) -> List[CheckValidacion]:
        query = select(CheckValidacion).where(CheckValidacion.tenant_id == tenant_id)
        if categoria:
            query = query.where(CheckValidacion.categoria == categoria)
        if solo_activos:
            query = query.where(CheckValidacion.activo.is_(True))
        query = query.order_by(CheckValidacion.categoria, CheckValidacion.orden)
        return list((await self.db.execute(query)).scalars().all())

    async def crear_check(self, tenant_id: UUID, data: Dict[str, Any]) -> CheckValidacion:
        existente = await self.db.execute(
            select(CheckValidacion).where(
                CheckValidacion.tenant_id == tenant_id, CheckValidacion.codigo == data["codigo"]
            )
        )
        if existente.scalar_one_or_none() is not None:
            raise MegalodonException(
                ErrorCode.VALIDACION_FALLIDA, f"Ya existe un check con código '{data['codigo']}'"
            )
        check = CheckValidacion(id=uuid4(), tenant_id=tenant_id, **data)
        self.db.add(check)
        await self.db.commit()
        await self.db.refresh(check)
        return check

    async def actualizar_check(self, check_id: UUID, tenant_id: UUID, data: Dict[str, Any]) -> CheckValidacion:
        check = await self.db.get(CheckValidacion, check_id)
        if not check or str(check.tenant_id) != str(tenant_id):
            raise MegalodonException(ErrorCode.DOCUMENTO_NO_ENCONTRADO, f"Check {check_id} no encontrado")
        for campo, valor in data.items():
            if valor is not None:
                setattr(check, campo, valor)
        await self.db.commit()
        await self.db.refresh(check)
        return check

    async def alternar_check(self, check_id: UUID, tenant_id: UUID) -> CheckValidacion:
        """Activa/desactiva un check (toggle de 'activo')."""
        check = await self.db.get(CheckValidacion, check_id)
        if not check or str(check.tenant_id) != str(tenant_id):
            raise MegalodonException(ErrorCode.DOCUMENTO_NO_ENCONTRADO, f"Check {check_id} no encontrado")
        check.activo = not check.activo
        await self.db.commit()
        await self.db.refresh(check)
        return check

    async def sembrar_checks_default(self, tenant_id: UUID) -> List[CheckValidacion]:
        """Crea el catálogo base de checks para un tenant que todavía no
        tiene ninguno. Idempotente: si ya existe un check con un código
        dado, se omite (no se duplica ni se sobreescribe)."""
        existentes = await self.db.execute(
            select(CheckValidacion.codigo).where(CheckValidacion.tenant_id == tenant_id)
        )
        codigos_existentes = {c for (c,) in existentes.all()}

        creados: List[CheckValidacion] = []
        for definicion in CHECKS_DEFAULT:
            if definicion["codigo"] in codigos_existentes:
                continue
            check = CheckValidacion(id=uuid4(), tenant_id=tenant_id, **definicion)
            self.db.add(check)
            creados.append(check)

        if creados:
            await self.db.commit()
            for check in creados:
                await self.db.refresh(check)
        return creados
