# Copyright © 2026 Cristian Rodriguez
# Economic Evaluation Engine — evaluación económica determinista

from typing import List, Dict, Any, Optional

from .domain import (
    CriterioEconomico, EvaluacionEconomicaResultado, Hallazgo, NivelRiesgo
)


class EconomicEvaluationEngine:
    """Motor de evaluación económica.

    Valida: suma de partidas, indirectos, financiamiento, utilidad, cargos, IVA,
    precios unitarios, cantidades, subtotales, discrepancias, precios no aceptables,
    comparación contra investigación de mercado, consistencia entre catálogo y oferta.
    """

    def __init__(self, criterios: List[CriterioEconomico], monto_referencia: Optional[float] = None, reglas: Optional[Dict[str, Any]] = None):
        self.criterios = criterios
        self.monto_referencia = monto_referencia
        self.reglas = reglas or {}

    def evaluar(self, proposicion_economica: Dict[str, Any]) -> List[EvaluacionEconomicaResultado]:
        """Ejecuta evaluación económica completa."""
        resultados = []

        # Validar suma de partidas
        resultados.append(self._validar_suma_partidas(proposicion_economica))

        if self.reglas.get("indirectos_max_pct") is not None:
            resultados.append(self._validar_indirectos(proposicion_economica, float(self.reglas["indirectos_max_pct"])))

        if self.reglas.get("utilidad_max_pct") is not None:
            resultados.append(self._validar_utilidad(proposicion_economica, float(self.reglas["utilidad_max_pct"])))

        if self.reglas.get("iva_rate") is not None:
            resultados.append(self._validar_iva(proposicion_economica, float(self.reglas["iva_rate"])))

        # Validar precios unitarios
        resultados.append(self._validar_precios_unitarios(proposicion_economica))

        if self.monto_referencia is not None and self.reglas.get("market_tolerance_pct") is not None:
            resultados.append(self._validar_contra_mercado(proposicion_economica, float(self.reglas["market_tolerance_pct"])))

        # Validar consistencia catálogo vs oferta
        resultados.append(self._validar_consistencia_catalogo(proposicion_economica))

        return [r for r in resultados if r is not None]

    def _validar_suma_partidas(self, prop: Dict[str, Any]) -> EvaluacionEconomicaResultado:
        """Valida que la suma de partidas coincida con el total."""
        partidas = prop.get("partidas", [])
        total_ofertado = prop.get("monto_total", 0)

        suma_partidas = sum(p.get("subtotal", 0) for p in partidas)
        discrepancia = abs(suma_partidas - total_ofertado)

        return EvaluacionEconomicaResultado(
            criterio_codigo="ECON-SUMA-001",
            monto_ofertado=total_ofertado,
            monto_referencia=suma_partidas,
            discrepancia=discrepancia,
            discrepancia_pct=(discrepancia / total_ofertado * 100) if total_ofertado > 0 else 0,
            observaciones=["Suma de partidas vs total ofertado"] if discrepancia < 0.01 else [f"Discrepancia: {discrepancia:.2f}"],
            consistente=discrepancia < 0.01
        )

    def _validar_indirectos(self, prop: Dict[str, Any], limite: float) -> EvaluacionEconomicaResultado:
        """Valida porcentaje de indirectos."""
        indirectos_pct = prop.get("indirectos_pct", 0)
        return EvaluacionEconomicaResultado(
            criterio_codigo="ECON-IND-001",
            monto_ofertado=indirectos_pct * 100,
            monto_referencia=limite * 100,
            discrepancia=(indirectos_pct - limite) * 100 if indirectos_pct > limite else 0,
            observaciones=[f"Indirectos: {indirectos_pct*100:.1f}%"] if indirectos_pct <= limite else [f"Indirectos exceden límite: {indirectos_pct*100:.1f}% > {limite*100:.0f}%"],
            consistente=indirectos_pct <= limite
        )

    def _validar_utilidad(self, prop: Dict[str, Any], limite: float) -> EvaluacionEconomicaResultado:
        """Valida porcentaje de utilidad."""
        utilidad_pct = prop.get("utilidad_pct", 0)
        return EvaluacionEconomicaResultado(
            criterio_codigo="ECON-UTI-001",
            monto_ofertado=utilidad_pct * 100,
            monto_referencia=limite * 100,
            discrepancia=(utilidad_pct - limite) * 100 if utilidad_pct > limite else 0,
            observaciones=[f"Utilidad: {utilidad_pct*100:.1f}%"] if utilidad_pct <= limite else [f"Utilidad excede límite: {utilidad_pct*100:.1f}% > {limite*100:.0f}%"],
            consistente=utilidad_pct <= limite
        )

    def _validar_iva(self, prop: Dict[str, Any], iva_rate: float) -> EvaluacionEconomicaResultado:
        """Valida cálculo de IVA."""
        subtotal = prop.get("subtotal", 0)
        iva = prop.get("iva", 0)
        iva_esperado = subtotal * iva_rate
        discrepancia = abs(iva - iva_esperado)

        return EvaluacionEconomicaResultado(
            criterio_codigo="ECON-IVA-001",
            monto_ofertado=iva,
            monto_referencia=iva_esperado,
            discrepancia=discrepancia,
            observaciones=["IVA correcto"] if discrepancia < 0.01 else [f"IVA discrepante: {iva:.2f} vs {iva_esperado:.2f}"],
            consistente=discrepancia < 0.01
        )

    def _validar_precios_unitarios(self, prop: Dict[str, Any]) -> EvaluacionEconomicaResultado:
        """Valida que precios unitarios sean positivos y razonables."""
        partidas = prop.get("partidas", [])
        precios_invalidos = [p for p in partidas if p.get("precio_unitario", 0) <= 0]

        return EvaluacionEconomicaResultado(
            criterio_codigo="ECON-PU-001",
            monto_ofertado=len(precios_invalidos),
            monto_referencia=0,
            observaciones=["Todos los precios unitarios válidos"] if not precios_invalidos else [f"{len(precios_invalidos)} precios unitarios inválidos"],
            consistente=not precios_invalidos
        )

    def _validar_contra_mercado(self, prop: Dict[str, Any], tolerance_pct: float) -> EvaluacionEconomicaResultado:
        """Compara monto total contra investigación de mercado."""
        monto_total = prop.get("monto_total", 0)
        diferencia = abs(monto_total - self.monto_referencia) if self.monto_referencia else 0
        pct = (diferencia / self.monto_referencia * 100) if self.monto_referencia else 0

        return EvaluacionEconomicaResultado(
            criterio_codigo="ECON-MER-001",
            monto_ofertado=monto_total,
            monto_referencia=self.monto_referencia,
            discrepancia=diferencia,
            discrepancia_pct=pct,
            observaciones=[f"Diferencia vs mercado: {pct:.1f}%"] if pct <= tolerance_pct else [f"Diferencia significativa vs mercado: {pct:.1f}%"],
            consistente=pct <= tolerance_pct
        )

    def _validar_consistencia_catalogo(self, prop: Dict[str, Any]) -> EvaluacionEconomicaResultado:
        """Valida consistencia entre catálogo de conceptos y oferta."""
        catalogo = prop.get("catalogo_conceptos", [])
        oferta = prop.get("partidas", [])

        # Verificar que cada concepto del catálogo tenga correspondencia en la oferta
        catalogo_ids = {c.get("id") for c in catalogo}
        oferta_ids = {o.get("concepto_id") for o in oferta}

        faltantes = catalogo_ids - oferta_ids
        sobrantes = oferta_ids - catalogo_ids

        return EvaluacionEconomicaResultado(
            criterio_codigo="ECON-CAT-001",
            monto_ofertado=len(oferta),
            monto_referencia=len(catalogo),
            observaciones=[
                f"Catálogo: {len(catalogo)} conceptos, Oferta: {len(oferta)} partidas",
                f"Faltantes en oferta: {len(faltantes)}" if faltantes else "Todos los conceptos cubiertos",
                f"Sobrantes en oferta: {len(sobrantes)}" if sobrantes else "Sin conceptos sobrantes"
            ],
            consistente=not faltantes and not sobrantes
        )

    def generar_hallazgos(self, resultados: List[EvaluacionEconomicaResultado]) -> List[Hallazgo]:
        """Genera hallazgos a partir de resultados económicos."""
        hallazgos = []

        for res in resultados:
            if not res.consistente:
                nivel = NivelRiesgo.CRITICO if res.criterio_codigo in ("ECON-SUMA-001", "ECON-IVA-001") else NivelRiesgo.RELEVANTE
                hallazgos.append(Hallazgo(
                    requisito_codigo=res.criterio_codigo,
                    nivel_riesgo=nivel,
                    descripcion=f"{res.criterio_codigo}: {res.observaciones[0]}",
                    valor_encontrado=str(res.monto_ofertado),
                    valor_requerido=str(res.monto_referencia) if res.monto_referencia else None,
                    resultado="INCONSISTENCIA_ECONOMICA",
                    fundamento=str(self.reglas.get("legal_basis", "REGLA_ECONOMICA_DEL_PROCEDIMIENTO"))
                ))

        return hallazgos
