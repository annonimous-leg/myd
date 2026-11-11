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


def test_ifc_wall_with_3d_axis_retains_world_space_body_mesh(tmp_path):
    source = (FIXTURES / "wall_metres.ifc").read_text()
    source = source.replace("(#22));", "(#32,#22));")
    source = source.replace("#24=IFCCARTESIANPOINT((0.,0.,0.));", "#24=IFCCARTESIANPOINT((10.,20.,30.));")
    source = source.replace(
        "ENDSEC;\nEND-ISO",
        "#29=IFCGEOMETRICREPRESENTATIONSUBCONTEXT('Axis','Model',*,*,*,*,#10,$,.GRAPH_VIEW.,$);\n"
        "#30=IFCCARTESIANPOINTLIST3D(((0.,0.,0.),(2.,0.,0.)));\n"
        "#31=IFCINDEXEDPOLYCURVE(#30,$,.F.);\n"
        "#32=IFCSHAPEREPRESENTATION(#29,'Axis','Curve3D',(#31));\n"
        "ENDSEC;\nEND-ISO",
    )
    path = tmp_path / "wall-axis-and-body.ifc"
    path.write_text(source)
    motor = MotorBIM()
    motor.cargar_ifc(str(path))
    wall, = motor.cuantificar(["IfcWall"], extraer_malla=True).elementos
    assert wall.malla is not None
    assert wall.bbox == pytest.approx([10, 20, 30, 12, 20.4, 33])
    assert wall.volumen == pytest.approx(2.4)


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


@pytest.mark.parametrize("missing_child", [False, True])
def test_aggregate_mesh_uses_world_children_without_inventing_parent_quantity(tmp_path, missing_child):
    import ifcopenshell
    import ifcopenshell.guid

    model = ifcopenshell.open(str(FIXTURES / "wall_metres.ifc"))
    wall, = model.by_type("IfcWall")
    # The child's world placement already includes the parent placement.
    parent_location = model.create_entity("IfcCartesianPoint", Coordinates=(10., 20., 30.))
    parent_axis = model.create_entity("IfcAxis2Placement3D", Location=parent_location)
    parent_placement = model.create_entity("IfcLocalPlacement", RelativePlacement=parent_axis)
    wall.ObjectPlacement.PlacementRelTo = parent_placement
    roof = model.create_entity(
        "IfcRoof", GlobalId=ifcopenshell.guid.new(), Name="Aggregate roof",
        ObjectPlacement=parent_placement,
    )
    second_location = model.create_entity("IfcCartesianPoint", Coordinates=(3., 0., 0.))
    second_axis = model.create_entity("IfcAxis2Placement3D", Location=second_location)
    second_placement = model.create_entity(
        "IfcLocalPlacement", PlacementRelTo=parent_placement, RelativePlacement=second_axis,
    )
    second_wall = model.create_entity(
        "IfcWall", GlobalId=ifcopenshell.guid.new(), ObjectPlacement=second_placement,
        Representation=wall.Representation,
    )
    children = [wall, second_wall]
    if missing_child:
        children.append(model.create_entity("IfcWall", GlobalId=ifcopenshell.guid.new()))
    model.create_entity("IfcRelAggregates", GlobalId=ifcopenshell.guid.new(),
                        RelatingObject=roof, RelatedObjects=children)
    path = tmp_path / "aggregate.ifc"
    model.write(str(path))

    motor = MotorBIM()
    motor.cargar_ifc(str(path))
    aggregate, = motor.cuantificar(["IfcRoof"], extraer_malla=True).elementos
    assert aggregate.volumen is None
    assert aggregate.fuente_volumen == "NO_DISPONIBLE"
    if missing_child:
        assert aggregate.malla is None
        assert "_error_geometria" in aggregate.propiedades
    else:
        assert aggregate.bbox == pytest.approx([10, 20, 30, 15, 20.4, 33])
        assert aggregate.propiedades["_componentes_geometria"] == [wall.GlobalId, second_wall.GlobalId]
        assert max(aggregate.malla.caras) < len(aggregate.malla.vertices) // 3
        mesh = MeshElement.from_flat(
            element_id=aggregate.global_id, global_id=aggregate.global_id,
            ifc_type=aggregate.tipo, vertices=aggregate.malla.vertices, faces=aggregate.malla.caras,
        )
        plan = build_plan_document([mesh], elevation_m=31.5)
        assert plan.segments
        assert len(PdfReader(BytesIO(composed_to_pdf(compose_a3_sheet(plan)))).pages) == 1
