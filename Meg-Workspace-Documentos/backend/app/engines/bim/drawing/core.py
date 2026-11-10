"""Independent geometric core for IFC-derived technical linework.

The module consumes normalized triangle meshes in metres. It deliberately
has no IFC, CAD, rendering, or network imports; format adapters feed it
geometry and exporters consume its deterministic 2D drawing documents.
"""
from __future__ import annotations

from collections import Counter
from dataclasses import dataclass, field
import math
from typing import Iterable, Mapping, Sequence

from app.engines.bim.drawing.occlusion import OcclusionIndex

Vec2 = tuple[float, float]
Vec3 = tuple[float, float, float]

DEFAULT_TOLERANCE_M = 1e-6
_TRIANGLE_AREA_EPSILON_SQUARED = 1e-24
_DIRECTION_EPSILON = 1e-10


def _finite_vec3(values: Sequence[float], label: str) -> Vec3:
    if len(values) != 3:
        raise ValueError(f"{label} must contain exactly three coordinates")
    vector = (float(values[0]), float(values[1]), float(values[2]))
    if not all(math.isfinite(value) for value in vector):
        raise ValueError(f"{label} coordinates must be finite")
    return vector


def _sub(a: Vec3, b: Vec3) -> Vec3:
    return (a[0] - b[0], a[1] - b[1], a[2] - b[2])


def _dot(a: Vec3, b: Vec3) -> float:
    return a[0] * b[0] + a[1] * b[1] + a[2] * b[2]


def _cross(a: Vec3, b: Vec3) -> Vec3:
    return (
        a[1] * b[2] - a[2] * b[1],
        a[2] * b[0] - a[0] * b[2],
        a[0] * b[1] - a[1] * b[0],
    )


def _norm(vector: Vec3) -> float:
    return math.sqrt(_dot(vector, vector))


def _normalize(vector: Vec3, label: str) -> Vec3:
    magnitude = _norm(vector)
    if not math.isfinite(magnitude) or magnitude <= 1e-15:
        raise ValueError(f"{label} must be finite and non-zero")
    return (vector[0] / magnitude, vector[1] / magnitude, vector[2] / magnitude)


def _validate_tolerance(tolerance_m: float) -> float:
    tolerance = float(tolerance_m)
    if not math.isfinite(tolerance) or tolerance <= 0:
        raise ValueError("tolerance_m must be finite and greater than zero")
    return tolerance


def _canonical_vertex_keys(
    vertices: Sequence[Vec3], tolerance_m: float
) -> tuple[Vec3, ...]:
    """Map coincident mesh vertices to deterministic tolerance-aware keys.

    Rounded grid coordinates are not a valid equivalence test: two points
    much closer than the tolerance can fall on opposite sides of a grid
    boundary. Search adjacent spatial cells and compare actual distances.
    Representatives are deterministic and clusters never grow beyond the
    declared tolerance from their representative.
    """
    tolerance = _validate_tolerance(tolerance_m)
    tolerance_squared = tolerance * tolerance
    cell_type = tuple[int, int, int]
    buckets: dict[cell_type, list[tuple[Vec3, Vec3]]] = {}
    representatives: dict[Vec3, Vec3] = {}

    for point in sorted(set(vertices)):
        cell = tuple(math.floor(value / tolerance) for value in point)
        candidates: list[tuple[float, Vec3]] = []
        for dx in (-1, 0, 1):
            for dy in (-1, 0, 1):
                for dz in (-1, 0, 1):
                    neighbor = (cell[0] + dx, cell[1] + dy, cell[2] + dz)
                    for existing, representative in buckets.get(neighbor, ()):
                        delta_existing = _sub(point, existing)
                        delta_representative = _sub(point, representative)
                        distance_squared = _dot(delta_existing, delta_existing)
                        representative_distance_squared = _dot(
                            delta_representative, delta_representative
                        )
                        if (
                            distance_squared <= tolerance_squared
                            and representative_distance_squared <= tolerance_squared
                        ):
                            candidates.append((distance_squared, representative))

        representative = (
            min(candidates, key=lambda candidate: (candidate[0], candidate[1]))[1]
            if candidates
            else point
        )
        representatives[point] = representative
        buckets.setdefault(cell, []).append((point, representative))

    return tuple(representatives[point] for point in vertices)


