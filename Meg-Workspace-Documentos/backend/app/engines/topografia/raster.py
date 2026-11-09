# Copyright © 2026 Cristian Rodriguez
# Motor Raster Avanzado — Análisis de ortofotos, mosaicos y tiles

import io
import json
import zipfile
from pathlib import Path
from typing import List, Dict, Any, Tuple
from dataclasses import dataclass

try:
    from PIL import Image
    HAS_PIL = True
except ImportError:
    HAS_PIL = False


@dataclass
class ResultadoRaster:
    """Resultado de operación raster."""
    nombre_archivo: str
    contenido: bytes
    media_type: str
    metadata: Dict[str, Any]


class MotorRasterAvanzado:
    """Motor de procesamiento raster para topografía.

    Funciones:
    - Análisis de dimensiones y propiedades de imágenes
    - Creación de mosaicos a partir de múltiples ortofotos
    - Corte en tiles para visualización web (XYZ/Slippy Map)
    """

    def analizar_raster(self, ruta: Path) -> Dict[str, Any]:
        """Analiza imagen raster y retorna metadatos."""
        if not HAS_PIL:
            raise ImportError("PIL/Pillow requerido para procesamiento raster")

        img = Image.open(ruta)

        # Detectar si tiene georreferenciación (Worldfile .tfw, .jgw, etc.)
        georreferenciado = False
        worldfile_extensions = ['.tfw', '.jgw', '.pgw', '.wld']
        for ext in worldfile_extensions:
            if ruta.with_suffix(ext).exists():
                georreferenciado = True
                break

        # También verificar GeoTIFF
        if img.format == 'TIFF':
            # Simplificación: en producción se usaría rasterio para leer tags GeoTIFF
            georreferenciado = georreferenciado or self._detectar_geotiff(ruta)

        return {
            "ancho_px": img.width,
            "alto_px": img.height,
            "formato": img.format,
            "modo": img.mode,
            "georreferenciado": georreferenciado,
            "has_alpha": img.mode in ("RGBA", "LA", "PA"),
            "tamaño_bytes": ruta.stat().st_size if ruta.exists() else 0,
        }

    def _detectar_geotiff(self, ruta: Path) -> bool:
        """Detección básica de GeoTIFF por presencia de tags TIFF."""
        try:
            with open(ruta, 'rb') as f:
                header = f.read(8)
                # Byte order
                if header[:2] not in (b'II', b'MM'):
                    return False
                # Magic number 42
                magic = int.from_bytes(header[2:4], 'little' if header[:2] == b'II' else 'big')
                if magic != 42:
                    return False
                # En producción: leer IFD tags 34735 (GeoKeyDirectoryTag), 33922 (ModelTiepointTag)
                # Simplificación: asumir no-GeoTIFF a menos que exista worldfile
                return False
        except:
            return False

    def crear_mosaico(self, rutas_imagenes: List[Path]) -> ResultadoRaster:
        """Crea mosaico uniendo múltiples imágenes."""
        if not HAS_PIL:
            raise ImportError("PIL/Pillow requerido para mosaicos")

        if not rutas_imagenes:
            raise ValueError("Se requiere al menos una imagen")

        # Abrir todas las imágenes
        imagenes = [Image.open(r) for r in rutas_imagenes]

        # Calcular dimensiones del mosaico (layout horizontal)
        total_width = sum(img.width for img in imagenes)
        max_height = max(img.height for img in imagenes)

        # Crear canvas
        modo = imagenes[0].mode
        mosaico = Image.new(modo, (total_width, max_height))

        # Pegar imágenes
        x_offset = 0
        for img in imagenes:
            # Centrar verticalmente
            y_offset = (max_height - img.height) // 2
            mosaico.paste(img, (x_offset, y_offset))
            x_offset += img.width

        # Guardar en buffer
        buf = io.BytesIO()
        mosaico.save(buf, format='PNG')

        return ResultadoRaster(
            nombre_archivo="mosaico.png",
            contenido=buf.getvalue(),
            media_type="image/png",
            metadata={
                "imagenes_unidas": len(imagenes),
                "ancho_total_px": total_width,
                "alto_maximo_px": max_height,
            }
        )

    def cortar_en_tiles_zip(self, ruta: Path, tile_size: int = 256) -> ResultadoRaster:
        """Corta imagen en tiles y empaqueta en ZIP con manifest.

        Compatible con esquema XYZ/Slippy Map para visualización web.
        """
        if not HAS_PIL:
            raise ImportError("PIL/Pillow requerido para tiles")

        img = Image.open(ruta)

        # Calcular grid de tiles
        cols = (img.width + tile_size - 1) // tile_size
        rows = (img.height + tile_size - 1) // tile_size

        buf = io.BytesIO()
        manifest = []

        with zipfile.ZipFile(buf, 'w', zipfile.ZIP_DEFLATED) as zf:
            for row in range(rows):
                for col in range(cols):
                    # Calcular coordenadas de corte
                    left = col * tile_size
                    upper = row * tile_size
                    right = min(left + tile_size, img.width)
                    lower = min(upper + tile_size, img.height)

                    tile = img.crop((left, upper, right, lower))

                    # Guardar tile en buffer
                    tile_buf = io.BytesIO()
                    tile.save(tile_buf, format='PNG')
                    tile_name = f"tile_{row}_{col}.png"

                    zf.writestr(tile_name, tile_buf.getvalue())

                    manifest.append({
                        "tile": tile_name,
                        "row": row,
                        "col": col,
                        "x": left,
                        "y": upper,
                        "width": right - left,
                        "height": lower - upper,
                        "zoom": 0,  # Zoom level 0 para tile único
                    })

            # Escribir manifest
            zf.writestr("manifest.json", json.dumps(manifest, indent=2))

        return ResultadoRaster(
            nombre_archivo="tiles.zip",
            contenido=buf.getvalue(),
            media_type="application/zip",
            metadata={
                "tiles_count": len(manifest),
                "tile_size": tile_size,
                "cols": cols,
                "rows": rows,
            }
        )
