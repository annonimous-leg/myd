"""Offline cryptographic acceptance tests; ephemeral certificates are not SAT evidence."""
from datetime import datetime, timedelta, timezone

import pytest
from asn1crypto import crl as asn1_crl, x509 as asn1_x509
from cryptography import x509
from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.primitives.asymmetric import rsa
from pyhanko_certvalidator import CertificateValidator
from pyhanko_certvalidator.errors import InsufficientRevinfoError, PathBuildingError, RevokedError

from app.modules.firma import validation_context as policy


@pytest.fixture
def pki(tmp_path):
    now = datetime.now(timezone.utc)
    ca_key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    signer_key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    ca_name = x509.Name([x509.NameAttribute(x509.NameOID.COMMON_NAME, "Meg test CA")])
    signer_name = x509.Name([x509.NameAttribute(x509.NameOID.COMMON_NAME, "Meg test signer")])
    ca = (
        x509.CertificateBuilder().subject_name(ca_name).issuer_name(ca_name)
        .public_key(ca_key.public_key()).serial_number(x509.random_serial_number())
        .not_valid_before(now - timedelta(days=1)).not_valid_after(now + timedelta(days=30))
        .add_extension(x509.BasicConstraints(ca=True, path_length=0), critical=True)
        .add_extension(x509.KeyUsage(
            digital_signature=True, content_commitment=False, key_encipherment=False,
            data_encipherment=False, key_agreement=False, key_cert_sign=True,
            crl_sign=True, encipher_only=False, decipher_only=False,
        ), critical=True)
        .add_extension(x509.SubjectKeyIdentifier.from_public_key(ca_key.public_key()), critical=False)
        .sign(ca_key, hashes.SHA256())
    )
    signer = (
        x509.CertificateBuilder().subject_name(signer_name).issuer_name(ca_name)
        .public_key(signer_key.public_key()).serial_number(x509.random_serial_number())
        .not_valid_before(now - timedelta(days=1)).not_valid_after(now + timedelta(days=7))
        .add_extension(x509.BasicConstraints(ca=False, path_length=None), critical=True)
        .add_extension(x509.KeyUsage(
            digital_signature=True, content_commitment=True, key_encipherment=False,
            data_encipherment=False, key_agreement=False, key_cert_sign=False,
            crl_sign=False, encipher_only=False, decipher_only=False,
        ), critical=True)
        .add_extension(x509.AuthorityKeyIdentifier.from_issuer_public_key(ca_key.public_key()), critical=False)
        # No AIA/CRL URLs: revocation evidence must still be required.
        .sign(ca_key, hashes.SHA256())
    )
    ca_path = tmp_path / "ca.pem"
    ca_path.write_bytes(ca.public_bytes(serialization.Encoding.PEM))

    def make_crl(revoked=False):
        builder = (
            x509.CertificateRevocationListBuilder().issuer_name(ca_name)
            .last_update(now - timedelta(hours=1)).next_update(now + timedelta(days=1))
            .add_extension(x509.CRLNumber(1), critical=False)
            .add_extension(x509.AuthorityKeyIdentifier.from_issuer_public_key(ca_key.public_key()), critical=False)
        )
        if revoked:
            entry = (
                x509.RevokedCertificateBuilder().serial_number(signer.serial_number)
                .revocation_date(now - timedelta(minutes=30))
                .add_extension(x509.CRLReason(x509.ReasonFlags.key_compromise), critical=False)
                .build()
            )
            builder = builder.add_revoked_certificate(entry)
        signed = builder.sign(ca_key, hashes.SHA256())
        return asn1_crl.CertificateList.load(signed.public_bytes(serialization.Encoding.DER))

    return {
        "ca": ca, "ca_path": str(ca_path), "signer": signer, "signer_key": signer_key,
        "signer_asn1": asn1_x509.Certificate.load(signer.public_bytes(serialization.Encoding.DER)),
        "good_crl": make_crl(), "revoked_crl": make_crl(revoked=True),
    }


def context_for(pki, *, crls):
    return policy.build_firma_validation_context(
        trust_root_paths=[pki["ca_path"]], intermediate_cert_paths=[],
        allow_fetching=False, crls=crls,
    )


def test_loads_every_certificate_in_pem_bundle_as_asn1(tmp_path, pki):
    bundle = tmp_path / "bundle.pem"
    bundle.write_bytes(pki["ca"].public_bytes(serialization.Encoding.PEM)
                       + pki["signer"].public_bytes(serialization.Encoding.PEM))
    certificates = policy.load_firma_certificates([str(bundle)])
    assert all(isinstance(cert, asn1_x509.Certificate) for cert in certificates)
    assert [cert.serial_number for cert in certificates] == [
        pki["ca"].serial_number, pki["signer"].serial_number,
    ]


@pytest.mark.parametrize("contents", [b"", b"not a PEM certificate"])
def test_invalid_configured_bundle_fails_instead_of_using_os_trust(tmp_path, contents):
    bundle = tmp_path / "invalid.pem"
    bundle.write_bytes(contents)
    with pytest.raises(policy.FirmaValidationConfigError, match="bundle"):
        policy.build_firma_validation_context(
            trust_root_paths=[str(bundle)], intermediate_cert_paths=[], allow_fetching=False,
        )


