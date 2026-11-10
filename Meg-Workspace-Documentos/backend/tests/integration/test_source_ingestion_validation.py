"""Malformed Office uploads must fail as document errors before persistence."""
from io import BytesIO
from unittest.mock import AsyncMock
from uuid import uuid4
from zipfile import ZIP_DEFLATED, ZipFile

import pytest
from sqlalchemy import func, select

from app.models.procurement import TenderEvidence, TenderPackage
from tests.conftest import _login
from tests.integration.test_closure_two_tenants import make_expediente
from tests.procurement.test_source_office_safety import office


@pytest.mark.asyncio
@pytest.mark.parametrize('kind,part', [('docx', 'word/document.xml'), ('xlsx', 'xl/workbook.xml')])
@pytest.mark.parametrize('damage', ['invalid_xml', 'missing_part'])
async def test_invalid_office_upload_returns_422_without_persisting(
    async_client, db_session, tenant_a_user, monkeypatch, kind, part, damage,
):
    tenant, user = tenant_a_user
    expediente = make_expediente(tenant, user)
    db_session.add(expediente)
    await db_session.flush()
    tender = TenderPackage(tenant_id=tenant.id, expediente_id=expediente.id,
                           identifier=f'UPLOAD-{uuid4().hex}', title='Validation', current_revision=1)
    db_session.add(tender)
    await db_session.commit()
    storage = AsyncMock()
    monkeypatch.setattr('app.services.procurement.service.storage_documentos', storage)
    payload = BytesIO()
    with ZipFile(BytesIO(office(kind))) as source, ZipFile(payload, 'w', ZIP_DEFLATED) as target:
        for entry in source.infolist():
            if entry.filename == part and damage == 'missing_part':
                continue
            target.writestr(entry, b'<broken>' if entry.filename == part else source.read(entry))
    headers = await _login(async_client, user.email)
    response = await async_client.post(f'/api/v1/procurement/tenders/{tender.id}/sources',
        headers=headers, files={'file': (f'broken.{kind}', payload.getvalue(), 'application/octet-stream')})
    assert response.status_code == 422, response.text
    storage.assert_not_called()
    assert await db_session.scalar(select(func.count()).select_from(TenderEvidence).where(
        TenderEvidence.tender_id == tender.id)) == 0
    await db_session.refresh(tender)
    assert tender.state == 'DISCOVERED'
    assert not (tender.source_manifest or {}).get('sources')
