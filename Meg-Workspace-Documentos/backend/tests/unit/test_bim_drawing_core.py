import math

import pytest

from app.engines.bim.drawing.core import (
    MeshElement,
    Plane,
    build_elevation_document,
    build_plan_document,
    build_section_document,
    cut_mesh_with_plane,
)


def cube_mesh(element_id="element-1"):
    vertices = [
        0, 0, 0,  2, 0, 0,  2, 1, 0,  0, 1, 0,
        0, 0, 3,  2, 0, 3,  2, 1, 3,  0, 1, 3,
    ]
    faces = [
        0, 2, 1, 0, 3, 2,
        4, 5, 6, 4, 6, 7,
        0, 1, 5, 0, 5, 4,
        1, 2, 6, 1, 6, 5,
        2, 3, 7, 2, 7, 6,
        3, 0, 4, 3, 4, 7,
    ]
    return MeshElement.from_flat(
        element_id=element_id,
        global_id=f"guid-{element_id}",
        ifc_type="IfcWall",
        vertices=vertices,
        faces=faces,
    )


def bounds(document):
    points = [point for line in document.segments for point in (line.start, line.end)]
    return (
        min(point[0] for point in points),
        min(point[1] for point in points),
        max(point[0] for point in points),
        max(point[1] for point in points),
    )


def total_length(document):
    return math.fsum(
        math.hypot(line.end[0] - line.start[0], line.end[1] - line.start[1])
        for line in document.segments
    )


def test_horizontal_plan_cut_uses_world_metre_coordinates():
    document = build_plan_document([cube_mesh()], elevation_m=1.5)

    assert document.kind == "PLAN"
    assert bounds(document) == pytest.approx((0, 0, 2, 1))
    assert total_length(document) == pytest.approx(6.0)
    assert all(line.layer == "IfcWall" for line in document.segments)


def test_vertical_section_projects_to_local_view_axes():
    mesh = cube_mesh()
    plane = Plane.from_origin_normal((1, 0, 0), (1, 0, 0))
    document = build_section_document([mesh], plane, title="Section A-A")

    assert document.kind == "SECTION"
    assert bounds(document) == pytest.approx((0, 0, 1, 3))
    assert total_length(document) == pytest.approx(8.0)


def test_cut_through_existing_mesh_vertices_has_no_zero_length_or_duplicate_lines():
    mesh = cube_mesh()
    plane = Plane.from_origin_normal((0, 0, 0), (0, 0, 1))
    segments = cut_mesh_with_plane(mesh, plane)

    assert segments
    assert all(math.hypot(s.end[0] - s.start[0], s.end[1] - s.start[1]) > 1e-6 for s in segments)
    keys = {
        (tuple(round(v, 6) for v in s.start), tuple(round(v, 6) for v in s.end))
        for s in segments
    }
    assert len(keys) == len(segments)


def test_coplanar_adjacent_triangles_emit_only_outer_boundary():
    mesh = MeshElement.from_flat(
        element_id="floor",
        global_id="floor-guid",
        ifc_type="IfcSlab",
        vertices=[0, 0, 0, 2, 0, 0, 2, 1, 0, 0, 1, 0],
        faces=[0, 1, 2, 0, 2, 3],
    )
    plane = Plane.from_origin_normal((0, 0, 0), (0, 0, 1))

    segments = cut_mesh_with_plane(mesh, plane)

    assert math.fsum(math.hypot(s.end[0] - s.start[0], s.end[1] - s.start[1]) for s in segments) == pytest.approx(6.0)
    assert len(segments) == 4


@pytest.mark.parametrize(
    "vertices, faces, message",
    [
        ([0, 0, 0, 1, 0, 0, 0, 1, float("nan")], [0, 1, 2], "finite"),
        ([0, 0, 0, 1, 0], [0, 1, 2], "multiple of three"),
        ([0, 0, 0, 1, 0, 0, 0, 1, 0], [0, 1], "multiple of three"),
        ([0, 0, 0, 1, 0, 0, 0, 1, 0], [0, 1, 3], "index"),
        ([0, 0, 0, 1, 0, 0, 2, 0, 0], [0, 1, 2], "degenerate"),
    ],
)
def test_mesh_validation_rejects_invalid_geometry(vertices, faces, message):
    with pytest.raises(ValueError, match=message):
        MeshElement.from_flat(
            element_id="bad",
            global_id="bad-guid",
            ifc_type="IfcWall",
            vertices=vertices,
            faces=faces,
        )


def test_plane_rejects_zero_or_non_finite_normal():
    with pytest.raises(ValueError, match="normal"):
        Plane.from_origin_normal((0, 0, 0), (0, 0, 0))
    with pytest.raises(ValueError, match="finite"):
        Plane.from_origin_normal((0, 0, 0), (float("inf"), 0, 1))


