# Copyright © 2026 Cristian Rodriguez
# All rights reserved.
"""Explicit certificate trust and revocation policy shared by PDF signing/validation."""
from collections.abc import Sequence
from pathlib import Path

from app.config import settings

FIRMA_REVOCATION_MODE = "require"


class FirmaValidationConfigError(ValueError):
    """A configured certificate bundle cannot be used safely."""


def load_firma_certificates(paths: Sequence[str]):
    """Read one or more PEM certificates per file and return ASN.1 objects."""
    from asn1crypto import x509 as asn1_x509
    from cryptography import x509
    from cryptography.hazmat.primitives.serialization import Encoding

    certificates = []
    for configured_path in paths:
        try:
            data = Path(configured_path).read_bytes()
            parsed = x509.load_pem_x509_certificates(data)
            if not parsed:
                raise ValueError("El archivo no contiene certificados PEM")
            certificates.extend(
                asn1_x509.Certificate.load(cert.public_bytes(Encoding.DER))
                for cert in parsed
            )
        except (OSError, ValueError, TypeError) as exc:
            raise FirmaValidationConfigError(
                f"No se pudo cargar el bundle de confianza PEM: {configured_path}"
            ) from exc
    return certificates


def build_firma_validation_context(
    *,
    trust_root_paths=None,
    intermediate_cert_paths=None,
    allow_fetching=None,
    crls=None,
    ocsps=None,
):
    """Build the same strict policy for signing certificates and timestamps.

    'require' demands revocation evidence even without advertised OCSP/CRL.
    Explicit empty roots prevent fallback to the OS/TLS trust store.
    Offline callers may supply evidence without changing the policy.
    Network fetching is opt-in deployment configuration, never a PDF choice.
    """
    from pyhanko_certvalidator import ValidationContext
    from pyhanko_certvalidator.fetchers.requests_fetchers import RequestsFetcherBackend

    roots = settings.FIEL_TRUST_ROOT_PATHS if trust_root_paths is None else trust_root_paths
    intermediates = (
        settings.FIEL_INTERMEDIATE_CERT_PATHS
        if intermediate_cert_paths is None else intermediate_cert_paths
    )
    if allow_fetching is None:
        allow_fetching = settings.FIEL_ALLOW_REVOCATION_FETCHING
    kwargs = {
        "trust_roots": load_firma_certificates(roots),
        "other_certs": load_firma_certificates(intermediates),
        "revocation_mode": FIRMA_REVOCATION_MODE,
        "allow_fetching": allow_fetching,
        "crls": [] if crls is None else crls,
        "ocsps": [] if ocsps is None else ocsps,
    }
    if allow_fetching:
        kwargs["fetcher_backend"] = RequestsFetcherBackend()
    return ValidationContext(**kwargs)
