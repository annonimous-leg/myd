# Copyright © 2026 Cristian Rodriguez
# Technical Evaluation Engine — evaluación técnica determinista

from typing import List, Dict, Any, Optional

from .domain import (
    CriterioTecnico, EvaluacionTecnicaResultado, Hallazgo, NivelRiesgo
)


class TechnicalEvaluationEngine:
    """Motor de evaluación técnica.

    Aplica exclusivamente los criterios técnicos establecidos en la convocatoria.
    Produce: cumple/no cumple con puntaje por criterio.
    """

    def __init__(self, criterios: List[CriterioTecnico]):
        self.criterios = criterios

    def evaluar(self, proposicion_tecnica: Dict[str, Any]) -> List[EvaluacionTecnicaResultado]:
        """Ejecuta evaluación técnica completa."""
        resultados = []

        for criterio in self.criterios:
            resultado = self._evaluar_criterio(criterio, proposicion_tecnica)
            resultados.append(resultado)

        return resultados

    def _evaluar_criterio(self, criterio: CriterioTecnico, prop: Dict[str, Any]) -> EvaluacionTecnicaResultado:
        """Evalúa un criterio técnico individual."""
        # Extraer valor de la proposición según el código del criterio
        valor = self._extraer_valor(prop, criterio.codigo)

        if valor is None:
            return EvaluacionTecnicaResultado(
                criterio_codigo=criterio.codigo,
                cumple=False,
                puntaje_obtenido=0.0,
                puntaje_maximo=criterio.puntaje_maximo,
                observaciones=["Valor no proporcionado para este criterio"],
                evidencias=[]
            )

        # Aplicar rúbrica
        puntaje = self._aplicar_rubrica(criterio, valor)
        cumple = puntaje > 0

        return EvaluacionTecnicaResultado(
            criterio_codigo=criterio.codigo,
            cumple=cumple,
            puntaje_obtenido=puntaje,
            puntaje_maximo=criterio.puntaje_maximo,
            observaciones=[f"Valor encontrado: {valor}"] if cumple else [f"Valor encontrado: {valor} — No cumple rúbrica"],
            evidencias=[f"PROP_TECNICA.pdf — {criterio.codigo}"]
        )

    def _extraer_valor(self, prop: Dict[str, Any], codigo: str) -> Optional[Any]:
        """Extrae valor de la proposición por código de criterio."""
        # Buscar en estructura anidada
        if "criterios_tecnicos" in prop:
            return prop["criterios_tecnicos"].get(codigo)
        if "especificaciones" in prop:
            return prop["especificaciones"].get(codigo)
        return prop.get(codigo)

    def _aplicar_rubrica(self, criterio: CriterioTecnico, valor: Any) -> float:
        """Aplica rúbrica al valor encontrado."""
        rubrica = criterio.rubrica

        # Si es numérico con umbral
        if "minimo" in rubrica and isinstance(valor, (int, float)):
            if valor >= rubrica["minimo"]:
                return criterio.puntaje_maximo
            elif "escala" in rubrica:
                # Puntaje proporcional
                return min(criterio.puntaje_maximo, 
                          (valor / rubrica["minimo"]) * criterio.puntaje_maximo)
            else:
                return 0.0

        # Si es booleano
        if "requerido" in rubrica:
            if valor == rubrica["requerido"]:
                return criterio.puntaje_maximo
            return 0.0

        # Default: asignar puntaje máximo si hay valor
        return criterio.puntaje_maximo if valor is not None else 0.0

    def generar_hallazgos(self, resultados: List[EvaluacionTecnicaResultado]) -> List[Hallazgo]:
        """Genera hallazgos a partir de resultados técnicos."""
        hallazgos = []

        for res in resultados:
            if not res.cumple:
                hallazgos.append(Hallazgo(
                    requisito_codigo=res.criterio_codigo,
                    nivel_riesgo=NivelRiesgo.CRITICO,
                    descripcion=f"Criterio técnico {res.criterio_codigo}: {res.observaciones[0]}",
                    resultado="INCUMPLIMIENTO_TECNICO",
                    fundamento=f"Convocatoria — Criterio técnico {res.criterio_codigo}"
                ))
            elif res.puntaje_obtenido < res.puntaje_maximo:
                hallazgos.append(Hallazgo(
                    requisito_codigo=res.criterio_codigo,
                    nivel_riesgo=NivelRiesgo.RELEVANTE,
                    descripcion=f"Criterio técnico {res.criterio_codigo}: puntaje parcial ({res.puntaje_obtenido}/{res.puntaje_maximo})",
                    resultado="CUMPLIMIENTO_PARCIAL",
                    fundamento=f"Convocatoria — Criterio técnico {res.criterio_codigo}"
                ))

        return hallazgos
