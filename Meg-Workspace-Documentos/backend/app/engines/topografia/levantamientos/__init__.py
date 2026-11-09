# Copyright © 2026 Cristian Rodriguez
# All rights reserved.
# Unauthorized copying, modification, distribution, or use is prohibited
# without prior written permission.

"""
Perfiles longitudinales: extrae la elevación del terreno a lo largo de un
eje/trazo (ej. eje de camino, línea de tubería) muestreando la superficie
TIN ya triangulada -- lo que en topografía se llama "perfil de terreno
natural", insumo real para diseño de rasante/camino.
"""
import math
from dataclasses import dataclass
from typing import List, Tuple

from scipy.interpolate import LinearNDInterpolator

from app.core.errors import MegalodonException, ErrorCode


@dataclass
class PuntoPerfil:
    cadenamiento: float  # distancia acumulada desde el inicio del eje (m)
    x: float
    y: float
    elevacion: float


class MotorPerfiles:
    """Genera perfiles longitudinales de terreno a partir de una
    superficie TIN ya triangulada (ver MotorTriangulacion)."""

    def generar_perfil(
        self,
        interpolador: LinearNDInterpolator,
        eje: List[Tuple[float, float]],
        intervalo_muestreo: float = 5.0,
    ) -> List[PuntoPerfil]:
        """eje: lista de vértices (x,y) que definen el trazo (PI's del
        eje). Se muestrea cada `intervalo_muestreo` metros a lo largo del
        eje completo, incluyendo siempre los PI's exactos."""
        if len(eje) < 2:
            raise MegalodonException(ErrorCode.TOPOGRAFIA_ERROR, "El eje necesita al menos 2 vértices")

        puntos: List[PuntoPerfil] = []
        cadenamiento_acumulado = 0.0

        for i in range(len(eje) - 1):
            x0, y0 = eje[i]
            x1, y1 = eje[i + 1]
            longitud_tramo = math.sqrt((x1 - x0) ** 2 + (y1 - y0) ** 2)
            if longitud_tramo == 0:
                continue

            num_muestras = max(1, int(longitud_tramo // intervalo_muestreo))
            for s in range(num_muestras + 1):
                t = s / num_muestras
                x = x0 + t * (x1 - x0)
                y = y0 + t * (y1 - y0)
                cadenamiento = cadenamiento_acumulado + t * longitud_tramo

                # Evita duplicar el punto de unión entre tramos (el
                # último del tramo anterior == el primero de este).
                if puntos and abs(puntos[-1].cadenamiento - cadenamiento) < 1e-6:
                    continue

                z = interpolador(x, y)
                elevacion = float(z) if z == z else None  # z==z es False solo si z es NaN
                if elevacion is None:
                    continue  # fuera del área cubierta por la superficie

                puntos.append(PuntoPerfil(
                    cadenamiento=round(cadenamiento, 3), x=round(x, 4), y=round(y, 4), elevacion=round(elevacion, 4),
                ))

            cadenamiento_acumulado += longitud_tramo

        if not puntos:
            raise MegalodonException(
                ErrorCode.TOPOGRAFIA_ERROR,
                "El eje no cruza el área cubierta por la superficie -- no se pudo generar el perfil",
            )
        return puntos
