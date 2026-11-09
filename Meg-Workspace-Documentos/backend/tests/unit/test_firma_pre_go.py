"""Signature evidence regressions: time, immutable renditions, chaining and TSA SSRF."""
from datetime import datetime, timezone
from types import SimpleNamespace
from uuid import uuid4
from hashlib import sha256

import pytest

from app.core.errors import MegalodonException
from app.services.firma_service import FirmaService


class FakeDB:
    def __init__(self):
        self.commits = 0
        self.rollbacks = 0
        self.flushes = 0

    async def commit(self):
        self.commits += 1

    async def rollback(self):
        self.rollbacks += 1

    async def flush(self):
        self.flushes += 1


class FakeStorage:
    def __init__(self, original_path):
        self.data = {original_path: b"%PDF-original"}
        self.uploads = []
        self.deleted = []

    async def descargar(self, path):
        return self.data[path]

    async def subir(self, path, contenido, content_type="application/octet-stream", *, overwrite=True):
        if not overwrite and path in self.data:
            raise AssertionError("immutable path collision")
        self.data[path] = contenido
        self.uploads.append((path, contenido, content_type, overwrite))
        return path

    async def eliminar(self, paths):
        for path in paths:
            self.deleted.append(path)
            self.data.pop(path, None)


@pytest.mark.asyncio
async def test_successive_signatures_are_unique_cumulative_and_use_real_signing_time(monkeypatch):
    original_path = f"tenant/test/{uuid4()}/documento.pdf"
    document = SimpleNamespace(
        id=uuid4(),
        storage_path=original_path,
        metadatos={},
        cifrado=False,
        nonce_cifrado=None,
        tag_cifrado=None,
        hash_sha256=sha256(b"%PDF-original").hexdigest(),
    )
    storage = FakeStorage(original_path)
    db = FakeDB()
    service = FirmaService(db)

    async def get_document(_, **kwargs):
        return document
    async def authorize(*args):
        return uuid4()

    cert = SimpleNamespace(
        rfc="RFC010101ABC",
        nombre="Firmante",
        vigencia_inicio=datetime(2020, 1, 1, tzinfo=timezone.utc),
        vigencia_fin=datetime(2030, 1, 1, tzinfo=timezone.utc),
    )
    service._obtener_documento = get_document
    service._autorizar_firma = authorize
    service.modulo.cargar_certificado_fiel = lambda *args, **kwargs: cert
    service.modulo.firmar_documento_pdf = (
        lambda *, pdf_bytes, **kwargs: pdf_bytes + b"|signed|"
    )
    monkeypatch.setattr(
        "app.services.firma_service.storage_documentos",
        lambda: storage,
    )

    before = datetime.now(timezone.utc)
    first = await service.firmar_documento(
        documento_id=document.id,
        certificado_cer=b"cer",
        certificado_key=b"key",
        password="secret",
        usuario_id=uuid4(),
        usar_tsa=False,
    )
    second = await service.firmar_documento(
        documento_id=document.id,
        certificado_cer=b"cer",
        certificado_key=b"key",
        password="secret",
        usuario_id=uuid4(),
        usar_tsa=False,
    )
    after = datetime.now(timezone.utc)

    assert first["storage_path_firmado"] != second["storage_path_firmado"]
    assert all(upload[3] is False for upload in storage.uploads)
    assert storage.data[first["storage_path_firmado"]] == b"%PDF-original|signed|"
    assert storage.data[second["storage_path_firmado"]] == b"%PDF-original|signed||signed|"

    recorded = datetime.fromisoformat(first["fecha_firma"])
    assert before <= recorded <= after
    assert recorded != cert.vigencia_inicio

    signatures = document.metadatos["firmas"]
    assert len(signatures) == 2
    assert signatures[0]["storage_path_origen_firma"] == original_path
    assert signatures[1]["storage_path_origen_firma"] == first["storage_path_firmado"]
    assert signatures[0]["sha256_firmado"] == first["sha256_firmado"]
    assert signatures[1]["sha256_firmado"] == second["sha256_firmado"]


