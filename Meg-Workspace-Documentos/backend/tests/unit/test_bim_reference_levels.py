"""Source-to-source level comparison, based on the actual office concrete IFC exports."""
import pytest

from app.engines.bim.referencias import cotejar_niveles


REVIT_OFFICE_LEVELS = [
    ("Sea Level", 0.0), ("Foundation", 51.0), ("Basement", 51.7),
    ("Level_01", 55.5), ("Level_02a_Parking", 58.9),
    ("Level_02", 59.7), ("Level_03", 63.65),
    ("Level_04", 67.6), ("Level_05", 71.92), ("Roof", 77.89),
]
ARCHICAD_OFFICE_LEVELS = [
    ("Foundations", 49.07), ("Basement", 51.7), ("Level_01", 55.5),
    ("Garage_02", 58.9), ("Level_02", 59.7), ("Level_03", 63.65),
    ("Level_04", 67.65), ("Level_05", 71.92), ("Roof", 75.92),
]


def test_office_concrete_sources_preserve_discrepant_levels_without_snap_or_alias():
    cotejo = cotejar_niveles(REVIT_OFFICE_LEVELS, ARCHICAD_OFFICE_LEVELS, tolerancia_m=0.01)

    assert cotejo["coincidentes"] == 5
    assert [(row["nombre"], row["diferencia_m"]) for row in cotejo["diferencias"]] == [
        ("Level_04", pytest.approx(0.05)), ("Roof", pytest.approx(-1.97)),
    ]
    assert cotejo["solo_referencia"] == ["Sea Level", "Foundation", "Level_02a_Parking"]
    assert cotejo["solo_candidato"] == ["Foundations", "Garage_02"]
    assert cotejo["apto_para_confirmacion_automatica"] is False


def test_level_comparison_uses_metric_tolerance_and_order_independent_names():
    cotejo = cotejar_niveles(
        [(" Roof ", 77.89), ("Level_01", 55.5)],
        [("level_01", 55.504), ("roof", 77.882)],
        tolerancia_m=0.01,
    )
    assert cotejo["coincidentes"] == 2
    assert cotejo["diferencias"] == []
    assert cotejo["apto_para_confirmacion_automatica"] is True


@pytest.mark.parametrize("levels", [
    [("Level_01", 55), ("level_01", 55)],
    [("Roof", float("nan"))],
    [("Roof", float("inf"))],
    [("", 55)],
])
def test_level_comparison_rejects_ambiguous_or_invalid_inputs(levels):
    with pytest.raises(ValueError):
        cotejar_niveles(levels, [("Roof", 77.89)])


def test_level_comparison_rejects_invalid_tolerance():
    with pytest.raises(ValueError):
        cotejar_niveles([("Roof", 77.89)], [("Roof", 77.89)], tolerancia_m=-1)
