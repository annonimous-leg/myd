# Copyright © 2026 Cristian Rodriguez
# All rights reserved.
# Unauthorized copying, modification, distribution, or use is prohibited
# without prior written permission.

"""
Motor de evaluación de licitaciones — Legal, Técnica y Económica.
Separadas, con dictamen auditable.
"""
from dataclasses import dataclass
from typing import Optional, List, Dict
from enum import Enum
import math

from app.models.licitacion import TipoEvaluacion, ResultadoEvaluacion
from app.core.errors import MegalodonException, ErrorCode


class CriterioLegal(str, Enum):
    EXISTENCIA_LEGAL = "EXISTENCIA_LEGAL"
    REPRESENTACION = "REPRESENTACION"
    FIRMA_ELECTRONICA = "FIRMA_ELECTRONICA"
    CUMPLIMIENTO_DOCUMENTAL = "CUMPLIMIENTO_DOCUMENTAL"
    NO_IMPEDIMENTOS = "NO_IMPEDIMENTOS"
    INTEGRIDAD_ARCHIVOS = "INTEGRIDAD_ARCHIVOS"
    REQUISITOS_OBLIGATORIOS = "REQUISITOS_OBLIGATORIOS"


class CriterioTecnico(str, Enum):
    ESPECIFICACION = "ESPECIFICACION"
    ALCANCE = "ALCANCE"
    METODO_CONSTRUCTIVO = "METODO_CONSTRUCTIVO"
    COMPATIBILIDAD_BIM = "COMPATIBILIDAD_BIM"
    ENTREGABLES = "ENTREGABLES"
    CALIDAD = "CALIDAD"
    CRONOGRAMA = "CRONOGRAMA"
    RECURSOS = "RECURSOS"


class CriterioEconomico(str, Enum):
    PRECIO = "PRECIO"
    DESGLOSE = "DESGLOSE"
    ANTICIPO = "ANTICIPO"
    FINANCIAMIENTO = "FINANCIAMIENTO"
    RIESGO = "RIESGO"
    UTILIDAD = "UTILIDAD"
    INDIRECTOS = "INDIRECTOS"
    CONSISTENCIA_MERCADO = "CONSISTENCIA_MERCADO"


@dataclass
class ResultadoCriterio:
    criterio: str
    cumple: bool
    observacion: str
    puntaje: Optional[float] = None


@dataclass
class ResultadoEvaluacionCapa:
    tipo: TipoEvaluacion
    resultado: ResultadoEvaluacion
    puntaje_total: Optional[float]
    criterios: List[ResultadoCriterio]
    dictamen: str
    trazable: bool