def _point2_key(point: Vec2, tolerance_m: float) -> tuple[int, int]:
    return (round(point[0] / tolerance_m), round(point[1] / tolerance_m))


@dataclass(frozen=True, slots=True)
class MeshElement:
    """One IFC element represented by a local indexed triangle mesh in metres."""

    element_id: str
    global_id: str
    ifc_type: str
    vertices: tuple[Vec3, ...]
    triangles: tuple[tuple[int, int, int], ...]

    @classmethod
    def from_flat(
        cls,
        *,
        element_id: str,
        global_id: str,
        ifc_type: str,
        vertices: Sequence[float],
        faces: Sequence[int],
    ) -> MeshElement:
        if not element_id or not global_id or not ifc_type:
            raise ValueError("element_id, global_id and ifc_type are required")
        if len(vertices) < 9 or len(vertices) % 3:
            raise ValueError("vertices length must be a multiple of three and contain at least three points")
        if len(faces) < 3 or len(faces) % 3:
            raise ValueError("faces length must be a multiple of three")

        coordinates = tuple(float(value) for value in vertices)
        if not all(math.isfinite(value) for value in coordinates):
            raise ValueError("mesh coordinates must be finite")
        points: tuple[Vec3, ...] = tuple(
            (coordinates[index], coordinates[index + 1], coordinates[index + 2])
            for index in range(0, len(coordinates), 3)
        )

        indices: list[int] = []
        for raw_index in faces:
            if isinstance(raw_index, bool):
                raise ValueError("face index must be an integer index")
            index = int(raw_index)
            if index != raw_index:
                raise ValueError("face index must be an integer index")
            if index < 0 or index >= len(points):
                raise ValueError(f"face index {index} is outside the vertex array")
            indices.append(index)

        triangles: list[tuple[int, int, int]] = []
        for offset in range(0, len(indices), 3):
            a, b, c = indices[offset : offset + 3]
            if len({a, b, c}) != 3:
                raise ValueError("degenerate triangle contains repeated vertex indices")
            cross = _cross(_sub(points[b], points[a]), _sub(points[c], points[a]))
            if _dot(cross, cross) <= _TRIANGLE_AREA_EPSILON_SQUARED:
                raise ValueError("degenerate triangle has zero or negligible area")
            triangles.append((a, b, c))

        return cls(
            element_id=str(element_id),
            global_id=str(global_id),
            ifc_type=str(ifc_type),
            vertices=points,
            triangles=tuple(triangles),
        )


@dataclass(frozen=True, slots=True)
class Plane:
    """Plane in world coordinates; the normal is normalized on construction."""

    origin: Vec3
    normal: Vec3

    def __post_init__(self) -> None:
        object.__setattr__(self, "origin", _finite_vec3(self.origin, "plane origin"))
        normal = _finite_vec3(self.normal, "plane normal")
        object.__setattr__(self, "normal", _normalize(normal, "plane normal"))

    @classmethod
    def from_origin_normal(
        cls, origin: Sequence[float], normal: Sequence[float]
    ) -> Plane:
        return cls(
            origin=_finite_vec3(origin, "plane origin"),
            normal=_finite_vec3(normal, "plane normal"),
        )

    def signed_distance(self, point: Vec3) -> float:
        return _dot(_sub(point, self.origin), self.normal)


