"""Deterministic, dependency-free vector serializers for drawing documents."""
from __future__ import annotations

from html import escape
import math
import re

from app.engines.bim.drawing.core import DrawingDocument, DrawingSegment


def _validated_segments(document: DrawingDocument) -> tuple[DrawingSegment, ...]:
    if not document.segments:
        raise ValueError("drawing document is empty")
    for segment in document.segments:
        values = (*segment.start, *segment.end)
        if len(values) != 4 or not all(math.isfinite(float(value)) for value in values):
            raise ValueError("drawing segment coordinates must be finite")
        if not segment.layer or not segment.element_id or not segment.global_id:
            raise ValueError("drawing segment layer and source identity are required")
        if math.hypot(segment.end[0] - segment.start[0], segment.end[1] - segment.start[1]) <= 1e-12:
            raise ValueError("drawing contains a zero-length segment")
    if document.units != "m":
        raise ValueError("only metre-based drawing documents can be exported")
    return document.segments


def _bounds(segments: tuple[DrawingSegment, ...]) -> tuple[float, float, float, float]:
    points = [point for segment in segments for point in (segment.start, segment.end)]
    return (
        min(point[0] for point in points),
        min(point[1] for point in points),
        max(point[0] for point in points),
        max(point[1] for point in points),
    )


def _number(value: float) -> str:
    if abs(value) < 5e-13:
        value = 0.0
    return f"{value:.9f}".rstrip("0").rstrip(".") or "0"


def to_svg(document: DrawingDocument, *, margin_m: float = 0.1) -> str:
    """Serialize a vector SVG with physical dimensions derived from metres."""
    segments = _validated_segments(document)
    margin = float(margin_m)
    if not math.isfinite(margin) or margin < 0:
        raise ValueError("margin_m must be finite and non-negative")
    min_x, min_y, max_x, max_y = _bounds(segments)
    raw_width, raw_height = max_x - min_x, max_y - min_y
    if raw_width <= 0 and raw_height <= 0:
        raise ValueError("drawing extents are degenerate")
    minimum_extent = max(margin * 2, 0.001)
    width = max(raw_width + margin * 2, minimum_extent)
    height = max(raw_height + margin * 2, minimum_extent)
    origin_x = min_x - margin
    origin_y = max_y + margin
    layer_names = sorted({segment.layer for segment in segments})
    layer_ids = {name: f"layer-{index + 1}" for index, name in enumerate(layer_names)}

    grouped: dict[tuple[str, bool], list[str]] = {
        (name, hidden): [] for name in layer_names for hidden in (False, True)
    }
    for segment in segments:
        x1 = segment.start[0] - origin_x
        y1 = origin_y - segment.start[1]
        x2 = segment.end[0] - origin_x
        y2 = origin_y - segment.end[1]
        grouped[segment.layer, segment.hidden].append(
            f"M {_number(x1)} {_number(y1)} L {_number(x2)} {_number(y2)}"
        )

    parts = [
        '<?xml version="1.0" encoding="UTF-8"?>',
        (
            '<svg xmlns="http://www.w3.org/2000/svg" version="1.1" '
            f'width="{_number(width * 1000)}mm" height="{_number(height * 1000)}mm" '
            f'viewBox="0 0 {_number(width)} {_number(height)}" '
            'data-units="m" '
            f'data-kind="{escape(document.kind, quote=True)}">'
        ),
        f"<title>{escape(document.title)}</title>",
        '<g fill="none" stroke="#111111" stroke-width="0.0008" '
        'stroke-linecap="square" stroke-linejoin="miter">',
    ]
    for layer in layer_names:
        parts.append(f'<g id="{layer_ids[layer]}" data-layer="{escape(layer, quote=True)}">')
        for hidden in (True, False):
            paths = " ".join(grouped[layer, hidden])
            if paths:
                dash = ' stroke-dasharray="0.06 0.04"' if hidden else ''
                parts.append(f'<path d="{paths}"{dash}/>')
        parts.append("</g>")
    parts.extend(["</g>", "</svg>"])
    return "\n".join(parts) + "\n"


def _safe_layer_names(layers: list[str]) -> dict[str, str]:
    used: set[str] = set()
    result: dict[str, str] = {}
    for original in sorted(set(layers)):
        safe = re.sub(r"[^A-Za-z0-9_-]+", "_", original).strip("_") or "LAYER"
        safe = safe[:240]
        candidate = safe
        suffix = 1
        while candidate.casefold() in used:
            suffix += 1
            candidate = f"{safe[:230]}_{suffix}"
        used.add(candidate.casefold())
        result[original] = candidate
    return result


def to_dxf(document: DrawingDocument) -> bytes:
    """Write an ASCII DXF R2000 file containing metre-based LINE entities."""
    segments = _validated_segments(document)
    layers = _safe_layer_names([segment.layer for segment in segments])
    lines = [
        "0", "SECTION", "2", "HEADER",
        "9", "$ACADVER", "1", "AC1015",
        "9", "$INSUNITS", "70", "6",
        "9", "$MEASUREMENT", "70", "1",
        "0", "ENDSEC",
        "0", "SECTION", "2", "TABLES",
    ]
    if any(segment.hidden for segment in segments):
        lines.extend([
            "0", "TABLE", "2", "LTYPE", "70", "1",
            "0", "LTYPE", "100", "AcDbSymbolTableRecord", "100", "AcDbLinetypeTableRecord",
            "2", "MEG_HIDDEN", "70", "0", "3", "Hidden mesh edges",
            "72", "65", "73", "2", "40", "0.10",
            "49", "0.06", "74", "0", "49", "-0.04", "74", "0", "0", "ENDTAB",
        ])
    lines.extend(["0", "TABLE", "2", "LAYER", "70", str(len(layers))])
    for original, safe in layers.items():
        lines.extend([
            "0", "LAYER",
            "100", "AcDbSymbolTableRecord",
            "100", "AcDbLayerTableRecord",
            "2", safe,
            "70", "0",
            "62", "7",
            "6", "CONTINUOUS",
        ])
    lines.extend(["0", "ENDTAB", "0", "ENDSEC", "0", "SECTION", "2", "ENTITIES"])
    for segment in segments:
        lines.extend([
            "0", "LINE",
            "100", "AcDbEntity",
            "8", layers[segment.layer],
            *(("6", "MEG_HIDDEN") if segment.hidden else ()),
            "100", "AcDbLine",
            "10", _number(segment.start[0]),
            "20", _number(segment.start[1]),
            "30", "0",
            "11", _number(segment.end[0]),
            "21", _number(segment.end[1]),
            "31", "0",
        ])
    lines.extend(["0", "ENDSEC", "0", "EOF"])
    return ("\r\n".join(lines) + "\r\n").encode("ascii")
