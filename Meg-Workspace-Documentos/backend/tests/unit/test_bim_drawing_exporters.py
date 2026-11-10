import xml.etree.ElementTree as ET

import pytest

from app.engines.bim.drawing.core import DrawingDocument, DrawingSegment
from app.engines.bim.drawing.exporters import to_dxf, to_svg


def sample_document():
    return DrawingDocument(
        kind="PLAN",
        title='Planta "Nivel 1" & revisión',
        units="m",
        segments=(
            DrawingSegment((0.0, 0.0), (2.0, 0.0), "IfcWall", "wall-1", "guid-1"),
            DrawingSegment((2.0, 0.0), (2.0, 1.0), "IfcSlab", "slab-1", "guid-2"),
        ),
        metadata={"model_revision": "revision-1", "visibility_mode": "cut_geometry"},
    )


def test_svg_is_valid_vector_xml_with_physical_size_layers_and_escaped_text():
    svg = to_svg(sample_document())
    root = ET.fromstring(svg)

    assert root.tag.endswith("svg")
    assert root.attrib["viewBox"]
    assert root.attrib["width"].endswith("mm")
    assert root.attrib["height"].endswith("mm")
    assert "Nivel 1" in svg
    assert "&amp;" in svg
    assert 'data-layer="IfcWall"' in svg
    assert root.find(".//{http://www.w3.org/2000/svg}path") is not None


def test_dxf_declares_metre_units_layers_entities_and_eof():
    dxf = to_dxf(sample_document())
    pairs = dxf.decode("ascii").splitlines()

    assert "$INSUNITS" in pairs
    insunits_index = pairs.index("$INSUNITS")
    assert pairs[insunits_index + 2] == "6"
    assert "LAYER" in pairs
    assert "IfcWall" in pairs
    assert "IfcSlab" in pairs
    assert "LINE" in pairs
    assert pairs[-2:] == ["0", "EOF"]


def test_exporters_reject_empty_or_invalid_documents():
    empty = DrawingDocument(kind="PLAN", title="Empty", units="m", segments=(), metadata={})
    with pytest.raises(ValueError, match="empty"):
        to_svg(empty)
    with pytest.raises(ValueError, match="empty"):
        to_dxf(empty)
    invalid = DrawingDocument(
        kind="PLAN",
        title="Invalid",
        units="m",
        segments=(DrawingSegment((0.0, 0.0), (float("nan"), 1.0), "IfcWall", "w", "g"),),
        metadata={},
    )
    with pytest.raises(ValueError, match="finite"):
        to_svg(invalid)


def test_hidden_edges_are_dashed_in_svg_dxf_and_pdf():
    from io import BytesIO

    from pypdf import PdfReader

    from app.engines.bim.drawing.sheet import compose_a3_sheet, composed_to_pdf

    document = DrawingDocument(
        kind="ELEVATION",
        title="Alzado",
        units="m",
        segments=(
            DrawingSegment((0, 0), (2, 0), "IfcWall", "front", "front"),
            DrawingSegment((0, 1), (2, 1), "IfcWall", "rear", "rear", hidden=True),
        ),
        metadata={"view_origin_m": (0, 0, 50), "view_up": (0, 0, 1)},
    )
    svg = ET.fromstring(to_svg(document))
    paths = svg.findall(".//{http://www.w3.org/2000/svg}path")
    assert [path.attrib.get("stroke-dasharray") for path in paths] == ["0.06 0.04", None]

    pairs = to_dxf(document).decode("ascii").splitlines()
    linetypes = pairs[:pairs.index("ENTITIES")]
    entities = pairs[pairs.index("ENTITIES"):]
    assert linetypes.count("MEG_HIDDEN") == entities.count("MEG_HIDDEN") == 1
    assert entities[entities.index("MEG_HIDDEN") - 1] == "6"
    assert entities.count("IfcWall") == 2
    assert "IfcWall_2" not in pairs

    sheet = compose_a3_sheet(document, levels=[("Planta baja", 50.5)])
    linework = [prim for prim in sheet.primitives if prim.layer == "CUT"]
    hidden, visible = linework
    assert hidden.dash and not visible.dash
    assert hidden.weight < visible.weight
    assert all(a > b for a, b in zip(hidden.rgb, visible.rgb))
    assert any(prim.text == "N01 +50.500" for prim in sheet.primitives)
    contents = PdfReader(BytesIO(composed_to_pdf(sheet))).pages[0].get_contents().get_data()
    assert contents.count(b"[3 2] 0 d") == 1


@pytest.mark.parametrize(
    ("extent", "labels"),
    [
        ((280, 245), {"280.00", "245.00"}),
        ((0.02, 0.01), {"0.02", "0.01"}),
        ((0, 22), {"22.00"}),
        ((28, 0), {"28.00"}),
    ],
)
def test_a3_overall_dimensions_fit_above_scale_bar(extent, labels):
    from app.engines.bim.drawing.sheet import compose_a3_sheet

    document = DrawingDocument(
        kind="ELEVATION",
        title="Alzado",
        units="m",
        segments=(DrawingSegment((500, 700), (500 + extent[0], 700 + extent[1]), "IfcWall", "w", "g"),),
    )
    sheet = compose_a3_sheet(document)
    dimensions = [prim for prim in sheet.primitives if prim.layer == "DIM"]
    assert {prim.text for prim in dimensions if prim.kind == "text"} == labels
    for prim in dimensions:
        if prim.kind == "text":
            width = len(prim.text) * prim.size * 0.65
            left = prim.x - width / (2 if prim.anchor == "middle" else 1)
            assert 8 < left < prim.x < 326
            assert 8 < prim.y < 275.8
        else:
            assert all(8 < x < 326 for x in (prim.x1, prim.x2))
            assert all(8 < y < 275.8 for y in (prim.y1, prim.y2))
    assert all(prim.layer != "DIM" for prim in compose_a3_sheet(document, include_overall_dims=False).primitives)