@pytest.mark.asyncio
async def test_caller_owned_signature_transaction_flushes_without_committing(monkeypatch):
    original_path = f"tenant/test/{uuid4()}/artifact.pdf"
    document = SimpleNamespace(
        id=uuid4(),
        storage_path=original_path,
        storage_bucket="exports",
        metadatos={},
        cifrado=False,
        nonce_cifrado=None,
        tag_cifrado=None,
        hash_sha256=sha256(b"%PDF-original").hexdigest(),
    )
    storage = FakeStorage(original_path)
    db = FakeDB()
    service = FirmaService(db)

    async def get_document(_, **kwargs):
        return document

    async def authorize(*args):
        return uuid4()

    cert = SimpleNamespace(
        rfc="RFC010101ABC",
        nombre="Firmante",
        vigencia_inicio=datetime(2020, 1, 1, tzinfo=timezone.utc),
        vigencia_fin=datetime(2030, 1, 1, tzinfo=timezone.utc),
    )
    service._obtener_documento = get_document
    service._autorizar_firma = authorize
    service.modulo.cargar_certificado_fiel = lambda *args, **kwargs: cert
    service.modulo.firmar_documento_pdf = lambda *, pdf_bytes, **kwargs: pdf_bytes + b"|signed|"
    monkeypatch.setattr("app.services.firma_service.settings.SUPABASE_BUCKET_DOCUMENTOS", "documents")
    monkeypatch.setattr("app.services.firma_service.settings.SUPABASE_BUCKET_EXPORTS", "exports")
    monkeypatch.setattr(
        "app.services.firma_service.storage_exportaciones",
        lambda: storage,
    )

    result = await service.firmar_documento(
        documento_id=document.id,
        certificado_cer=b"cer",
        certificado_key=b"key",
        password="secret",
        usuario_id=uuid4(),
        usar_tsa=False,
        commit=False,
    )

    assert result["storage_path_firmado"] in storage.data
    assert db.flushes == 1
    assert db.commits == 0


@pytest.mark.asyncio
async def test_request_cannot_choose_arbitrary_tsa(monkeypatch):
    original_path = f"tenant/test/{uuid4()}/documento.pdf"
    document = SimpleNamespace(
        id=uuid4(),
        storage_path=original_path,
        metadatos={},
        cifrado=False,
        nonce_cifrado=None,
        tag_cifrado=None,
        hash_sha256=sha256(b"%PDF-original").hexdigest(),
    )
    storage = FakeStorage(original_path)
    service = FirmaService(FakeDB())

    async def get_document(_, **kwargs):
        return document
    async def authorize(*args):
        return uuid4()

    service._obtener_documento = get_document
    service._autorizar_firma = authorize
    monkeypatch.setattr(
        "app.services.firma_service.storage_documentos",
        lambda: storage,
    )

    with pytest.raises(MegalodonException) as exc:
        await service.firmar_documento(
            documento_id=document.id,
            certificado_cer=b"cer",
            certificado_key=b"key",
            password="secret",
            usuario_id=uuid4(),
            usar_tsa=True,
            tsa_url="http://127.0.0.1:8080/internal",
        )

    assert exc.value.status_code == 422
    assert storage.uploads == []


@pytest.mark.asyncio
async def test_legacy_signed_rendition_requires_complete_current_trust_policy(monkeypatch):
    original_path = f"tenant/test/{uuid4()}/documento.pdf"
    signed_path = f"{original_path}.firmado.pdf"
    document = SimpleNamespace(storage_path=original_path)
    storage = FakeStorage(original_path)
    storage.data[signed_path] = b"%PDF-legacy-signed"
    service = FirmaService(FakeDB())
    policy_calls = []

    async def fake_crypto_call(function, *args, **kwargs):
        policy_calls.append(function.__name__)
        return function(*args, **kwargs)

    service._crypto_call = fake_crypto_call
    service.modulo.validar_firma_pdf = lambda content: {
        "aceptacion_completa": content == b"%PDF-legacy-signed"
    }
    monkeypatch.setattr(
        "app.services.firma_service.storage_documentos",
        lambda: storage,
    )

    content = await service._signed_content(
        document,
        {"storage_path_firmado": signed_path},
        uuid4(),
    )

    assert content == b"%PDF-legacy-signed"
    assert policy_calls == ["<lambda>"]


@pytest.mark.asyncio
async def test_legacy_signed_rendition_is_rejected_when_current_trust_policy_fails(monkeypatch):
    original_path = f"tenant/test/{uuid4()}/documento.pdf"
    signed_path = f"{original_path}.firmado.pdf"
    document = SimpleNamespace(storage_path=original_path)
    storage = FakeStorage(original_path)
    storage.data[signed_path] = b"%PDF-untrusted-legacy"
    service = FirmaService(FakeDB())

    async def fake_crypto_call(function, *args, **kwargs):
        return function(*args, **kwargs)

    service._crypto_call = fake_crypto_call
    service.modulo.validar_firma_pdf = lambda content: {
        "aceptacion_completa": False
    }
    monkeypatch.setattr(
        "app.services.firma_service.storage_documentos",
        lambda: storage,
    )

    with pytest.raises(MegalodonException, match="política de confianza/revocación") as exc:
        await service._signed_content(
            document,
            {"storage_path_firmado": signed_path},
            uuid4(),
        )

    assert exc.value.status_code == 409