@dataclass(frozen=True, slots=True)
class ViewFrame:
    """Orthonormal 2D drawing frame attached to a world-space plane."""

    origin: Vec3
    right: Vec3
    up: Vec3
    normal: Vec3

    @classmethod
    def from_plane(cls, plane: Plane) -> ViewFrame:
        # For horizontal plans, world Y is the vertical-on-sheet axis.
        # For vertical sections/elevations, world Z remains vertical.
        if abs(plane.normal[2]) >= 0.999999:
            up_hint: Vec3 = (0.0, 1.0, 0.0)
        else:
            up_hint = (0.0, 0.0, 1.0)
        right = _normalize(_cross(up_hint, plane.normal), "view right axis")
        up = _normalize(_cross(plane.normal, right), "view up axis")
        return cls(plane.origin, right, up, plane.normal)

    def project(self, point: Vec3) -> Vec2:
        relative = _sub(point, self.origin)
        return (_dot(relative, self.right), _dot(relative, self.up))


@dataclass(frozen=True, slots=True)
class DrawingSegment:
    start: Vec2
    end: Vec2
    layer: str
    element_id: str
    global_id: str


@dataclass(frozen=True, slots=True)
class DrawingDocument:
    kind: str
    title: str
    units: str
    segments: tuple[DrawingSegment, ...]
    metadata: Mapping[str, object] = field(default_factory=dict)


def _farthest_pair(points: Sequence[Vec3]) -> tuple[Vec3, Vec3]:
    best_pair = (points[0], points[1])
    best_distance = -1.0
    for index, first in enumerate(points):
        for second in points[index + 1 :]:
            delta = _sub(first, second)
            distance = _dot(delta, delta)
            if distance > best_distance:
                best_distance = distance
                best_pair = (first, second)
    return best_pair


def _unique_points(points: Iterable[Vec3], tolerance_m: float) -> list[Vec3]:
    result: list[Vec3] = []
    for point in points:
        if not any(_norm(_sub(point, existing)) <= tolerance_m for existing in result):
            result.append(point)
    return result


def _project_segment(
    first: Vec3,
    second: Vec3,
    frame: ViewFrame,
    mesh: MeshElement,
    tolerance_m: float,
) -> DrawingSegment | None:
    start = frame.project(first)
    end = frame.project(second)
    length = math.hypot(end[0] - start[0], end[1] - start[1])
    if not math.isfinite(length) or length <= tolerance_m:
        return None
    if end < start:
        start, end = end, start
    return DrawingSegment(start, end, mesh.ifc_type, mesh.element_id, mesh.global_id)


def _deduplicate_segments(
    segments: Iterable[DrawingSegment], tolerance_m: float
) -> tuple[DrawingSegment, ...]:
    unique: dict[tuple[object, ...], DrawingSegment] = {}
    for segment in segments:
        start_key = _point2_key(segment.start, tolerance_m)
        end_key = _point2_key(segment.end, tolerance_m)
        first, second = sorted((start_key, end_key))
        key = (segment.layer, segment.element_id, first, second)
        unique.setdefault(key, segment)
    return tuple(
        unique[key]
        for key in sorted(unique, key=lambda value: (str(value[0]), str(value[1]), value[2], value[3]))
    )


