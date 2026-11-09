"""Real PDF co-signing and persistence with storage as the external boundary."""
import asyncio
from hashlib import sha256
from io import BytesIO
from uuid import uuid4
from datetime import datetime, timedelta, timezone

import pytest
from pyhanko.pdf_utils.reader import PdfFileReader
from sqlalchemy.ext.asyncio import async_sessionmaker

from app.core.crypto import cifrar_sobre
from app.core.errors import MegalodonException
from app.models.expediente import Documento, ExpedienteObra
from app.models.user import UserRole
from app.services.firma_service import FirmaService
from tests.conftest import _create_tenant_and_user, _login
from tests.fixtures.signing import signing_fixture
from tests.integration.test_closure_two_tenants import make_expediente
from tests.unit.test_firma_pre_go import FakeStorage


async def setup_document(db, monkeypatch, *, encrypted=False):
    tenant, user = await _create_tenant_and_user(db, "signature", "signer@example.mx", role=UserRole.ADMIN)
    exp = make_expediente(tenant, user)
    db.add(exp)
    await db.flush()
    fixture = signing_fixture()
    path = f"{tenant.id}/{exp.id}/{uuid4()}.pdf"
    storage = FakeStorage(path)
    storage.data[path] = fixture["pdf"]
    extra = {}
    if encrypted:
        stored, nonce, tag, dek = cifrar_sobre(fixture["pdf"], str(tenant.id))
        storage.data[path] = stored
        extra = dict(cifrado=True, nonce_cifrado=nonce.hex(), tag_cifrado=tag.hex(), encryption_key_enc=dek)
    document = Documento(expediente_id=exp.id, identificador=uuid4().hex,
        nombre="Acceptance.pdf", tipo_documental="ACTA", formato="pdf", storage_path=path,
        storage_bucket="documentos", size_bytes=len(fixture["pdf"]),
        hash_sha256=sha256(fixture["pdf"]).hexdigest(), creado_por_id=user.id, **extra)
    db.add(document)
    await db.commit()
    monkeypatch.setattr("app.services.firma_service.storage_documentos", lambda: storage)
    args = dict(documento_id=document.id, usuario_id=user.id, certificado_cer=fixture["cer"],
        certificado_key=fixture["key"], password=fixture["password"], usar_tsa=False)
    return document, storage, args, tenant.id


@pytest.mark.asyncio
@pytest.mark.parametrize("encrypted", [False, True])
async def test_real_pdf_cosignatures_preserve_both_signatures_and_encryption(db_session, monkeypatch, encrypted):
    doc, storage, args, tenant_id = await setup_document(db_session, monkeypatch, encrypted=encrypted)
    service = FirmaService(db_session)
    await service.firmar_documento(**args)
    await service.firmar_documento(**args)
    await db_session.refresh(doc)
    signatures = doc.metadatos["firmas"]
    assert len(signatures) == 2
    assert signatures[1]["sha256_origen_firma"] == signatures[0]["sha256_firmado"]
    content = await service._signed_content(doc, signatures[-1], tenant_id)
    assert len(PdfFileReader(BytesIO(content)).embedded_signatures) == 2
    result = await service.validar_firma(doc.id)
    # The fixture signs real PDF bytes, but its self-signed certificate is
    # deliberately not an approved trust anchor and carries no revocation evidence.
    assert result["total_firmas"] == 2
    assert result["firmas_validas"] == 0
    assert result["aceptacion_completa"] is False
    assert all(item["intacta"] and item["criptograficamente_valida"] for item in result["detalles"])
    assert all(not item["confiable"] and not item["valida"] for item in result["detalles"])
    if encrypted:
        assert all(f["cifrado"] for f in signatures)
        assert not storage.data[signatures[-1]["storage_path_firmado"]].startswith(b"%PDF")


@pytest.mark.asyncio
async def test_changed_predecessor_is_rejected_without_losing_saved_signature(db_session, monkeypatch):
    doc, storage, args, _ = await setup_document(db_session, monkeypatch)
    service = FirmaService(db_session)
    first = await service.firmar_documento(**args)
    document_id = doc.id
    storage.data[first["storage_path_firmado"]] = b"unrelated content"
    with pytest.raises(MegalodonException, match="SHA-256"):
        await service.firmar_documento(**args)
    doc = await db_session.get(Documento, document_id)
    assert len(doc.metadatos["firmas"]) == len(storage.uploads) == 1


