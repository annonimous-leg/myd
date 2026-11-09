# Copyright © 2026 Cristian Rodriguez
# All rights reserved.

"""Exact piecewise-linear TIN overlay, with separate cut/fill integration.

Coordinates and elevations must be metric. Saved faces are authoritative;
point-only inputs explicitly construct a Delaunay TIN.
intersections preserve both triangulations' edges. The zero-height line splits
mixed cells before integration. No centroid classification or extrapolation.
"""
from dataclasses import dataclass
from typing import List, Tuple

import numpy as np
from scipy.spatial import Delaunay, QhullError
from shapely.geometry import Polygon
from shapely.strtree import STRtree

from app.core.errors import MegalodonException, ErrorCode


@dataclass
class ResultadoVolumen:
    volumen_corte_m3: float
    volumen_terraplen_m3: float
    volumen_neto_m3: float  # fill - cut
    area_analizada_m2: float
    num_triangulos_analizados: int
    cobertura: dict


def _surface(points, *, preserve_indices=False) -> np.ndarray:
    try:
        array = np.asarray(points, dtype=float)
    except (ValueError, TypeError) as exc:
        raise MegalodonException(ErrorCode.TOPOGRAFIA_ERROR, "Superficie XYZ inválida") from exc
    if array.ndim != 2 or array.shape[1] != 3 or not np.isfinite(array).all():
        raise MegalodonException(ErrorCode.TOPOGRAFIA_ERROR, "La superficie requiere coordenadas XYZ finitas")
    if not preserve_indices:
        array = np.unique(array, axis=0)
    if len(np.unique(array[:, :2], axis=0)) != len(array):
        raise MegalodonException(ErrorCode.TOPOGRAFIA_ERROR, "Una coordenada XY tiene elevaciones contradictorias")
    if len(array) < 3:
        raise MegalodonException(ErrorCode.PUNTOS_INSUFICIENTES, "Se necesitan tres puntos XY distintos por superficie")
    return array


def _tin(array, faces=None):
    if faces is None:
        try:
            triangles = Delaunay(array[:, :2]).simplices
        except QhullError as exc:
            raise MegalodonException(ErrorCode.TOPOGRAFIA_ERROR, "No se puede triangular una superficie degenerada") from exc
    else:
        try:
            values = np.asarray(faces, dtype=float)
        except (ValueError, TypeError) as exc:
            raise MegalodonException(ErrorCode.TOPOGRAFIA_ERROR, "Índices de malla inválidos") from exc
        if (values.ndim not in (1, 2) or not values.size or values.size % 3
                or (values.ndim == 2 and values.shape[1] != 3)
                or not np.isfinite(values).all() or (values != np.floor(values)).any()
                or (values < 0).any() or (values >= len(array)).any()):
            raise MegalodonException(ErrorCode.TOPOGRAFIA_ERROR, "Índices de malla inválidos")
        triangles = values.astype(np.int64).reshape(-1, 3)
    if len(np.unique(triangles)) != len(array):
        raise MegalodonException(
            ErrorCode.TOPOGRAFIA_ERROR,
            "La triangulación omite puntos por degeneración numérica; revise las coordenadas",
        )
    polygons, planes = [], []
    for triangle in triangles:
        xyz = array[triangle]
        origin = xyz[0, :2]
        try:
            gradient = np.linalg.solve(xyz[1:, :2] - origin, xyz[1:, 2] - xyz[0, 2])
        except np.linalg.LinAlgError as exc:
            raise MegalodonException(ErrorCode.TOPOGRAFIA_ERROR, "Triángulo de superficie degenerado") from exc
        if not np.isfinite(gradient).all():
            raise MegalodonException(ErrorCode.TOPOGRAFIA_ERROR, "Elevaciones fuera del rango de cálculo")
        polygons.append(Polygon(xyz[:, :2]))
        planes.append((origin, xyz[0, 2], gradient))
    if faces is not None:
        index = STRtree(polygons)
        for i, polygon in enumerate(polygons):
            for j in index.query(polygon, predicate="intersects"):
                if j > i and polygon.intersection(polygons[j]).area > 0:
                    raise MegalodonException(ErrorCode.TOPOGRAFIA_ERROR, "La malla tiene caras superpuestas")
    return polygons, planes


