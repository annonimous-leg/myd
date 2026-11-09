# Copyright © 2026 Cristian Rodriguez
# All rights reserved.
# Unauthorized copying, modification, distribution, or use is prohibited
# without prior written permission.

"""
Motor de compliance — Evaluación automática de reglas según estado del procedimiento.
Las reglas se evalúan solas, no manualmente.
"""
from typing import List, Dict, Optional
import ast
from dataclasses import dataclass

from app.models.compliance import ReglaCumplimiento, EstadoRegla, EvaluacionCompliance
from app.models.licitacion import Licitacion, EstadoLicitacion
from app.models.contrato import Contrato, EstadoContrato
from app.models.expediente import ExpedienteObra
from app.core.errors import MegalodonException, ErrorCode
# CORREGIDO 2026-09-01: evaluar_condicion() ya usaba MegalodonException/
# ErrorCode sin importarlos -- cualquier regla sin condición o con sintaxis
# no evaluable producía NameError en vez del error de dominio que el código
# claramente pretendía lanzar. No se detectaba antes porque nada llamaba a
# evaluar_licitacion()/evaluar_contrato() con una regla en ese estado en las
# rutas ejercitadas por la app hasta ahora.


@dataclass
class ResultadoEvaluacionRegla:
    regla_id: str
    nombre: str
    estado: EstadoRegla
    observaciones: str
    cumple: bool


