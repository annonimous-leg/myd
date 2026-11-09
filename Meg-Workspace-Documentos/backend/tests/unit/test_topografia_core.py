from __future__ import annotations

import struct
from pathlib import Path

import pytest

from app.engines.topografia.exportacion import ExportadorTopografia
from app.engines.topografia.geodesia import MotorGeodesia
from app.engines.topografia.importadores.las_importer import ImportadorLAS


def _build_minimal_las(path: Path, x: float = 123.45, y: float = 456.78, z: float = 12.34) -> None:
    scale = 0.01
    xi = int(round(x / scale))
    yi = int(round(y / scale))
    zi = int(round(z / scale))

    header = bytearray(227)
    header[0:4] = b"LASF"
    header[24] = 1
    header[25] = 2
    struct.pack_into("<I", header, 96, 227)  # offset to point data
    header[104] = 0  # point format 0
    struct.pack_into("<H", header, 105, 20)  # record length
    struct.pack_into("<I", header, 107, 1)  # legacy count
    struct.pack_into("<d", header, 131, scale)
    struct.pack_into("<d", header, 139, scale)
    struct.pack_into("<d", header, 147, scale)
    struct.pack_into("<d", header, 155, 0.0)
    struct.pack_into("<d", header, 163, 0.0)
    struct.pack_into("<d", header, 171, 0.0)

    point = struct.pack("<iiiHBBbBH", xi, yi, zi, 0, 0, 0, 0, 0, 0)
    # pad to 20 bytes if needed
    point = point.ljust(20, b"\x00")
    path.write_bytes(bytes(header) + point)


def test_importador_las_parsea_punto_binario(tmp_path: Path) -> None:
    las_path = tmp_path / "muestra.las"
    _build_minimal_las(las_path)

    puntos = ImportadorLAS().desde_archivo(las_path)

    assert len(puntos) == 1
    assert puntos[0].identificador == "LAS-000001"
    assert puntos[0].x == pytest.approx(123.45, abs=1e-6)
    assert puntos[0].y == pytest.approx(456.78, abs=1e-6)
    assert puntos[0].z == pytest.approx(12.34, abs=1e-6)


def test_ajuste_poligonal_bowditch_cierra_el_traverse() -> None:
    motor = MotorGeodesia()
    vertices = [(0.0, 0.0), (50.0, 0.0), (50.0, 25.0), (0.6, 0.2)]

    resultado = motor.ajustar_poligonal(vertices)

    assert resultado.metodo == "BOWDITCH"
    assert resultado.vertices_ajustados[0] == pytest.approx(vertices[0])
    assert resultado.vertices_ajustados[-1] == pytest.approx(vertices[0])
    assert resultado.error_cierre_m > 0
    assert len(resultado.correcciones) == len(vertices) - 1


def test_exportador_dxf_genera_faces_y_points() -> None:
    exportador = ExportadorTopografia()
    vertices = [0.0, 0.0, 0.0, 10.0, 0.0, 1.0, 0.0, 10.0, 2.0]
    caras = [0, 1, 2]

    dxf = exportador.exportar_superficie_dxf("prueba", vertices, caras, puntos=[(0.0, 0.0, 0.0)])
    contenido = dxf.contenido.decode("utf-8")

    assert dxf.nombre_archivo == "prueba_superficie.dxf"
    assert "3DFACE" in contenido
    assert "POINT" in contenido
    assert "TOPO_TRIANGLES" in contenido


def test_exportador_csv_genera_encabezado_y_registros() -> None:
    exportador = ExportadorTopografia()

    csv_result = exportador.exportar_puntos_csv(
        [(1.0, 2.0, 3.0), (4.1234567, 5.0, 6.0)],
        nombre="levantamiento_demo",
    )

    contenido = csv_result.contenido.decode("utf-8")

    assert csv_result.nombre_archivo == "levantamiento_demo.csv"
    assert csv_result.media_type == "text/csv; charset=utf-8"
    assert contenido.splitlines()[0] == "id,x,y,z"
    assert "P00001,1.000000,2.000000,3.000000" in contenido
    assert "P00002,4.123457,5.000000,6.000000" in contenido
