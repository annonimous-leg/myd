"""Analytic volumes; no external engine or text/import-only checks."""
import pytest
from app.engines.topografia.volumenes import MotorVolumenes
from app.core.errors import MegalodonException
from app.engines.topografia.triangulacion import MotorTriangulacion


def test_triangle_crossing_grade_keeps_cut_and_fill_separately():
    surface = [(0, 0, 1), (1, 0, -1), (0, 1, -1)]
    result = MotorVolumenes().calcular_contra_elevacion_referencia(surface, 0)
    # Cut triangle legs .5, area 1/8, average height 1/3 => 1/24.
    # Signed net = 1/6; fill = net + cut = 5/24.
    assert result.volumen_corte_m3 == round(1 / 24, 3)
    assert result.volumen_terraplen_m3 == round(5 / 24, 3)
    assert result.volumen_neto_m3 == round(1 / 6, 3)
    assert result.area_analizada_m2 == 0.5


def test_partial_overlap_integrates_only_the_common_footprint():
    existing = [(0, 0, 1), (1, 0, 1), (0, 1, 1)]
    project = [(0.5, 0, 2), (1.5, 0, 2), (0.5, 1, 2)]
    result = MotorVolumenes().calcular_entre_superficies(existing, project)
    assert result.area_analizada_m2 == 0.125
    assert result.volumen_terraplen_m3 == 0.125
    assert result.volumen_corte_m3 == 0


def test_disjoint_surfaces_are_unmeasurable_instead_of_successful_zero():
    existing = [(0, 0, 1), (1, 0, 1), (0, 1, 1)]
    project = [(2, 0, 2), (3, 0, 2), (2, 1, 2)]
    with pytest.raises(MegalodonException, match="común|solapan"):
        MotorVolumenes().calcular_entre_superficies(existing, project)


@pytest.mark.parametrize("points", [
    [(0, 0, 1), (0, 0, 2), (1, 0, 1), (0, 1, 1)],
    [(0, 0, 1), (1, 0, float('nan')), (0, 1, 1)],
    [(0, 0, 1), (1, 0, 1), (2, 0, 1)],
])
def test_invalid_surface_is_rejected_with_domain_error(points):
    with pytest.raises(MegalodonException):
        MotorVolumenes().calcular_contra_elevacion_referencia(points, 0)


def test_overlay_preserves_both_tins_edges_and_is_translation_invariant():
    # Square pyramid height 1/base area 4, sliced at height .5.
    # Cut is a smaller pyramid: height .5/base area 1 => 1/6.
    # Signed net = 4*.5 - 4/3 = 2/3; fill = 5/6.
    existing = [(-1, -1, 0), (1, -1, 0), (1, 1, 0), (-1, 1, 0), (0, 0, 1)]
    project = [(-1, -1, .5), (1, -1, .5), (1, 1, .5), (-1, 1, .5)]
    for dx, dy in [(0, 0), (500000, 2200000)]:
        shifted_ex = [(x+dx, y+dy, z) for x, y, z in existing]
        shifted_pr = [(x+dx, y+dy, z) for x, y, z in project]
        result = MotorVolumenes().calcular_entre_superficies(shifted_ex, shifted_pr)
        assert result.volumen_corte_m3 == round(1/6, 3)
        assert result.volumen_terraplen_m3 == round(5/6, 3)
        assert result.volumen_neto_m3 == round(2/3, 3)
        assert result.area_analizada_m2 == 4
        reversed_result = MotorVolumenes().calcular_entre_superficies(shifted_pr, shifted_ex)
        assert reversed_result.volumen_corte_m3 == result.volumen_terraplen_m3
        assert reversed_result.volumen_terraplen_m3 == result.volumen_corte_m3
        assert reversed_result.volumen_neto_m3 == -result.volumen_neto_m3


def test_numerically_omitted_elevation_is_rejected_instead_of_flattened():
    points = [(0, 0, 0), (1, 0, 0), (1, 1, 0), (0, 1, 0), (1e-15, 1e-15, 1)]
    with pytest.raises(MegalodonException, match="omite|degenerad"):
        MotorVolumenes().calcular_contra_elevacion_referencia(points, 0)


def test_saved_diagonal_is_authoritative_for_nonplanar_square():
    points = [(0, 0, 1), (1, 0, 0), (1, 1, 0), (0, 1, 0)]
    motor = MotorVolumenes()
    first = motor.calcular_contra_elevacion_referencia(points, 0, caras_superficie=[2, 3, 1, 1, 3, 0])
    second = motor.calcular_contra_elevacion_referencia(points, 0, caras_superficie=[0, 1, 2, 0, 2, 3])
    assert first.volumen_corte_m3 == round(1 / 6, 3)
    assert second.volumen_corte_m3 == round(1 / 3, 3)


@pytest.mark.parametrize("faces", [[0, 1], [0, 1, 4], [0, 1, 1], [0, 1, 2.5], [0, 1, 2, 0, 1, 2]])
def test_invalid_saved_faces_fail_instead_of_retriangulating(faces):
    points = [(0, 0, 1), (1, 0, 0), (0, 1, 0)]
    with pytest.raises(MegalodonException):
        MotorVolumenes().calcular_contra_elevacion_referencia(points, 0, caras_superficie=faces)


@pytest.mark.parametrize("points", [
    [(0, 0, 0), (1, 0, None), (0, 1, 0)],
    [(0, 0, 0), (1, 0, float('inf')), (0, 1, 0)],
    [(0, 0, 0), (0, 0, 1), (1, 0, 0), (0, 1, 0)],
    [(0, 0, 0), (1, 0, 0), (1, 1, 0), (0, 1, 0), (1e-15, 1e-15, 1)],
])
def test_saved_tin_generation_never_omits_invalid_elevations(points):
    with pytest.raises(MegalodonException):
        MotorTriangulacion().triangular(points)


@pytest.mark.parametrize('size', [11, 101])
def test_dense_utm_grid_preserves_all_points_and_absolute_height_queries(size):
    for dx, dy in [(0, 0), (500000, 2100000)]:
        points = [(dx + x / 10, dy + y / 10, (x + y) / 10) for x in range(size) for y in range(size)]
        tin = MotorTriangulacion().triangular(points)
        assert tin.estadisticas.num_triangulos == 2 * (size - 1) ** 2
        assert len(set(tin.malla.caras)) == len(points)
        assert float(tin.interpolador(dx + .35, dy + .45)) == pytest.approx(.8, abs=1e-8)
        assert tin.estadisticas.area_plan == pytest.approx(((size - 1) / 10) ** 2)
