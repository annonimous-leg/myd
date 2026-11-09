# Copyright © 2026 Cristian Rodriguez
# All rights reserved.
# Unauthorized copying, modification, distribution, or use is prohibited
# without prior written permission.

"""
Motor de triangulación: construye una Red de Triángulos Irregulares (TIN)
real a partir de una nube de puntos topográficos, usando triangulación de
Delaunay (scipy.spatial.Delaunay -- el mismo algoritmo que usa cualquier
software de topografía profesional para esto).

La malla resultante usa el MISMO formato que el motor BIM
(vertices/caras planos) a propósito: así el visor 3D del frontend puede
reusar el mismo componente de renderizado para BIM y para topografía.
"""
from dataclasses import dataclass, field
from typing import List, Tuple
import math

import numpy as np
from scipy.spatial import Delaunay
from scipy.interpolate import LinearNDInterpolator

from app.core.errors import MegalodonException, ErrorCode


@dataclass
class MallaTIN:
    """Malla triangulada, mismo formato que MallaElemento en el motor BIM
    (vertices/caras planos, listos para THREE.BufferGeometry)."""
    vertices: List[float]  # [x1,y1,z1, x2,y2,z2, ...]
    caras: List[int]       # [i1,i2,i3, ...]


@dataclass
class EstadisticasSuperficie:
    area_plan: float          # área en planta (proyección XY), no de superficie inclinada
    area_superficie: float    # área real de la superficie (considerando pendiente)
    elevacion_min: float
    elevacion_max: float
    elevacion_media: float
    num_puntos: int
    num_triangulos: int
    pendiente_media_pct: float


@dataclass
class InterpoladorTIN:
    """Queries stay in survey coordinates; Qhull uses a local XY origin."""
    origen: np.ndarray
    lineal: LinearNDInterpolator

    def __call__(self, x, y=None):
        if y is None:
            return self.lineal(np.asarray(x) - self.origen)
        return self.lineal(np.asarray(x) - self.origen[0], np.asarray(y) - self.origen[1])


@dataclass
class ResultadoTriangulacion:
    malla: MallaTIN
    estadisticas: EstadisticasSuperficie
    interpolador: InterpoladorTIN = field(repr=False)


