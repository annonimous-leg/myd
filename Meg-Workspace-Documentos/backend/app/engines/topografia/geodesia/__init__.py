# Copyright © 2026 Cristian Rodriguez
# All rights reserved.
# Unauthorized copying, modification, distribution, or use is prohibited
# without prior written permission.

"""
Motor de geodesia: transformación de coordenadas entre sistemas de
referencia (GPS/geográficas <-> proyectadas UTM) y cálculos de
distancia, azimut y cierre de poligonal.
"""
from __future__ import annotations

import math
from dataclasses import dataclass
from typing import List, Tuple

from pyproj import Transformer

from app.core.errors import MegalodonException, ErrorCode


@dataclass(slots=True)
class ResultadoCierre:
    """Cierre de una poligonal (traverse)."""

    error_cierre_m: float
    perimetro_m: float
    precision_relativa: str  # ej. "1:5000"
    dentro_tolerancia: bool


@dataclass(slots=True)
class ResultadoAjustePoligonal:
    metodo: str
    vertices_ajustados: list[tuple[float, float]]
    error_cierre_m: float
    error_cierre_post_ajuste_m: float
    perimetro_m: float
    precision: str
    correcciones: list[dict[str, float]]
    cumple_tolerancia: bool


class MotorGeodesia:
    """Transformaciones de coordenadas y cálculos geodésicos básicos."""

    def transformar_coordenadas(
        self,
        puntos: List[Tuple[float, float]],
        crs_origen: str,
        crs_destino: str,
    ) -> List[Tuple[float, float]]:
        """Transforma una lista de (x, y) [o (lon, lat)] entre dos CRS."""
        try:
            transformer = Transformer.from_crs(crs_origen, crs_destino, always_xy=True)
        except Exception as e:
            raise MegalodonException(ErrorCode.TOPOGRAFIA_ERROR, f"CRS inválido: {e}")

        try:
            return [transformer.transform(x, y) for x, y in puntos]
        except Exception as e:
            raise MegalodonException(ErrorCode.TOPOGRAFIA_ERROR, f"Error al transformar coordenadas: {e}")

    def distancia_azimut(
        self, p1: Tuple[float, float], p2: Tuple[float, float]
    ) -> Tuple[float, float]:
        """Distancia (m) y azimut (grados desde el norte, sentido horario)."""
        dx = p2[0] - p1[0]
        dy = p2[1] - p1[1]
        distancia = math.sqrt(dx ** 2 + dy ** 2)
        azimut = math.degrees(math.atan2(dx, dy)) % 360
        return round(distancia, 4), round(azimut, 6)

    def cierre_poligonal(
        self, vertices: List[Tuple[float, float]], tolerancia_relativa: float = 1 / 5000
    ) -> ResultadoCierre:
        """Verifica el cierre de una poligonal cerrada (traverse)."""
        if len(vertices) < 3:
            raise MegalodonException(
                ErrorCode.PUNTOS_INSUFICIENTES, "Se necesitan al menos 3 vértices para una poligonal"
            )

        perimetro = 0.0
        for i in range(len(vertices) - 1):
            d, _ = self.distancia_azimut(vertices[i], vertices[i + 1])
            perimetro += d

        error_x = vertices[-1][0] - vertices[0][0]
        error_y = vertices[-1][1] - vertices[0][1]
        error_cierre = math.sqrt(error_x ** 2 + error_y ** 2)
        precision = perimetro / error_cierre if error_cierre > 0 else float("inf")
        precision_str = f"1:{int(precision)}" if precision != float("inf") else "1:∞ (cierre exacto)"

        return ResultadoCierre(
            error_cierre_m=round(error_cierre, 4),
            perimetro_m=round(perimetro, 4),
            precision_relativa=precision_str,
            dentro_tolerancia=(error_cierre / perimetro <= tolerancia_relativa) if perimetro > 0 else False,
        )

    def ajustar_poligonal(
        self,
        vertices: List[Tuple[float, float]],
        tolerancia_relativa: float = 1 / 5000,
    ) -> ResultadoAjustePoligonal:
        """Ajusta una poligonal cerrada por Bowditch."""
        if len(vertices) < 3:
            raise MegalodonException(
                ErrorCode.PUNTOS_INSUFICIENTES, "Se necesitan al menos 3 vértices para una poligonal"
            )

        perimetro = 0.0
        segmentos: list[float] = []
        for i in range(len(vertices) - 1):
            d, _ = self.distancia_azimut(vertices[i], vertices[i + 1])
            segmentos.append(d)
            perimetro += d

        error_x = vertices[-1][0] - vertices[0][0]
        error_y = vertices[-1][1] - vertices[0][1]
        error_cierre = math.sqrt(error_x ** 2 + error_y ** 2)
        precision = perimetro / error_cierre if error_cierre > 0 else float("inf")
        precision_str = f"1:{int(precision)}" if precision != float("inf") else "1:∞ (cierre exacto)"

        vertices_ajustados: list[tuple[float, float]] = [vertices[0]]
        correcciones: list[dict[str, float]] = []
        distancia_acumulada = 0.0

        for i in range(1, len(vertices) - 1):
            distancia_acumulada += segmentos[i - 1]
            factor = distancia_acumulada / perimetro if perimetro > 0 else 0.0
            cx = -error_x * factor
            cy = -error_y * factor
            x, y = vertices[i]
            vertices_ajustados.append((x + cx, y + cy))
            correcciones.append({"dx": cx, "dy": cy})

        vertices_ajustados.append(vertices[0])
        correcciones.append({"dx": -error_x, "dy": -error_y})

        return ResultadoAjustePoligonal(
            metodo="BOWDITCH",
            vertices_ajustados=[(round(v[0], 4), round(v[1], 4)) for v in vertices_ajustados],
            error_cierre_m=round(error_cierre, 4),
            error_cierre_post_ajuste_m=0.0,
            perimetro_m=round(perimetro, 4),
            precision=precision_str,
            correcciones=correcciones,
            cumple_tolerancia=(error_cierre / perimetro <= tolerancia_relativa) if perimetro > 0 else False,
        )
