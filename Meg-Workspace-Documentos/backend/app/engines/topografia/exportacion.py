# Copyright © 2026 Cristian Rodriguez
# Exportador Topografía — DXF, CSV, XYZ, LandXML

import io
from dataclasses import dataclass
from typing import List, Tuple, Optional


@dataclass
class ArchivoExportado:
    """Resultado de exportación."""
    nombre_archivo: str
    contenido: bytes
    media_type: str
    formato: str


class ExportadorTopografia:
    """Exporta datos topográficos a formatos estándar de la industria.

    Formatos soportados:
    - DXF (AutoCAD): superficies 3D (3DFACE), puntos (POINT), líneas
    - CSV: puntos con coordenadas id,x,y,z
    - XYZ: formato texto plano para importación en software GIS
    - LandXML: estándar para intercambio de datos topográficos
    """

    def exportar_superficie_dxf(self, nombre: str, vertices: List[float],
                                 caras: List[int], puntos: Optional[List[Tuple[float, float, float]]] = None) -> ArchivoExportado:
        """Exporta superficie TIN a DXF con 3DFACE y POINT.

        Args:
            nombre: Nombre base del archivo (sin extensión)
            vertices: Lista plana [x1,y1,z1, x2,y2,z2, ...]
            caras: Índices de triángulos [i1,i2,i3, i4,i5,i6, ...]
            puntos: Puntos adicionales a incluir como entidades POINT
        """
        buf = io.StringIO()

        # Encabezado DXF
        buf.write("0\nSECTION\n")
        buf.write("2\nHEADER\n")
        buf.write("9\n$ACADVER\n1\nAC1015\n")  # AutoCAD 2000
        buf.write("0\nENDSEC\n")

        # Tabla de capas
        buf.write("0\nSECTION\n")
        buf.write("2\nTABLES\n")
        buf.write("0\nTABLE\n2\nLAYER\n70\n2\n")
        buf.write("0\nLAYER\n2\nTOPO_TRIANGLES\n70\n0\n62\n7\n6\nContinuous\n")
        buf.write("0\nLAYER\n2\nTOPO_POINTS\n70\n0\n62\n1\n6\nContinuous\n")
        buf.write("0\nENDTAB\n")
        buf.write("0\nENDSEC\n")

        # Entidades
        buf.write("0\nSECTION\n")
        buf.write("2\nENTITIES\n")

        # 3DFACE por cada cara
        for i in range(0, len(caras), 3):
            if i + 2 >= len(caras):
                break
            i1, i2, i3 = caras[i] * 3, caras[i+1] * 3, caras[i+2] * 3

            buf.write("0\n3DFACE\n")
            buf.write("8\nTOPO_TRIANGLES\n")
            # Vértice 1
            buf.write(f"10\n{vertices[i1]}\n20\n{vertices[i1+1]}\n30\n{vertices[i1+2]}\n")
            # Vértice 2
            buf.write(f"11\n{vertices[i2]}\n21\n{vertices[i2+1]}\n31\n{vertices[i2+2]}\n")
            # Vértice 3
            buf.write(f"12\n{vertices[i3]}\n22\n{vertices[i3+1]}\n32\n{vertices[i3+2]}\n")
            # Vértice 4 (igual al 3 para triángulo)
            buf.write(f"13\n{vertices[i3]}\n23\n{vertices[i3+1]}\n33\n{vertices[i3+2]}\n")

        # POINT por cada punto adicional
        if puntos:
            for x, y, z in puntos:
                buf.write("0\nPOINT\n")
                buf.write("8\nTOPO_POINTS\n")
                buf.write(f"10\n{x}\n20\n{y}\n30\n{z}\n")

        buf.write("0\nENDSEC\n")
        buf.write("0\nEOF\n")

        return ArchivoExportado(
            nombre_archivo=f"{nombre}_superficie.dxf",
            contenido=buf.getvalue().encode("utf-8"),
            media_type="application/dxf",
            formato="DXF"
        )

    def exportar_puntos_csv(self, puntos: List[Tuple[float, float, float]],
                            nombre: str = "levantamiento") -> ArchivoExportado:
        """Exporta puntos a CSV con encabezado estándar.

        Formato: id,x,y,z (compatible con tests)
        """
        buf = io.StringIO()
        buf.write("id,x,y,z\n")

        for i, (x, y, z) in enumerate(puntos, 1):
            buf.write(f"P{i:05d},{x:.6f},{y:.6f},{z:.6f}\n")

        return ArchivoExportado(
            nombre_archivo=f"{nombre}.csv",
            contenido=buf.getvalue().encode("utf-8"),
            media_type="text/csv; charset=utf-8",
            formato="CSV"
        )

    def exportar_puntos_xyz(self, puntos: List[Tuple[float, float, float]],
                            nombre: str = "nube") -> ArchivoExportado:
        """Exporta puntos a formato XYZ plano (compatible con GIS)."""
        buf = io.StringIO()

        for x, y, z in puntos:
            buf.write(f"{x:.6f} {y:.6f} {z:.6f}\n")

        return ArchivoExportado(
            nombre_archivo=f"{nombre}.xyz",
            contenido=buf.getvalue().encode("utf-8"),
            media_type="text/plain",
            formato="XYZ"
        )

    def exportar_landxml(self, nombre: str, puntos: List[Tuple[float, float, float]],
                         caras: List[int]) -> ArchivoExportado:
        """Exporta a LandXML 1.2 (estándar para intercambio topográfico)."""
        buf = io.StringIO()

        buf.write('<?xml version="1.0" encoding="UTF-8"?>\n')
        buf.write('<LandXML xmlns="http://www.landxml.org/schema/LandXML-1.2" ')
        buf.write('xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance" ')
        buf.write('xsi:schemaLocation="http://www.landxml.org/schema/LandXML-1.2 http://www.landxml.org/schema/LandXML-1.2/LandXML-1.2.xsd" ')
        buf.write('version="1.2" date="2026-01-01" time="00:00:00">\n')
        buf.write(f'  <Project name="{nombre}"/>\n')
        buf.write('  <Application name="Megalodon" version="4.0.0" manufacturer="Cristian Rodriguez"/>\n')
        buf.write('  <Surfaces>\n')
        buf.write(f'    <Surface name="{nombre}">\n')
        buf.write('      <Definition surfType="TIN">\n')
        buf.write('        <Pnts>\n')

        for i, (x, y, z) in enumerate(puntos):
            buf.write(f'          <P id="{i+1}">{x:.6f} {y:.6f} {z:.6f}</P>\n')

        buf.write('        </Pnts>\n')
        buf.write('        <Faces>\n')

        for i in range(0, len(caras), 3):
            if i + 2 >= len(caras):
                break
            buf.write(f'          <F>{caras[i]+1} {caras[i+1]+1} {caras[i+2]+1}</F>\n')

        buf.write('        </Faces>\n')
        buf.write('      </Definition>\n')
        buf.write('    </Surface>\n')
        buf.write('  </Surfaces>\n')
        buf.write('</LandXML>\n')

        return ArchivoExportado(
            nombre_archivo=f"{nombre}.xml",
            contenido=buf.getvalue().encode("utf-8"),
            media_type="application/xml",
            formato="LandXML"
        )
