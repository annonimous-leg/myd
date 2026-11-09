"""Storage-bucket routing regressions for document and tender-artifact signatures."""
from types import SimpleNamespace

import pytest

from app.core.errors import MegalodonException
from app.services import firma_service as firma_module
from app.services.firma_service import FirmaService


def test_document_signature_uses_the_bucket_declared_by_document(monkeypatch):
    documents = object()
    exports = object()
    monkeypatch.setattr(firma_module.settings, "SUPABASE_BUCKET_DOCUMENTOS", "documents")
    monkeypatch.setattr(firma_module.settings, "SUPABASE_BUCKET_EXPORTS", "exports")
    monkeypatch.setattr(firma_module, "storage_documentos", lambda: documents)
    monkeypatch.setattr(firma_module, "storage_exportaciones", lambda: exports)

    service = FirmaService(object())

    assert service._storage_for_document(SimpleNamespace(storage_bucket="documents")) is documents
    assert service._storage_for_document(SimpleNamespace(storage_bucket="exports")) is exports


def test_legacy_document_without_bucket_defaults_to_document_bucket(monkeypatch):
    documents = object()
    monkeypatch.setattr(firma_module.settings, "SUPABASE_BUCKET_DOCUMENTOS", "documents")
    monkeypatch.setattr(firma_module.settings, "SUPABASE_BUCKET_EXPORTS", "exports")
    monkeypatch.setattr(firma_module, "storage_documentos", lambda: documents)

    service = FirmaService(object())

    assert service._storage_for_document(SimpleNamespace()) is documents


def test_unrecognized_storage_bucket_fails_closed(monkeypatch):
    monkeypatch.setattr(firma_module.settings, "SUPABASE_BUCKET_DOCUMENTOS", "documents")
    monkeypatch.setattr(firma_module.settings, "SUPABASE_BUCKET_EXPORTS", "exports")
    service = FirmaService(object())

    with pytest.raises(MegalodonException) as exc:
        service._storage_for_document(SimpleNamespace(storage_bucket="untrusted-bucket"))

    assert exc.value.status_code == 409
