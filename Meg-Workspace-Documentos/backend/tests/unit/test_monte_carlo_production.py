import math

import numpy as np
import pytest

from app.engines.riesgo.monte_carlo import MotorMonteCarlo, VariableRiesgo


def test_cost_monte_carlo_is_reproducible_and_nonzero_exceedance():
    variables = [
        VariableRiesgo(
            "inflacion_material",
            "normal",
            {"media": 0.05, "desviacion": 0.02},
            impacto="costo_pct",
        ),
        VariableRiesgo(
            "productividad",
            "triangular",
            {"min": -0.05, "moda": 0.0, "max": 0.10},
            impacto="costo_pct",
        ),
    ]
    a = MotorMonteCarlo(seed=123).simular_presupuesto(1_000_000, variables, 20_000, 1_020_000)
    b = MotorMonteCarlo(seed=123).simular_presupuesto(1_000_000, variables, 20_000, 1_020_000)
    assert a.to_dict() == b.to_dict()
    assert a.media > 1_000_000
    assert 0 <= a.prob_exceder_presupuesto <= 1
    assert a.contingencia_p80 >= 0
    assert a.sensibilidad_presupuesto


def test_schedule_risk_is_simulated_not_placeholder():
    variables = [
        VariableRiesgo(
            "retraso_suministro",
            "triangular",
            {"min": 0.0, "moda": 0.05, "max": 0.25},
            impacto="plazo_pct",
        ),
        VariableRiesgo(
            "dias_permiso",
            "triangular",
            {"min": 0.0, "moda": 2.0, "max": 10.0},
            impacto="plazo_dias",
        ),
    ]
    r = MotorMonteCarlo(seed=7).simular_presupuesto(
        10_000_000,
        variables,
        10_000,
        11_000_000,
        plazo_base=180,
        plazo_maximo=210,
    )
    assert r.prob_exceder_plazo is not None
    assert r.prob_exceder_plazo > 0
    assert r.plazo is not None
    assert r.plazo["estado"] == "SIMULADO"
    assert r.plazo["p80"] > 180
    assert r.margen_plazo_p80 > 0


def test_reject_schedule_without_schedule_variables():
    variables = [VariableRiesgo("coste", "normal", {"media": 0.0, "desviacion": 0.01})]
    with pytest.raises(Exception):
        MotorMonteCarlo(seed=1).simular_presupuesto(
            1_000_000, variables, 1_000, 1_100_000, plazo_base=100, plazo_maximo=120
        )


def test_invalid_distribution_parameters_are_rejected():
    with pytest.raises(Exception):
        VariableRiesgo("x", "triangular", {"min": 2, "moda": 1, "max": 3})
    with pytest.raises(Exception):
        VariableRiesgo("x", "normal", {"media": 0, "desviacion": -1})


def test_confidence_level_changes_mean_interval_width():
    variables = [VariableRiesgo("coste", "normal", {"media": 0.0, "desviacion": 0.05})]
    low = MotorMonteCarlo(seed=10).simular_presupuesto(1_000_000, variables, 20_000, 1_300_000, confidence_level=0.80)
    high = MotorMonteCarlo(seed=10).simular_presupuesto(1_000_000, variables, 20_000, 1_300_000, confidence_level=0.99)
    assert high.nivel_confianza == 0.99
    assert (high.ic_confianza_superior - high.ic_confianza_inferior) > (low.ic_confianza_superior - low.ic_confianza_inferior)


def test_fixed_days_impact_works_without_fake_probability():
    variables = [VariableRiesgo("permiso", "triangular", {"min": 0, "moda": 3, "max": 6}, impacto="plazo_dias")]
    result = MotorMonteCarlo(seed=55).simular_presupuesto(
        2_000_000, variables, 5_000, 2_500_000, plazo_base=100, plazo_maximo=106
    )
    assert result.plazo["p80"] > 100
    assert result.prob_exceder_plazo is not None