def cut_mesh_with_plane(
    mesh: MeshElement,
    plane: Plane,
    *,
    tolerance_m: float = DEFAULT_TOLERANCE_M,
) -> tuple[DrawingSegment, ...]:
    """Intersect one indexed mesh with a plane and return 2D cut linework.

    Coplanar faces are processed as a patch: shared triangulation edges are
    removed, while the patch boundary is retained. Duplicate intersections
    on shared triangle edges are collapsed at the configured metre tolerance.
    """
    tolerance = _validate_tolerance(tolerance_m)
    vertex_keys = _canonical_vertex_keys(mesh.vertices, tolerance)
    raw_segments: list[tuple[Vec3, Vec3]] = []
    coplanar_edge_counts: Counter[tuple[Vec3, Vec3]] = Counter()
    coplanar_edge_points: dict[tuple[Vec3, Vec3], tuple[Vec3, Vec3]] = {}

    for triangle in mesh.triangles:
        points = [mesh.vertices[index] for index in triangle]
        distances = [plane.signed_distance(point) for point in points]
        on_plane = [abs(distance) <= tolerance for distance in distances]

        if all(on_plane):
            for edge_index in range(3):
                first = points[edge_index]
                second = points[(edge_index + 1) % 3]
                first_key = vertex_keys[triangle[edge_index]]
                second_key = vertex_keys[triangle[(edge_index + 1) % 3]]
                if second_key < first_key:
                    first_key, second_key = second_key, first_key
                    first, second = second, first
                edge_key = (first_key, second_key)
                coplanar_edge_counts[edge_key] += 1
                coplanar_edge_points.setdefault(edge_key, (first, second))
            continue

        intersections: list[Vec3] = []
        for edge_index in range(3):
            first = points[edge_index]
            second = points[(edge_index + 1) % 3]
            distance_first = distances[edge_index]
            distance_second = distances[(edge_index + 1) % 3]
            first_on = on_plane[edge_index]
            second_on = on_plane[(edge_index + 1) % 3]

            if first_on and second_on:
                intersections.extend((first, second))
            elif first_on:
                intersections.append(first)
            elif second_on:
                intersections.append(second)
            elif (distance_first < 0 < distance_second) or (
                distance_second < 0 < distance_first
            ):
                denominator = distance_first - distance_second
                if abs(denominator) > 0:
                    ratio = distance_first / denominator
                    intersections.append(
                        (
                            first[0] + ratio * (second[0] - first[0]),
                            first[1] + ratio * (second[1] - first[1]),
                            first[2] + ratio * (second[2] - first[2]),
                        )
                    )

        unique_points = _unique_points(intersections, tolerance)
        if len(unique_points) >= 2:
            raw_segments.append(_farthest_pair(unique_points))

    for edge_key, count in coplanar_edge_counts.items():
        if count == 1:
            raw_segments.append(coplanar_edge_points[edge_key])

    frame = ViewFrame.from_plane(plane)
    projected = (
        segment
        for first, second in raw_segments
        if (segment := _project_segment(first, second, frame, mesh, tolerance)) is not None
    )
    return _deduplicate_segments(projected, tolerance)


def _make_cut_document(
    elements: Iterable[MeshElement],
    plane: Plane,
    *,
    kind: str,
    title: str,
    tolerance_m: float,
) -> DrawingDocument:
    tolerance = _validate_tolerance(tolerance_m)
    frame = ViewFrame.from_plane(plane)
    lines = []
    for mesh in sorted(elements, key=lambda element: (element.ifc_type, element.global_id, element.element_id)):
        lines.extend(cut_mesh_with_plane(mesh, plane, tolerance_m=tolerance))
    segments = _deduplicate_segments(lines, tolerance)
    return DrawingDocument(
        kind=kind,
        title=title,
        units="m",
        segments=segments,
        metadata={
            "coordinate_units": "m",
            "plane_origin_m": plane.origin,
            "plane_normal": plane.normal,
            "view_right": frame.right,
            "view_up": frame.up,
            "tolerance_m": tolerance,
            "visibility_mode": "cut_geometry_only",
            "engine": "megalodon-vector-drawing",
            "engine_version": "0.1.0",
        },
    )


def build_plan_document(
    elements: Iterable[MeshElement],
    *,
    elevation_m: float,
    title: str = "Planta",
    tolerance_m: float = DEFAULT_TOLERANCE_M,
) -> DrawingDocument:
    elevation = float(elevation_m)
    if not math.isfinite(elevation):
        raise ValueError("elevation_m must be finite")
    plane = Plane.from_origin_normal((0.0, 0.0, elevation), (0.0, 0.0, 1.0))
    return _make_cut_document(
        elements, plane, kind="PLAN", title=title, tolerance_m=tolerance_m
    )


def build_section_document(
    elements: Iterable[MeshElement],
    plane: Plane,
    *,
    title: str = "Sección",
    tolerance_m: float = DEFAULT_TOLERANCE_M,
) -> DrawingDocument:
    if abs(plane.normal[2]) > 1e-6:
        raise ValueError("section plane must be vertical (horizontal normal)")
    return _make_cut_document(
        elements, plane, kind="SECTION", title=title, tolerance_m=tolerance_m
    )


