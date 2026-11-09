from __future__ import annotations

import io
import json
import zipfile
from pathlib import Path

import pytest
from PIL import Image

from app.engines.topografia.raster import MotorRasterAvanzado
from app.engines.topografia.drenaje import MotorDrenaje
from app.engines.topografia.planeacion_obra import MotorPlaneacionObraAvanzada


def _crear_png(path: Path, size: tuple[int, int] = (64, 64), color: tuple[int, int, int, int] = (255, 0, 0, 255)) -> None:
    img = Image.new("RGBA", size, color)
    img.save(path)


def test_raster_analisis_mosaico_y_tiles(tmp_path: Path) -> None:
    raster = tmp_path / "orto.png"
    _crear_png(raster, (32, 16))
    overlay = tmp_path / "overlay.png"
    _crear_png(overlay, (16, 16), (0, 255, 0, 128))

    motor = MotorRasterAvanzado()
    reporte = motor.analizar_raster(raster)
    assert reporte["ancho_px"] == 32
    assert reporte["alto_px"] == 16
    assert reporte["georreferenciado"] is False

    mosaico = motor.crear_mosaico([raster, overlay])
    assert mosaico.media_type == "image/png"
    assert mosaico.nombre_archivo.endswith(".png")

    tiles = motor.cortar_en_tiles_zip(raster, tile_size=8)
    assert tiles.media_type == "application/zip"
    with zipfile.ZipFile(io.BytesIO(tiles.contenido)) as zf:
        assert "manifest.json" in zf.namelist()
        manifest = json.loads(zf.read("manifest.json"))
        assert len(manifest) == 8


def test_drenaje_analiza_cuenca_y_rutas() -> None:
    motor = MotorDrenaje()
    puntos = [
        (0.0, 0.0, 15.0),
        (20.0, 0.0, 14.0),
        (20.0, 20.0, 10.0),
        (0.0, 20.0, 12.0),
        (10.0, 10.0, 6.0),
        (5.0, 5.0, 18.0),
    ]

    reporte = motor.analizar_superficie(puntos, coeficiente_runoff=0.45, intensidad_lluvia_mm_h=60.0)
    assert reporte["area_cuenca_m2"] > 0
    assert reporte["caudal_m3s"] > 0
    assert reporte["rutas"]
    assert reporte["recomendaciones"]


def test_planeacion_avanzada_integra_volumen_drenaje_y_terrazas() -> None:
    motor = MotorPlaneacionObraAvanzada()
    puntos = [
        (0.0, 0.0, 100.0),
        (20.0, 0.0, 101.0),
        (20.0, 20.0, 102.0),
        (0.0, 20.0, 99.0),
        (10.0, 10.0, 100.5),
    ]

    plan = motor.generar_plan(
        puntos,
        cota_objetivo=100.0,
        salto_terrazas=0.5,
        tarifas={"corte_m3": 120.0, "relleno_m3": 90.0, "drenaje_m2": 15.0},
    )
    assert plan["volumen"]["area_analizada_m2"] > 0
    assert isinstance(plan["terrazas"], list)
    assert plan["drenaje"]["caudal_m3s"] > 0
    assert plan["talud_recomendado"] >= 1.0