@pytest.mark.asyncio
async def test_versioned_signed_rendition_without_hash_is_rejected(monkeypatch):
    original_path = f"tenant/test/{uuid4()}/documento.pdf"
    signed_path = f"{original_path}.firmado.{uuid4()}.pdf"
    document = SimpleNamespace(storage_path=original_path)
    storage = FakeStorage(original_path)
    storage.data[signed_path] = b"%PDF-versioned-signed"
    service = FirmaService(FakeDB())
    validation_calls = []

    async def fake_crypto_call(function, *args, **kwargs):
        validation_calls.append(function.__name__)
        return function(*args, **kwargs)

    service._crypto_call = fake_crypto_call
    service.modulo.validar_firma_pdf = lambda content: {"aceptacion_completa": True}
    monkeypatch.setattr(
        "app.services.firma_service.storage_documentos",
        lambda: storage,
    )

    with pytest.raises(MegalodonException, match="carece de una huella verificable") as exc:
        await service._signed_content(
            document,
            {"firma_id": str(uuid4()), "storage_path_firmado": signed_path},
            uuid4(),
        )

    assert exc.value.status_code == 409
    assert validation_calls == []


@pytest.mark.asyncio
async def test_multiple_unverifiable_legacy_signatures_cannot_be_extended(monkeypatch):
    original_path = f"tenant/test/{uuid4()}/documento.pdf"
    document = SimpleNamespace(
        id=uuid4(),
        storage_path=original_path,
        metadatos={
            "firmas": [
                {"storage_path_firmado": f"{original_path}.firmado.pdf"},
                {"storage_path_firmado": f"{original_path}.firmado.pdf"},
            ]
        },
    )
    storage = FakeStorage(original_path)
    service = FirmaService(FakeDB())

    async def get_document(*args, **kwargs):
        return document

    async def authorize(*args, **kwargs):
        return uuid4()

    service._obtener_documento = get_document
    service._autorizar_firma = authorize
    monkeypatch.setattr(
        "app.services.firma_service.storage_documentos",
        lambda: storage,
    )

    with pytest.raises(MegalodonException, match="varias firmas sin huellas independientes") as exc:
        await service.firmar_documento(
            documento_id=document.id,
            certificado_cer=b"cer",
            certificado_key=b"key",
            password="secret",
            usuario_id=uuid4(),
            usar_tsa=False,
        )

    assert exc.value.status_code == 409
    assert storage.uploads == []
    assert service.db.rollbacks == 1



@pytest.mark.asyncio
async def test_pades_verification_report_is_persisted_with_signed_rendition(monkeypatch):
    original_path = f"tenant/test/{uuid4()}/evidence.pdf"
    original_bytes = b"%PDF-original"
    document = SimpleNamespace(
        id=uuid4(), storage_path=original_path, storage_bucket="documentos",
        metadatos={}, cifrado=False, nonce_cifrado=None, tag_cifrado=None,
        hash_sha256=sha256(original_bytes).hexdigest(),
    )
    storage = FakeStorage(original_path)
    storage.data[original_path] = original_bytes
    service = FirmaService(FakeDB())

    async def get_document(*_args, **_kwargs):
        return document
    async def authorize(*_args, **_kwargs):
        return uuid4()
    certificate = SimpleNamespace(
        rfc="RFC010101ABC", nombre="Firmante de prueba",
        vigencia_inicio=datetime(2026, 1, 1, tzinfo=timezone.utc),
        vigencia_fin=datetime(2030, 1, 1, tzinfo=timezone.utc),
    )
    service._obtener_documento = get_document
    service._autorizar_firma = authorize
    service.modulo.cargar_certificado_fiel = lambda *_args, **_kwargs: certificate

    async def crypto_call(function, *args, **kwargs):
        return function(*args, **kwargs)
    service._crypto_call = crypto_call

    class VerifiedPadesSigner:
        def __init__(self, *_args, **_kwargs):
            pass
        def sign_pades_lt(self, source, destination, **_kwargs):
            from pathlib import Path
            Path(destination).write_bytes(Path(source).read_bytes() + b"|pades-lta|")
            return {
                "success": True, "verified": True, "profile": "PAdES-B-LTA",
                "tsa_url": "http://timestamp.digicert.com",
                "validation": {"signature_intact": True, "signature_trusted": True,
                    "timestamp_trusted": True, "revocation_data_embedded": True,
                    "ltv_profile_valid": True},
            }
        def cleanup(self):
            pass

    monkeypatch.setattr("app.services.firma_service.PAdESLTSigner", VerifiedPadesSigner)
    monkeypatch.setattr("app.services.firma_service.storage_documentos", lambda: storage)
    await service.firmar_documento(
        documento_id=document.id, certificado_cer=b"test-certificate",
        certificado_key=b"test-private-key", password="test-only",
        usuario_id=uuid4(), usar_tsa=True)
    assert document.metadatos["firmas"][0]["validacion_pades"]["ltv_profile_valid"] is True
