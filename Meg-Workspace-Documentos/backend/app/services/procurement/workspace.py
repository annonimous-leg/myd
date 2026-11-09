from __future__ import annotations
from base64 import b64decode, b64encode
from binascii import Error as Base64Error
from hashlib import sha256
import json
from math import isfinite
import re
from anyio import to_thread
from uuid import UUID
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from app.core.errors import ErrorCode, MegalodonException
from app.models.procurement import TenderPackage, TenderDocument, TenderDocumentRevision, TenderRequirement, TenderEvidence, TenderArtifact

from app.engines.procurement.format_field_map import load_format_catalog, resolve_format
from app.engines.procurement.workspace_pdf import render_workspace_pdf
from app.engines.procurement.workspace_docx import Field, TemplateError, render_draft
from app.engines.procurement.workspace_xlsx import render_xlsx
from app.integrations.supabase_storage import storage_documentos, storage_exportaciones


_FIELD_LABELS = {
    "bidder.representative_name": "Nombre del representante",
    "bidder.representative_role": "Cargo del representante",
    "bidder.representative.name": "Nombre del representante",
    "bidder.representative.role": "Cargo del representante",
    "bidder.legal_name": "Razón social",
    "technical.planning": "Planeación integral",
    "technical.construction_method": "Procedimiento constructivo",
}
_MAX_FIELD_LENGTH = 2000
_MAX_DRAFT_BYTES = 128 * 1024
_MAX_DOCX_DRAFT_BYTES = 512 * 1024
_DOCX_TYPE = "application/vnd.openxmlformats-officedocument.wordprocessingml.document"
_PDF_TYPE = "application/pdf"
_XLSX_TYPE = "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"


def _field_value(model: dict, path: str) -> str:
    value = model
    for segment in path.split("."):
        value = value.get(segment) if isinstance(value, dict) else None
    return value if isinstance(value, str) else ""


def _budget_field(model: dict, path: str, number: str) -> str:
    economic = model.get("economic") or {}
    matches = [row for row in economic.get("partidas") or []
               if isinstance(row, dict) and str(row.get("numero")) == number]
    value = matches[0].get(path.split(".")[-1]) if len(matches) == 1 else None
    return str(value) if type(value) in (int, float) and isfinite(value) else ""


def _template_token(template: dict | None, fields: list[dict]) -> str | None:
    if not template:
        return None
    budget = {field["path"]: field["value"] for field in fields if field["read_only"]}
    return model_hash({"template": template, "budget": budget}) if budget else model_hash(template)


def model_hash(model: dict) -> str:
    return sha256(json.dumps(model or {}, sort_keys=True, default=str, separators=(",", ":")).encode()).hexdigest()

