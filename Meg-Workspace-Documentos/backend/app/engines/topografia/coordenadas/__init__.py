# Copyright © 2026 Cristian Rodriguez
# All rights reserved.
# Unauthorized copying, modification, distribution, or use is prohibited
# without prior written permission.

"""
Importación de puntos topográficos desde formatos de campo comunes
(CSV tipo PENZD: Punto, Este/Norte o Norte/Este, Elevación, Descripción --
el formato estándar que exportan la mayoría de estaciones totales y GPS
RTK) y validación básica de datos crudos antes de triangular.
"""
import csv
import io
from dataclasses import dataclass
from typing import List, Optional, Tuple

from app.core.errors import MegalodonException, ErrorCode


@dataclass
class PuntoImportado:
    identificador: str
    x: float  # Este / Easting
    y: float  # Norte / Northing
    z: Optional[float]
    descripcion: str = ""


class ImportadorPuntos:
    """Importa puntos desde CSV en formatos de campo comunes."""

    def desde_csv_penzd(self, contenido: str) -> List[PuntoImportado]:
        """Formato PENZD clásico: Punto,Este,Norte,Elevación,Descripción
        (el orden E,N -- no N,E -- es el estándar de estación total, ojo
        al importar de GPS que a veces exportan N,E)."""
        return self._parsear(contenido, columnas=("punto", "este", "norte", "elevacion", "descripcion"))

    def desde_csv_generico(self, contenido: str, mapeo_columnas: Optional[dict] = None) -> List[PuntoImportado]:
        """CSV genérico con encabezados. mapeo_columnas permite indicar
        los nombres reales de columnas si no son id/x/y/z/descripcion,
        ej. {"x": "Easting", "y": "Northing", "z": "Elev"}."""
        mapeo = mapeo_columnas or {}
        col_id = mapeo.get("id", "id")
        col_x = mapeo.get("x", "x")
        col_y = mapeo.get("y", "y")
        col_z = mapeo.get("z", "z")
        col_desc = mapeo.get("descripcion", "descripcion")

        reader = csv.DictReader(io.StringIO(contenido))
        puntos = []
        for i, fila in enumerate(reader, 1):
            try:
                puntos.append(PuntoImportado(
                    identificador=str(fila.get(col_id, i)),
                    x=float(fila[col_x]),
                    y=float(fila[col_y]),
                    z=float(fila[col_z]) if fila.get(col_z) not in (None, "") else None,
                    descripcion=fila.get(col_desc, "") or "",
                ))
            except (KeyError, ValueError) as e:
                raise MegalodonException(
                    ErrorCode.TOPOGRAFIA_ERROR,
                    f"Error en la fila {i} del CSV: {e}",
                )
        if not puntos:
            raise MegalodonException(ErrorCode.PUNTOS_INSUFICIENTES, "El CSV no contiene puntos válidos")
        return puntos

    def _parsear(self, contenido: str, columnas: Tuple[str, ...]) -> List[PuntoImportado]:
        lector = csv.reader(io.StringIO(contenido))
        puntos = []
        for i, fila in enumerate(lector, 1):
            if not fila or fila[0].strip().startswith("#"):
                continue
            if len(fila) < 4:
                raise MegalodonException(
                    ErrorCode.TOPOGRAFIA_ERROR,
                    f"Fila {i}: se esperaban al menos 4 columnas (punto,este,norte,elevación), se recibieron {len(fila)}",
                )
            try:
                puntos.append(PuntoImportado(
                    identificador=fila[0].strip(),
                    x=float(fila[1]),
                    y=float(fila[2]),
                    z=float(fila[3]) if len(fila) > 3 and fila[3].strip() else None,
                    descripcion=fila[4].strip() if len(fila) > 4 else "",
                ))
            except ValueError as e:
                raise MegalodonException(ErrorCode.TOPOGRAFIA_ERROR, f"Fila {i}: valor numérico inválido ({e})")
        if not puntos:
            raise MegalodonException(ErrorCode.PUNTOS_INSUFICIENTES, "El CSV no contiene puntos válidos")
        return puntos
