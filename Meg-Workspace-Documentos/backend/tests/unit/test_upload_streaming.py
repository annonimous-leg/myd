"""Large upload regressions: validate without accumulating and keep streams reusable."""
from io import BytesIO

import pytest
from starlette.datastructures import UploadFile

from app.core.errors import MegalodonException
from app.utils.upload_limits import validate_upload_with_limit


@pytest.mark.asyncio
async def test_validate_upload_counts_and_rewinds_file_handle():
    payload = b"a" * (2 * 1024 * 1024 + 123)
    upload = UploadFile(filename="modelo.ifc", file=BytesIO(payload))

    size = await validate_upload_with_limit(upload, max_size_mb=3, chunk_size=256 * 1024)

    assert size == len(payload)
    assert upload.file.tell() == 0
    assert upload.file.read(64) == payload[:64]


@pytest.mark.asyncio
async def test_validate_upload_rejects_limit_and_still_rewinds():
    payload = b"x" * (1024 * 1024 + 1)
    upload = UploadFile(filename="grande.ifc", file=BytesIO(payload))

    with pytest.raises(MegalodonException) as exc:
        await validate_upload_with_limit(upload, max_size_mb=1, chunk_size=128 * 1024)

    assert exc.value.status_code == 413
    assert upload.file.tell() == 0