def test_missing_bundle_fails_instead_of_using_os_trust(tmp_path):
    with pytest.raises(policy.FirmaValidationConfigError, match="bundle"):
        policy.load_firma_certificates([str(tmp_path / "missing.pem")])


def test_empty_roots_are_explicit_and_fetching_is_off_by_default(monkeypatch):
    import pyhanko_certvalidator
    import pyhanko_certvalidator.registry

    original = pyhanko_certvalidator.ValidationContext
    received = {}

    def capture(**kwargs):
        received.update(kwargs)
        return original(**kwargs)

    def forbidden_system_roots():
        raise AssertionError("System trust must not be used")

    monkeypatch.setattr(policy.settings, "FIEL_TRUST_ROOT_PATHS", [])
    monkeypatch.setattr(policy.settings, "FIEL_INTERMEDIATE_CERT_PATHS", [])
    monkeypatch.setattr(policy.settings, "FIEL_ALLOW_REVOCATION_FETCHING", False)
    monkeypatch.setattr(pyhanko_certvalidator, "ValidationContext", capture)
    monkeypatch.setattr(pyhanko_certvalidator.registry, "_system_trust_roots", forbidden_system_roots)
    context = policy.build_firma_validation_context()
    assert received["trust_roots"] == []
    assert received["other_certs"] == []
    assert received["revocation_mode"] == "require"
    assert received["allow_fetching"] is False
    assert "fetcher_backend" not in received
    assert context.fetching_allowed is False


def test_network_fetching_requires_explicit_deployment_opt_in(monkeypatch):
    monkeypatch.setattr(policy.settings, "FIEL_ALLOW_REVOCATION_FETCHING", True)
    context = policy.build_firma_validation_context(trust_root_paths=[], intermediate_cert_paths=[])
    assert context.fetching_allowed is True


@pytest.mark.asyncio
async def test_real_chain_with_valid_signed_crl_is_accepted_offline(pki):
    context = context_for(pki, crls=[pki["good_crl"]])
    validator = CertificateValidator(pki["signer_asn1"], validation_context=context)
    validated = await validator.async_validate_usage({"digital_signature"})
    assert validated is not None
    assert context.fetching_allowed is False
    assert context.soft_fail_exceptions == []


@pytest.mark.asyncio
async def test_real_signed_crl_rejects_revoked_signer(pki):
    validator = CertificateValidator(
        pki["signer_asn1"], validation_context=context_for(pki, crls=[pki["revoked_crl"]]),
    )
    with pytest.raises(RevokedError):
        await validator.async_validate_usage({"digital_signature"})


@pytest.mark.asyncio
async def test_missing_revocation_evidence_is_rejected_even_without_urls(pki):
    validator = CertificateValidator(pki["signer_asn1"], validation_context=context_for(pki, crls=[]))
    with pytest.raises(InsufficientRevinfoError):
        await validator.async_validate_usage({"digital_signature"})


@pytest.mark.asyncio
async def test_intermediate_certificate_never_becomes_trust_anchor(pki):
    context = policy.build_firma_validation_context(
        trust_root_paths=[], intermediate_cert_paths=[pki["ca_path"]],
        allow_fetching=False, crls=[pki["good_crl"]],
    )
    validator = CertificateValidator(pki["signer_asn1"], validation_context=context)
    with pytest.raises(PathBuildingError):
        await validator.async_validate_usage({"digital_signature"})


@pytest.mark.parametrize("evidence,accepted", [("good_crl", True), ("revoked_crl", False), (None, False)])
def test_pdf_acceptance_requires_trust_and_revocation_evidence(pki, monkeypatch, evidence, accepted):
    from io import BytesIO
    from asn1crypto.keys import PrivateKeyInfo
    from reportlab.pdfgen import canvas
    from pyhanko.pdf_utils.incremental_writer import IncrementalPdfFileWriter
    from pyhanko.sign import signers
    from pyhanko_certvalidator.registry import SimpleCertificateStore
    from app.modules.firma import firma_electronica

    pdf = BytesIO()
    page = canvas.Canvas(pdf)
    page.drawString(40, 720, "Ephemeral trust acceptance fixture")
    page.save()
    key_der = pki["signer_key"].private_bytes(
        serialization.Encoding.DER, serialization.PrivateFormat.PKCS8, serialization.NoEncryption(),
    )
    signer = signers.SimpleSigner(
        signing_cert=pki["signer_asn1"], signing_key=PrivateKeyInfo.load(key_der),
        cert_registry=SimpleCertificateStore(),
    )
    signed = signers.sign_pdf(
        IncrementalPdfFileWriter(BytesIO(pdf.getvalue())),
        signers.PdfSignatureMetadata(field_name="Acceptance"), signer=signer,
    ).getvalue()
    context = context_for(pki, crls=[pki[evidence]] if evidence else [])
    monkeypatch.setattr(firma_electronica, "build_firma_validation_context", lambda: context)
    result = firma_electronica.ModuloFirmaElectronica().validar_firma_pdf(signed)
    assert result["total_firmas"] == 1
    assert result["detalles"][0]["criptograficamente_valida"] is True
    assert result["detalles"][0]["intacta"] is True
    assert result["aceptacion_completa"] is accepted
    assert result["detalles"][0]["valida"] is accepted
    assert result["firmas_validas"] == int(accepted)
    assert result["validacion_ltv"] == "no_evaluada"
    assert result["aceptacion_sat"] is None
