# Copyright © 2026 Cristian Rodriguez
# Importador LAS — Lee nubes de puntos en formato LAS/LAZ

import struct
from pathlib import Path
from typing import List, Optional
from dataclasses import dataclass


@dataclass
class PuntoLAS:
    """Punto topográfico importado desde LAS."""
    identificador: str
    x: float
    y: float
    z: float
    intensidad: int = 0
    clasificacion: int = 0
    return_number: int = 1
    scan_angle: int = 0


class ImportadorLAS:
    """Importa nubes de puntos desde archivos LAS (ASPRS Standard).

    Soporta formatos 0-3 (legacy) y lectura básica de encabezado.
    Para formatos avanzados (6-10, LAZ comprimido) se requiere lazrs o laspy.
    """

    def __init__(self):
        self.puntos: List[PuntoLAS] = []

    def desde_archivo(self, ruta: Path) -> List[PuntoLAS]:
        """Lee archivo LAS y retorna lista de puntos."""
        data = ruta.read_bytes()
        if len(data) < 227:
            raise ValueError(f"Archivo LAS demasiado pequeño: {len(data)} bytes")

        # Validar firma
        if data[0:4] != b"LASF":
            raise ValueError("Firma LAS inválida (se esperaba 'LASF')")

        # Leer encabezado
        version_major = data[24]
        version_minor = data[25]
        offset_to_points = struct.unpack_from("<I", data, 96)[0]
        point_format = data[104]
        point_record_length = struct.unpack_from("<H", data, 105)[0]
        legacy_point_count = struct.unpack_from("<I", data, 107)[0]

        # Factores de escala y offset
        scale_x = struct.unpack_from("<d", data, 131)[0]
        scale_y = struct.unpack_from("<d", data, 139)[0]
        scale_z = struct.unpack_from("<d", data, 147)[0]
        offset_x = struct.unpack_from("<d", data, 155)[0]
        offset_y = struct.unpack_from("<d", data, 163)[0]
        offset_z = struct.unpack_from("<d", data, 171)[0]

        # Leer puntos
        puntos = []
        for i in range(legacy_point_count):
            start = offset_to_points + i * point_record_length
            if start + point_record_length > len(data):
                break

            xi = struct.unpack_from("<i", data, start)[0]
            yi = struct.unpack_from("<i", data, start + 4)[0]
            zi = struct.unpack_from("<i", data, start + 8)[0]

            # Escalar y desplazar
            x = xi * scale_x + offset_x
            y = yi * scale_y + offset_y
            z = zi * scale_z + offset_z

            # Leer intensidad y clasificación si el formato lo permite
            intensidad = 0
            clasificacion = 0
            if point_record_length >= 14:
                intensidad = struct.unpack_from("<H", data, start + 12)[0]
            if point_record_length >= 15:
                clasificacion = data[start + 15]

            puntos.append(PuntoLAS(
                identificador=f"LAS-{i+1:06d}",
                x=x,
                y=y,
                z=z,
                intensidad=intensidad,
                clasificacion=clasificacion
            ))

        self.puntos = puntos
        return puntos

    def resumen(self) -> dict:
        """Retorna resumen estadístico de la nube de puntos."""
        if not self.puntos:
            return {"total": 0, "x_min": 0, "x_max": 0, "y_min": 0, "y_max": 0, "z_min": 0, "z_max": 0}

        xs = [p.x for p in self.puntos]
        ys = [p.y for p in self.puntos]
        zs = [p.z for p in self.puntos]

        return {
            "total": len(self.puntos),
            "x_min": min(xs),
            "x_max": max(xs),
            "y_min": min(ys),
            "y_max": max(ys),
            "z_min": min(zs),
            "z_max": max(zs),
            "z_range": max(zs) - min(zs),
        }
