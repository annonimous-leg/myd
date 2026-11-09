from app.engines.juridico.motor_evaluacion import MotorEvaluacion


def matrix():
    return {
        "legal": {"LEGAL_A": {"campo": "LEGAL_A", "requerido": True}},
        "tecnico": {"TEC_A": {"ponderacion": 50}, "TEC_B": {"ponderacion": 50}},
        "economico": {"ECO_A": {"ponderacion": 100}},
        "minimo_tecnico": 75,
        "minimo_economico": 60,
        "variacion_mercado_max": 0.25,
        "variacion_mercado_penalty": 0.5,
    }


def test_evaluation_uses_frozen_matrix_values():
    motor = MotorEvaluacion(matrix())
    tech = motor.evaluar_tecnica("p", {"TEC_A": 100, "TEC_B": 50})
    assert tech.puntaje_total == 75
    assert tech.resultado.value == "APROBADA"


def test_missing_matrix_values_fail_closed():
    try:
        MotorEvaluacion({"tecnico": {"TEC_A": {"ponderacion": 100}}}).evaluar_tecnica("p", {"TEC_A": 100})
    except Exception as exc:
        assert "matriz" in str(exc).lower() or "econ" in str(exc).lower() or "mínimo" in str(exc).lower()
    else:
        raise AssertionError("La evaluación no debe inventar mínimos ni completar una matriz incompleta")
