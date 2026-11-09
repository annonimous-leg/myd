"""Megalodon-owned vector drawing engine for normalized BIM meshes."""

from app.engines.bim.drawing.core import (
    DrawingDocument,
    DrawingSegment,
    MeshElement,
    Plane,
    ViewFrame,
    build_elevation_document,
    build_plan_document,
    build_section_document,
    cut_mesh_with_plane,
)
from app.engines.bim.drawing.exporters import to_dxf, to_svg

__all__ = [
    "DrawingDocument",
    "DrawingSegment",
    "MeshElement",
    "Plane",
    "ViewFrame",
    "build_elevation_document",
    "build_plan_document",
    "build_section_document",
    "cut_mesh_with_plane",
    "to_dxf",
    "to_svg",
]
