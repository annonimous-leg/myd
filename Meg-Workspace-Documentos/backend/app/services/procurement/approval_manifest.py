"""Bind a human procurement approval to exactly the original stored artifacts.

The manifest contains only server-derived identities and content digests. Do not
include mutable signature renditions: those are produced *after* human approval,
and are separately verified against their approved unsigned originals.
"""
from __future__ import annotations

import hashlib
import json
import re
from typing import Any, Iterable

from app.services.procurement.artifact_policy import artifact_submission_eligible

_HEX_SHA256 = re.compile(r"[0-9a-f]{64}\Z")


class ApprovalManifestError(ValueError):
    pass


def _sha256_bytes(content: bytes) -> str:
    return hashlib.sha256(content).hexdigest()


def manifest_digest(manifest: dict[str, Any]) -> str:
    return _sha256_bytes(json.dumps(
        manifest, sort_keys=True, separators=(",", ":"), ensure_ascii=False,
    ).encode("utf-8"))


def original_artifact_manifest(
    artifacts: Iterable[Any], *, tenant_id: Any, tender_id: Any, revision: int,
) -> dict[str, Any]:
    """Build deterministic review scope from active submission-eligible originals.

    Neither caller-provided paths nor unscoped/obsolete artifacts are accepted.
    """
    tenant, tender = str(tenant_id), str(tender_id)
    prefix = f"tenders/{tenant}/{tender}/r{revision}/"
    entries = []
    codes = set()
    for a in artifacts:
        if not artifact_submission_eligible(a):
            continue
        if str(a.tenant_id) != tenant or str(a.tender_id) != tender:
            raise ApprovalManifestError("Un artefacto pertenece a otro expediente o empresa.")
        if str(getattr(a, "status", "")) == "SUPERSEDED":
            raise ApprovalManifestError("Un artefacto obsoleto no puede aprobarse.")
        metadata = getattr(a, "artifact_metadata", None) or {}
        if not isinstance(metadata, dict) or metadata.get("reference_only") is True:
            raise ApprovalManifestError("No se pueden aprobar documentos marcados como referencia.")
        if "revision" in metadata and metadata["revision"] != revision:
            raise ApprovalManifestError("El artefacto pertenece a otra revisión.")
        code = str(a.artifact_code)
        if not code or code in codes:
            raise ApprovalManifestError("El expediente contiene códigos de artefacto vacíos o duplicados.")
        codes.add(code)
        path = str(a.storage_path or "")
        if not path.startswith(prefix) or any(segment in {"", ".", ".."} for segment in path.split("/")):
            raise ApprovalManifestError("Ruta del artefacto fuera del expediente/revisión.")
        sha256 = str(a.content_hash or "")
        if not _HEX_SHA256.fullmatch(sha256):
            raise ApprovalManifestError("El artefacto carece de un SHA-256 válido.")
        entries.append({
            "id": str(a.id),
            "code": code,
            "version": int(a.version),
            "media_type": str(a.media_type),
            "storage_path": path,
            "sha256": sha256,
            "source_model_hash": str(a.source_model_hash or ""),
        })
    if not entries:
        raise ApprovalManifestError("No hay artefactos elegibles para aprobar.")
    entries.sort(key=lambda x: (x["code"], x["version"], x["id"]))
    return {"schema": "MEGALODON_APPROVED_ORIGINALS_V1", "tenant_id": tenant,
            "tender_id": tender, "revision": revision, "artifacts": entries}


def verified_approval_manifest(
    approvals: Iterable[Any], expected: dict[str, Any], required_roles: set[str],
) -> str:
    """Reject old, inconsistent and tampered role approvals (fail-closed)."""
    digest = manifest_digest(expected)
    found: set[str] = set()
    for row in approvals:
        if row.decision != "APPROVED":
            continue
        if row.revision != expected["revision"] or str(row.tenant_id) != expected["tenant_id"] or str(row.tender_id) != expected["tender_id"]:
            raise ApprovalManifestError("La aprobación pertenece a otra empresa o revisión.")
        if row.artifact_manifest_hash != digest or row.artifact_manifest != expected:
            raise ApprovalManifestError("La aprobación no coincide con los archivos originales actuales.")
        found.add(row.role)
    missing = required_roles - found
    if missing:
        raise ApprovalManifestError("Faltan aprobaciones de roles: " + ", ".join(sorted(missing)))
    return digest


def verify_original_bytes(entry: dict[str, Any], content: bytes) -> None:
    if not isinstance(content, bytes) or _sha256_bytes(content) != entry["sha256"]:
        raise ApprovalManifestError(f"Los bytes originales aprobados cambiaron: {entry['code']}.")


def verify_package_bytes(expected_sha256: str | None, content: bytes) -> None:
    if not isinstance(expected_sha256, str) or not _HEX_SHA256.fullmatch(expected_sha256):
        raise ApprovalManifestError("El paquete no tiene un SHA-256 registrado válido.")
    if not isinstance(content, bytes) or _sha256_bytes(content) != expected_sha256:
        raise ApprovalManifestError("El paquete almacenado ya no coincide con el contenido original entregable.")
