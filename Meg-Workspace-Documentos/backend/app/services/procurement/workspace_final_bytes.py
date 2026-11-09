"""Read the exact reviewed Workspace DOCX/XLSX bytes for official compilation.

Never regenerate an editable official template at the approval/delivery stage.
The source/template configuration and saved bytes must still match exactly.
"""
from __future__ import annotations

from base64 import b64decode
from binascii import Error as Base64Error
from hashlib import sha256
from io import BytesIO
import json
from typing import Any
from zipfile import BadZipFile, ZipFile


class WorkspaceFinalBytesError(ValueError):
    pass


MAX_FINAL_BYTES = 512 * 1024
DOCX_MEDIA_TYPE = "application/vnd.openxmlformats-officedocument.wordprocessingml.document"
XLSX_MEDIA_TYPE = "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"


def reviewed_workspace_artifact(
    binding: dict[str, Any], document: Any, revision_row: Any, current_revision: int,
    *, current_source_model_hash: str,
) -> tuple[bytes, str, dict]:
    """Fail closed unless a reviewer-owned revision contains the exact rendered bytes."""
    docx = "workspace_docx" in binding
    xlsx = "workspace_xlsx" in binding
    if docx == xlsx:
        raise WorkspaceFinalBytesError("El formato debe tener exactamente una plantilla DOCX o XLSX.")
    key = "workspace_docx" if docx else "workspace_xlsx"
    template = binding[key]
    if not isinstance(template, dict):
        raise WorkspaceFinalBytesError("El mapa de la plantilla no es válido.")
    if (document is None or revision_row is None or
        not document.human_modified or document.tender_revision != current_revision or
        revision_row.document_id != document.id or revision_row.version != document.version or
        revision_row.tender_revision != current_revision or revision_row.operation != "HUMAN_EDIT_RENDER" or
        revision_row.source_model_hash != current_source_model_hash):
        raise WorkspaceFinalBytesError("Falta una revisión humana renderizada y vigente del anexo oficial.")
    metadata = revision_row.revision_metadata or {}
    draft = metadata.get(key)
    if not isinstance(draft, dict):
        raise WorkspaceFinalBytesError("La revisión no contiene los bytes originales aprobables.")
    config_hash = sha256(json.dumps(template, sort_keys=True, default=str, separators=(",", ":")).encode()).hexdigest()
    if (draft.get("source_sha256") != template.get("source_sha256") or
        draft.get("map_version") != template.get("version") or
        draft.get("map_sha256") != config_hash or
        (xlsx and draft.get("server_recalculated") is not True)):
        raise WorkspaceFinalBytesError("Cambió la plantilla, su mapa o el cálculo del documento. Vuelve a revisarlo.")
    try:
        content = b64decode(draft["content"], validate=True)
    except (KeyError, TypeError, ValueError, Base64Error) as exc:
        raise WorkspaceFinalBytesError("El contenido de la revisión no es Base64 válido.") from exc
    if not 0 < len(content) <= MAX_FINAL_BYTES or sha256(content).hexdigest() != draft.get("sha256"):
        raise WorkspaceFinalBytesError("El SHA-256 del archivo guardado no coincide con la revisión.")
    try:
        with ZipFile(BytesIO(content)) as archive:
            expected = "word/document.xml" if docx else "xl/workbook.xml"
            if expected not in archive.namelist():
                raise WorkspaceFinalBytesError("La revisión no corresponde al tipo de plantilla declarado.")
    except BadZipFile as exc:
        raise WorkspaceFinalBytesError("El archivo original revisado no es un Office válido.") from exc
    return content, DOCX_MEDIA_TYPE if docx else XLSX_MEDIA_TYPE, {
        "workspace_document_id": str(document.id),
        "workspace_document_version": document.version,
        "workspace_revision_sha256": draft["sha256"],
        "workspace_map_sha256": config_hash,
        "workspace_source_sha256": draft["source_sha256"],
    }
