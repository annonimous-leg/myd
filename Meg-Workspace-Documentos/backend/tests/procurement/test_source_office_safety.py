"""Exercise the public source extractor with real Office packages."""
from io import BytesIO
from types import SimpleNamespace
from unittest.mock import AsyncMock, patch
from uuid import uuid4
from zipfile import ZIP_DEFLATED, ZipFile

import pytest
from docx import Document
from openpyxl import Workbook

from app.engines.procurement.source_extract import TenderSourceExtractor


def office(kind):
    stream = BytesIO()
    if kind == "docx":
        document = Document()
        document.add_paragraph("REQUISITOS DE PARTICIPACIÓN")
        document.add_paragraph("R-01 - Presentar experiencia")
        document.save(stream)
    else:
        workbook = Workbook()
        workbook.active.append(["Clave", "Descripción", "Obligatorio"])
        workbook.active.append(["R-01", "Presentar experiencia", "Sí"])
        workbook.save(stream)
    return stream.getvalue()


def append_part(original, name, data):
    result = BytesIO()
    with ZipFile(BytesIO(original)) as source, ZipFile(result, "w", ZIP_DEFLATED) as target:
        for entry in source.infolist():
            target.writestr(entry, source.read(entry))
        target.writestr(name, data)
    return result.getvalue()


@pytest.mark.parametrize("kind", ["docx", "xlsx"])
def test_normal_office_sources_keep_text_and_source_coordinates(kind):
    raw = office(kind)
    extracted = TenderSourceExtractor().extract(f"bases.{kind}", "application/octet-stream", raw)
    assert "Presentar experiencia" in extracted.text
    assert extracted.metadata["format"] == kind
    assert extracted.metadata["blocks"]


@pytest.mark.parametrize("kind,part", [("docx", "word/vbaProject.bin"), ("xlsx", "xl/vbaProject.bin"), ("xlsx", "xl/macrosheets/sheet1.xml")])
def test_active_office_parts_are_rejected_before_library_parsing(kind, part):
    raw = append_part(office(kind), part, b"untrusted active content")
    with pytest.raises(ValueError, match="activ|macro"):
        TenderSourceExtractor().extract(f"bases.{kind}", "application/octet-stream", raw)


@pytest.mark.parametrize("kind", ["docx", "xlsx"])
def test_expanded_size_is_bounded_before_parsing(kind):
    with patch.object(TenderSourceExtractor, "MAX_OFFICE_EXPANDED_BYTES", 512, create=True):
        with pytest.raises(ValueError, match="descompresi"):
            TenderSourceExtractor().extract(f"bases.{kind}", "application/octet-stream", office(kind))


@pytest.mark.parametrize("kind", ["docx", "xlsx"])
def test_entry_count_is_bounded_before_parsing(kind):
    with patch.object(TenderSourceExtractor, "MAX_OFFICE_ENTRIES", 1, create=True):
        with pytest.raises(ValueError, match="descompresi"):
            TenderSourceExtractor().extract(f"bases.{kind}", "application/octet-stream", office(kind))


@pytest.mark.parametrize("name", ["../outside.xml", "/absolute.xml", "word/../outside.xml"])
def test_ambiguous_zip_paths_are_rejected(name):
    raw = append_part(office("docx"), name, b"outside")
    with pytest.raises(ValueError, match="ZIP"):
        TenderSourceExtractor().extract("bases.docx", "application/octet-stream", raw)


def test_macro_extension_is_not_silently_imported_as_xlsx():
    with pytest.raises(ValueError, match="macro"):
        TenderSourceExtractor().extract("bases.xlsm", "application/octet-stream", office("xlsx"))


@pytest.mark.parametrize("kind", ["docx", "xlsx"])
def test_invalid_archive_reports_a_document_validation_error(kind):
    with pytest.raises(ValueError, match="Office"):
        TenderSourceExtractor().extract(f"bases.{kind}", "application/octet-stream", b"not an Office archive")


def test_passive_signature_part_is_preserved_as_evidence_not_treated_as_approval():
    raw = append_part(office("docx"), "_xmlsignatures/sig1.xml", b"<signature/>")
    extracted = TenderSourceExtractor().extract("bases.docx", "application/octet-stream", raw)
    assert "Presentar experiencia" in extracted.text
    assert "approved" not in extracted.metadata


@pytest.mark.asyncio
@pytest.mark.parametrize("filename,content", [("bases.docx", b"invalid"), ("bases.xlsm", b"invalid")])
async def test_service_returns_422_without_storing_or_committing_invalid_sources(filename, content):
    from app.core.errors import ErrorCode, MegalodonException
    from app.services.procurement.service import ProcurementService

    db = AsyncMock()
    db.scalar.return_value = None
    service = ProcurementService(db, SimpleNamespace(id=uuid4(), tenant_id=uuid4()))
    tender = SimpleNamespace(id=uuid4(), frozen=False, state="DISCOVERED")
    service._get = AsyncMock(return_value=tender)
    with patch("app.services.procurement.service.storage_documentos") as storage:
        with pytest.raises(MegalodonException) as error:
            await service.ingest_source(tender.id, filename, "application/octet-stream", content)
        assert error.value.status_code == 422
        assert error.value.code == ErrorCode.ARCHIVO_ERROR
        storage.assert_not_called()
        db.commit.assert_not_awaited()