@pytest.mark.asyncio
async def test_concurrent_postgres_cosignatures_form_one_chain(db_session, monkeypatch):
    if db_session.bind.dialect.name != "postgresql":
        pytest.skip("Row-lock acceptance requires PostgreSQL")
    doc, storage, args, tenant_id = await setup_document(db_session, monkeypatch)
    document_id = doc.id
    factory = async_sessionmaker(db_session.bind, expire_on_commit=False)

    async def sign():
        async with factory() as session:
            # Prime both identity maps to verify populate_existing after lock.
            await session.get(Documento, document_id)
            await asyncio.sleep(0)
            return await FirmaService(session).firmar_documento(**args)

    first, second = await asyncio.wait_for(asyncio.gather(sign(), sign()), timeout=30)
    assert first["storage_path_firmado"] != second["storage_path_firmado"]
    await db_session.refresh(doc)
    signatures = doc.metadatos["firmas"]
    assert len(signatures) == 2
    assert signatures[1]["storage_path_origen_firma"] == signatures[0]["storage_path_firmado"]
    assert signatures[1]["sha256_origen_firma"] == signatures[0]["sha256_firmado"]
    content = await FirmaService(db_session)._signed_content(doc, signatures[-1], tenant_id)
    assert len(PdfFileReader(BytesIO(content)).embedded_signatures) == 2


@pytest.mark.asyncio
@pytest.mark.parametrize("committed", [False, True])
async def test_failed_commit_cleanup_never_deletes_a_committed_rendition(db_session, monkeypatch, committed):
    doc, storage, args, _ = await setup_document(db_session, monkeypatch)
    document_id = doc.id
    original_commit = db_session.commit

    async def fail_commit():
        if committed:
            await original_commit()
        raise RuntimeError("Commit acknowledgement unavailable")

    monkeypatch.setattr(db_session, "commit", fail_commit)
    with pytest.raises(RuntimeError, match="acknowledgement"):
        await FirmaService(db_session).firmar_documento(**args)
    doc = await db_session.get(Documento, document_id)
    if committed:
        assert len(doc.metadatos["firmas"]) == 1
        assert doc.metadatos["firmas"][0]["storage_path_firmado"] in storage.data
        assert not storage.deleted
    else:
        assert not (doc.metadatos or {}).get("firmas")
        assert len(storage.deleted) == 1


@pytest.mark.asyncio
async def test_reconciliation_only_removes_old_unreferenced_renditions(db_session, monkeypatch):
    doc, storage, args, _ = await setup_document(db_session, monkeypatch)
    service = FirmaService(db_session)
    signed = await service.firmar_documento(**args)
    document_id, actor_id = doc.id, args['usuario_id']
    directory, _, name = doc.storage_path.rpartition('/')
    old = (datetime.now(timezone.utc) - timedelta(days=2)).isoformat()
    recent = datetime.now(timezone.utc).isoformat()
    orphan = f'{name}.firmado.{uuid4()}.pdf'
    active = f'{name}.firmado.{uuid4()}.pdf'
    undated = f'{name}.firmado.{uuid4()}.pdf'
    objects = [
        {'name': signed['storage_path_firmado'].rsplit('/', 1)[1], 'updated_at': old},
        {'name': orphan, 'updated_at': old},
        {'name': active, 'updated_at': recent},
        {'name': undated},
        {'name': f'{name}.firmado.invalid.pdf', 'updated_at': old},
        {'name': f'other.pdf.firmado.{uuid4()}.pdf', 'updated_at': old},
    ]

    async def listing(path, *, offset):
        assert path == directory
        return objects[offset:offset + 100]

    monkeypatch.setattr(storage, 'listar', listing, raising=False)
    inventory = await service.reconciliar_firmas(document_id, actor_id)
    assert inventory['huerfanos'] == [f'{directory}/{orphan}']
    assert inventory['eliminados'] == 0 and not storage.deleted
    cleanup = await service.reconciliar_firmas(document_id, actor_id, eliminar=True)
    assert cleanup['eliminados'] == 1
    assert storage.deleted == [f'{directory}/{orphan}']
    assert signed['storage_path_firmado'] in storage.data


@pytest.mark.asyncio
@pytest.mark.parametrize('role', [UserRole.ADMIN, UserRole.TECNICO, UserRole.LECTOR])
async def test_merkle_attestation_requires_approval_and_records_actor(async_client, db_session, role):
    tenant, user = await _create_tenant_and_user(db_session, 'merkle-review', 'merkle@example.mx', role=role)
    exp = make_expediente(tenant, user)
    exp.merkle_root = sha256(b'acceptance ledger').hexdigest()
    db_session.add(exp)
    await db_session.commit()
    exp_id, user_id = exp.id, user.id
    fixture = signing_fixture()
    headers = await _login(async_client, user.email)
    response = await async_client.post(f'/api/v1/firma/expedientes/{exp_id}/merkle', headers=headers,
        files={'certificado_cer': ('test.cer', fixture['cer']),
               'certificado_key': ('test.key', fixture['key'])}, data={'password': fixture['password']})
    assert response.status_code == (200 if role == UserRole.ADMIN else 403), response.text
    db_session.expire_all()
    saved = await db_session.get(ExpedienteObra, exp_id)
    signatures = (saved.metadatos or {}).get('firmas_merkle', [])
    if role == UserRole.ADMIN:
        assert len(signatures) == 1
        assert signatures[0]['usuario_id'] == str(user_id)
        assert signatures[0]['merkle_root'] == saved.merkle_root
        assert response.json()['firma_id'] == signatures[0]['firma_id']
    else:
        assert not signatures