class MotorCompliance:
    """
    Motor de evaluación automática de compliance.

    Principio: Cada regla tiene una condición (campo + operador + valor)
    que se evalúa automáticamente contra el estado actual del procedimiento.
    """

    def __init__(self):
        self.operadores = {
            "==": lambda a, b: a == b,
            "!=": lambda a, b: a != b,
            ">": lambda a, b: a > b if a is not None and b is not None else False,
            "<": lambda a, b: a < b if a is not None and b is not None else False,
            ">=": lambda a, b: a >= b if a is not None and b is not None else False,
            "<=": lambda a, b: a <= b if a is not None and b is not None else False,
            "in": lambda a, b: a in b if b is not None else False,
            "not_in": lambda a, b: a not in b if b is not None else False,
            "is_not_none": lambda a, b: a is not None,
            "is_none": lambda a, b: a is None,
        }

    def evaluar_condicion(
        self,
        condicion: str,
        contexto: Dict,
    ) -> bool:
        """
        Evalúa una condición contra un contexto.

        Formatos soportados:
        - "campo == valor"
        - "campo > valor"  
        - "campo is_not_none"
        - "campo in [val1, val2]"
        """
        if not condicion:
            raise MegalodonException(
                ErrorCode.NORMATIVO_GENERICO,
                "Regla de compliance sin condición evaluable.",
                details={"estado": "NOT_EVALUABLE"},
            )

        partes = condicion.split()
        if len(partes) < 3:
            raise MegalodonException(
                ErrorCode.NORMATIVO_GENERICO,
                "Regla de compliance con sintaxis no evaluable.",
                details={"estado": "NOT_EVALUABLE", "condicion": condicion},
            )

        campo = partes[0]
        operador = partes[1]
        valor_str = " ".join(partes[2:])

        # Obtener valor del contexto
        valor_campo = contexto.get(campo)

        # Parsear valor de comparación
        try:
            if valor_str.startswith("[") and valor_str.endswith("]"):
                # SEGURIDAD: antes usaba eval() sobre texto de condición de
                # negocio (potencialmente editable por usuarios/plantillas).
                # ast.literal_eval solo acepta literales de Python (listas,
                # números, strings, etc.), nunca ejecuta código.
                try:
                    valor_comparacion = ast.literal_eval(valor_str)
                except (ValueError, SyntaxError):
                    valor_comparacion = valor_str
            elif valor_str.lower() == "true":
                valor_comparacion = True
            elif valor_str.lower() == "false":
                valor_comparacion = False
            elif valor_str.lower() == "none":
                valor_comparacion = None
            else:
                try:
                    valor_comparacion = float(valor_str)
                except ValueError:
                    valor_comparacion = valor_str
        except Exception:
            valor_comparacion = valor_str

        # Ejecutar operador
        op_func = self.operadores.get(operador)
        if not op_func:
            return False

        return op_func(valor_campo, valor_comparacion)

    def _evaluar_regla_segura(
        self,
        regla: ReglaCumplimiento,
        contexto: Dict,
    ) -> ResultadoEvaluacionRegla:
        """
        Evalúa una regla contra un contexto, sin dejar que una condición
        ausente o con sintaxis no evaluable tumbe la evaluación completa del
        resto de las reglas del expediente/licitación/contrato.

        Antes, evaluar_licitacion()/evaluar_contrato() llamaban a
        evaluar_condicion() directamente: si UNA regla no tenía condición o
        tenía sintaxis inválida, MegalodonException se propagaba sin capturar
        y tumbaba la evaluación de TODAS las demás reglas del lote. Ahora esa
        regla queda en PENDIENTE (requiere revisión manual) y las demás se
        siguen evaluando con normalidad.
        """
        try:
            cumple = self.evaluar_condicion(regla.condicion_evaluacion, contexto)
        except MegalodonException as e:
            return ResultadoEvaluacionRegla(
                regla_id=str(regla.id), nombre=regla.nombre, estado=EstadoRegla.PENDIENTE,
                observaciones=f"No evaluable automáticamente: {e.message if hasattr(e, 'message') else e}",
                cumple=False,
            )

        estado = EstadoRegla.CUMPLIDA if cumple else EstadoRegla.NO_CUMPLIDA
        if not regla.obligatorio and not cumple:
            estado = EstadoRegla.NO_APLICA

        return ResultadoEvaluacionRegla(
            regla_id=str(regla.id), nombre=regla.nombre, estado=estado,
            observaciones=f"Condición: {regla.condicion_evaluacion} → {'CUMPLE' if cumple else 'NO CUMPLE'}",
            cumple=cumple,
        )

    def evaluar_licitacion(
        self,
        licitacion: Licitacion,
        reglas: List[ReglaCumplimiento],
    ) -> List[ResultadoEvaluacionRegla]:
        """Evalúa todas las reglas aplicables a una licitación."""
        contexto = {
            "estado": licitacion.estado,
            "monto_estimado": float(licitacion.monto_estimado) if licitacion.monto_estimado else None,
            "plazo_dias": licitacion.plazo_dias,
            "fecha_convocatoria": licitacion.fecha_convocatoria,
            "fecha_junta_aclaraciones": licitacion.fecha_junta_aclaraciones,
            "fecha_apertura": licitacion.fecha_apertura,
            "fecha_fallo": licitacion.fecha_fallo,
            "bases_congeladas": licitacion.bases_congeladas,
            "dictamen": licitacion.dictamen,
            "tipo_procedimiento": licitacion.tipo_procedimiento,
        }

        resultados = []
        for regla in reglas:
            if not regla.activa:
                continue
            # Verificar si la regla aplica a este tipo de procedimiento
            if regla.tipo_procedimiento != "TODOS" and regla.tipo_procedimiento != licitacion.tipo_procedimiento:
                continue
            resultados.append(self._evaluar_regla_segura(regla, contexto))
        return resultados

    def evaluar_contrato(
        self,
        contrato: Contrato,
        reglas: List[ReglaCumplimiento],
    ) -> List[ResultadoEvaluacionRegla]:
        """Evalúa todas las reglas aplicables a un contrato."""
        contexto = {
            "estado": contrato.estado,
            "monto_total": float(contrato.monto_total) if contrato.monto_total else None,
            "plazo_dias": contrato.plazo_dias,
            "fecha_firma": contrato.fecha_firma,
            "fecha_inicio": contrato.fecha_inicio,
            "fecha_termino": contrato.fecha_termino,
            "avance_fisico": float(contrato.avance_fisico) if contrato.avance_fisico else 0,
            "avance_financiero": float(contrato.avance_financiero) if contrato.avance_financiero else 0,
            "fecha_finiquito": contrato.fecha_finiquito,
        }

        resultados = []
        for regla in reglas:
            if not regla.activa:
                continue
            resultados.append(self._evaluar_regla_segura(regla, contexto))
        return resultados

    def evaluar_expediente(
        self,
        expediente: ExpedienteObra,
        reglas: List[ReglaCumplimiento],
    ) -> List[ResultadoEvaluacionRegla]:
        """
        Evalúa todas las reglas aplicables a un expediente completo.

        CORREGIDO (F-04 de auditoría 2026-09-01): compliance_service.
        evaluar_expediente() nunca llamaba a este motor -- ni siquiera
        cargaba el expediente; clasificaba cada regla en cumplida/incumplida
        solo según si TENÍA una condición, sin mirar el estado real. Aquí sí
        se arma un contexto real desde el expediente cargado (con sus
        licitaciones/contratos/documentos vía selectinload en el servicio):
        estado del expediente, presencia y estado de licitación/contrato,
        cantidad de documentos, avances -- exactamente las señales que la
        auditoría marcó como ausentes del cálculo anterior.

        Cuando el expediente tiene más de una licitación o contrato (p. ej.
        procedimiento declarado desierto y relanzado), se evalúa contra el
        más reciente -- el resto queda disponible en el propio expediente
        para quien necesite el historial completo, pero el compliance del
        expediente se juzga por su procedimiento vigente.
        """
        licitaciones = list(expediente.licitaciones or [])
        contratos = list(expediente.contratos or [])
        documentos = list(expediente.documentos or [])

        licitacion_vigente = licitaciones[-1] if licitaciones else None
        contrato_vigente = contratos[-1] if contratos else None

        contexto = {
            "estado": expediente.estado,
            "tipo_contrato": expediente.tipo_contrato,
            "clasificacion": expediente.clasificacion,
            "monto_contrato": float(expediente.monto_contrato) if expediente.monto_contrato else None,
            "plazo_dias": expediente.plazo_dias,
            "tiene_responsable": expediente.responsable_id is not None,
            "cantidad_documentos": len(documentos),
            "tiene_documentos": len(documentos) > 0,
            "cantidad_licitaciones": len(licitaciones),
            "tiene_licitacion": licitacion_vigente is not None,
            "estado_licitacion": licitacion_vigente.estado if licitacion_vigente else None,
            "cantidad_contratos": len(contratos),
            "tiene_contrato": contrato_vigente is not None,
            "estado_contrato": contrato_vigente.estado if contrato_vigente else None,
            "fecha_firma": contrato_vigente.fecha_firma if contrato_vigente else None,
            "avance_fisico": float(contrato_vigente.avance_fisico) if contrato_vigente and contrato_vigente.avance_fisico else None,
            "avance_financiero": float(contrato_vigente.avance_financiero) if contrato_vigente and contrato_vigente.avance_financiero else None,
        }

        # CORREGIDO (contra-auditoría V8, bug real detectado): la primera
        # versión de esta función filtraba con
        # "regla.tipo_procedimiento not in ('TODOS', expediente.tipo_contrato)".
        # ReglaCumplimiento.tipo_procedimiento vive en el vocabulario de
        # TipoProcedimiento (LICITACION_PUBLICA/INVITACION_TRES/
        # ADJUDICACION_DIRECTA/..., ver app.models.licitacion) -- el MISMO
        # que ya usa evaluar_licitacion() de este mismo motor, comparando
        # contra licitacion.tipo_procedimiento. expediente.tipo_contrato en
        # cambio es TipoContrato (PRECIOS_UNITARIOS/PRECIO_ALZADO/MIXTO/...,
        # ver app.models.expediente) -- la naturaleza de precios del
        # contrato, un concepto distinto. Con el filtro original, una regla
        # con tipo_procedimiento="LICITACION_PUBLICA" nunca podía aplicar a
        # NINGÚN expediente, porque "LICITACION_PUBLICA" no es un valor
        # posible de tipo_contrato. Ahora se compara contra el
        # tipo_procedimiento de la LICITACIÓN vigente del expediente (el
        # mismo campo que evaluar_licitacion ya usa) -- y si el expediente
        # todavía no tiene licitación con procedimiento asignado, una regla
        # específica de un procedimiento queda PENDIENTE (no se descarta en
        # silencio ni se fuerza a "aplica").
        tipo_procedimiento_vigente = licitacion_vigente.tipo_procedimiento if licitacion_vigente else None

        resultados = []
        for regla in reglas:
            if not regla.activa:
                continue
            if regla.tipo_procedimiento != "TODOS":
                if tipo_procedimiento_vigente is None:
                    resultados.append(ResultadoEvaluacionRegla(
                        regla_id=str(regla.id), nombre=regla.nombre, estado=EstadoRegla.PENDIENTE,
                        observaciones=(
                            f"Regla específica de tipo_procedimiento={regla.tipo_procedimiento}, pero "
                            "el expediente todavía no tiene una licitación con procedimiento asignado "
                            "-- no se puede determinar si aplica."
                        ),
                        cumple=False,
                    ))
                    continue
                if regla.tipo_procedimiento != tipo_procedimiento_vigente:
                    continue
            resultados.append(self._evaluar_regla_segura(regla, contexto))
        return resultados

    def generar_alertas(
        self,
        resultados: List[ResultadoEvaluacionRegla],
    ) -> List[Dict]:
        """Genera alertas para reglas no cumplidas obligatorias."""
        alertas = []
        for r in resultados:
            if r.estado == EstadoRegla.NO_CUMPLIDA:
                alertas.append({
                    "tipo": "CRITICO" if r.cumple is False else "ADVERTENCIA",
                    "regla": r.nombre,
                    "mensaje": r.observaciones,
                    "accion_requerida": "Atender antes de continuar con el procedimiento",
                })
        return alertas
