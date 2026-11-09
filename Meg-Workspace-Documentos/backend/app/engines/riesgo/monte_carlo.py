# Copyright © 2026 Cristian Rodriguez
# All rights reserved.

"""Motor determinista/reproducible de simulación Monte Carlo.

La simulación usa un modelo de riesgos por impactos relativos y/o días.
No contiene datos sintéticos ni fallback silencioso: los parámetros inválidos
se rechazan y las dimensiones no simuladas se reportan explícitamente como
NO_SIMULADO.
"""
from __future__ import annotations

from dataclasses import dataclass
from math import sqrt
from statistics import NormalDist
from typing import Any, Callable, Dict, List, Optional

import numpy as np
from scipy.special import ndtr, ndtri
from scipy.stats import beta as beta_distribution

from app.core.errors import ErrorCode, MegalodonException

ProgressCallback = Callable[[int], None]

SUPPORTED_DISTRIBUTIONS = {"normal", "triangular", "uniform", "lognormal", "beta"}
SUPPORTED_IMPACTS = {"costo_pct", "plazo_pct", "plazo_dias", "costo_y_plazo_pct"}


@dataclass(frozen=True)
class VariableRiesgo:
    nombre: str
    distribucion: str
    parametros: Dict[str, float]
    impacto: str = "costo_pct"

    def __post_init__(self) -> None:
        if not self.nombre.strip():
            raise MegalodonException(ErrorCode.PARAMETRO_INVALIDO, "La variable de riesgo requiere nombre.")
        if self.distribucion not in SUPPORTED_DISTRIBUTIONS:
            raise MegalodonException(
                ErrorCode.PARAMETRO_INVALIDO,
                f"Distribución no soportada: {self.distribucion}",
            )
        if self.impacto not in SUPPORTED_IMPACTS:
            raise MegalodonException(
                ErrorCode.PARAMETRO_INVALIDO,
                f"Impacto no soportado: {self.impacto}",
            )
        self._validate_params()

    def _require(self, *keys: str) -> None:
        missing = [key for key in keys if key not in self.parametros]
        if missing:
            raise MegalodonException(
                ErrorCode.PARAMETRO_INVALIDO,
                f"Faltan parámetros para {self.nombre}: {', '.join(missing)}",
            )

    def _validate_params(self) -> None:
        if self.distribucion == "normal":
            self._require("media", "desviacion")
            if self.parametros["desviacion"] < 0:
                raise MegalodonException(ErrorCode.PARAMETRO_INVALIDO, f"Desviación negativa en {self.nombre}.")
        elif self.distribucion == "triangular":
            self._require("min", "moda", "max")
            lo, mode, hi = (self.parametros[k] for k in ("min", "moda", "max"))
            if not (lo <= mode <= hi) or lo == hi:
                raise MegalodonException(ErrorCode.PARAMETRO_INVALIDO, f"Triangular inválida en {self.nombre}.")
        elif self.distribucion == "uniform":
            self._require("min", "max")
            if self.parametros["min"] >= self.parametros["max"]:
                raise MegalodonException(ErrorCode.PARAMETRO_INVALIDO, f"Uniforme inválida en {self.nombre}.")
        elif self.distribucion == "lognormal":
            self._require("mu", "sigma")
            if self.parametros["sigma"] <= 0:
                raise MegalodonException(ErrorCode.PARAMETRO_INVALIDO, f"Sigma debe ser > 0 en {self.nombre}.")
        elif self.distribucion == "beta":
            self._require("alpha", "beta")
            if self.parametros["alpha"] <= 0 or self.parametros["beta"] <= 0:
                raise MegalodonException(ErrorCode.PARAMETRO_INVALIDO, f"Alpha/Beta deben ser > 0 en {self.nombre}.")

    def sample(self, rng: np.random.Generator, n: int) -> np.ndarray:
        if self.distribucion == "normal":
            return rng.normal(self.parametros["media"], self.parametros["desviacion"], n)
        if self.distribucion == "triangular":
            return rng.triangular(self.parametros["min"], self.parametros["moda"], self.parametros["max"], n)
        if self.distribucion == "uniform":
            return rng.uniform(self.parametros["min"], self.parametros["max"], n)
        if self.distribucion == "lognormal":
            return rng.lognormal(self.parametros["mu"], self.parametros["sigma"], n)
        if self.distribucion == "beta":
            return rng.beta(self.parametros["alpha"], self.parametros["beta"], n)
        raise AssertionError("Distribución validada previamente")


