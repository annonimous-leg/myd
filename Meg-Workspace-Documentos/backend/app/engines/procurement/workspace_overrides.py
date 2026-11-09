"""Strictly project reviewed Workspace fields onto one artifact's canonical model.

This module deliberately does not render/approve/serve any document. The binary
prepared for delivery must be separately reviewed and pinned by its content hash.
"""
from __future__ import annotations

from copy import deepcopy
from typing import Any


_ALLOWED_EDITOR_KEYS = {
    "workspace_xlsx": "xlsx_field_overrides",
    "workspace_docx": "docx_field_overrides",
}


def model_with_workspace_overrides(
    canonical_model: dict[str, Any],
    binding: dict[str, Any],
    document_content_model: dict[str, Any] | None,
    *,
    human_modified: bool,
    document_tender_revision: int,
    current_tender_revision: int,
) -> tuple[dict[str, Any], list[str]]:
    """Apply editable, explicitly mapped fields for a single artifact.

    Reject stale revisions, undeclared paths and budget-controlled fields; never
    let template-specific overrides accidentally cross into another format.
    Maintains the historical field_overrides key for legacy documents.
    """
    if not human_modified:
        return canonical_model, []
    if not isinstance(document_content_model, dict):
        raise ValueError("Los datos editados del documento son inválidos.")

    template_key = next((key for key in _ALLOWED_EDITOR_KEYS if key in binding), None)
    override_key = _ALLOWED_EDITOR_KEYS.get(template_key, "field_overrides")
    overrides = document_content_model.get(override_key)
    if overrides is None and template_key:
        overrides = document_content_model.get("field_overrides")
    if overrides is None or overrides == {}:
        return canonical_model, []
    if not isinstance(overrides, dict):
        raise ValueError("Los campos editados deben formar un objeto de rutas y valores.")
    if document_tender_revision != current_tender_revision:
        raise ValueError("La edición pertenece a otra revisión del expediente y necesita revisarse de nuevo.")

    allowed_paths = {str(path) for path in binding.get("canonical_paths") or ()}
    template_fields = None
    if template_key:
        template = binding.get(template_key)
        if not isinstance(template, dict) or not isinstance(template.get("fields"), dict):
            raise ValueError("El mapa editable del formato no es válido.")
        template_fields = template["fields"]

    result = deepcopy(canonical_model)
    applied: list[str] = []
    for path in sorted(overrides):
        if not isinstance(path, str) or not path or path not in allowed_paths:
            raise ValueError(f"Campo fuera del catálogo del formato: {path!r}.")
        if template_fields is not None:
            field = template_fields.get(path)
            if not isinstance(field, dict):
                raise ValueError(f"Campo no editable en la plantilla: {path!r}.")
            if field.get("partida_numero") is not None or field.get("read_only") is True:
                raise ValueError(f"Campo presupuestal de solo lectura: {path!r}.")
        value = overrides[path]
        if not isinstance(value, str):
            raise ValueError(f"El campo {path!r} debe contener texto validado.")

        cursor = result
        parts = path.split(".")
        if any(not part for part in parts):
            raise ValueError(f"Ruta canónica inválida: {path!r}.")
        for part in parts[:-1]:
            nested = cursor.get(part)
            if nested is None:
                nested = {}
                cursor[part] = nested
            if not isinstance(nested, dict):
                raise ValueError(f"Ruta canónica incompatible: {path!r}.")
            cursor = nested
        cursor[parts[-1]] = value
        applied.append(path)
    return result, applied
