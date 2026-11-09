"""Small, deterministic PDF drafts from editable, catalog-bound annex fields."""
from io import BytesIO
from xml.sax.saxutils import escape

from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import getSampleStyleSheet
from reportlab.platypus import Paragraph, SimpleDocTemplate, Spacer


def render_workspace_pdf(title: str, identifier: str, version: int, fields: list[dict]) -> bytes:
    output = BytesIO()
    styles = getSampleStyleSheet()
    document = SimpleDocTemplate(output, pagesize=A4, title=title, author="Megalodon",
                                 invariant=1, leftMargin=58, rightMargin=58)
    body = [
        Paragraph("MEGALODON / WORKSPACE", styles["Normal"]),
        Spacer(1, 18),
        Paragraph(escape(title), styles["Title"]),
        Paragraph(escape(f"{identifier} · Borrador de trabajo · v{version}"), styles["Normal"]),
        Spacer(1, 26),
    ]
    for field in fields:
        body.append(Paragraph(escape(field["label"]), styles["Heading3"]))
        body.append(Paragraph(escape(field["value"] or "Pendiente de captura").replace("\n", "<br/>"),
                              styles["BodyText"]))
        body.append(Spacer(1, 12))
    document.build(body)
    return output.getvalue()