class TenderWorkspaceService:
    def __init__(self, db: AsyncSession, user):
        self.db, self.user = db, user

    async def tender(self, tender_id: UUID, lock: bool=False) -> TenderPackage:
        q = select(TenderPackage).where(TenderPackage.id == tender_id, TenderPackage.tenant_id == self.user.tenant_id)
        if lock: q = q.with_for_update()
        row = await self.db.scalar(q)
        if row is None: raise MegalodonException(ErrorCode.DOCUMENTO_NO_ENCONTRADO, "TenderPackage no encontrado.", 404)
        return row

    async def list_documents(self, tender_id: UUID) -> list[TenderDocument]:
        await self.tender(tender_id)
        return list((await self.db.scalars(select(TenderDocument).where(TenderDocument.tender_id == tender_id, TenderDocument.tenant_id == self.user.tenant_id).order_by(TenderDocument.artifact_code, TenderDocument.version.desc()))).all())

    async def document_templates(self, tender_id: UUID) -> list[dict]:
        tender = await self.tender(tender_id)
        if not tender.jurisdiction_code or tender.frozen:
            return []
        try:
            catalog = await load_format_catalog(
                self.db, tenant_id=self.user.tenant_id, jurisdiction_code=tender.jurisdiction_code,
            )
        except ValueError:
            return []
        return [{"artifact_code": code, "name": binding.get("title") or code}
                for code, binding in catalog.items() if {"workspace_docx", "workspace_xlsx"} & binding.keys()]

    async def get_document(self, tender_id: UUID, document_id: UUID) -> TenderDocument:
        await self.tender(tender_id)
        row = await self.db.scalar(select(TenderDocument).where(TenderDocument.id == document_id, TenderDocument.tender_id == tender_id, TenderDocument.tenant_id == self.user.tenant_id))
        if row is None: raise MegalodonException(ErrorCode.DOCUMENTO_NO_ENCONTRADO, "Documento de workspace no encontrado.", 404)
        return row

    async def _context(self, tender: TenderPackage, artifact_code: str) -> tuple[list[str], list[str], list[str]]:
        reqs = list((await self.db.scalars(select(TenderRequirement).where(TenderRequirement.tender_id == tender.id, TenderRequirement.tenant_id == self.user.tenant_id))).all())
        evid = list((await self.db.scalars(select(TenderEvidence).where(TenderEvidence.tender_id == tender.id, TenderEvidence.tenant_id == self.user.tenant_id))).all())
        related_reqs = [str(r.id) for r in reqs if artifact_code in (r.artifact_required or [])]
        sources = [str(e.id) for e in evid]
        deps = ["canonical_model.facts", "canonical_model.technical", "canonical_model.economic", "canonical_model.schedule"]
        return sources, related_reqs, deps

    async def open_or_create(self, tender_id: UUID, artifact_code: str, name: str, media_type: str="text/plain") -> TenderDocument:
        tender = await self.tender(tender_id, lock=True)
        row = await self.db.scalar(select(TenderDocument).where(TenderDocument.tender_id == tender.id, TenderDocument.tenant_id == self.user.tenant_id, TenderDocument.artifact_code == artifact_code).order_by(TenderDocument.version.desc()).limit(1))
        if row: return row
        if tender.frozen:
            raise MegalodonException(ErrorCode.CONFLICT, "La licitación está congelada.", 409)
        sources, reqs, deps = await self._context(tender, artifact_code)
        row = TenderDocument(tenant_id=self.user.tenant_id, creado_por_id=self.user.id, actualizado_por_id=self.user.id, tender_id=tender.id, artifact_code=artifact_code, name=name, media_type=media_type, content_text="", content_model={}, status="DRAFT", version=1, tender_revision=tender.current_revision, generated_from_revision=None, generated_model_hash=None, source_evidence_ids=sources, requirement_ids=reqs, data_dependencies=deps)
        self.db.add(row); await self.db.flush()
        self.db.add(TenderDocumentRevision(tenant_id=self.user.tenant_id, document_id=row.id, version=1, operation="CREATE", content_text="", content_model={}, tender_revision=tender.current_revision, human_modified=False, revision_metadata={"created": True}))
        await self.db.commit(); await self.db.refresh(row); return row

    async def update_document(self, tender_id: UUID, document_id: UUID, *, content_text: str, content_model: dict, expected_row_version: int) -> TenderDocument:
        tender = await self.tender(tender_id, lock=True)
        row = await self.get_document(tender_id, document_id)
        if row.locked or tender.frozen: raise MegalodonException(ErrorCode.CONFLICT, "El documento está bloqueado o el TenderPackage está congelado.", 409)
        if row.row_version != expected_row_version: raise MegalodonException(ErrorCode.CONFLICT, "Conflicto de versión del documento; recarga antes de guardar.", 409)
        row.version += 1; row.content_text = content_text; row.content_model = content_model or {}; row.tender_revision = tender.current_revision; row.human_modified = True; row.status = "DRAFT"; row.actualizado_por_id=self.user.id
        await self.db.flush()
        self.db.add(TenderDocumentRevision(tenant_id=self.user.tenant_id, document_id=row.id, version=row.version, operation="HUMAN_EDIT", content_text=content_text, content_model=content_model or {}, tender_revision=tender.current_revision, source_model_hash=model_hash(tender.canonical_model), human_modified=True, revision_metadata={"expected_row_version": expected_row_version}))
        await self.db.commit(); await self.db.refresh(row); return row

    async def _editor_binding(self, tender: TenderPackage, row: TenderDocument) -> dict:
        try:
            return (await resolve_format(
                self.db, tenant_id=self.user.tenant_id, jurisdiction_code=tender.jurisdiction_code,
                code=row.artifact_code,
            ) or {}) if tender.jurisdiction_code else {}
        except ValueError:
            return {}

    def _template_config(self, binding: dict, format_name: str) -> dict | None:
        key = f"workspace_{format_name}"
        if key not in binding:
            return None
        config = binding[key]
        if isinstance(config, dict):
            version, digest, fields = (config.get(key) for key in ("version", "source_sha256", "fields"))
            if (isinstance(version, str) and 0 < len(version.strip()) <= 100
                    and isinstance(digest, str) and re.fullmatch(r"[0-9a-f]{64}", digest)
                    and isinstance(fields, dict) and 0 < len(fields) <= 10
                    and all(isinstance(path, str) and re.fullmatch(r"[a-zA-Z0-9_]+(?:\.[a-zA-Z0-9_]+)+", path)
                            and isinstance(field, dict)
                            and (isinstance(field.get("tag"), str) and 0 < len(field["tag"].strip()) <= 128
                                 if format_name == "docx" else
                                 isinstance(field.get("sheet"), str) and 0 < len(field["sheet"]) <= 31
                                 and isinstance(field.get("cell"), str)
                                 and re.fullmatch(r"[A-Z]{1,3}[1-9][0-9]{0,6}", field["cell"])
                                 and field.get("type", "text") in ("text", "number"))
                            and ("partida_numero" not in field or (
                                format_name == "xlsx" and field.get("type") == "number"
                                and path in {"economic.precio_unitario", "economic.cantidad", "economic.importe"}
                                and isinstance(field["partida_numero"], str) and 0 < len(field["partida_numero"].strip()) <= 100))
                            and isinstance(field.get("label"), str) and 0 < len(field["label"].strip()) <= 150
                            and isinstance(field.get("required", True), bool)
                            for path, field in fields.items())
                    and len({(field.get("sheet"), field.get("cell")) if format_name == "xlsx" else field["tag"] for field in fields.values()}) == len(fields)):
                return config
        raise MegalodonException(ErrorCode.VALIDACION_FALLIDA, "El mapa de la plantilla del anexo es inválido.", 422)

    def _editor_fields(self, tender: TenderPackage, row: TenderDocument,
                       binding: dict, template: dict | None, format_name: str) -> list[dict]:
        if template:
            labels = {path: config["label"] for path, config in template["fields"].items()}
        elif binding.get("compiler") == "compile_annex_pdf":
            labels = {path: _FIELD_LABELS[path] for path in (binding.get("canonical_paths") or [])
                      if isinstance(path, str) and path in _FIELD_LABELS}
        else:
            return []
        override_key = f"{format_name}_field_overrides" if template else "field_overrides"
        overrides = (row.content_model or {}).get(override_key) or {}
        if not isinstance(overrides, dict):
            overrides = {}
        model = tender.canonical_model or {}
        fields = []
        for path, label in labels.items():
            number = template["fields"][path].get("partida_numero") if template else None
            value = overrides.get(path)
            if number is not None:
                value = _budget_field(model, path, number)
            elif not isinstance(value, str):
                value = _field_value(model, path)
            fields.append({"path": path, "label": label, "value": value,
                           "max_length": _MAX_FIELD_LENGTH, "read_only": number is not None})
        return fields

    async def _revision(self, row: TenderDocument, version: int) -> TenderDocumentRevision | None:
        return await self.db.scalar(select(TenderDocumentRevision).where(
            TenderDocumentRevision.tenant_id == self.user.tenant_id,
            TenderDocumentRevision.document_id == row.id,
            TenderDocumentRevision.version == version,
        ))

    async def editor(self, tender_id: UUID, document_id: UUID) -> dict:
        tender = await self.tender(tender_id)
        row = await self.get_document(tender_id, document_id)
        revision = await self._revision(row, row.version)
        metadata = revision.revision_metadata if revision else {}
        draft = metadata.get("workspace_xlsx") or metadata.get("workspace_docx") or metadata.get("workspace_pdf")
        draft_media = _XLSX_TYPE if metadata.get("workspace_xlsx") else _DOCX_TYPE if metadata.get("workspace_docx") else _PDF_TYPE
        binding = await self._editor_binding(tender, row)
        format_name = "xlsx" if "workspace_xlsx" in binding else "docx" if "workspace_docx" in binding else "pdf"
        template = self._template_config(binding, format_name) if format_name != "pdf" else None
        fields = self._editor_fields(tender, row, binding, template, format_name)
        return {
            "id": str(row.id), "name": row.name, "artifact_code": row.artifact_code,
            "version": row.version, "row_version": row.row_version,
            "locked": row.locked or tender.frozen,
            "fields": fields,
            "render_format": format_name,
            "template_token": _template_token(template, fields),
            "file_available": bool(draft or metadata.get("artifact_id") and row.media_type in {_PDF_TYPE, _XLSX_TYPE}),
            "media_type": draft_media if draft else row.media_type,
            "sha256": draft["sha256"] if draft else None,
        }

    async def _render_template(self, tender: TenderPackage, config: dict, fields: list[dict], format_name: str) -> dict:
        source = await self.db.scalar(select(TenderEvidence).where(
            TenderEvidence.tenant_id == self.user.tenant_id,
            TenderEvidence.tender_id == tender.id,
            TenderEvidence.kind == "SOURCE_DOCUMENT",
            TenderEvidence.status == "ACTIVE",
            TenderEvidence.source_hash == config["source_sha256"],
        ))
        prefix = f"tenders/{self.user.tenant_id}/{tender.id}/sources/"
        path = source.source_uri if source else None
        if not path or not path.startswith(prefix) or not re.fullmatch(
            rf"r[0-9]+/{config['source_sha256'][:16]}-[^/\\%?#\x00-\x1f]+", path[len(prefix):],
        ):
            raise MegalodonException(ErrorCode.DOCUMENTO_NO_ENCONTRADO,
                                    "Carga el archivo original configurado en las fuentes de esta licitación.", 404)
        size = (source.value or {}).get("size_bytes")
        if type(size) is not int or not 0 < size <= _MAX_DOCX_DRAFT_BYTES:
            raise MegalodonException(ErrorCode.VALIDACION_FALLIDA, "El archivo original supera el límite de Workspace o no tiene tamaño verificable.", 422)
        original = await storage_documentos().descargar(path)
        if len(original) != size or sha256(original).hexdigest() != config["source_sha256"]:
            raise MegalodonException(ErrorCode.ARCHIVO_ERROR, "El archivo original no coincide con la evidencia.", 409)
        values = {field["path"]: field["value"] for field in fields}
        try:
            if format_name == "xlsx":
                draft = await to_thread.run_sync(render_xlsx, original, config, values)
            else:
                field_map = {key: Field(item["tag"], item.get("required", True))
                             for key, item in config["fields"].items()}
                draft = await to_thread.run_sync(render_draft, original, field_map, values)
        except TemplateError as exc:
            raise MegalodonException(ErrorCode.VALIDACION_FALLIDA, str(exc), 422) from exc
        if len(draft.content) > _MAX_DOCX_DRAFT_BYTES:
            raise MegalodonException(ErrorCode.VALIDACION_FALLIDA, "El borrador supera el límite de Workspace.", 422)
        return {
            "sha256": draft.content_sha256, "content": b64encode(draft.content).decode("ascii"),
            "source_sha256": draft.source_sha256, "source_evidence_id": str(source.id),
            "map_version": config["version"], "map_sha256": model_hash(config),
            "renderer": draft.renderer, "submission_eligible": False,
        }

    async def save_rendered(self, tender_id: UUID, document_id: UUID, *, values: dict[str, str],
                            expected_row_version: int, template_token: str | None = None) -> dict:
        tender = await self.tender(tender_id, lock=True)
        row = await self.get_document(tender_id, document_id)
        if row.locked or tender.frozen:
            raise MegalodonException(ErrorCode.CONFLICT, "El documento está bloqueado.", 409)
        if row.row_version != expected_row_version:
            raise MegalodonException(ErrorCode.CONFLICT, "El documento cambió. Recarga antes de guardar.", 409)
        binding = await self._editor_binding(tender, row)
        format_name = "xlsx" if "workspace_xlsx" in binding else "docx" if "workspace_docx" in binding else "pdf"
        template = self._template_config(binding, format_name) if format_name != "pdf" else None
        fields = self._editor_fields(tender, row, binding, template, format_name)
        if template_token != _template_token(template, fields):
            raise MegalodonException(ErrorCode.CONFLICT, "La plantilla o el presupuesto cambió. Recarga antes de guardar.", 409)
        allowed = {field["path"] for field in fields if not field["read_only"]}
        budget_fields = [field for field in fields if field["read_only"]]
        if (not values and not budget_fields) or not values.keys() <= allowed:
            raise MegalodonException(ErrorCode.VALIDACION_FALLIDA, "Hay campos fuera del formato editable.", 422)
        if any(not field["value"] for field in budget_fields):
            raise MegalodonException(ErrorCode.VALIDACION_FALLIDA, "Faltan partidas vinculadas o sus valores en el presupuesto.", 422)
        if any(len(value) > _MAX_FIELD_LENGTH or (not template and not value.strip()) for value in values.values()):
            raise MegalodonException(ErrorCode.VALIDACION_FALLIDA, "Completa los campos modificados con texto válido.", 422)
        if not template:
            values = {path: value.strip() for path, value in values.items()}
        for field in fields:
            field["value"] = values.get(field["path"], field["value"])
        version = row.version + 1
        if template:
            draft = await self._render_template(tender, template, fields, format_name)
            metadata_key = f"workspace_{format_name}"
            media = _XLSX_TYPE if format_name == "xlsx" else _DOCX_TYPE
        else:
            content = render_workspace_pdf(row.name, tender.identifier, version, fields)
            if len(content) > _MAX_DRAFT_BYTES:
                raise MegalodonException(ErrorCode.VALIDACION_FALLIDA, "El borrador supera el tamaño permitido.", 422)
            draft = {"sha256": sha256(content).hexdigest(), "content": b64encode(content).decode("ascii")}
            metadata_key, media = "workspace_pdf", _PDF_TYPE
        model = dict(row.content_model or {})
        override_key = f"{format_name}_field_overrides" if template else "field_overrides"
        old_overrides = model.get(override_key)
        model[override_key] = {**(old_overrides if isinstance(old_overrides, dict) else {}), **values}
        row.content_model = model
        row.version = version
        row.tender_revision = tender.current_revision
        row.status = "DRAFT"
        row.human_modified = True
        row.actualizado_por_id = self.user.id
        await self.db.flush()
        self.db.add(TenderDocumentRevision(
            tenant_id=self.user.tenant_id, document_id=row.id, version=version,
            operation="HUMAN_EDIT_RENDER", content_text=row.content_text, content_model=model,
            tender_revision=tender.current_revision, source_model_hash=model_hash(tender.canonical_model),
            human_modified=True, revision_metadata={
                "actor_id": str(self.user.id),
                metadata_key: draft,
            },
        ))
        saved = {
            "id": str(row.id), "name": row.name, "artifact_code": row.artifact_code,
            "version": version, "row_version": row.row_version, "locked": False,
            "fields": fields, "file_available": True, "media_type": media, "sha256": draft["sha256"],
            "render_format": format_name, "template_token": template_token,
        }
        await self.db.commit()
        return saved

    async def revision_file(self, tender_id: UUID, document_id: UUID, version: int) -> tuple[bytes, str]:
        row = await self.get_document(tender_id, document_id)
        revision = await self._revision(row, version)
        metadata = revision.revision_metadata if revision else {}
        draft = metadata.get("workspace_xlsx") or metadata.get("workspace_docx") or metadata.get("workspace_pdf")
        draft_media = _XLSX_TYPE if metadata.get("workspace_xlsx") else _DOCX_TYPE if metadata.get("workspace_docx") else _PDF_TYPE
        if draft:
            try:
                content = b64decode(draft["content"], validate=True)
            except (Base64Error, KeyError, TypeError, ValueError) as exc:
                raise MegalodonException(ErrorCode.ARCHIVO_ERROR, "Archivo de revisión inválido.", 409) from exc
            digest = draft.get("sha256")
            media = draft_media
        elif metadata.get("artifact_id"):
            artifact = await self.db.scalar(select(TenderArtifact).where(
                TenderArtifact.id == UUID(metadata["artifact_id"]),
                TenderArtifact.tender_id == tender_id,
                TenderArtifact.tenant_id == self.user.tenant_id,
                TenderArtifact.artifact_code == row.artifact_code,
            ))
            if not artifact or artifact.media_type not in {_PDF_TYPE, _XLSX_TYPE} or not artifact.storage_path:
                raise MegalodonException(ErrorCode.DOCUMENTO_NO_ENCONTRADO, "Esta revisión no tiene archivo.", 404)
            content = await storage_exportaciones().descargar(artifact.storage_path)
            digest, media = artifact.content_hash, artifact.media_type
        else:
            raise MegalodonException(ErrorCode.DOCUMENTO_NO_ENCONTRADO, "Esta revisión no tiene archivo.", 404)
        if sha256(content).hexdigest() != digest:
            raise MegalodonException(ErrorCode.ARCHIVO_ERROR, "El archivo no coincide con la revisión.", 409)
        return content, media

    async def history(self, tender_id: UUID, document_id: UUID) -> list[TenderDocumentRevision]:
        await self.get_document(tender_id, document_id)
        return list((await self.db.scalars(select(TenderDocumentRevision).where(TenderDocumentRevision.document_id == document_id, TenderDocumentRevision.tenant_id == self.user.tenant_id).order_by(TenderDocumentRevision.version.desc()))).all())

    async def regenerate(self, tender_id: UUID, document_id: UUID, *, generated_text: str, generated_model: dict, expected_row_version: int) -> TenderDocument:
        """Import a client-produced draft without claiming server-side generation.

        A real regeneration engine must execute server-side and persist provider,
        model, prompt and source provenance before this operation can mark a
        document as GENERATED. Until then, client content remains a human-owned DRAFT.
        """
        tender = await self.tender(tender_id, lock=True)
        row = await self.get_document(tender_id, document_id)
        if row.locked or tender.frozen:
            raise MegalodonException(ErrorCode.CONFLICT, "El documento está bloqueado o el TenderPackage está congelado.", 409)
        if row.row_version != expected_row_version:
            raise MegalodonException(ErrorCode.CONFLICT, "Conflicto de versión del documento.", 409)
        if row.human_modified:
            row.last_conflict = {
                "kind": "HUMAN_EDIT_WOULD_BE_OVERWRITTEN",
                "document_version": row.version,
                "tender_revision": tender.current_revision,
                "current_model_hash": model_hash(tender.canonical_model),
                "incoming_content_origin": "client_supplied",
            }
            await self.db.commit()
            raise MegalodonException(
                ErrorCode.CONFLICT,
                "Importación bloqueada: existe una edición humana que podría perderse. Revisa el documento o crea una nueva versión.",
                409,
            )
        row.version += 1
        row.content_text = generated_text
        row.content_model = generated_model or {}
        row.tender_revision = tender.current_revision
        row.generated_from_revision = None
        row.generated_model_hash = None
        row.human_modified = True
        row.last_conflict = None
        row.status = "DRAFT"
        row.actualizado_por_id = self.user.id
        await self.db.flush()
        self.db.add(TenderDocumentRevision(
            tenant_id=self.user.tenant_id,
            document_id=row.id,
            version=row.version,
            operation="CLIENT_DRAFT_IMPORT",
            content_text=generated_text,
            content_model=generated_model or {},
            tender_revision=tender.current_revision,
            source_model_hash=None,
            human_modified=True,
            revision_metadata={
                "content_origin": "client_supplied",
                "server_generation_verified": False,
            },
        ))
        await self.db.commit()
        await self.db.refresh(row)
        return row

    async def lock_document(self, tender_id: UUID, document_id: UUID, locked: bool) -> TenderDocument:
        tender=await self.tender(tender_id, lock=True); row=await self.get_document(tender_id, document_id); row.locked=locked; row.status="VALIDATED" if locked else row.status; row.actualizado_por_id=self.user.id; await self.db.commit(); await self.db.refresh(row); return row
