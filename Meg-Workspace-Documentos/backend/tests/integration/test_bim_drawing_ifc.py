from io import BytesIO
from pathlib import Path

import pytest
from pypdf import PdfReader

from app.engines.bim.drawing.core import (
    MeshElement,
    Plane,
    build_elevation_document,
    build_plan_document,
    build_section_document,
)
from app.engines.bim.drawing.sheet import compose_a3_sheet, composed_to_pdf
from app.engines.bim.motor_bim import MotorBIM


FIXTURES = Path(__file__).parents[1] / "fixtures" / "ifc"


@pytest.mark.parametrize("filename", ["wall_metres.ifc", "wall_millimetres.ifc", "wall_metres_ifc2x3.ifc"])
def test_native_drawing_engine_derives_same_views_from_ifc_unit_variants(filename):
    motor = MotorBIM()
    motor.cargar_ifc(str(FIXTURES / filename))
    extracted = motor.cuantificar(["IfcWall"], extraer_malla=True).elementos
    assert len(extracted) == 1
    element = extracted[0]
    assert element.malla is not None

    mesh = MeshElement.from_flat(
        element_id=element.global_id,
        global_id=element.global_id,
        ifc_type=element.tipo,
        vertices=element.malla.vertices,
        faces=element.malla.caras,
    )
    document = build_plan_document([mesh], elevation_m=1.5)

    points = [point for line in document.segments for point in (line.start, line.end)]
    assert points
    assert min(point[0] for point in points) == pytest.approx(0.0, abs=1e-5)
    assert max(point[0] for point in points) == pytest.approx(2.0, abs=1e-5)
    assert min(point[1] for point in points) == pytest.approx(0.0, abs=1e-5)
    assert max(point[1] for point in points) == pytest.approx(0.4, abs=1e-5)
    sheet = compose_a3_sheet(document)
    assert sheet.bounds_m == pytest.approx((0.0, 0.0, 2.0, 0.4), abs=1e-5)
    pdf = PdfReader(BytesIO(composed_to_pdf(sheet)))
    assert len(pdf.pages) == 1
    assert float(pdf.pages[0].mediabox.width) == pytest.approx(420 * 72 / 25.4, abs=0.01)


    section = build_section_document([mesh], Plane.from_origin_normal((1, 0, 0), (1, 0, 0)))
    elevation = build_elevation_document([mesh], view_direction=(0, -1, 0))
    for view, width_m in ((section, 0.4), (elevation, 2.0)):
        view_sheet = compose_a3_sheet(view)
        left, bottom, right, top = view_sheet.bounds_m
        assert (right - left, top - bottom) == pytest.approx((width_m, 3.0), abs=1e-5)
        view_pdf = PdfReader(BytesIO(composed_to_pdf(view_sheet)))
        assert len(view_pdf.pages) == 1
        assert float(view_pdf.pages[0].mediabox.width) == pytest.approx(420 * 72 / 25.4, abs=0.01)
