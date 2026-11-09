"""Evidencia local de inmovilización de versiones y archivos aprobados."""
from copy import deepcopy
from dataclasses import dataclass
from uuid import UUID
import unittest

from app.services.procurement.approval_manifest import (
    ApprovalManifestError, manifest_digest, original_artifact_manifest,
    verified_approval_manifest, verify_original_bytes, verify_package_bytes,
)

TENANT = UUID("11111111-1111-1111-1111-111111111111")
TENDER = UUID("22222222-2222-2222-2222-222222222222")
SHA = "a" * 64


@dataclass
class Artifact:
    id: UUID = UUID("33333333-3333-3333-3333-333333333333")
    tenant_id: UUID = TENANT
    tender_id: UUID = TENDER
    artifact_code: str = "ANX01"
    version: int = 2
    media_type: str = "application/pdf"
    storage_path: str = f"tenders/{TENANT}/{TENDER}/r4/ANX01-v2-{SHA}.pdf"
    content_hash: str = SHA
    source_model_hash: str = "b" * 64
    status: str = "GENERATED"
    artifact_metadata: dict | None = None


@dataclass
class Approval:
    artifact_manifest_hash: str
    artifact_manifest: dict
    role: str = "revisor"
    decision: str = "APPROVED"
    revision: int = 4
    tenant_id: UUID = TENANT
    tender_id: UUID = TENDER


class ApprovalManifestTests(unittest.TestCase):
    def setUp(self):
        self.artifact = Artifact(artifact_metadata={"submission_eligible": True, "revision": 4})
        self.manifest = original_artifact_manifest([self.artifact], tenant_id=TENANT, tender_id=TENDER, revision=4)

    def test_manifest_has_exact_original_identity_and_hash(self):
        entry = self.manifest["artifacts"][0]
        self.assertEqual(entry["sha256"], SHA)
        self.assertEqual(entry["storage_path"], self.artifact.storage_path)
        self.assertEqual(entry["version"], 2)

    def test_manifest_is_order_independent(self):
        second = deepcopy(self.artifact)
        second.id = UUID("44444444-4444-4444-4444-444444444444")
        second.artifact_code = "ANX02"
        both1 = original_artifact_manifest([self.artifact, second], tenant_id=TENANT, tender_id=TENDER, revision=4)
        both2 = original_artifact_manifest([second, self.artifact], tenant_id=TENANT, tender_id=TENDER, revision=4)
        self.assertEqual(manifest_digest(both1), manifest_digest(both2))

    def test_changed_bytes_rejected(self):
        with self.assertRaises(ApprovalManifestError):
            verify_original_bytes(self.manifest["artifacts"][0], b"alterado")

    def test_package_bytes_verified(self):
        import hashlib
        raw = b"zip-original"
        verify_package_bytes(hashlib.sha256(raw).hexdigest(), raw)
        with self.assertRaises(ApprovalManifestError):
            verify_package_bytes(hashlib.sha256(raw).hexdigest(), b"zip-falso")

    def test_required_roles_pin_identical_manifest(self):
        approval = Approval(manifest_digest(self.manifest), self.manifest)
        self.assertEqual(verified_approval_manifest([approval], self.manifest, {"revisor"}), manifest_digest(self.manifest))

    def test_legacy_approval_without_sha_blocked(self):
        approval = Approval("", self.manifest)
        with self.assertRaises(ApprovalManifestError):
            verified_approval_manifest([approval], self.manifest, {"revisor"})

    def test_different_document_version_blocked(self):
        approval = Approval(manifest_digest(self.manifest), self.manifest)
        self.artifact.version += 1
        current = original_artifact_manifest([self.artifact], tenant_id=TENANT, tender_id=TENDER, revision=4)
        with self.assertRaises(ApprovalManifestError):
            verified_approval_manifest([approval], current, {"revisor"})

    def test_approver_from_other_tenant_blocked(self):
        approval = Approval(manifest_digest(self.manifest), self.manifest)
        approval.tenant_id = UUID("99999999-9999-9999-9999-999999999999")
        with self.assertRaises(ApprovalManifestError):
            verified_approval_manifest([approval], self.manifest, {"revisor"})

    def test_approver_from_prior_revision_blocked(self):
        approval = Approval(manifest_digest(self.manifest), self.manifest)
        approval.revision = 3
        with self.assertRaises(ApprovalManifestError):
            verified_approval_manifest([approval], self.manifest, {"revisor"})

    def test_missing_role_blocked(self):
        approval = Approval(manifest_digest(self.manifest), self.manifest)
        with self.assertRaises(ApprovalManifestError):
            verified_approval_manifest([approval], self.manifest, {"revisor", "legal"})

    def test_wrong_storage_path_blocked(self):
        self.artifact.storage_path = "tenders/other/r4/foreign.pdf"
        with self.assertRaises(ApprovalManifestError):
            original_artifact_manifest([self.artifact], tenant_id=TENANT, tender_id=TENDER, revision=4)

    def test_reference_artifact_not_approved(self):
        self.artifact.artifact_metadata["reference_only"] = True
        with self.assertRaises(ApprovalManifestError):
            original_artifact_manifest([self.artifact], tenant_id=TENANT, tender_id=TENDER, revision=4)

    def test_unknown_policy_not_approved(self):
        self.artifact.artifact_metadata.pop("submission_eligible")
        with self.assertRaises(ApprovalManifestError):
            original_artifact_manifest([self.artifact], tenant_id=TENANT, tender_id=TENDER, revision=4)

    def test_superseded_version_blocked(self):
        self.artifact.status = "SUPERSEDED"
        with self.assertRaises(ApprovalManifestError):
            original_artifact_manifest([self.artifact], tenant_id=TENANT, tender_id=TENDER, revision=4)

    def test_inconsistent_revision_metadata_blocked(self):
        self.artifact.artifact_metadata["revision"] = 2
        with self.assertRaises(ApprovalManifestError):
            original_artifact_manifest([self.artifact], tenant_id=TENANT, tender_id=TENDER, revision=4)

    def test_wrong_artifact_owner_blocked(self):
        self.artifact.tenant_id = UUID("99999999-9999-9999-9999-999999999999")
        with self.assertRaises(ApprovalManifestError):
            original_artifact_manifest([self.artifact], tenant_id=TENANT, tender_id=TENDER, revision=4)

    def test_duplicate_codes_blocked(self):
        second = deepcopy(self.artifact)
        second.id = UUID("44444444-4444-4444-4444-444444444444")
        with self.assertRaises(ApprovalManifestError):
            original_artifact_manifest([self.artifact, second], tenant_id=TENANT, tender_id=TENDER, revision=4)


if __name__ == "__main__":
    unittest.main()