def _clip_grade(vertices, *, positive):
    """Clip a convex polygon carrying linear height differences at its vertices."""
    result = []
    previous = vertices[-1]
    previous_inside = previous[2] >= 0 if positive else previous[2] <= 0
    for current in vertices:
        inside = current[2] >= 0 if positive else current[2] <= 0
        if inside != previous_inside:
            fraction = previous[2] / (previous[2] - current[2])
            point = previous + fraction * (current - previous)
            point[2] = 0.0
            result.append(point)
        if inside:
            result.append(current)
        previous, previous_inside = current, inside
    return result


def _integral(vertices) -> float:
    """A linear field integrates as triangle area times its vertex mean."""
    if len(vertices) < 3:
        return 0.0
    origin = vertices[0]
    volume = 0.0
    for a, b in zip(vertices[1:-1], vertices[2:]):
        da, db = a[:2] - origin[:2], b[:2] - origin[:2]
        area = abs(da[0] * db[1] - da[1] * db[0]) / 2
        volume += area * (origin[2] + a[2] + b[2]) / 3
    return volume


class MotorVolumenes:
    def calcular_entre_superficies(
        self,
        puntos_existente: List[Tuple[float, float, float]],
        puntos_proyecto: List[Tuple[float, float, float]],
        *, caras_existente=None, caras_proyecto=None,
    ) -> ResultadoVolumen:
        existing = _surface(puntos_existente, preserve_indices=caras_existente is not None)
        project = _surface(puntos_proyecto, preserve_indices=caras_proyecto is not None)
        # Common local origin reduces numerical cancellation at large UTM offsets.
        origin = existing[0, :2].copy()
        existing[:, :2] -= origin
        project[:, :2] -= origin
        ex_polygons, ex_planes = _tin(existing, caras_existente)
        pr_polygons, pr_planes = _tin(project, caras_proyecto)
        index = STRtree(pr_polygons)
        cut = fill = area_total = 0.0
        triangles = 0
        for polygon, ex_plane in zip(ex_polygons, ex_planes):
            for candidate in index.query(polygon, predicate="intersects"):
                cell = polygon.intersection(pr_polygons[candidate])
                if cell.geom_type != "Polygon" or cell.area == 0:
                    continue  # shared edges/vertices have no measurable volume
                xy = np.asarray(cell.exterior.coords[:-1], dtype=float)
                ex_origin, ex_height, ex_gradient = ex_plane
                pr_origin, pr_height, pr_gradient = pr_planes[candidate]
                delta = (pr_height + (xy - pr_origin) @ pr_gradient
                         - ex_height - (xy - ex_origin) @ ex_gradient)
                vertices = np.column_stack((xy, delta))
                fill += _integral(_clip_grade(vertices, positive=True))
                cut -= _integral(_clip_grade(vertices, positive=False))
                area_total += cell.area
                triangles += len(vertices) - 2
        if area_total <= 0:
            raise MegalodonException(ErrorCode.TOPOGRAFIA_ERROR, "Las superficies no tienen área común; no se solapan")
        if not np.isfinite([cut, fill, area_total]).all():
            raise MegalodonException(ErrorCode.TOPOGRAFIA_ERROR, "Volumen fuera del rango de cálculo")
        area_existente = sum(p.area for p in ex_polygons)
        area_proyecto = sum(p.area for p in pr_polygons)
        tolerancia = max(1e-9, max(area_existente, area_proyecto) * 1e-10)
        pendientes = [max(0.0, area - area_total) for area in (area_existente, area_proyecto)]
        pendientes = [0.0 if area <= tolerancia else area for area in pendientes]
        return ResultadoVolumen(
            volumen_corte_m3=round(cut, 3),
            volumen_terraplen_m3=round(fill, 3),
            volumen_neto_m3=round(fill - cut, 3),
            area_analizada_m2=round(area_total, 3),
            num_triangulos_analizados=triangles,
            cobertura={
                "completa": not any(pendientes), "area_existente_m2": area_existente,
                "area_proyecto_m2": area_proyecto, "area_comun_m2": area_total,
                "area_existente_pendiente_m2": pendientes[0],
                "area_proyecto_pendiente_m2": pendientes[1],
            },
        )

    def calcular_contra_elevacion_referencia(
        self,
        puntos_superficie: List[Tuple[float, float, float]],
        elevacion_referencia: float,
        *, caras_superficie=None,
    ) -> ResultadoVolumen:
        surface = _surface(puntos_superficie, preserve_indices=caras_superficie is not None)
        reference = [(x, y, elevacion_referencia) for x, y, _ in surface]
        return self.calcular_entre_superficies(
            surface, reference, caras_existente=caras_superficie, caras_proyecto=caras_superficie,
        )