def test_joint_budget_and_schedule_exceedance_is_bounded():
    variables = [
        VariableRiesgo("costo", "normal", {"media": 0.08, "desviacion": 0.01}, impacto="costo_pct"),
        VariableRiesgo("retraso", "normal", {"media": 0.08, "desviacion": 0.01}, impacto="plazo_pct"),
    ]
    r = MotorMonteCarlo(seed=11).simular_presupuesto(1_000_000, variables, 25_000, 1_050_000, plazo_base=100, plazo_maximo=105)
    assert 0.0 <= (r.prob_exceder_presupuesto or 0.0) <= 1.0
    assert 0.0 <= (r.prob_exceder_plazo or 0.0) <= 1.0
    assert 0.0 <= (r.prob_exceder_ambos or 0.0) <= 1.0
    assert (r.prob_exceder_ambos or 0.0) <= (r.prob_exceder_presupuesto or 0.0)
    assert (r.prob_exceder_ambos or 0.0) <= (r.prob_exceder_plazo or 0.0)


def test_no_schedule_does_not_claim_schedule_risk():
    variables = [VariableRiesgo("coste", "normal", {"media": 0.03, "desviacion": 0.01}, impacto="costo_pct")]
    r = MotorMonteCarlo(seed=12).simular_presupuesto(1_000_000, variables, 2_000, 1_200_000)
    assert r.prob_exceder_plazo is None
    assert r.plazo["estado"] == "NO_SIMULADO"


def test_correlated_risks_are_supported_and_reproducible():
    variables = [
        VariableRiesgo("materiales", "normal", {"media": 0.05, "desviacion": 0.02}, impacto="costo_pct"),
        VariableRiesgo("mano_obra", "normal", {"media": 0.03, "desviacion": 0.01}, impacto="costo_pct"),
    ]
    corr = {"materiales": {"mano_obra": 0.65}, "mano_obra": {"materiales": 0.65}}
    a = MotorMonteCarlo(seed=42).simular_presupuesto(1_000_000, variables, 10_000, 1_200_000, correlaciones=corr)
    b = MotorMonteCarlo(seed=42).simular_presupuesto(1_000_000, variables, 10_000, 1_200_000, correlaciones=corr)
    assert a.to_dict() == b.to_dict()
    assert a.sensibilidad_presupuesto


def test_invalid_correlation_matrix_is_rejected():
    variables = [
        VariableRiesgo("a", "normal", {"media": 0.0, "desviacion": 0.01}),
        VariableRiesgo("b", "normal", {"media": 0.0, "desviacion": 0.01}),
        VariableRiesgo("c", "normal", {"media": 0.0, "desviacion": 0.01}),
    ]
    corr = {
        "a": {"b": 0.99, "c": -0.99},
        "b": {"a": 0.99, "c": 0.99},
        "c": {"a": -0.99, "b": 0.99},
    }
    with pytest.raises(Exception):
        MotorMonteCarlo(seed=1).simular_presupuesto(1_000_000, variables, 1000, 1_500_000, correlaciones=corr)


def test_correlation_matrix_is_part_of_api_contract():
    from pathlib import Path
    api = Path(__file__).parents[1] / ".." / "app" / "api" / "v1" / "montecarlo.py"
    text = api.resolve().read_text(encoding="utf-8")
    assert "correlaciones: Dict[str, Dict[str, float]]" in text


def test_worker_uses_persisted_seed_not_a_hidden_default():
    from pathlib import Path
    from types import SimpleNamespace

    from app.services.montecarlo_service import MonteCarloService

    worker = Path(__file__).parents[1] / ".." / "app" / "workers" / "montecarlo_tasks.py"
    w = worker.resolve().read_text(encoding="utf-8")

    run = SimpleNamespace(
        id="00000000-0000-0000-0000-000000000001",
        tenant_id="00000000-0000-0000-0000-000000000002",
        configuracion={"seed": 999, "iteraciones": 1000},
        presupuesto_base=1000,
        seed=123456,
        plazo_base_dias=None,
        plazo_maximo_dias=None,
    )
    payload = MonteCarloService.payload_worker(run)

    assert 'seed=int(data["seed"])' in w
    assert payload["seed"] == 123456
    assert payload["seed"] != run.configuracion["seed"]
