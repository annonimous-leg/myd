from base64 import b64encode
from hashlib import sha256
from io import BytesIO
import json
from types import SimpleNamespace
import unittest
from uuid import UUID
from zipfile import ZipFile

from app.services.procurement.workspace_final_bytes import (
    WorkspaceFinalBytesError, reviewed_workspace_artifact,
    DOCX_MEDIA_TYPE, XLSX_MEDIA_TYPE,
)


def office_bytes(kind: str) -> bytes:
    stream = BytesIO()
    with ZipFile(stream, "w") as z:
        z.writestr("word/document.xml" if kind == "docx" else "xl/workbook.xml", b"<office/>")
    return stream.getvalue()


class WorkspaceFinalBytesTests(unittest.TestCase):
    def setUp(self):
        self.doc = SimpleNamespace(id=UUID("11111111-1111-1111-1111-111111111111"), version=3, human_modified=True, tender_revision=4)
        self.source_model_hash = "c" * 64
        self.template = {"version": "v1", "source_sha256": "a" * 64, "fields": {"bidder.legal_name": {"tag": "legal"}}}

    def setup_revision(self, kind="docx"):
        raw = office_bytes(kind)
        meta = {"source_sha256": self.template["source_sha256"], "map_version": "v1",
                "map_sha256": sha256(json.dumps(self.template, sort_keys=True, default=str, separators=(",", ":")).encode()).hexdigest(),
                "content": b64encode(raw).decode(), "sha256": sha256(raw).hexdigest(),
                "server_recalculated": kind == "xlsx"}
        rev = SimpleNamespace(document_id=self.doc.id, version=3, tender_revision=4, operation="HUMAN_EDIT_RENDER", source_model_hash=self.source_model_hash, revision_metadata={f"workspace_{kind}": meta})
        return rev, raw

    def verify(self, binding, document, revision, tender_revision):
        return reviewed_workspace_artifact(
            binding, document, revision, tender_revision,
            current_source_model_hash=self.source_model_hash,
        )

    def test_changed_canonical_model_requires_new_human_review(self):
        rev, _ = self.setup_revision()
        rev.source_model_hash = "f" * 64
        with self.assertRaises(WorkspaceFinalBytesError):
            self.verify({"workspace_docx": self.template}, self.doc, rev, 4)

    def test_docx_original_bytes_not_regenerated(self):
        rev, original = self.setup_revision()
        data, mime, origin = self.verify({"workspace_docx": self.template}, self.doc, rev, 4)
        self.assertEqual(data, original)
        self.assertEqual(mime, DOCX_MEDIA_TYPE)
        self.assertEqual(origin["workspace_revision_sha256"], sha256(original).hexdigest())

    def test_xlsx_recalc_is_required(self):
        rev, original = self.setup_revision("xlsx")
        self.assertEqual(self.verify({"workspace_xlsx": self.template}, self.doc, rev, 4)[0], original)
        rev.revision_metadata["workspace_xlsx"]["server_recalculated"] = False
        with self.assertRaises(WorkspaceFinalBytesError):
            self.verify({"workspace_xlsx": self.template}, self.doc, rev, 4)

    def test_stale_tender_revision_rejected(self):
        rev, _ = self.setup_revision()
        with self.assertRaises(WorkspaceFinalBytesError):
            self.verify({"workspace_docx": self.template}, self.doc, rev, 5)

    def test_different_template_source_rejected(self):
        rev, _ = self.setup_revision()
        binding = {"workspace_docx": {**self.template, "source_sha256": "b" * 64}}
        with self.assertRaises(WorkspaceFinalBytesError):
            self.verify(binding, self.doc, rev, 4)

    def test_tampered_revision_bytes_rejected(self):
        rev, _ = self.setup_revision()
        rev.revision_metadata["workspace_docx"]["sha256"] = "b" * 64
        with self.assertRaises(WorkspaceFinalBytesError):
            self.verify({"workspace_docx": self.template}, self.doc, rev, 4)

    def test_nonrendered_manual_edit_rejected(self):
        rev, _ = self.setup_revision()
        rev.operation = "HUMAN_EDIT"
        with self.assertRaises(WorkspaceFinalBytesError):
            self.verify({"workspace_docx": self.template}, self.doc, rev, 4)

    def test_wrong_document_revision_id_rejected(self):
        rev, _ = self.setup_revision()
        rev.document_id = UUID("22222222-2222-2222-2222-222222222222")
        with self.assertRaises(WorkspaceFinalBytesError):
            self.verify({"workspace_docx": self.template}, self.doc, rev, 4)

    def test_missing_reviewed_document_rejected(self):
        rev, _ = self.setup_revision()
        with self.assertRaises(WorkspaceFinalBytesError):
            self.verify({"workspace_docx": self.template}, None, rev, 4)

    def test_invalid_media_rejected(self):
        rev, _ = self.setup_revision()
        with self.assertRaises(WorkspaceFinalBytesError):
            self.verify({"workspace_xlsx": self.template}, self.doc, rev, 4)

    def test_two_declared_template_types_rejected(self):
        rev, _ = self.setup_revision()
        with self.assertRaises(WorkspaceFinalBytesError):
            self.verify({"workspace_docx": self.template, "workspace_xlsx": self.template}, self.doc, rev, 4)


if __name__ == "__main__":
    unittest.main()
