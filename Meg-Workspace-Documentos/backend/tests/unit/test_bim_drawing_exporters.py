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

    sheet = compose_a3_sheet(document)
    contents = PdfReader(BytesIO(composed_to_pdf(sheet))).pages[0].get_contents().get_data()
    assert contents.count(b"[3 2] 0 d") == 1
