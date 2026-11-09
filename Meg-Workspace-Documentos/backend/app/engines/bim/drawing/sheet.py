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


def _fit_scale(width_m: float, height_m: float, scale: float | None) -> float:
    """Choose 1:N so geometry fits the drawing area with margin."""
    draw_w = DRAW_RIGHT - DRAW_LEFT - 16.0
    draw_h = DRAW_BOTTOM - DRAW_TOP - 24.0
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
    prims.append(PaperPrim(kind="text", layer="TITLE", x=x, y=268, text=code, size=6.5, anchor="start", rgb=ink))
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
    mx,
    my,
    min_x: float,
    min_y: float,
    max_x: float,
    max_y: float,
) -> None:
    ink = (0.1, 0.1, 0.1)
    # Horizontal overall below geometry
    y_dim = min_y - (max_y - min_y) * 0.06 - 0.35
    prims.append(
        PaperPrim(kind="line", layer="DIM", x1=mx(min_x), y1=my(y_dim), x2=mx(max_x), y2=my(y_dim), weight=0.15, rgb=ink)
    )
    for x in (min_x, max_x):
        prims.append(
            PaperPrim(kind="line", layer="DIM", x1=mx(x), y1=my(y_dim) - 1.2, x2=mx(x), y2=my(y_dim) + 1.2, weight=0.15, rgb=ink)
        )
    span = max_x - min_x
    prims.append(
        PaperPrim(
            kind="text",
            layer="DIM",
            x=mx((min_x + max_x) / 2),
            y=my(y_dim) + 3.5,
            text=f"{span:.2f}",
            size=2.2,
            anchor="middle",
            rgb=ink,
        )
    )
    # Vertical overall
    x_dim = min_x - (max_x - min_x) * 0.06 - 0.35
    prims.append(
        PaperPrim(kind="line", layer="DIM", x1=mx(x_dim), y1=my(min_y), x2=mx(x_dim), y2=my(max_y), weight=0.15, rgb=ink)
    )
    for y in (min_y, max_y):
        prims.append(
            PaperPrim(kind="line", layer="DIM", x1=mx(x_dim) - 1.2, y1=my(y), x2=mx(x_dim) + 1.2, y2=my(y), weight=0.15, rgb=ink)
        )
    span_y = max_y - min_y
    prims.append(
        PaperPrim(
            kind="text",
            layer="DIM",
            x=mx(x_dim) - 2.5,
            y=my((min_y + max_y) / 2),
            text=f"{span_y:.2f}",
            size=2.2,
            anchor="end",
            rgb=ink,
        )
    )


def _default_code(kind: str) -> str:
    mapping = {"PLAN": "A-101", "SECTION": "A-201", "ELEVATION": "A-301"}
    return mapping.get(kind.upper(), "A-000")


def compose_a3_sheet(
    document: DrawingDocument,
    *,
    scale: float | None = None,
    meta: SheetMeta | None = None,
    include_overall_dims: bool = True,
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

    plot_scale = _fit_scale(width_m, height_m, scale)
    mm_per_m = 1000.0 / plot_scale

    # Centre geometry in drawing area
    draw_w = DRAW_RIGHT - DRAW_LEFT
    draw_h = DRAW_BOTTOM - DRAW_TOP
    geom_w_mm = width_m * mm_per_m
    geom_h_mm = height_m * mm_per_m
    paper_ox = DRAW_LEFT + (draw_w - geom_w_mm) / 2.0
    paper_oy = DRAW_TOP + (draw_h + geom_h_mm) / 2.0
    mx, my, _ = _map_factory(min_x, min_y, plot_scale, paper_ox, paper_oy)

    prims: list[PaperPrim] = []
    _frame(prims)

    for segment in document.segments:
        bucket = _layer_bucket(segment.layer)
        prims.append(
            PaperPrim(
                kind="line",
                layer=bucket,
                x1=mx(segment.start[0]),
                y1=my(segment.start[1]),
                x2=mx(segment.end[0]),
                y2=my(segment.end[1]),
                weight=_stroke_for(bucket),
                rgb=(0.1, 0.1, 0.1),
            )
        )

    if include_overall_dims and width_m > 0 and height_m > 0:
        _overall_dims(prims, mx, my, min_x, min_y, max_x, max_y)

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
        },
    )


# ---------------------------------------------------------------------------
# Paper-space exporters (A3)
# ---------------------------------------------------------------------------

_PT = 72.0 / 25.4


def _latin1_pdf(text: str) -> str:
    cleaned = (
        text.replace("á", "a")
        .replace("é", "e")
        .replace("í", "i")
        .replace("ó", "o")
        .replace("ú", "u")
        .replace("ñ", "n")
        .replace("Á", "A")
        .replace("É", "E")
        .replace("Í", "I")
        .replace("Ó", "O")
        .replace("Ú", "U")
        .replace("Ñ", "N")
    )
    out = []
    for ch in cleaned:
        code = ord(ch)
        if 32 <= code <= 255 and ch not in "\\()":
            out.append(ch)
        elif ch in "\\()":
            out.append("\\" + ch)
        else:
            out.append("?")
    return "".join(out)


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
            commands.append(f"({_latin1_pdf(prim.text)}) Tj")
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
        "<< /Type /Font /Subtype /Type1 /BaseFont /Helvetica >>",
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
