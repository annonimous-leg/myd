"""A3 sheet composer for IFC-derived DrawingDocument linework.

Maps model-space metres into a fixed A3 landscape sheet (420 × 297 mm) with:
  - drawing frame and title block
  - graphical scale bar
  - overall dimension chains from geometry bounds
  - layer-aware stroke weights

This is the production path for any IFC model. It does not depend on the
hardcoded residential solid used by the Plan Studio demo.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Literal, Mapping, Sequence
import math

from app.engines.bim.drawing.core import DrawingDocument, DrawingSegment

PaperAnchor = Literal["start", "middle", "end"]
PaperLayer = Literal["CUT", "DIM", "TITLE", "NOTE", "GLAZING", "OTHER"]

PAPER_W_MM = 420.0
PAPER_H_MM = 297.0
DRAW_LEFT = 12.0
DRAW_RIGHT = 318.0  # title block starts ~326
DRAW_TOP = 12.0
DRAW_BOTTOM = 285.0
TITLE_X = 330.0
DIM_LEFT = 36.0
DIM_BOTTOM = 20.0
DIM_OFFSET = 7.0

# Default plot scale 1:100 → 10 mm on paper per metre
DEFAULT_SCALE = 100.0


@dataclass(frozen=True, slots=True)
class PaperPrim:
    kind: Literal["line", "fill", "text"]
    layer: PaperLayer
    # line
    x1: float = 0.0
    y1: float = 0.0
    x2: float = 0.0
    y2: float = 0.0
    weight: float = 0.25
    dash: bool = False
    # fill
    points: tuple[float, ...] = ()
    # text
    x: float = 0.0
    y: float = 0.0
    text: str = ""
    size: float = 2.4
    anchor: PaperAnchor = "start"
    rgb: tuple[float, float, float] = (0.1, 0.1, 0.1)


@dataclass(frozen=True, slots=True)
class ComposedSheet:
    """A3 landscape sheet in paper millimetres."""

    code: str
    title: str
    kind: str
    width_mm: float
    height_mm: float
    scale: float
    primitives: tuple[PaperPrim, ...]
    source_segment_count: int
    bounds_m: tuple[float, float, float, float]  # min_x, min_y, max_x, max_y
    metadata: Mapping[str, object] = field(default_factory=dict)


@dataclass(frozen=True, slots=True)
class SheetMeta:
    project_name: str = ""
    subtitle: str = ""
    sheet_code: str = ""
    revision: str = ""
    date: str = ""
    organization: str = ""
    notes: tuple[str, ...] = ()


def _bounds(segments: Sequence[DrawingSegment]) -> tuple[float, float, float, float]:
    xs = [c for s in segments for c in (s.start[0], s.end[0])]
    ys = [c for s in segments for c in (s.start[1], s.end[1])]
    return min(xs), min(ys), max(xs), max(ys)


def _layer_bucket(name: str) -> PaperLayer:
    upper = name.upper()
    if "WINDOW" in upper or "GLAZ" in upper or "OPENING" in upper:
        return "GLAZING"
    if "DOOR" in upper:
        return "CUT"
    if upper.startswith("IFCWALL") or "WALL" in upper or "SLAB" in upper or "COLUMN" in upper:
        return "CUT"
    return "OTHER"


def _stroke_for(layer: PaperLayer) -> float:
    if layer == "CUT":
        return 0.35
    if layer == "GLAZING":
        return 0.18
    if layer == "DIM":
        return 0.15
    return 0.22


def _fit_scale(
    width_m: float,
    height_m: float,
    draw_w: float,
    draw_h: float,
    scale: float | None,
) -> float:
    """Choose 1:N so geometry fits the drawing area with margin."""
    if scale is not None:
        s = float(scale)
        if not math.isfinite(s) or s <= 0:
            raise ValueError("scale must be finite and > 0")
        return s
    # mm on paper = m * 1000 / N  →  N = m * 1000 / mm_available
    need_w = max(width_m, 1e-6) * 1000.0 / max(draw_w, 1.0)
    need_h = max(height_m, 1e-6) * 1000.0 / max(draw_h, 1.0)
    needed = max(need_w, need_h) * 1.08  # small margin
    # snap to common architectural scales
    candidates = (50, 75, 100, 125, 150, 200, 250, 500, 1000)
    for candidate in candidates:
        if candidate >= needed:
            return float(candidate)
    return float(math.ceil(needed / 50.0) * 50.0)


def _map_factory(
    origin_x_m: float,
    origin_y_m: float,
    scale: float,
    paper_ox: float,
    paper_oy: float,
):
    mm_per_m = 1000.0 / scale

    def mx(x: float) -> float:
        return paper_ox + (x - origin_x_m) * mm_per_m

    def my(y: float) -> float:
        # paper Y grows downward in our primitive convention matching SVG
        return paper_oy - (y - origin_y_m) * mm_per_m

    return mx, my, mm_per_m


def _frame(prims: list[PaperPrim]) -> None:
    ink = (0.1, 0.1, 0.1)
    prims.append(PaperPrim(kind="line", layer="TITLE", x1=8, y1=8, x2=412, y2=8, weight=0.4, rgb=ink))
    prims.append(PaperPrim(kind="line", layer="TITLE", x1=412, y1=8, x2=412, y2=289, weight=0.4, rgb=ink))
    prims.append(PaperPrim(kind="line", layer="TITLE", x1=412, y1=289, x2=8, y2=289, weight=0.4, rgb=ink))
    prims.append(PaperPrim(kind="line", layer="TITLE", x1=8, y1=289, x2=8, y2=8, weight=0.4, rgb=ink))
    prims.append(PaperPrim(kind="line", layer="TITLE", x1=326, y1=8, x2=326, y2=289, weight=0.28, rgb=ink))


def _scale_bar(prims: list[PaperPrim], scale: float, origin_x: float = 18.0, origin_y: float = 278.0) -> None:
    ink = (0.1, 0.1, 0.1)
    mid = (0.35, 0.35, 0.35)
    mm_per_m = 1000.0 / scale
    # Prefer 5 m bar if it fits; else 2 m
    metres = 5 if 5 * mm_per_m <= 90 else (2 if 2 * mm_per_m <= 90 else 1)
    total = metres * mm_per_m
    prims.append(PaperPrim(kind="line", layer="TITLE", x1=origin_x, y1=origin_y, x2=origin_x + total, y2=origin_y, weight=0.55, rgb=ink))
    for m in range(metres + 1):
        x = origin_x + m * mm_per_m
        tall = m == 0 or m == metres
        prims.append(
            PaperPrim(
                kind="line",
                layer="TITLE",
                x1=x,
                y1=origin_y,
                x2=x,
                y2=origin_y - (2.2 if tall else 1.2),
                weight=0.25,
                rgb=ink,
            )
        )
        if tall:
            prims.append(
                PaperPrim(kind="text", layer="TITLE", x=x, y=origin_y + 4.0, text=str(m), size=1.8, anchor="middle", rgb=mid)
            )
    for m in range(0, metres, 2):
        x0 = origin_x + m * mm_per_m
        x1 = origin_x + (m + 1) * mm_per_m
        prims.append(
            PaperPrim(kind="fill", layer="TITLE", points=(x0, origin_y, x1, origin_y, x1, origin_y - 1.4, x0, origin_y - 1.4), rgb=ink)
        )
    prims.append(
        PaperPrim(
            kind="text",
            layer="TITLE",
            x=origin_x,
            y=origin_y + 8.2,
            text=f"ESCALA 1:{int(scale) if scale == int(scale) else scale}",
            size=1.7,
            anchor="start",
            rgb=mid,
        )
    )


def _title_block(
    prims: list[PaperPrim],
    *,
    code: str,
    title: str,
    kind: str,
    scale: float,
    meta: SheetMeta,
    extra: Sequence[str],
) -> None:
    ink = (0.1, 0.1, 0.1)
    mid = (0.35, 0.35, 0.35)
    x = TITLE_X
    y = 18.0

    def row(label: str, value: str, size: float = 2.3) -> None:
        nonlocal y
        prims.append(PaperPrim(kind="text", layer="TITLE", x=x, y=y, text=label, size=1.6, anchor="start", rgb=mid))
        y += size + 0.5
        prims.append(PaperPrim(kind="text", layer="TITLE", x=x, y=y, text=value[:48], size=size, anchor="start", rgb=ink))
        y += 4.0
        prims.append(PaperPrim(kind="line", layer="TITLE", x1=328, y1=y - 2.0, x2=410, y2=y - 2.0, weight=0.1, rgb=mid))

    prims.append(PaperPrim(kind="text", layer="TITLE", x=x, y=y, text=meta.organization[:48], size=3.2, anchor="start", rgb=ink))
    y += 4.0
    prims.append(PaperPrim(kind="text", layer="TITLE", x=x, y=y, text="MEGALODON · IFC", size=2.0, anchor="start", rgb=mid))
    y += 5.5
    row("PROYECTO", meta.project_name)
    row("SUBTÍTULO", meta.subtitle)
    row("LÁMINA", title, 2.6)
    row("TIPO", kind)
    row("ESCALA", f"1:{int(scale) if scale == int(scale) else scale}  ·  metros")
    if meta.date:
        row("FECHA", meta.date)
    if meta.revision:
        row("REVISIÓN", meta.revision)
    for line in (*meta.notes, *extra):
        if not line:
            continue
        prims.append(PaperPrim(kind="text", layer="NOTE", x=x, y=y, text=line[:52], size=1.7, anchor="start", rgb=ink))
        y += 3.0
    prims.append(PaperPrim(kind="text", layer="TITLE", x=x, y=268, text=code, size=min(6.5, 78.0 / (max(1, len(code)) * 0.65)), anchor="start", rgb=ink))
    prims.append(
        PaperPrim(
            kind="text",
            layer="NOTE",
            x=x,
            y=278,
            text="Generado desde IFC · verificar en obra",
            size=1.6,
            anchor="start",
            rgb=ink,
        )
    )


def _overall_dims(
    prims: list[PaperPrim],
    left: float,
    bottom: float,
    right: float,
    top: float,
    width_m: float,
    height_m: float,
) -> None:
    def line(x1: float, y1: float, x2: float, y2: float) -> None:
        prims.append(PaperPrim(kind="line", layer="DIM", x1=x1, y1=y1, x2=x2, y2=y2, weight=0.15))

    def tick(x: float, y: float) -> None:
        line(x - 0.8, y + 0.8, x + 0.8, y - 0.8)

    if width_m > 0:
        y = bottom + DIM_OFFSET
        line(left, y, right, y)
        for x in (left, right):
            line(x, bottom + 1.2, x, y + 1.8)
            tick(x, y)
        prims.append(PaperPrim(
            kind="text", layer="DIM", x=(left + right) / 2, y=y + 3.5,
            text=f"{width_m:.2f}", size=2.2, anchor="middle",
        ))

    if height_m > 0:
        x = left - DIM_OFFSET
        line(x, bottom, x, top)
        for y in (bottom, top):
            line(left - 1.2, y, x - 1.8, y)
            tick(x, y)
        prims.append(PaperPrim(
            kind="text", layer="DIM", x=x - 2.5, y=(bottom + top) / 2,
            text=f"{height_m:.2f}", size=2.2, anchor="end",
        ))


def _default_code(kind: str) -> str:
    mapping = {"PLAN": "A-101", "SECTION": "A-201", "ELEVATION": "A-301"}
    return mapping.get(kind.upper(), "A-000")


def _element_extents(document: DrawingDocument) -> list[tuple[str, str, tuple[float, float, float, float]]]:
    groups: dict[tuple[str, str], list[DrawingSegment]] = {}
    for segment in document.segments:
        if not segment.hidden:
            groups.setdefault((segment.global_id, segment.layer), []).append(segment)
    extents = [(guid, layer, _bounds(segments)) for (guid, layer), segments in groups.items()]
    return sorted(extents, key=lambda item: (
        -max(item[2][2] - item[2][0], item[2][3] - item[2][1]), item[0],
    ))


def _element_schedule(prims: list[PaperPrim], document: DrawingDocument, mx, my) -> dict:
    extents = _element_extents(document)
    prims.append(PaperPrim(kind="text", layer="NOTE", x=TITLE_X, y=112,
                           text="COTAS DE TRAZOS VISIBLES (m)", size=2.2))
    rows = []
    for number, (guid, layer, (left, bottom, right, top)) in enumerate(extents[:8], 1):
        label = f"E{number:02}"
        # Anchor the key on actual visible linework. The table carries the spans.
        segment = next(s for s in document.segments if s.global_id == guid and not s.hidden)
        x = mx((segment.start[0] + segment.end[0]) / 2)
        y = my((segment.start[1] + segment.end[1]) / 2)
        prims.append(PaperPrim(kind="text", layer="NOTE", x=x, y=y - 0.8,
                               text=label, size=1.9, anchor="middle", rgb=(0.05, 0.29, 0.46)))
        width, height = right - left, top - bottom
        text = f"{label}   {layer[:22]}   {width:.3f} × {height:.3f}"
        prims.append(PaperPrim(kind="text", layer="NOTE", x=TITLE_X, y=112 + 4 * number, text=text, size=1.9))
        rows.append({"clave": label, "global_id": guid, "ancho_m": width, "alto_m": height})
    if len(extents) > len(rows):
        prims.append(PaperPrim(kind="text", layer="NOTE", x=TITLE_X, y=148,
                               text=f"Elementos adicionales: {len(extents) - len(rows)}", size=1.8))
    return {"cotas_elementos": rows, "elementos_visibles": len(extents)}


def _level_schedule(
    prims: list[PaperPrim],
    levels: Sequence[tuple[str, float]],
    document: DrawingDocument,
    right: float,
    top: float,
    bottom: float,
    my,
) -> None:
    prims.append(PaperPrim(kind="text", layer="NOTE", x=TITLE_X, y=158,
                           text="NIVELES IFC · Z DEL MODELO (m)", size=2.2))
    if not levels:
        prims.append(PaperPrim(kind="text", layer="NOTE", x=TITLE_X, y=162,
                               text="Sin niveles con posición IFC disponible", size=1.9))
    origin = document.metadata.get("plane_origin_m", document.metadata.get("view_origin_m"))
    up = document.metadata.get("view_up")
    vertical = document.kind != "PLAN" and origin is not None and up is not None and abs(up[2] - 1) < 1e-10
    last_marker_y = math.inf
    for number, (name, elevation) in enumerate(levels[:12], 1):
        label = f"N{number:02}"
        if vertical:
            y = my(elevation - origin[2])
            if top - 0.01 <= y <= bottom + 0.01 and last_marker_y - y >= 4:
                prims.append(PaperPrim(kind="line", layer="NOTE", x1=right, y1=y,
                                       x2=right + 5, y2=y, weight=0.15))
                prims.append(PaperPrim(kind="text", layer="NOTE", x=right + 5.5, y=y + 0.6,
                                       text=f"{label} {elevation:+.3f}", size=1.8))
                last_marker_y = y
        prims.append(PaperPrim(kind="text", layer="NOTE", x=TITLE_X, y=158 + 4 * number,
                               text=f"{label}   {elevation:+.3f}   {name[:32]}", size=1.9))
    if len(levels) > 12:
        prims.append(PaperPrim(kind="text", layer="NOTE", x=TITLE_X, y=210,
                               text=f"Niveles adicionales: {len(levels) - 12}", size=1.8))


def compose_a3_sheet(
    document: DrawingDocument,
    *,
    scale: float | None = None,
    meta: SheetMeta | None = None,
    include_overall_dims: bool = True,
    include_element_dims: bool = False,
    levels: Sequence[tuple[str, float]] | None = None,
) -> ComposedSheet:
    """Compose a professional A3 landscape sheet from an IFC DrawingDocument."""
    if document.units != "m":
        raise ValueError("only metre-based drawing documents can be composed")
    if not document.segments:
        raise ValueError("drawing document is empty")

    meta = meta or SheetMeta()
    kind = document.kind.upper()
    min_x, min_y, max_x, max_y = _bounds(document.segments)
    width_m = max_x - min_x
    height_m = max_y - min_y
    if width_m <= 0 and height_m <= 0:
        raise ValueError("drawing extents are degenerate")

    # Reserve paper space for labels and keep the drawing above the scale bar.
    draw_left = DRAW_LEFT + (DIM_LEFT if include_overall_dims and height_m > 0 else 0.0)
    draw_bottom = DRAW_BOTTOM - DIM_BOTTOM
    draw_right = DRAW_RIGHT - (12.0 if levels and kind != "PLAN" else 0.0)
    draw_w = draw_right - draw_left
    draw_h = draw_bottom - DRAW_TOP
    plot_scale = _fit_scale(width_m, height_m, draw_w - 16.0, draw_h, scale)
    mm_per_m = 1000.0 / plot_scale

    geom_w_mm = width_m * mm_per_m
    geom_h_mm = height_m * mm_per_m
    paper_ox = draw_left + (draw_w - geom_w_mm) / 2.0
    paper_oy = DRAW_TOP + (draw_h + geom_h_mm) / 2.0
    mx, my, _ = _map_factory(min_x, min_y, plot_scale, paper_ox, paper_oy)

    prims: list[PaperPrim] = []
    _frame(prims)

    # Draw concealed geometry first so visible edges stay legible at overlaps.
    for segment in sorted(document.segments, key=lambda segment: not segment.hidden):
        bucket = _layer_bucket(segment.layer)
        prims.append(
            PaperPrim(
                kind="line",
                layer=bucket,
                x1=mx(segment.start[0]),
                y1=my(segment.start[1]),
                x2=mx(segment.end[0]),
                y2=my(segment.end[1]),
                weight=0.10 if segment.hidden else _stroke_for(bucket),
                dash=segment.hidden,
                rgb=(0.65, 0.65, 0.65) if segment.hidden else (0.1, 0.1, 0.1),
            )
        )

    if include_overall_dims:
        _overall_dims(prims, mx(min_x), my(min_y), mx(max_x), my(max_y), width_m, height_m)

    _scale_bar(prims, plot_scale)

    code = meta.sheet_code or _default_code(kind)
    extra = [
        f"Segmentos: {len(document.segments)}",
        f"Extensión: {width_m:.2f} × {height_m:.2f} m",
    ]
    _title_block(
        prims,
        code=code,
        title=document.title or kind,
        kind=kind,
        scale=plot_scale,
        meta=meta,
        extra=extra,
    )

    detail_metadata = _element_schedule(prims, document, mx, my) if include_element_dims else {}
    if levels is not None:
        _level_schedule(prims, levels, document, mx(max_x), my(max_y), my(min_y), my)
        detail_metadata["niveles_ifc"] = [{"nombre": name, "z_m": z} for name, z in levels]

    return ComposedSheet(
        code=code,
        title=document.title or kind,
        kind=kind,
        width_mm=PAPER_W_MM,
        height_mm=PAPER_H_MM,
        scale=plot_scale,
        primitives=tuple(prims),
        source_segment_count=len(document.segments),
        bounds_m=(min_x, min_y, max_x, max_y),
        metadata={
            "source_kind": document.kind,
            "source_title": document.title,
            "engine": "megalodon-a3-sheet",
            "engine_version": "1.0.0",
            **dict(document.metadata),
            **detail_metadata,
        },
    )


# ---------------------------------------------------------------------------
# Paper-space exporters (A3)
# ---------------------------------------------------------------------------

_PT = 72.0 / 25.4


def _pdf_literal(text: str) -> str:
    encoded = text.encode("cp1252", errors="replace").decode("latin-1")
    return "".join(
        "\\" + ch if ch in "\\()" else ch if ord(ch) >= 32 else " "
        for ch in encoded
    )


def composed_to_pdf(sheet: ComposedSheet) -> bytes:
    """Vector PDF of the A3 sheet."""
    commands: list[str] = []
    scale = lambda mm: mm * _PT  # noqa: E731
    pdf_y = lambda y: (sheet.height_mm - y) * _PT  # noqa: E731

    for prim in sheet.primitives:
        r, g, b = prim.rgb
        if prim.kind == "fill":
            commands.append(f"{r:.3f} {g:.3f} {b:.3f} rg")
            for i in range(0, len(prim.points), 2):
                x, y = scale(prim.points[i]), pdf_y(prim.points[i + 1])
                commands.append(f"{x:.3f} {y:.3f} m" if i == 0 else f"{x:.3f} {y:.3f} l")
            commands.extend(["h", "f"])
        elif prim.kind == "line":
            commands.append(f"{r:.3f} {g:.3f} {b:.3f} RG")
            commands.append(f"{(prim.weight * _PT):.3f} w")
            commands.append("[3 2] 0 d" if prim.dash else "[] 0 d")
            commands.append(f"{scale(prim.x1):.3f} {pdf_y(prim.y1):.3f} m")
            commands.append(f"{scale(prim.x2):.3f} {pdf_y(prim.y2):.3f} l")
            commands.append("S")
        else:
            width = len(prim.text) * prim.size * 0.48
            shift = width / 2 if prim.anchor == "middle" else width if prim.anchor == "end" else 0
            commands.append("BT")
            commands.append(f"{r:.3f} {g:.3f} {b:.3f} rg")
            commands.append(f"/F1 {scale(prim.size):.3f} Tf")
            commands.append(f"{scale(prim.x - shift):.3f} {pdf_y(prim.y):.3f} Td")
            commands.append(f"({_pdf_literal(prim.text)}) Tj")
            commands.append("ET")

    stream = "\n".join(commands)
    page_w = sheet.width_mm * _PT
    page_h = sheet.height_mm * _PT
    objects = [
        "<< /Type /Catalog /Pages 2 0 R >>",
        "<< /Type /Pages /Kids [3 0 R] /Count 1 >>",
        (
            f"<< /Type /Page /Parent 2 0 R /MediaBox [0 0 {page_w:.2f} {page_h:.2f}] "
            f"/Contents 4 0 R /Resources << /Font << /F1 5 0 R >> >> >>"
        ),
        f"<< /Length {len(stream.encode('latin-1'))} >>\nstream\n{stream}\nendstream",
        "<< /Type /Font /Subtype /Type1 /BaseFont /Helvetica /Encoding /WinAnsiEncoding >>",
    ]
    out = bytearray(b"%PDF-1.4\n")
    offsets = [0]
    for index, obj in enumerate(objects, start=1):
        offsets.append(len(out))
        out.extend(f"{index} 0 obj\n{obj}\nendobj\n".encode("latin-1"))
    xref = len(out)
    out.extend(f"xref\n0 {len(objects) + 1}\n".encode("ascii"))
    out.extend(b"0000000000 65535 f \n")
    for offset in offsets[1:]:
        out.extend(f"{offset:010d} 00000 n \n".encode("ascii"))
    out.extend(
        f"trailer\n<< /Size {len(objects) + 1} /Root 1 0 R >>\nstartxref\n{xref}\n%%EOF\n".encode("ascii")
    )
    return bytes(out)