class MotorTriangulacion:
    """Construye superficies TIN reales a partir de puntos topográficos."""

    def triangular(self, puntos: List[Tuple[float, float, float]]) -> ResultadoTriangulacion:
        """puntos: lista de (x, y, z) en el CRS del levantamiento."""
        if len(puntos) < 3:
            raise MegalodonException(
                ErrorCode.PUNTOS_INSUFICIENTES,
                f"Se necesitan al menos 3 puntos para triangular (se recibieron {len(puntos)})",
            )

        try:
            arr = np.array(puntos, dtype=float)
        except (ValueError, TypeError) as exc:
            raise MegalodonException(ErrorCode.TOPOGRAFIA_ERROR, "Coordenadas XYZ inválidas") from exc
        if arr.ndim != 2 or arr.shape[1] != 3 or not np.isfinite(arr).all():
            raise MegalodonException(ErrorCode.TOPOGRAFIA_ERROR, "Se requieren coordenadas XYZ finitas, con elevación en cada punto")
        if len(np.unique(arr[:, :2], axis=0)) != len(arr):
            raise MegalodonException(ErrorCode.TOPOGRAFIA_ERROR, "Hay coordenadas XY duplicadas; revise los puntos antes de triangular")
        xy = arr[:, :2]
        z = arr[:, 2]
        origen = xy[0].copy()

        try:
            delaunay = Delaunay(xy - origen)
        except Exception as e:
            raise MegalodonException(
                ErrorCode.TOPOGRAFIA_ERROR,
                f"No se pudo triangular (¿puntos colineales o duplicados?): {e}",
            )
        if len(np.unique(delaunay.simplices)) != len(arr):
            raise MegalodonException(ErrorCode.TOPOGRAFIA_ERROR, "La triangulación omite puntos por degeneración numérica")

        vertices_flat: List[float] = []
        for x, y, zi in zip(arr[:, 0], arr[:, 1], z):
            vertices_flat.extend([float(x), float(y), float(zi)])
        caras_flat: List[int] = [int(i) for simplex in delaunay.simplices for i in simplex]

        # Área y pendiente por triángulo (área plan vs área de superficie
        # real -- en terreno inclinado son distintas, y la diferencia
        # importa para movimiento de tierras).
        area_plan_total = 0.0
        area_superficie_total = 0.0
        pendientes: List[float] = []
        for tri in delaunay.simplices:
            p0, p1, p2 = arr[tri[0]], arr[tri[1]], arr[tri[2]]
            area_plan = abs((p1[0] - p0[0]) * (p2[1] - p0[1]) - (p2[0] - p0[0]) * (p1[1] - p0[1])) / 2.0
            v1 = p1 - p0
            v2 = p2 - p0
            normal = np.cross(v1, v2)
            area_3d = np.linalg.norm(normal) / 2.0
            area_plan_total += area_plan
            area_superficie_total += area_3d
            if area_plan > 1e-9 and normal[2] != 0:
                pendiente = np.sqrt(normal[0] ** 2 + normal[1] ** 2) / abs(normal[2])
                pendientes.append(pendiente * 100)

        interpolador = InterpoladorTIN(origen, LinearNDInterpolator(delaunay, z))

        stats = EstadisticasSuperficie(
            area_plan=round(area_plan_total, 4),
            area_superficie=round(area_superficie_total, 4),
            elevacion_min=float(z.min()),
            elevacion_max=float(z.max()),
            elevacion_media=float(z.mean()),
            num_puntos=len(puntos),
            num_triangulos=len(delaunay.simplices),
            pendiente_media_pct=round(float(np.mean(pendientes)), 2) if pendientes else 0.0,
        )

        return ResultadoTriangulacion(
            malla=MallaTIN(vertices=vertices_flat, caras=caras_flat),
            estadisticas=stats,
            interpolador=interpolador,
        )

    def generar_curvas_nivel(
        self,
        resultado: "ResultadoTriangulacion",
        intervalo: float = 1.0,
    ) -> dict:
        """Genera curvas de nivel reales cortando la malla TIN a cada
        elevación (método "marching triangles": para cada triángulo, se
        buscan las aristas cuya Z cruza el nivel buscado y se interpola
        el punto de cruce). Regresa {elevacion: [[(x,y),(x,y)], ...]} --
        una lista de segmentos de línea por cada nivel."""
        verts = resultado.malla.vertices
        caras = resultado.malla.caras
        puntos = [(verts[i], verts[i + 1], verts[i + 2]) for i in range(0, len(verts), 3)]

        z_min = min(p[2] for p in puntos)
        z_max = max(p[2] for p in puntos)
        if z_max <= z_min:
            return {}

        primer_nivel = math.ceil(z_min / intervalo) * intervalo
        niveles = []
        nivel = primer_nivel
        while nivel <= z_max:
            niveles.append(round(nivel, 4))
            nivel += intervalo

        curvas: dict = {n: [] for n in niveles}

        for i in range(0, len(caras), 3):
            i0, i1, i2 = caras[i], caras[i + 1], caras[i + 2]
            tri = [puntos[i0], puntos[i1], puntos[i2]]
            tri_zmin = min(p[2] for p in tri)
            tri_zmax = max(p[2] for p in tri)

            for n in niveles:
                if n < tri_zmin or n > tri_zmax:
                    continue
                cruces = []
                for a, b in ((0, 1), (1, 2), (2, 0)):
                    za, zb = tri[a][2], tri[b][2]
                    if (za - n) * (zb - n) <= 0 and za != zb:
                        t = (n - za) / (zb - za)
                        x = tri[a][0] + t * (tri[b][0] - tri[a][0])
                        y = tri[a][1] + t * (tri[b][1] - tri[a][1])
                        cruces.append((round(x, 4), round(y, 4)))
                if len(cruces) == 2:
                    curvas[n].append(cruces)

        return {n: segs for n, segs in curvas.items() if segs}