@dataclass
class ResultadoMonteCarlo:
    media: float
    mediana: float
    desviacion: float
    minimo: float
    maximo: float
    percentil_1: float
    percentil_5: float
    percentil_80: float
    percentil_95: float
    percentil_10: float
    percentil_25: float
    percentil_75: float
    percentil_90: float
    percentil_99: float
    cv: float
    prob_exceder_presupuesto: Optional[float]
    prob_exceder_plazo: Optional[float]
    ic_95_inferior: float
    ic_95_superior: float
    ic_confianza_inferior: float
    ic_confianza_superior: float
    histograma: List[Dict[str, float]]
    corridas: List[float]
    plazo: Optional[Dict[str, Any]] = None
    sensibilidad_presupuesto: List[Dict[str, float]] | None = None
    sensibilidad_plazo: List[Dict[str, float]] | None = None
    prob_exceder_ambos: Optional[float] = None
    contingencia_p80: float = 0.0
    contingencia_p90: float = 0.0
    margen_plazo_p80: Optional[float] = None
    valores_recortados: int = 0
    nivel_confianza: float = 0.95

    def to_dict(self) -> Dict[str, Any]:
        return {
            "media": self.media,
            "mediana": self.mediana,
            "desviacion": self.desviacion,
            "minimo": self.minimo,
            "maximo": self.maximo,
            "percentil_1": self.percentil_1,
            "percentil_5": self.percentil_5,
            "percentil_80": self.percentil_80,
            "percentil_95": self.percentil_95,
            "percentil_10": self.percentil_10,
            "percentil_25": self.percentil_25,
            "percentil_75": self.percentil_75,
            "percentil_90": self.percentil_90,
            "percentil_99": self.percentil_99,
            "cv": self.cv,
            "prob_exceder_presupuesto": self.prob_exceder_presupuesto,
            "prob_exceder_plazo": self.prob_exceder_plazo,
            "prob_exceder_ambos": self.prob_exceder_ambos,
            "ic_95": [self.ic_95_inferior, self.ic_95_superior],
            "intervalo_confianza_media": [self.ic_confianza_inferior, self.ic_confianza_superior],
            "histograma": self.histograma[:50],
            "corridas": self.corridas,
            "plazo": self.plazo,
            "sensibilidad_presupuesto": self.sensibilidad_presupuesto or [],
            "sensibilidad_plazo": self.sensibilidad_plazo or [],
            "contingencia_p80": self.contingencia_p80,
            "contingencia_p90": self.contingencia_p90,
            "margen_plazo_p80": self.margen_plazo_p80,
            "valores_recortados": self.valores_recortados,
            "nivel_confianza": self.nivel_confianza,
            "intervalo_confianza_media": [self.ic_95_inferior, self.ic_95_superior],
        }


