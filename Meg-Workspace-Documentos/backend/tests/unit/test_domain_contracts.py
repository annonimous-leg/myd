from datetime import datetime, timezone

import pytest

from app.engines.procurement.domain_contracts import DomainReference, DomainSnapshot, snapshot_source_is_current, source_revision_token


def test_snapshot_payload_is_recursively_immutable():
    snapshot = DomainSnapshot(
        source=DomainReference("BIM_MODEL", "bim-1", "tenant-a"),
        snapshot={"elements": [{"quantity": 0, "meta": {"unit": "m3"}}]},
        engine_version="test@1",
    )
    with pytest.raises(TypeError):
        snapshot.snapshot["elements"] = []
    with pytest.raises(TypeError):
        snapshot.snapshot["elements"][0]["meta"]["unit"] = "m2"


def test_snapshot_rejects_stale_explicit_hash():
    with pytest.raises(ValueError):
        DomainSnapshot(
            source=DomainReference("BIM_MODEL", "bim-1", "tenant-a"),
            snapshot={"x": 1},
            engine_version="test@1",
            output_hash="0" * 64,
        )


def test_snapshot_canonical_representation_is_deterministic_without_capture_time():
    source = DomainReference("BIM_MODEL", "bim-1", "tenant-a", revision="7")
    a = DomainSnapshot(source=source, snapshot={"x": [1, 2]}, engine_version="engine@1", captured_at=datetime(2026, 1, 1, tzinfo=timezone.utc))
    b = DomainSnapshot(source=source, snapshot={"x": [1, 2]}, engine_version="engine@1", captured_at=datetime(2026, 2, 2, tzinfo=timezone.utc))
    assert a.output_hash == b.output_hash
    assert a.to_dict() != b.to_dict()
    assert a.to_canonical_dict() == b.to_canonical_dict()


def test_source_revision_token_is_stable_and_changes_when_source_changes():
    from datetime import datetime

    updated = datetime(2026, 8, 31, 10, 0, 0, tzinfo=timezone.utc)
    a = source_revision_token(updated, "7")
    b = source_revision_token(updated, "7")
    c = source_revision_token(updated.replace(second=1), "7")
    assert a == b
    assert a != c


def test_snapshot_source_current_requires_exact_revision():
    assert snapshot_source_is_current("r1", "r1")
    assert not snapshot_source_is_current("r1", "r2")
    assert not snapshot_source_is_current(None, "r1")
    assert not snapshot_source_is_current("r1", None)
