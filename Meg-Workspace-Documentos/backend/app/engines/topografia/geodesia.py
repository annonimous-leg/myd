


import math
from dataclasses import dataclass
from typing import Dict, List, Tuple

from app.core.errors import ErrorCode, MegalodonException


@dataclass(slots=True)
class AjustePoligonalResult:
    metodo: str
    vertices_ajustados: list[tuple[float, float, float]]
    error_cierre_m: float
    error_cierre_post_ajuste_m: float
    perimetro_m: float
    precision: str
    correcciones: list[dict[str, float]]
    cumple_tolerancia: bool


class MotorGeodesia:
    """Motor de geodesia para ajuste de poligonales y transformación de coordenadas.

    Implementa:
    - Ajuste de poligonal por método de mínimos cuadrados
    - Transformación de coordenadas geográficas a UTM
    - Cálculo de acimutes y distancias
    """

    def ajustar_poligonal(self, vertices: List[Tuple[float, float, float]]) -> AjustePoligonalResult:
        """Ajusta poligonal topográfica por método de Bowditch/Compás.

        Args:
            vertices: Lista de (x, y, z) en orden de recorrido

        Returns:
            Resultados ajustados con vertices_ajustados como tuplas.
        """
        if len(vertices) < 3:
            raise ValueError("Poligonal requiere al menos 3 vértices")

        n = len(vertices)

        dx_cierre = vertices[-1][0] - vertices[0][0]
        dy_cierre = vertices[-1][1] - vertices[0][1]
        dz_cierre = vertices[-1][2] - vertices[0][2]
        error_cierre = math.sqrt(dx_cierre**2 + dy_cierre**2 + dz_cierre**2)

        segmentos = []
        perimetro = 0.0
        for i in range(n - 1):
            dx = vertices[i + 1][0] - vertices[i][0]
            dy = vertices[i + 1][1] - vertices[i][1]
            dist = math.sqrt(dx**2 + dy**2)
            segmentos.append(dist)
            perimetro += dist

        vertices_ajustados: list[tuple[float, float, float]] = [vertices[0]]
        correcciones: list[dict[str, float]] = []
        distancia_acumulada = 0.0

        for i in range(1, n - 1):
            distancia_acumulada += segmentos[i - 1]
            factor = distancia_acumulada / perimetro if perimetro > 0 else 0.0
            cx = -dx_cierre * factor
            cy = -dy_cierre * factor
            cz = -dz_cierre * factor
            x, y, z = vertices[i]
            vertices_ajustados.append((x + cx, y + cy, z + cz))
            correcciones.append({"dx": cx, "dy": cy, "dz": cz})

        vertices_ajustados.append(vertices[0])
        correcciones.append({"dx": -dx_cierre, "dy": -dy_cierre, "dz": -dz_cierre})

        dx_post = vertices_ajustados[-1][0] - vertices_ajustados[0][0]
        dy_post = vertices_ajustados[-1][1] - vertices_ajustados[0][1]
        dz_post = vertices_ajustados[-1][2] - vertices_ajustados[0][2]
        error_post = math.sqrt(dx_post**2 + dy_post**2 + dz_post**2)

        precision = (error_cierre / perimetro) if perimetro > 0 else 0

        return AjustePoligonalResult(
            metodo="BOWDITCH",
            vertices_ajustados=[(round(v[0], 4), round(v[1], 4), round(v[2], 4)) for v in vertices_ajustados],
            error_cierre_m=round(error_cierre, 4),
            error_cierre_post_ajuste_m=round(error_post, 4),
            perimetro_m=round(perimetro, 2),
            precision=f"1:{int(1/precision)}" if precision > 0 else "Infinita",
            correcciones=correcciones,
            cumple_tolerancia=error_cierre < (perimetro / 5000),
        )

    def transformar_utm(self, lat: float, lon: float, zona: int = 14) -> Dict[str, float]:
        """Transforma WGS84 a UTM usando PROJ/pyproj oficial.

        En producción no existe una fórmula de respaldo aproximada: la
        transformación debe ser geodésicamente reproducible y usar el mismo
        motor de referencia en todos los workers.
        """
        try:
            import pyproj
        except ImportError as exc:
            raise MegalodonException(
                ErrorCode.TOPOGRAFIA_ERROR,
                "pyproj/PROJ es obligatorio para transformaciones UTM en producción.",
            ) from exc
        if not 1 <= zona <= 60:
            raise MegalodonException(ErrorCode.TOPOGRAFIA_ERROR, "La zona UTM debe estar entre 1 y 60.")
        epsg = (32600 if lat >= 0 else 32700) + zona
        transformer = pyproj.Transformer.from_crs("EPSG:4326", f"EPSG:{epsg}", always_xy=True)
        x, y = transformer.transform(lon, lat)
        return {"x_utm": round(x, 4), "y_utm": round(y, 4), "zona": zona, "hemisferio": "N" if lat >= 0 else "S"}