class MotorMonteCarlo:
    def __init__(self, seed: Optional[int] = None, chunk_size: int = 50_000):
        if chunk_size < 1_000:
            raise MegalodonException(ErrorCode.PARAMETRO_INVALIDO, "chunk_size debe ser >= 1000.")
        self.seed = seed
        self.chunk_size = chunk_size

    @staticmethod
    def _histograma(resultados: np.ndarray, bins: int = 50) -> List[Dict[str, float]]:
        hist, edges = np.histogram(resultados, bins=bins)
        total = len(resultados)
        return [
            {
                "bin_start": float(edges[i]),
                "bin_end": float(edges[i + 1]),
                "min": float(edges[i]),
                "max": float(edges[i + 1]),
                "count": int(hist[i]),
                "frecuencia": int(hist[i]),
                "frequency": float(hist[i] / total),
                "probabilidad": float(hist[i] / total),
            }
            for i in range(len(hist))
        ]

    @staticmethod
    def _stats(resultados: np.ndarray, confidence_level: float = 0.95) -> Dict[str, float]:
        media = float(np.mean(resultados))
        std = float(np.std(resultados, ddof=1)) if len(resultados) > 1 else 0.0
        se = std / sqrt(len(resultados)) if len(resultados) > 1 else 0.0
        z95 = NormalDist().inv_cdf(0.975)
        z = NormalDist().inv_cdf(0.5 + confidence_level / 2.0)
        return {
            "media": media,
            "mediana": float(np.median(resultados)),
            "desviacion": std,
            "minimo": float(np.min(resultados)),
            "maximo": float(np.max(resultados)),
            "p1": float(np.percentile(resultados, 1)),
            "p5": float(np.percentile(resultados, 5)),
            "p10": float(np.percentile(resultados, 10)),
            "p25": float(np.percentile(resultados, 25)),

            "p50": float(np.percentile(resultados, 50)),
            "p80": float(np.percentile(resultados, 80)),
            "p75": float(np.percentile(resultados, 75)),
            "p90": float(np.percentile(resultados, 90)),
            "p95": float(np.percentile(resultados, 95)),
            "p99": float(np.percentile(resultados, 99)),
            "cv": float(std / media * 100) if media else 0.0,
            # Intervalo de confianza de la MEDIA, no percentiles de los datos.
            "ic95_inf": media - z95 * se,
            "ic95_sup": media + z95 * se,
            "ic_conf_inf": media - z * se,
            "ic_conf_sup": media + z * se,
        }

    @staticmethod
    def _pearson(x_sum, x_sq, xy_sum, y_sum, y_sq, n):
        numerator = n * xy_sum - x_sum * y_sum
        den_x = n * x_sq - x_sum * x_sum
        den_y = n * y_sq - y_sum * y_sum
        denominator = sqrt(max(den_x, 0.0) * max(den_y, 0.0))
        if denominator == 0:
            return 0.0
        return float(numerator / denominator)

    @staticmethod
    def _validar_correlaciones(variables: List[VariableRiesgo], correlaciones: Optional[Dict[str, Dict[str, float]]]) -> Optional[np.ndarray]:
        if not correlaciones:
            return None
        names = [v.nombre for v in variables]
        if len(set(names)) != len(names):
            raise MegalodonException(ErrorCode.PARAMETRO_INVALIDO, "Las variables de riesgo deben tener nombres únicos para usar correlaciones.")
        unknown = set(correlaciones) - set(names)
        if unknown:
            raise MegalodonException(ErrorCode.PARAMETRO_INVALIDO, f"Variables desconocidas en correlaciones: {sorted(unknown)}")
        n = len(names)
        matrix = np.eye(n, dtype=np.float64)
        index = {name: i for i, name in enumerate(names)}
        for a, row in correlaciones.items():
            if not isinstance(row, dict):
                raise MegalodonException(ErrorCode.PARAMETRO_INVALIDO, f"La fila de correlación de {a} debe ser objeto.")
            for b, value in row.items():
                if b not in index:
                    raise MegalodonException(ErrorCode.PARAMETRO_INVALIDO, f"Variable desconocida en correlación: {b}")
                try:
                    rho = float(value)
                except (TypeError, ValueError) as exc:
                    raise MegalodonException(ErrorCode.PARAMETRO_INVALIDO, f"Correlación inválida entre {a} y {b}.") from exc
                if rho < -1.0 or rho > 1.0:
                    raise MegalodonException(ErrorCode.PARAMETRO_INVALIDO, f"Correlación fuera de [-1,1] entre {a} y {b}.")
                matrix[index[a], index[b]] = rho
        if not np.allclose(matrix, matrix.T, atol=1e-8):
            raise MegalodonException(ErrorCode.PARAMETRO_INVALIDO, "La matriz de correlaciones debe ser simétrica.")
        np.fill_diagonal(matrix, 1.0)
        eigenvalues = np.linalg.eigvalsh(matrix)
        if float(np.min(eigenvalues)) < -1e-8:
            raise MegalodonException(ErrorCode.PARAMETRO_INVALIDO, "La matriz de correlaciones no es semidefinida positiva.")
        return matrix

    @staticmethod
    def _sample_correlated(variables: List[VariableRiesgo], rng: np.random.Generator, n: int, matrix: np.ndarray) -> List[np.ndarray]:
        # Gaussian copula: preserves the requested marginal distributions while
        # introducing the configured rank/linear dependence structure.
        eigenvalues, eigenvectors = np.linalg.eigh(matrix)
        factor = eigenvectors @ np.diag(np.sqrt(np.clip(eigenvalues, 0.0, None)))
        z = rng.normal(size=(n, len(variables))) @ factor.T
        u = np.clip(ndtr(z), 1e-12, 1.0 - 1e-12)
        out: List[np.ndarray] = []
        for idx, variable in enumerate(variables):
            ui = u[:, idx]
            if variable.distribucion == "normal":
                values = variable.parametros["media"] + variable.parametros["desviacion"] * ndtri(ui)
            elif variable.distribucion == "uniform":
                values = variable.parametros["min"] + ui * (variable.parametros["max"] - variable.parametros["min"])
            elif variable.distribucion == "triangular":
                lo = variable.parametros["min"]
                mode = variable.parametros["moda"]
                hi = variable.parametros["max"]
                f = (mode - lo) / (hi - lo)
                left = lo + np.sqrt(ui * (hi - lo) * (mode - lo))
                right = hi - np.sqrt((1.0 - ui) * (hi - lo) * (hi - mode))
                values = np.where(ui <= f, left, right)
            elif variable.distribucion == "lognormal":
                values = np.exp(variable.parametros["mu"] + variable.parametros["sigma"] * ndtri(ui))
            elif variable.distribucion == "beta":
                values = beta_distribution.ppf(ui, variable.parametros["alpha"], variable.parametros["beta"])
            else:
                raise AssertionError("Distribución validada previamente")
            out.append(np.asarray(values, dtype=np.float64))
        return out

    def simular_presupuesto(
        self,
        presupuesto_base: float,
        variables: List[VariableRiesgo],
        iteraciones: int = 10_000,
        presupuesto_maximo: Optional[float] = None,
        plazo_base: Optional[int] = None,
        plazo_maximo: Optional[int] = None,
        progress_callback: Optional[ProgressCallback] = None,
        confidence_level: float = 0.95,
        correlaciones: Optional[Dict[str, Dict[str, float]]] = None,
    ) -> ResultadoMonteCarlo:
        if presupuesto_base <= 0:
            raise MegalodonException(ErrorCode.PARAMETRO_INVALIDO, "presupuesto_base debe ser > 0.")
        if iteraciones < 100 or iteraciones > 1_000_000:
            raise MegalodonException(ErrorCode.PARAMETRO_INVALIDO, "iteraciones fuera del rango permitido.")
        if presupuesto_maximo is not None and presupuesto_maximo <= 0:
            raise MegalodonException(ErrorCode.PARAMETRO_INVALIDO, "presupuesto_maximo debe ser > 0.")
        if not 0.80 <= confidence_level <= 0.999:
            raise MegalodonException(ErrorCode.PARAMETRO_INVALIDO, "confidence_level debe estar entre 0.80 y 0.999.")
        if plazo_base is not None and plazo_base <= 0:
            raise MegalodonException(ErrorCode.PARAMETRO_INVALIDO, "plazo_base debe ser > 0.")
        if plazo_maximo is not None and (plazo_base is None or plazo_maximo <= 0 or plazo_maximo < plazo_base):
            raise MegalodonException(ErrorCode.PARAMETRO_INVALIDO, "plazo_maximo inválido.")
        if not variables:
            raise MegalodonException(ErrorCode.PARAMETRO_INVALIDO, "Se requiere al menos una variable de riesgo.")

        if plazo_base is not None and not any(v.impacto in {"plazo_pct", "plazo_dias", "costo_y_plazo_pct"} for v in variables):
            raise MegalodonException(
                ErrorCode.PARAMETRO_INVALIDO,
                "Se proporcionó plazo_base pero no existen variables con impacto de plazo.",
            )

        correlation_matrix = self._validar_correlaciones(variables, correlaciones)
        rng = np.random.default_rng(self.seed)
        resultados_coste = np.empty(iteraciones, dtype=np.float64)
        resultados_plazo = np.empty(iteraciones, dtype=np.float64) if plazo_base is not None else None
        corridas_coste = min(iteraciones, 1_000)
        corridas_plazo = min(iteraciones, 1_000)
        valores_recortados = 0

        n_vars = len(variables)
        x_sum = np.zeros(n_vars)
        x_sq = np.zeros(n_vars)
        xy_cost = np.zeros(n_vars)
        xy_plazo = np.zeros(n_vars)
        y_cost_sum = 0.0
        y_cost_sq = 0.0
        y_plazo_sum = 0.0
        y_plazo_sq = 0.0

        cursor = 0
        while cursor < iteraciones:
            end = min(cursor + self.chunk_size, iteraciones)
            n = end - cursor
            draws = (
                self._sample_correlated(variables, rng, n, correlation_matrix)
                if correlation_matrix is not None
                else [v.sample(rng, n) for v in variables]
            )

            delta_cost_pct = np.zeros(n, dtype=np.float64)
            delta_plazo_pct = np.zeros(n, dtype=np.float64)
            delta_plazo_days = np.zeros(n, dtype=np.float64)
            for idx, (v, draw) in enumerate(zip(variables, draws)):
                x_sum[idx] += float(np.sum(draw))
                x_sq[idx] += float(np.dot(draw, draw))
                if v.impacto in {"costo_pct", "costo_y_plazo_pct"}:
                    delta_cost_pct += draw
                if v.impacto in {"plazo_pct", "costo_y_plazo_pct"}:
                    delta_plazo_pct += draw
                elif v.impacto == "plazo_dias":
                    delta_plazo_days += draw

            # Los impactos porcentuales son aditivos entre variables de riesgo;
            # esto evita el efecto de composición artificial del motor anterior.
            cost = presupuesto_base * (1.0 + delta_cost_pct)
            clipped_cost = cost <= 0
            if np.any(clipped_cost):
                valores_recortados += int(np.count_nonzero(clipped_cost))
                cost = np.maximum(cost, 0.01)
            resultados_coste[cursor:end] = cost

            y_cost_sum += float(np.sum(cost))
            y_cost_sq += float(np.dot(cost, cost))
            for idx, draw in enumerate(draws):
                xy_cost[idx] += float(np.dot(draw, cost))

            if resultados_plazo is not None:
                plazo = plazo_base * (1.0 + delta_plazo_pct) + delta_plazo_days
                clipped_plazo = plazo <= 0
                if np.any(clipped_plazo):
                    valores_recortados += int(np.count_nonzero(clipped_plazo))
                    plazo = np.maximum(plazo, 0.1)
                resultados_plazo[cursor:end] = plazo
                y_plazo_sum += float(np.sum(plazo))
                y_plazo_sq += float(np.dot(plazo, plazo))
                for idx, draw in enumerate(draws):
                    xy_plazo[idx] += float(np.dot(draw, plazo))

            cursor = end
            if progress_callback:
                progress_callback(int(cursor / iteraciones * 100))

        stats = self._stats(resultados_coste, confidence_level)
        prob_exceder = None
        if presupuesto_maximo is not None:
            prob_exceder = float(np.mean(resultados_coste > presupuesto_maximo))

        plazo_stats = None
        prob_plazo = None
        prob_ambos = None
        margen_p80 = None
        sensibilidad_plazo: List[Dict[str, float]] = []
        if resultados_plazo is not None:
            plazo_stats = self._stats(resultados_plazo, confidence_level)
            if plazo_maximo is not None:
                prob_plazo = float(np.mean(resultados_plazo > plazo_maximo))
                if presupuesto_maximo is not None:
                    prob_ambos = float(np.mean((resultados_coste > presupuesto_maximo) & (resultados_plazo > plazo_maximo)))
            margen_p80 = plazo_stats["p80"] - plazo_base
            for idx, v in enumerate(variables):
                if v.impacto not in {"plazo_pct", "plazo_dias", "costo_y_plazo_pct"}:
                    continue
                r = self._pearson(x_sum[idx], x_sq[idx], xy_plazo[idx], y_plazo_sum, y_plazo_sq, iteraciones)
                sensibilidad_plazo.append({"variable": v.nombre, "correlacion": r, "impacto": abs(r), "impact": abs(r)})
            sensibilidad_plazo.sort(key=lambda x: x["impacto"], reverse=True)

        sensibilidad_coste: List[Dict[str, float]] = []
        for idx, v in enumerate(variables):
            if v.impacto not in {"costo_pct", "costo_y_plazo_pct"}:
                continue
            r = self._pearson(x_sum[idx], x_sq[idx], xy_cost[idx], y_cost_sum, y_cost_sq, iteraciones)
            sensibilidad_coste.append({"variable": v.nombre, "correlacion": r, "impacto": abs(r), "impact": abs(r)})
        sensibilidad_coste.sort(key=lambda x: x["impacto"], reverse=True)

        return ResultadoMonteCarlo(
            media=stats["media"],
            mediana=stats["mediana"],
            desviacion=stats["desviacion"],
            minimo=stats["minimo"],
            maximo=stats["maximo"],
            percentil_1=stats["p1"],
            percentil_5=stats["p5"],
            percentil_80=stats["p80"],
            percentil_95=stats["p95"],
            percentil_10=stats["p10"],
            percentil_25=stats["p25"],
            percentil_75=stats["p75"],
            percentil_90=stats["p90"],
            percentil_99=stats["p99"],
            cv=stats["cv"],
            prob_exceder_presupuesto=prob_exceder,
            prob_exceder_plazo=prob_plazo,
            ic_95_inferior=stats["ic95_inf"],
            ic_95_superior=stats["ic95_sup"],
            ic_confianza_inferior=stats["ic_conf_inf"],
            ic_confianza_superior=stats["ic_conf_sup"],
            histograma=self._histograma(resultados_coste),
            corridas=resultados_coste[:corridas_coste].tolist(),
            plazo=(
                {
                    "estado": "SIMULADO",
                    "media": plazo_stats["media"],
                    "mediana": plazo_stats["mediana"],
                    "desviacion": plazo_stats["desviacion"],
                    "minimo": plazo_stats["minimo"],
                    "maximo": plazo_stats["maximo"],
                    "p5": plazo_stats["p5"],
                    "p10": plazo_stats["p10"],
                    "p50": plazo_stats["p50"],
                    "p80": plazo_stats["p80"],
                    "p90": plazo_stats["p90"],
                    "p95": plazo_stats["p95"],
                    "ic95": [plazo_stats["ic95_inf"], plazo_stats["ic95_sup"]],
                    "intervalo_confianza": [plazo_stats["ic_conf_inf"], plazo_stats["ic_conf_sup"]],
                    "prob_exceder_plazo": prob_plazo,
                    "histograma": self._histograma(resultados_plazo),
                    "corridas": resultados_plazo[:corridas_plazo].tolist(),
                }
                if plazo_stats is not None
                else {"estado": "NO_SIMULADO", "razon": "No se proporcionó plazo_base_dias."}
            ),
            sensibilidad_presupuesto=sensibilidad_coste,
            sensibilidad_plazo=sensibilidad_plazo,
            prob_exceder_ambos=prob_ambos,
            contingencia_p80=max(0.0, stats["p80"] - presupuesto_base),
            contingencia_p90=max(0.0, stats["p90"] - presupuesto_base),
            margen_plazo_p80=margen_p80,
            valores_recortados=valores_recortados,
            nivel_confianza=confidence_level,
        )