def build_elevation_document(
    elements: Iterable[MeshElement],
    *,
    view_direction: Sequence[float],
    origin: Sequence[float] = (0.0, 0.0, 0.0),
    title: str = "Alzado",
    tolerance_m: float = DEFAULT_TOLERANCE_M,
) -> DrawingDocument:
    """Project silhouette edges and clip portions behind the mesh surfaces.

    The view direction points toward the observer. The candidates remain
    silhouette and boundary edges of the triangulated input.
    """
    tolerance = _validate_tolerance(tolerance_m)
    direction = _normalize(_finite_vec3(view_direction, "view direction"), "view direction")
    plane = Plane.from_origin_normal(origin, direction)
    frame = ViewFrame.from_plane(plane)
    meshes = sorted(elements, key=lambda element: (element.ifc_type, element.global_id, element.element_id))
    projected: list[DrawingSegment] = []

    def with_depth(point: Vec3) -> Vec3:
        return (*frame.project(point), plane.signed_distance(point))

    projected_meshes = [
        (mesh, {vertex: with_depth(vertex) for vertex in mesh.vertices})
        for mesh in meshes
    ]
    occlusion = OcclusionIndex.build(
        (
            (vertices[mesh.vertices[a]], vertices[mesh.vertices[b]], vertices[mesh.vertices[c]])
            for mesh, vertices in projected_meshes
            for a, b, c in mesh.triangles
        ),
        tolerance,
    )
    for mesh, vertices in projected_meshes:
        vertex_keys = _canonical_vertex_keys(mesh.vertices, tolerance)
        edges: dict[tuple[Vec3, Vec3], list[float]] = {}
        for triangle in mesh.triangles:
            a, b, c = (mesh.vertices[index] for index in triangle)
            normal = _cross(_sub(b, a), _sub(c, a))
            normal_length = _norm(normal)
            if normal_length <= 0:
                continue
            facing = _dot(normal, direction) / normal_length
            for edge_index in range(3):
                first = vertex_keys[triangle[edge_index]]
                second = vertex_keys[triangle[(edge_index + 1) % 3]]
                if second < first:
                    first, second = second, first
                edges.setdefault((first, second), []).append(facing)

        for (first, second), facings in edges.items():
            toward = any(value > _DIRECTION_EPSILON for value in facings)
            away = any(value < -_DIRECTION_EPSILON for value in facings)
            edge_on = any(abs(value) <= _DIRECTION_EPSILON for value in facings)
            boundary = len(facings) == 1
            is_silhouette = (boundary and toward) or (toward and (away or edge_on))
            if is_silhouette:
                start, end = vertices[first], vertices[second]
                dx, dy = end[0] - start[0], end[1] - start[1]
                length = math.hypot(dx, dy)
                if not math.isfinite(length) or length <= tolerance:
                    continue
                intervals = occlusion.visible_intervals(start, end, tolerance) if occlusion else ((0.0, 1.0),)
                for low, high in intervals:
                    a = start[:2] if low == 0.0 else (start[0] + dx * low, start[1] + dy * low)
                    b = end[:2] if high == 1.0 else (start[0] + dx * high, start[1] + dy * high)
                    if b < a:
                        a, b = b, a
                    projected.append(DrawingSegment(a, b, mesh.ifc_type, mesh.element_id, mesh.global_id))

    segments = _deduplicate_segments(projected, tolerance)
    return DrawingDocument(
        kind="ELEVATION",
        title=title,
        units="m",
        segments=segments,
        metadata={
            "coordinate_units": "m",
            "view_direction": direction,
            "view_origin_m": frame.origin,
            "tolerance_m": tolerance,
            "visibility_mode": "occlusion_clipped_mesh_silhouette",
            "engine": "megalodon-vector-drawing",
            "engine_version": "0.2.0",
        },
    )
