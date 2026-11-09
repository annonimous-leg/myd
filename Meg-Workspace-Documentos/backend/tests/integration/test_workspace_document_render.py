from hashlib import sha256
from io import BytesIO
from uuid import uuid4

import pytest
from pypdf import PdfReader

from app.models.procurement import JurisdictionProfile, TenderPackage
from app.services.procurement.workspace import TenderWorkspaceService
from tests.conftest import _login
from tests.integration.test_closure_two_tenants import make_expediente


@pytest.mark.asyncio
async def test_workspace_pdf_versions_use_edited_fields_and_identical_downloads(
    async_client, db_session, tenant_a_user, tenant_b_user
):
    tenant, user = tenant_a_user
    _, outsider = tenant_b_user
    exp = make_expediente(tenant, user)
    db_session.add(exp)
    await db_session.flush()
    code = f"MX-TEST-{uuid4().hex[:8].upper()}"
    db_session.add(JurisdictionProfile(
        tenant_id=tenant.id, code=code, authority="Dependencia", government_level="STATE",
        matter="PUBLIC_WORKS", profile_version="1", active=True,
        templates={"format_definitions": [{
            "format_code": "DA-01", "title": "Carta de interés", "compiler": "compile_annex_pdf",
            "canonical_paths": ["bidder.representative_name", "bidder.representative_role"],
        }]},
    ))
    tender = TenderPackage(
        tenant_id=tenant.id, expediente_id=exp.id, identifier=f"TP-{uuid4().hex}",
        title="Proyecto", jurisdiction_code=code, current_revision=1,
        canonical_model={"bidder": {"representative_name": "Ana López"}},
    )
    db_session.add(tender)
    await db_session.commit()
    doc = await TenderWorkspaceService(db_session, user).open_or_create(tender.id, "DA-01", "Carta de interés")
    url = f"/api/v1/procurement/tenders/{tender.id}/workspace/documents/{doc.id}"
    headers = await _login(async_client, user.email)
    outsider_headers = await _login(async_client, outsider.email)
    editor = await async_client.get(f"{url}/editor", headers=headers)
    assert editor.status_code == 200, editor.text
    assert editor.json()["fields"][0]["value"] == "Ana López"
    payload = {"expected_row_version": doc.row_version, "values": {
        "bidder.representative_name": "María Núñez", "bidder.representative_role": "Directora de obra",
    }}
    denied = await async_client.post(f"{url}/render", headers=headers, json={
        **payload, "values": {**payload["values"], "economic.budget_total": "1"},
    })
    assert denied.status_code == 422
    saved = await async_client.post(f"{url}/render", headers=headers, json=payload)
    assert saved.status_code == 200, saved.text
    version = saved.json()["version"]
    file_url = f"{url}/versions/{version}/file"
    preview = await async_client.get(file_url, headers=headers)
    download = await async_client.get(file_url + "?download=true", headers=headers)
    assert preview.status_code == download.status_code == 200
    assert preview.content == download.content
    assert sha256(preview.content).hexdigest() == saved.json()["sha256"]
    assert download.headers["content-disposition"].startswith("attachment")
    history = await async_client.get(f"{url}/history", headers=headers)
    assert history.status_code == 200
    assert "workspace_pdf" not in history.json()[0]["metadata"]
    assert history.json()[0]["content_model"]["field_overrides"] == payload["values"]
    rendered = "\n".join(p.extract_text() for p in PdfReader(BytesIO(preview.content)).pages)
    assert "María Núñez" in rendered and "Directora de obra" in rendered and "Ana López" not in rendered
    assert (await async_client.get(file_url, headers=outsider_headers)).status_code == 404
    assert (await async_client.post(f"{url}/render", headers=headers, json=payload)).status_code == 409
    new_payload = {"expected_row_version": saved.json()["row_version"],
                   "values": {**payload["values"], "bidder.representative_name": "Luisa Ruiz"}}
    assert (await async_client.post(f"{url}/render", headers=headers, json=new_payload)).status_code == 200
    assert (await async_client.get(file_url, headers=headers)).content == preview.content


