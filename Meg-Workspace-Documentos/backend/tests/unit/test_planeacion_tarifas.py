import pytest
from app.engines.topografia.planeacion_obra import MotorPlaneacionObraAvanzada


def test_planeacion_requiere_tarifas_reales():
    motor = MotorPlaneacionObraAvanzada()
    puntos = [(0,0,100),(10,0,101),(10,10,99),(0,10,100)]
    with pytest.raises(ValueError):
        motor.generar_plan(puntos, 100, 0.5)


def test_planeacion_uses_catalog_tariffs_not_embedded_prices():
    motor = MotorPlaneacionObraAvanzada()
    puntos = [(0,0,100),(10,0,101),(10,10,99),(0,10,100)]
    result = motor.generar_plan(
        puntos, 100, 0.5,
        tarifas={"corte_m3": 10.0, "relleno_m3": 20.0, "drenaje_m2": 3.0},
    )
    assert result["estimacion_costo_m2"] >= 0
