"""Clip projected mesh edges against nearer projected triangles."""

from __future__ import annotations

from dataclasses import dataclass
from math import hypot
from typing import Iterable

Point = tuple[float, float, float]  # projected x, y and depth toward the observer
Bounds = tuple[float, float, float, float]


def _side(a: Point, b: Point, point: Point) -> float:
    return (b[0] - a[0]) * (point[1] - a[1]) - (b[1] - a[1]) * (point[0] - a[0])


def _bounds(points: tuple[Point, ...]) -> Bounds:
    x, y, _ = zip(*points)
    return min(x), min(y), max(x), max(y)


def _overlaps(a: Bounds, b: Bounds) -> bool:
    return a[0] <= b[2] and b[0] <= a[2] and a[1] <= b[3] and b[1] <= a[3]


@dataclass(frozen=True, slots=True)
class _Triangle:
    points: tuple[Point, Point, Point]
    area: float
    bounds: Bounds

    def hidden_interval(
        self, start: Point, end: Point, tolerance: float
    ) -> tuple[float, float] | None:
        a, b, c = self.points
        weights_start = (_side(b, c, start), _side(c, a, start), _side(a, b, start))
        weights_end = (_side(b, c, end), _side(c, a, end), _side(a, b, end))
        depth_start = sum(weight * (p[2] - start[2]) for weight, p in zip(weights_start, self.points))
        depth_end = sum(weight * (p[2] - end[2]) for weight, p in zip(weights_end, self.points))
        minimum_depth = tolerance * self.area
        if max(depth_start, depth_end) <= minimum_depth:
            return None

        # The three triangle half planes and the depth difference are all
        # linear along the edge, so each clips the same parameter interval.
        low, high = 0.0, 1.0
        for first, last in zip(
            (*weights_start, depth_start - minimum_depth),
            (*weights_end, depth_end - minimum_depth),
        ):
            if first < 0 and last < 0:
                return None
            if first < 0:
                low = max(low, first / (first - last))
            elif last < 0:
                high = min(high, first / (first - last))
            if low >= high:
                return None
        return low, high


@dataclass(frozen=True, slots=True)
class OcclusionIndex:
    bounds: Bounds
    max_depth: float
    triangles: tuple[_Triangle, ...] = ()
    children: tuple[OcclusionIndex, ...] = ()

    @classmethod
    def build(
        cls, faces: Iterable[tuple[Point, Point, Point]], tolerance: float
    ) -> OcclusionIndex | None:
        triangles = []
        for a, b, c in faces:
            area = _side(a, b, c)
            longest = max(hypot(p[0] - q[0], p[1] - q[1]) for p, q in ((a, b), (b, c), (c, a)))
            if abs(area) <= tolerance * longest:
                continue
            points = (a, b, c) if area > 0 else (a, c, b)
            triangles.append(_Triangle(points, abs(area), _bounds(points)))
        return cls._partition(triangles) if triangles else None

    @classmethod
    def _partition(cls, triangles: list[_Triangle]) -> OcclusionIndex:
        bounds = (
            min(t.bounds[0] for t in triangles), min(t.bounds[1] for t in triangles),
            max(t.bounds[2] for t in triangles), max(t.bounds[3] for t in triangles),
        )
        if len(triangles) <= 8:
            return cls(bounds, max(p[2] for t in triangles for p in t.points), tuple(triangles))
        axis = int(bounds[3] - bounds[1] > bounds[2] - bounds[0])
        triangles.sort(key=lambda t: t.bounds[axis] + t.bounds[axis + 2])
        middle = len(triangles) // 2
        children = (cls._partition(triangles[:middle]), cls._partition(triangles[middle:]))
        return cls(bounds, max(child.max_depth for child in children), children=children)

    def _candidates(self, bounds: Bounds, depth: float) -> Iterable[_Triangle]:
        if self.max_depth <= depth or not _overlaps(self.bounds, bounds):
            return
        yield from (triangle for triangle in self.triangles if _overlaps(triangle.bounds, bounds))
        for child in self.children:
            yield from child._candidates(bounds, depth)

    def visible_intervals(
        self, start: Point, end: Point, tolerance: float
    ) -> Iterable[tuple[float, float]]:
        hidden = []
        for triangle in self._candidates(_bounds((start, end)), min(start[2], end[2]) + tolerance):
            interval = triangle.hidden_interval(start, end, tolerance)
            if interval is not None:
                hidden.append(interval)
                if interval == (0.0, 1.0):
                    return
        cursor = 0.0
        parameter_tolerance = tolerance / hypot(end[0] - start[0], end[1] - start[1])
        for low, high in sorted(hidden):
            if low > cursor + parameter_tolerance:
                yield cursor, low
            cursor = max(cursor, high)
        if 1.0 > cursor + parameter_tolerance:
            yield cursor, 1.0
