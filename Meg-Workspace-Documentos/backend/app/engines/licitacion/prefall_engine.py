# Copyright © 2026 Cristian Rodriguez
# Pre-Fall Engine — simulación determinista del resultado licitatorio

from typing import List, Dict, Any, Optional
from uuid import UUID

from .domain import (
    ConvocatoriaEstructurada, PreFallResult, EstadoSolvencia, NivelRiesgo,
    Hallazgo, EvaluacionTecnicaResultado, EvaluacionEconomicaResultado
)
from .completeness_engine import DocumentComplianceEngine
from .technical_engine import TechnicalEvaluationEngine
from .economic_engine import EconomicEvaluationEngine


class PreFallEngine:
    """Motor de Pre-Fallo.

    Recibe: convocatoria, criterios, requisitos, proposiciones, evaluaciones.
    Produce: PreFallResult con estado, solvencia, puntaje, ranking preliminar,
    causales detectadas, evidencias, reglas aplicadas, riesgos, advertencias, trazabilidad.

    NO dice "Megalodon adjudica". Dice:
    "Aplicando exclusivamente los criterios publicados en la convocatoria y las
    evidencias cargadas, esta proposición resulta preliminarmente solvente/no solvente
    y obtiene X puntos."
    """

    def __init__(self, convocatoria: ConvocatoriaEstructurada, historical_patterns: Optional[Dict[str, Any]] = None):
        self.convocatoria = convocatoria
        self.historical_patterns = historical_patterns or {}
        historical_dependency = self.historical_patterns.get("jurisdiction_code")
        if self.historical_patterns and historical_dependency != convocatoria.jurisdiction_code:
            raise ValueError("Los patrones históricos de pre-fallo deben pertenecer a la misma dependencia del expediente.")
        self.completeness = DocumentComplianceEngine(convocatoria.requisitos)
        self.technical = TechnicalEvaluationEngine(convocatoria.criterios_tecnicos)
        self.economic = EconomicEvaluationEngine(
            convocatoria.criterios_economicos,
            monto_referencia=convocatoria.monto_estimado,
            reglas=convocatoria.reglas_economicas,
        )

    def simular(self, proposicion_id: UUID, licitante_nombre: str,
                documentos: Dict[str, Any], prop_tecnica: Dict[str, Any],
                prop_economica: Dict[str, Any]) -> PreFallResult:
        """Ejecuta simulación completa de pre-fallo para una proposición."""

        # 1. Completitud documental
        hallazgos_completeness = self.completeness.validar(documentos)

        # 2. Evaluación técnica
        resultados_tecnicos = self.technical.evaluar(prop_tecnica)
        hallazgos_tecnicos = self.technical.generar_hallazgos(resultados_tecnicos)

        # 3. Evaluación económica
        resultados_economicos = self.economic.evaluar(prop_economica)
        hallazgos_economicos = self.economic.generar_hallazgos(resultados_economicos)

        # 4. Consolidar hallazgos
        todos_hallazgos = hallazgos_completeness + hallazgos_tecnicos + hallazgos_economicos

        # 5. Clasificar por nivel de riesgo
        criticos = [h for h in todos_hallazgos if h.nivel_riesgo == NivelRiesgo.CRITICO]
        relevantes = [h for h in todos_hallazgos if h.nivel_riesgo == NivelRiesgo.RELEVANTE]
        no_sustantivos = [h for h in todos_hallazgos if h.nivel_riesgo == NivelRiesgo.NO_SUSTANTIVO]

        # 6. Calcular porcentajes por categoría
        legal_pct = self._calcular_pct_legal(todos_hallazgos)
        admin_pct = self._calcular_pct_admin(todos_hallazgos)
        tecnico_pct = self._calcular_pct_tecnico(resultados_tecnicos)
        economico_pct = self._calcular_pct_economico(resultados_economicos)

        # 7. Determinar solvencia preliminar
        # CRÍTICO → potencialmente afecta solvencia
        # Si hay críticos en requisitos obligatorios → NO SOLVENTE
        estado = self._determinar_solvencia(criticos, resultados_tecnicos, resultados_economicos)

        # 8. Calcular puntaje total (si aplica criterio de puntos)
        puntaje_total = self._calcular_puntaje_total(resultados_tecnicos, resultados_economicos)

        # 9. Construir trazabilidad
        trazabilidad = self._construir_trazabilidad(
            todos_hallazgos, resultados_tecnicos, resultados_economicos
        )

        return PreFallResult(
            licitacion_id=self.convocatoria.licitacion_id,
            proposicion_id=proposicion_id,
            licitante_nombre=licitante_nombre,
            estado_general=estado,
            legal_pct=legal_pct,
            administrativo_pct=admin_pct,
            tecnico_pct=tecnico_pct,
            economico_pct=economico_pct,
            puntaje_total=puntaje_total,
            ranking_preliminar=None,  # Se calcula después comparando contra otras proposiciones
            riesgos_criticos=len(criticos),
            advertencias=len(relevantes),
            inconsistencias=len([h for h in todos_hallazgos if h.resultado.startswith("INCONSISTENCIA")]),
            hallazgos=todos_hallazgos,
            evaluacion_tecnica=resultados_tecnicos,
            evaluacion_economica=resultados_economicos,
            trazabilidad=trazabilidad,
            version=1
        )

    def _calcular_pct_legal(self, hallazgos: List[Hallazgo]) -> float:
        """Calcula porcentaje de cumplimiento legal."""
        legal_hallazgos = [h for h in hallazgos if h.requisito_codigo.startswith("LEGAL") or h.resultado == "FALTANTE_DOCUMENTAL_LEGAL"]
        if not legal_hallazgos:
            return 100.0
        criticos = [h for h in legal_hallazgos if h.nivel_riesgo == NivelRiesgo.CRITICO]
        return max(0.0, 100.0 - len(criticos) * 20.0)

    def _calcular_pct_admin(self, hallazgos: List[Hallazgo]) -> float:
        """Calcula porcentaje de cumplimiento administrativo."""
        admin_hallazgos = [h for h in hallazgos if "ADMIN" in h.requisito_codigo or h.resultado in ("FALTANTE_DOCUMENTAL", "FIRMA_INVALIDA", "VIGENCIA_VENCIDA")]
        if not admin_hallazgos:
            return 100.0
        criticos = len([h for h in admin_hallazgos if h.nivel_riesgo == NivelRiesgo.CRITICO])
        return max(0.0, 100.0 - criticos * 8.0)

    def _calcular_pct_tecnico(self, resultados: List[EvaluacionTecnicaResultado]) -> float:
        """Calcula porcentaje de cumplimiento técnico."""
        if not resultados:
            return 100.0
        puntaje_total = sum(r.puntaje_obtenido for r in resultados)
        puntaje_max = sum(r.puntaje_maximo for r in resultados)
        return (puntaje_total / puntaje_max * 100) if puntaje_max > 0 else 100.0

    def _calcular_pct_economico(self, resultados: List[EvaluacionEconomicaResultado]) -> float:
        """Calcula porcentaje de cumplimiento económico."""
        if not resultados:
            return 100.0
        consistentes = sum(1 for r in resultados if r.consistente)
        return (consistentes / len(resultados) * 100) if resultados else 100.0

    def _determinar_solvencia(self, criticos: List[Hallazgo], 
                              tecnicos: List[EvaluacionTecnicaResultado],
                              economicos: List[EvaluacionEconomicaResultado]) -> EstadoSolvencia:
        """Determina estado de solvencia preliminar."""
        # Si hay hallazgos críticos en requisitos obligatorios → NO SOLVENTE
        if any(h.nivel_riesgo == NivelRiesgo.CRITICO for h in criticos):
            return EstadoSolvencia.NO_SOLVENTE

        # Si hay incumplimientos técnicos materiales → NO SOLVENTE
        if any(not r.cumple for r in tecnicos):
            return EstadoSolvencia.NO_SOLVENTE

        # Si hay inconsistencias económicas críticas → NO SOLVENTE
        if any(not r.consistente for r in economicos if r.criterio_codigo in ("ECON-SUMA-001", "ECON-IVA-001")):
            return EstadoSolvencia.NO_SOLVENTE

        # Si hay advertencias pero no críticos → RIESGO
        if criticos:
            return EstadoSolvencia.RIESGO

        return EstadoSolvencia.SOLVENTE

    def _calcular_puntaje_total(self, tecnicos: List[EvaluacionTecnicaResultado],
                                economicos: List[EvaluacionEconomicaResultado]) -> Optional[float]:
        """Calcula puntaje sólo cuando la convocatoria define ponderaciones explícitas."""
        wt = self.convocatoria.ponderacion_tecnica
        we = self.convocatoria.ponderacion_economica
        if wt is None or we is None:
            return None
        if wt < 0 or we < 0 or abs((wt + we) - 100.0) > 1e-9:
            raise ValueError("Las ponderaciones técnica/económica deben sumar 100.")
        tech_max = sum(r.puntaje_maximo for r in tecnicos)
        tech_score = (sum(r.puntaje_obtenido for r in tecnicos) / tech_max * wt) if tech_max else 0.0
        economic_score = (sum(1 for r in economicos if r.consistente) / len(economicos) * we) if economicos else 0.0
        return round(tech_score + economic_score, 2)

    def _construir_trazabilidad(self, hallazgos: List[Hallazgo],
                                tecnicos: List[EvaluacionTecnicaResultado],
                                economicos: List[EvaluacionEconomicaResultado]) -> List[Dict[str, Any]]:
        """Construye trazabilidad completa de la evaluación."""
        trazabilidad = []

        for h in hallazgos:
            trazabilidad.append({
                "tipo": "HALLAZGO",
                "requisito": h.requisito_codigo,
                "nivel": h.nivel_riesgo.value,
                "descripcion": h.descripcion,
                "documento": h.documento_afectado,
                "resultado": h.resultado,
                "fundamento": h.fundamento,
                "confianza": h.confianza,
                "fecha": h.fecha_deteccion.isoformat()
            })

        for t in tecnicos:
            trazabilidad.append({
                "tipo": "EVALUACION_TECNICA",
                "criterio": t.criterio_codigo,
                "cumple": t.cumple,
                "puntaje": f"{t.puntaje_obtenido}/{t.puntaje_maximo}",
                "observaciones": t.observaciones
            })

        for e in economicos:
            trazabilidad.append({
                "tipo": "EVALUACION_ECONOMICA",
                "criterio": e.criterio_codigo,
                "consistente": e.consistente,
                "monto_ofertado": e.monto_ofertado,
                "monto_referencia": e.monto_referencia,
                "observaciones": e.observaciones
            })

        return trazabilidad

    def calcular_ranking(self, resultados: List[PreFallResult]) -> List[PreFallResult]:
        """Calcula ranking preliminar entre múltiples proposiciones."""
        # Ordenar: solventes primero, luego por puntaje descendente
        ordenados = sorted(
            resultados,
            key=lambda r: (
                r.estado_general == EstadoSolvencia.SOLVENTE,
                r.puntaje_total or 0
            ),
            reverse=True
        )

        for i, res in enumerate(ordenados, 1):
            res.ranking_preliminar = i

        return ordenados
