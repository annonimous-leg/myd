import math

import pytest

from app.engines.bim.drawing.core import MeshElement, Plane, cut_mesh_with_plane


def test_coplanar_patch_merges_shared_edges_within_tolerance_across_quantization_bins():
    tolerance_m = 1e-6
    # The two triangles form a 2 m x 1 m rectangle. Their shared diagonal
    # represents the same edge, but the duplicated A vertex differs by
    # 0.02 micrometres: below the declared tolerance and across round() bins.
    mesh = MeshElement.from_flat(
        element_id="floor",
        global_id="floor-guid",
        ifc_type="IfcSlab",
        vertices=[
            0.49 * tolerance_m, 0.0, 0.0,  # A
            2.0, 0.0, 0.0,                 # B
            2.0, 1.0, 0.0,                 # C
            0.51 * tolerance_m, 0.0, 0.0,  # A' (within tolerance of A)
            0.0, 1.0, 0.0,                 # D
        ],
        faces=[0, 1, 2, 3, 2, 4],
    )
    plane = Plane.from_origin_normal((0.0, 0.0, 0.0), (0.0, 0.0, 1.0))

    segments = cut_mesh_with_plane(mesh, plane, tolerance_m=tolerance_m)
    total_length = math.fsum(
        math.hypot(
            segment.end[0] - segment.start[0],
            segment.end[1] - segment.start[1],
        )
        for segment in segments
    )

    # A coplanar triangulation seam is not part of the drawing boundary.
    assert len(segments) == 4
    assert total_length == pytest.approx(6.0, abs=1e-6)