class MotorEvaluacion:
    """Evaluador determinista parametrizado exclusivamente por la matriz congelada.

    No contiene pesos, mínimos ni penalizaciones de una dependencia. Esos valores
    deben existir en ``Licitacion.matriz_evaluacion`` y quedar congelados antes
    de evaluar.
    """

    def __init__(self, matriz: Dict):
        if not isinstance(matriz, dict) or not matriz:
            raise MegalodonException(ErrorCode.VALIDACION_FALLIDA, "Matriz de evaluación ausente.", 409)
        self.matriz = matriz
        self.pesos_tecnicos = self._weights("tecnico")
        self.pesos_economicos = self._weights("economico")
        self.min_tecnico = self._number("minimo_tecnico")
        self.min_economico = self._number("minimo_economico")

    def _weights(self, key: str) -> Dict[str, float]:
        raw = self.matriz.get(key)
        if not isinstance(raw, dict) or not raw:
            return {}
        out: Dict[str, float] = {}
        for code, spec in raw.items():
            if not isinstance(spec, dict):
                raise MegalodonException(ErrorCode.VALIDACION_FALLIDA, f"Criterio {key}.{code} inválido.", 409)
            weight = spec.get("peso", spec.get("ponderacion"))
            if weight is None:
                raise MegalodonException(ErrorCode.VALIDACION_FALLIDA, f"Falta ponderación para {key}.{code}.", 409)
            value = self._finite(weight, f"ponderación {key}.{code}")
            if value < 0:
                raise MegalodonException(ErrorCode.VALIDACION_FALLIDA, f"Ponderación negativa en {key}.{code}.", 409)
            out[str(code)] = value
        return out

    def _number(self, key: str) -> Optional[float]:
        value = self.matriz.get(key)
        return None if value is None else self._finite(value, key)

    @staticmethod
    def _finite(value, name: str) -> float:
        try:
            if isinstance(value, bool):
                raise ValueError
            number = float(value)
            if not math.isfinite(number):
                raise ValueError
            return number
        except (TypeError, ValueError, OverflowError) as exc:
            raise MegalodonException(ErrorCode.VALIDACION_FALLIDA, f"Valor numérico inválido: {name}.", 409) from exc

    def validar_matriz_completa(self) -> None:
        """Validate the frozen decision policy before any state is changed."""
        legal = self._require_spec("legal")
        for code, spec in legal.items():
            if not isinstance(spec, dict) or not isinstance(spec.get("requerido", True), bool):
                raise MegalodonException(ErrorCode.VALIDACION_FALLIDA, f"Criterio legal inválido: {code}.", 409)
        for name, weights, minimum in (
            ("técnica", self.pesos_tecnicos, self.min_tecnico),
            ("económica", self.pesos_economicos, self.min_economico),
        ):
            if not weights or sum(weights.values()) <= 0 or minimum is None or not 0 <= minimum <= 100:
                raise MegalodonException(ErrorCode.VALIDACION_FALLIDA, f"La matriz {name} requiere pesos y mínimo entre 0 y 100.", 409)
        if (self.matriz.get("variacion_mercado_max") is None) != (self.matriz.get("variacion_mercado_penalty") is None):
            raise MegalodonException(ErrorCode.VALIDACION_FALLIDA, "La regla de variación de mercado está incompleta.", 409)
        for key in ("variacion_mercado_max", "variacion_mercado_penalty"):
            value = self._number(key)
            if value is not None and not 0 <= value <= 1:
                raise MegalodonException(ErrorCode.VALIDACION_FALLIDA, f"{key} debe estar entre 0 y 1.", 409)

    def _score(self, value, code: str) -> float:
        score = self._finite(value, code)
        if not 0 <= score <= 100:
            raise MegalodonException(ErrorCode.VALIDACION_FALLIDA, f"El puntaje de {code} debe estar entre 0 y 100.", 409)
        return score

    def _require_spec(self, key: str) -> Dict:
        spec = self.matriz.get(key)
        if not isinstance(spec, dict) or not spec:
            raise MegalodonException(ErrorCode.VALIDACION_FALLIDA, f"No existe especificación de evaluación para {key}.", 409)
        return spec

    def evaluar_legal(self, proposicion_id: str, datos: Dict) -> ResultadoEvaluacionCapa:
        _ = proposicion_id
        criterios_cfg = self._require_spec("legal")
        criterios = []
        for code, spec in criterios_cfg.items():
            if not isinstance(spec, dict):
                raise MegalodonException(ErrorCode.VALIDACION_FALLIDA, f"Criterio legal inválido: {code}.", 409)
            field = str(spec.get("campo", code))
            required = bool(spec.get("requerido", True))
            present = datos.get(field)
            cumple = present is True if required else True
            criterios.append(ResultadoCriterio(str(code), cumple, "Cumple" if cumple else "NO CUMPLE - revisar expediente"))
        ok = all(c.cumple for c in criterios)
        return ResultadoEvaluacionCapa(TipoEvaluacion.LEGAL, ResultadoEvaluacion.APROBADA if ok else ResultadoEvaluacion.RECHAZADA, 100.0 if ok else 0.0, criterios, "APROBADA LEGALMENTE" if ok else "RECHAZADA POR INCUMPLIMIENTO", True)

    def evaluar_tecnica(self, proposicion_id: str, datos: Dict) -> ResultadoEvaluacionCapa:
        _ = proposicion_id
        if not self.pesos_tecnicos or self.min_tecnico is None:
            raise MegalodonException(ErrorCode.VALIDACION_FALLIDA, "La matriz técnica está incompleta.", 409)
        total_weight = sum(self.pesos_tecnicos.values())
        if total_weight <= 0:
            raise MegalodonException(ErrorCode.VALIDACION_FALLIDA, "La ponderación técnica debe ser mayor que cero.", 409)
        criterios=[]; total=0.0
        for code, weight in self.pesos_tecnicos.items():
            value = datos.get(code)
            if value is None:
                raise MegalodonException(ErrorCode.VALIDACION_FALLIDA, f"Falta evidencia/puntaje técnico para {code}.", 409)
            score=self._score(value, code); criterios.append(ResultadoCriterio(code, score >= 0, f"Puntaje: {score}/100", score)); total += score * weight / total_weight
        ok=total >= self.min_tecnico
        return ResultadoEvaluacionCapa(TipoEvaluacion.TECNICA, ResultadoEvaluacion.APROBADA if ok else ResultadoEvaluacion.RECHAZADA, round(total,2), criterios, f"Puntaje técnico: {total:.2f} (mínimo: {self.min_tecnico:g})", True)

    def evaluar_economica(self, proposicion_id: str, datos: Dict, precio_referencia: Optional[float]=None) -> ResultadoEvaluacionCapa:
        _ = proposicion_id
        if not self.pesos_economicos or self.min_economico is None:
            raise MegalodonException(ErrorCode.VALIDACION_FALLIDA, "La matriz económica está incompleta.", 409)
        total_weight=sum(self.pesos_economicos.values())
        if total_weight <= 0:
            raise MegalodonException(ErrorCode.VALIDACION_FALLIDA, "La ponderación económica debe ser mayor que cero.", 409)
        criterios=[]; total=0.0
        for code, weight in self.pesos_economicos.items():
            value=datos.get(code)
            if value is None:
                raise MegalodonException(ErrorCode.VALIDACION_FALLIDA, f"Falta evidencia/puntaje económico para {code}.", 409)
            score=self._score(value, code); criterios.append(ResultadoCriterio(code, score >= 0, f"Puntaje: {score}/100", score)); total += score*weight/total_weight
        penalty=self.matriz.get("variacion_mercado_penalty")
        limit=self.matriz.get("variacion_mercado_max")
        precio=datos.get("precio_total")
        if precio_referencia and precio_referencia > 0 and limit is not None and penalty is not None and precio is not None:
            variation=abs(float(precio)-float(precio_referencia))/float(precio_referencia)
            if variation > float(limit):
                total *= float(penalty)
                criterios.append(ResultadoCriterio("VARIACION_MERCADO", False, f"Variación {variation:.2%} excede el límite del expediente", None))
        ok=total >= self.min_economico
        return ResultadoEvaluacionCapa(TipoEvaluacion.ECONOMICA, ResultadoEvaluacion.APROBADA if ok else ResultadoEvaluacion.RECHAZADA, round(total,2), criterios, f"Puntaje económico: {total:.2f} (mínimo: {self.min_economico:g})", True)

    def dictamen_final(self, evaluaciones: List[ResultadoEvaluacionCapa]) -> Dict:
        legal=next((e for e in evaluaciones if e.tipo==TipoEvaluacion.LEGAL),None)
        tecnica=next((e for e in evaluaciones if e.tipo==TipoEvaluacion.TECNICA),None)
        economica=next((e for e in evaluaciones if e.tipo==TipoEvaluacion.ECONOMICA),None)
        approved=bool(legal and legal.resultado==ResultadoEvaluacion.APROBADA and tecnica and tecnica.resultado==ResultadoEvaluacion.APROBADA and economica and economica.resultado==ResultadoEvaluacion.APROBADA)
        return {"resultado":"APROBADA" if approved else "RECHAZADA", "motivo":"Cumple evaluaciones" if approved else "No cumple una o más capas", "evaluaciones":evaluaciones, "adjudicable":approved, "puntaje_tecnico":tecnica.puntaje_total if tecnica else None, "puntaje_economico":economica.puntaje_total if economica else None}
