# Copyright © 2026 Cristian Rodriguez
"""Motor de workflow con condiciones dinámicas evaluables."""
from typing import Optional, Dict, Any, List
from uuid import UUID
from datetime import datetime, timedelta
from enum import Enum

from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, and_, func

from app.models.workflow import Workflow, WorkflowPaso, WorkflowTransicion, WorkflowCondicion
from app.models.user import User
from app.core.errors import MegalodonException, ErrorCode


class WorkflowError(MegalodonException):
    """Error de negocio del motor de workflow (transición inválida,
    condición mal configurada, paso inexistente, etc.)."""
    def __init__(self, message: str, status_code: int = 400):
        super().__init__(ErrorCode.VALIDACION_FALLIDA, message, status_code)


class OperadorCondicion(str, Enum):
    IGUAL = "=="
    DIFERENTE = "!="
    MAYOR = ">"
    MAYOR_IGUAL = ">="
    MENOR = "<"
    MENOR_IGUAL = "<="
    CONTIENE = "contains"
    EMPIEZA_CON = "startswith"
    TERMINA_CON = "endswith"
    EN_LISTA = "in"
    VACIO = "is_empty"
    NO_VACIO = "is_not_empty"

class MotorWorkflow:
    """Motor de evaluación de workflow con condiciones dinámicas."""

    async def evaluar_condicion(
        self,
        condicion: WorkflowCondicion,
        contexto: Dict[str, Any],
    ) -> bool:
        """Evalúa una condición dinámica contra un contexto de datos."""
        campo = condicion.campo
        operador = condicion.operador
        valor_referencia = condicion.valor_referencia

        # Obtener valor del contexto
        valor_actual = self._obtener_valor_anidado(contexto, campo)

        if operador == OperadorCondicion.IGUAL:
            return str(valor_actual) == str(valor_referencia)
        elif operador == OperadorCondicion.DIFERENTE:
            return str(valor_actual) != str(valor_referencia)
        elif operador == OperadorCondicion.MAYOR:
            return float(valor_actual or 0) > float(valor_referencia)
        elif operador == OperadorCondicion.MAYOR_IGUAL:
            return float(valor_actual or 0) >= float(valor_referencia)
        elif operador == OperadorCondicion.MENOR:
            return float(valor_actual or 0) < float(valor_referencia)
        elif operador == OperadorCondicion.MENOR_IGUAL:
            return float(valor_actual or 0) <= float(valor_referencia)
        elif operador == OperadorCondicion.CONTIENE:
            return str(valor_referencia) in str(valor_actual or "")
        elif operador == OperadorCondicion.EMPIEZA_CON:
            return str(valor_actual or "").startswith(str(valor_referencia))
        elif operador == OperadorCondicion.TERMINA_CON:
            return str(valor_actual or "").endswith(str(valor_referencia))
        elif operador == OperadorCondicion.EN_LISTA:
            lista = valor_referencia if isinstance(valor_referencia, list) else [valor_referencia]
            return str(valor_actual) in [str(v) for v in lista]
        elif operador == OperadorCondicion.VACIO:
            return not valor_actual or str(valor_actual).strip() == ""
        elif operador == OperadorCondicion.NO_VACIO:
            return bool(valor_actual) and str(valor_actual).strip() != ""
        return False

    def _obtener_valor_anidado(self, contexto: Dict[str, Any], campo: str) -> Any:
        """Obtiene un valor anidado del contexto usando notación punto."""
        partes = campo.split(".")
        valor = contexto
        for parte in partes:
            if isinstance(valor, dict):
                valor = valor.get(parte)
            else:
                return None
            if valor is None:
                return None
        return valor

    async def validar_transicion(
        self,
        db: AsyncSession,
        workflow_id: UUID,
        paso_origen_id: UUID,
        paso_destino_id: UUID,
        contexto: Dict[str, Any],
        current_user: User,
    ) -> Dict[str, Any]:
        """Valida una transición evaluando todas las condiciones asociadas."""
        # Verificar existencia del flujo y pasos
        workflow = await db.get(Workflow, workflow_id)
        if not workflow:
            raise MegalodonException(ErrorCode.DOCUMENTO_NO_ENCONTRADO, "Workflow no encontrado.", 404)

        paso_origen = await db.get(WorkflowPaso, paso_origen_id)
        paso_destino = await db.get(WorkflowPaso, paso_destino_id)
        if not paso_origen or not paso_destino:
            raise MegalodonException(ErrorCode.DOCUMENTO_NO_ENCONTRADO, "Paso no encontrado.", 404)

        # Buscar transición
        stmt = select(WorkflowTransicion).where(
            and_(
                WorkflowTransicion.workflow_id == workflow_id,
                WorkflowTransicion.paso_origen_id == paso_origen_id,
                WorkflowTransicion.paso_destino_id == paso_destino_id,
            )
        )
        transicion = (await db.execute(stmt)).scalar_one_or_none()
        if not transicion:
            raise MegalodonException(ErrorCode.VALIDACION_FALLIDA, "Transición no definida.", 400)

        # Evaluar condiciones
        condiciones = await db.execute(
            select(WorkflowCondicion).where(
                WorkflowCondicion.transicion_id == transicion.id
            ).order_by(WorkflowCondicion.orden)
        )
        condiciones = condiciones.scalars().all()

        resultados = []
        todas_cumplidas = True

        for cond in condiciones:
            cumple = await self.evaluar_condicion(cond, contexto)
            resultados.append({
                "condicion_id": str(cond.id),
                "campo": cond.campo,
                "operador": cond.operador,
                "valor_referencia": cond.valor_referencia,
                "cumple": cumple,
            })
            if not cumple and cond.obligatoria:
                todas_cumplidas = False

        return {
            "transicion_valida": todas_cumplidas,
            "transicion_id": str(transicion.id),
            "condiciones_evaluadas": len(resultados),
            "condiciones_cumplidas": sum(1 for r in resultados if r["cumple"]),
            "detalle": resultados,
        }

    async def verificar_sla_vencidos(
        self,
        db: AsyncSession,
        workflow_id: Optional[UUID] = None,
        tenant_id: Optional[UUID | str] = None,
    ) -> List[Dict[str, Any]]:
        """Detecta tareas vencidas y las escala."""
        from datetime import datetime
        ahora = datetime.utcnow()

        query = select(WorkflowPaso).where(
            and_(
                WorkflowPaso.estado == "EN_PROGRESO",
                WorkflowPaso.fecha_limite != None,
                WorkflowPaso.fecha_limite < ahora,
            )
        )
        if workflow_id:
            query = query.where(WorkflowPaso.workflow_id == workflow_id)
        if tenant_id is not None:
            # Workflow.tenant_id == tenant_id — aislamiento explícito por tenant
            query = query.join(Workflow, WorkflowPaso.workflow_id == Workflow.id).where(Workflow.tenant_id == tenant_id)

        pasos_vencidos = (await db.execute(query)).scalars().all()

        alertas = []
        for paso in pasos_vencidos:
            paso.estado = "VENCIDO"
            paso.updated_at = ahora
            alertas.append({
                "paso_id": str(paso.id),
                "workflow_id": str(paso.workflow_id),
                "nombre": paso.nombre,
                "fecha_limite": paso.fecha_limite.isoformat(),
                "dias_vencido": (ahora - paso.fecha_limite).days,
                "accion": "ESCALADO",
            })

        await db.commit()
        return alertas

    async def crear_condicion(
        self,
        db: AsyncSession,
        transicion_id: UUID,
        campo: str,
        operador: str,
        valor_referencia: Any,
        obligatoria: bool = True,
        orden: int = 0,
    ) -> WorkflowCondicion:
        """Crea una condición dinámica para una transición."""
        cond = WorkflowCondicion(
            transicion_id=transicion_id,
            campo=campo,
            operador=operador,
            valor_referencia=valor_referencia,
            obligatoria=obligatoria,
            orden=orden,
        )
        db.add(cond)
        await db.commit()
        await db.refresh(cond)
        return cond


# app/modules/workflow/__init__.py importa "WorkflowEngine" (y así se usaría
# desde fuera del módulo); la clase se define en español como el resto de
# los motores del sistema (MotorValidador, MotorBusquedaLegal, etc.), así
# que se expone también bajo ese alias en vez de renombrarla.
WorkflowEngine = MotorWorkflow