def test_elevation_outputs_visible_cube_outline():
    document = build_elevation_document([cube_mesh()], view_direction=(0, -1, 0))

    assert document.kind == "ELEVATION"
    assert document.metadata["visibility_mode"] == "occlusion_clipped_mesh_edges"
    assert bounds(document) == pytest.approx((0, 0, 2, 3))
    assert total_length(document) == pytest.approx(10.0)


def test_plan_result_is_deterministic_for_element_input_order():
    first = cube_mesh("a")
    second = cube_mesh("b")
    forward = build_plan_document([first, second], elevation_m=1.5)
    reversed_order = build_plan_document([second, first], elevation_m=1.5)

    assert forward == reversed_order


def test_section_rejects_non_vertical_cut_plane():
    with pytest.raises(ValueError, match="vertical"):
        build_section_document(
            [cube_mesh()],
            Plane.from_origin_normal((0, 0, 0), (0, 1, 1)),
        )


def _elevation_panel(element_id, left, right, bottom, top, y):
    return MeshElement.from_flat(
        element_id=element_id,
        global_id=element_id,
        ifc_type="IfcPlate",
        vertices=[left, y, bottom, right, y, bottom, right, y, top, left, y, top],
        faces=[0, 1, 2, 0, 2, 3],
    )


def test_elevation_clips_a_rear_edge_at_the_foreground_silhouette():
    rear = _elevation_panel("rear", 0, 6, 0, 3, 1)
    front = _elevation_panel("front", 2, 4, -1, 2, 0)
    document = build_elevation_document([rear, front], view_direction=(0, -1, 0))
    rear_floor = [
        (line.start, line.end) for line in document.segments
        if line.element_id == "rear" and line.start[1] == line.end[1] == 0
    ]

    assert rear_floor == [((0, 0), (2, 0)), ((4, 0), (6, 0))]
    assert build_elevation_document([front, rear], view_direction=(0, -1, 0)) == document


@pytest.mark.parametrize("depth, rear_visible", [(0, False), (1, True), (1 - 0.5e-6, True)])
def test_elevation_distinguishes_occluded_and_coincident_panels(depth, rear_visible):
    rear = _elevation_panel("rear", 0, 6, 0, 3, 1)
    front = _elevation_panel("front", -1, 7, -1, 4, depth)

    document = build_elevation_document([rear, front], view_direction=(0, -1, 0))

    assert sum(line.element_id == "rear" for line in document.segments) == (4 if rear_visible else 0)
    assert sum(line.element_id == "front" for line in document.segments) == 4


def _folded_panel(fold_depth):
    return MeshElement.from_flat(
        element_id="folded",
        global_id="folded",
        ifc_type="IfcPlate",
        vertices=[0, 0, 0, 1, -fold_depth, 0, 2, 0, 0,
                  0, 0, 2, 1, -fold_depth, 2, 2, 0, 2],
        faces=[0, 1, 4, 0, 4, 3, 1, 2, 5, 1, 5, 4],
    )


@pytest.mark.parametrize("fold_depth, visible_crease", [(0.5, True), (0.001, False)])
def test_elevation_draws_front_facing_folds_but_omits_nearly_flat_seams(fold_depth, visible_crease):
    document = build_elevation_document([_folded_panel(fold_depth)], view_direction=(0, -1, 0))

    assert any(line.start == (1, 0) and line.end == (1, 2) for line in document.segments) is visible_crease
    assert len(document.segments) == (7 if visible_crease else 6)



def test_elevation_clips_a_crease_behind_another_element():
    foreground = _elevation_panel("front", 0.5, 1.5, 0.5, 1.5, -1)
    document = build_elevation_document([_folded_panel(0.5), foreground], view_direction=(0, -1, 0))

    crease = [
        (line.start, line.end) for line in document.segments
        if line.element_id == "folded" and line.start[0] == line.end[0] == 1
    ]
    assert crease == [((1, 0), (1, 0.5)), ((1, 1.5), (1, 2))]


def test_elevation_classifies_hidden_intervals_when_requested():
    rear = _elevation_panel("rear", 0, 6, 0, 3, 1)
    left = _elevation_panel("left", 2, 3.5, -1, 2, 0)
    right = _elevation_panel("right", 3, 4, -1, 2, 0)
    document = build_elevation_document([rear, left, right], view_direction=(0, -1, 0), include_hidden=True)
    rear_floor = [
        (line.start, line.end, line.hidden) for line in document.segments
        if line.element_id == "rear" and line.start[1] == line.end[1] == 0
    ]

    assert document.metadata["visibility_mode"] == "mesh_edges_with_hidden_lines"
    assert rear_floor == [((0, 0), (2, 0), False), ((2, 0), (4, 0), True), ((4, 0), (6, 0), False)]