@pytest.mark.asyncio
@pytest.mark.parametrize("format_name", ["docx", "xlsx"])
async def test_workspace_template_uses_verified_tender_source_and_keeps_old_revisions(
    async_client, db_session, tenant_a_user, tenant_b_user, monkeypatch, format_name,
):
    from unittest.mock import AsyncMock
    from lxml import etree
    from app.engines.procurement.workspace_docx import WORD
    from app.models.procurement import TenderEvidence
    from tests.unit.test_workspace_docx import fixture, package_parts

    tenant, user = tenant_a_user
    _, outsider = tenant_b_user
    exp = make_expediente(tenant, user)
    db_session.add(exp)
    await db_session.flush()
    code = f"MX-TEST-{uuid4().hex[:8].upper()}"
    if format_name == "xlsx":
        from openpyxl import Workbook, load_workbook
        workbook = Workbook()
        sheet = workbook.active
        sheet.append(["Nombre", "Cargo", "=1+2", "Precio"])
        buffer = BytesIO()
        workbook.save(buffer)
        original = buffer.getvalue()
        fields = {
            "bidder.name": {"sheet": "Sheet", "cell": "A1", "label": "Representante"},
            "bidder.role": {"sheet": "Sheet", "cell": "B1", "label": "Cargo"},
            "economic.precio_unitario": {"sheet": "Sheet", "cell": "D1", "label": "Precio",
                                         "type": "number", "partida_numero": "01"},
        }
    else:
        original = fixture()
        fields = {
            "bidder.name": {"tag": "signer", "label": "Representante"},
            "bidder.role": {"tag": "title", "label": "Cargo"},
        }
    source_hash = sha256(original).hexdigest()
    db_session.add(JurisdictionProfile(
        tenant_id=tenant.id, code=code, authority="Dependencia", government_level="STATE",
        matter="PUBLIC_WORKS", profile_version="1", active=True,
        templates={"format_definitions": [{
            "format_code": "DA-01", "title": "Carta de interés", "compiler": "compile_annex_pdf",
            f"workspace_{format_name}": {
                "version": "1", "source_sha256": source_hash, "fields": fields,
            },
        }]},
    ))
    tender = TenderPackage(
        tenant_id=tenant.id, expediente_id=exp.id, identifier=f"TP-{uuid4().hex}",
        title="Proyecto", jurisdiction_code=code, current_revision=1,
        canonical_model={
            "bidder": {"name": "Ana López", "role": "Directora"},
            "economic": {"partidas": [{"numero": "01", "precio_unitario": 123.45}]},
        },
    )
    db_session.add(tender)
    await db_session.flush()
    path = f"tenders/{tenant.id}/{tender.id}/sources/r1/{source_hash[:16]}-Formato oficial.{format_name}"
    await db_session.commit()
    headers = await _login(async_client, user.email)
    outsider_headers = await _login(async_client, outsider.email)
    workspace_url = f"/api/v1/procurement/tenders/{tender.id}/workspace"
    templates = await async_client.get(f"{workspace_url}/document-templates", headers=headers)
    assert templates.status_code == 200, templates.text
    assert templates.json() == [{"artifact_code": "DA-01", "name": "Carta de interés"}]
    assert (await async_client.get(f"{workspace_url}/document-templates", headers=outsider_headers)).status_code == 404
    opened = await async_client.post(f"{workspace_url}/documents", headers=headers, json=templates.json()[0])
    assert opened.status_code == 201, opened.text
    doc = opened.json()
    url = f"{workspace_url}/documents/{doc['id']}"
    editor = (await async_client.get(f"{url}/editor", headers=headers)).json()
    assert editor["render_format"] == format_name
    payload = {
        "expected_row_version": doc["row_version"], "template_token": editor["template_token"],
        "values": {"bidder.name": "María Núñez"},
    }
    assert (await async_client.post(f"{url}/render", headers=headers, json=payload)).status_code == 404
    db_session.add(TenderEvidence(
        tenant_id=tenant.id, tender_id=tender.id, kind="SOURCE_DOCUMENT", subject="Formato",
        value={"size_bytes": len(original)}, source_uri=path, source_hash=source_hash, status="ACTIVE",
    ))
    await db_session.commit()
    storage = AsyncMock()
    storage.descargar.return_value = bytes(len(original))
    monkeypatch.setattr("app.services.procurement.workspace.storage_documentos", lambda: storage)
    assert (await async_client.post(f"{url}/render", headers=headers, json=payload)).status_code == 409
    storage.descargar.return_value = original
    assert (await async_client.post(f"{url}/render", headers=headers,
                                   json={**payload, "template_token": "0" * 64})).status_code == 409
    if format_name == "xlsx":
        assert {"path": "economic.precio_unitario", "label": "Precio", "value": "123.45",
                "max_length": 2000, "read_only": True} in editor["fields"]
        forbidden = {**payload, "values": {"economic.precio_unitario": "1"}}
        assert (await async_client.post(f"{url}/render", headers=headers, json=forbidden)).status_code == 422
    saved = await async_client.post(f"{url}/render", headers=headers, json=payload)
    assert saved.status_code == 200, saved.text
    storage.descargar.assert_awaited_with(path)
    draft = saved.json()
    file_url = f"{url}/versions/{draft['version']}/file"
    download = await async_client.get(file_url, headers=headers)
    assert download.status_code == 200
    assert download.headers["content-disposition"].endswith(f'.{format_name}"')
    assert download.headers["content-disposition"].startswith("attachment")
    assert sha256(download.content).hexdigest() == draft["sha256"]
    if format_name == "xlsx":
        sheet = load_workbook(BytesIO(download.content)).active
        assert [cell.value for cell in sheet[1]] == ["María Núñez", "Directora", "=1+2", 123.45]
    else:
        root = etree.fromstring(package_parts(download.content)["word/document.xml"])
        assert [item.find(".//" + WORD + "t").text for item in root.iter(WORD + "sdt")] == [
            "María Núñez", "Directora",
        ]
    assert (await async_client.get(file_url, headers=outsider_headers)).status_code == 404
    assert (await async_client.post(f"{url}/render", headers=headers, json=payload)).status_code == 409
    updated = await async_client.post(f"{url}/render", headers=headers, json={
        **payload, "expected_row_version": draft["row_version"], "values": {"bidder.name": "Luisa Ruiz"},
    })
    assert updated.status_code == 200, updated.text
    assert updated.json()["sha256"] != draft["sha256"]
    assert (await async_client.get(file_url, headers=headers)).content == download.content
    history = await async_client.get(f"{url}/history", headers=headers)
    assert all(f"workspace_{format_name}" not in item["metadata"] for item in history.json())
    assert history.json()[0]["content_model"][f"{format_name}_field_overrides"] == {"bidder.name": "Luisa Ruiz"}
    assert "field_overrides" not in history.json()[0]["content_model"]
