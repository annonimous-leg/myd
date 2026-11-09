"""Public evidence writes must not forge system-managed source or artifact records."""

import importlib.util
import sys
from pathlib import Path

import pytest
from pydantic import ValidationError

# Load this pure-Pydantic contract module without triggering app.schemas package
# side effects (which initialize the application's database engine).
_SCHEMA_PATH = Path(__file__).resolve().parents[2] / "app" / "schemas" / "procurement" / "schemas.py"
_SPEC = importlib.util.spec_from_file_location("megalodon_procurement_schema_contract", _SCHEMA_PATH)
assert _SPEC is not None and _SPEC.loader is not None
_SCHEMA = importlib.util.module_from_spec(_SPEC)
sys.modules[_SPEC.name] = _SCHEMA
_SPEC.loader.exec_module(_SCHEMA)
EvidenceCreate = _SCHEMA.EvidenceCreate


@pytest.mark.parametrize("kind", ["SOURCE_DOCUMENT", "GENERATED_ARTIFACT", "CALCULATION"])
def test_public_evidence_contract_rejects_system_managed_kinds(kind: str) -> None:
    with pytest.raises(ValidationError):
        EvidenceCreate(kind=kind, subject="forged source", value={})


@pytest.mark.parametrize("kind", ["COMPANY_RECORD", "EXTERNAL_RECORD", "USER_ASSERTION"])
def test_public_evidence_contract_accepts_user_supplied_evidence_kinds(kind: str) -> None:
    evidence = EvidenceCreate(kind=kind, subject="user evidence", value={"claim": "example"})

    assert evidence.kind == kind
