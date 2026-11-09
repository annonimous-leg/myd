"""Repeated PAdES acceptance with an ephemeral CA and an in-process RFC 3161 TSA.

These tests prove the signing/verifier path with deterministic test PKI only.
They are not SAT trust anchors, production e.firma credentials, or a public TSA.
"""
from datetime import datetime, timedelta, timezone

import pytest
from asn1crypto import crl as asn1_crl, x509 as asn1_x509
from asn1crypto.keys import PrivateKeyInfo
from cryptography import x509
from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.primitives.asymmetric import rsa
from cryptography.x509.oid import ExtendedKeyUsageOID, NameOID
from pyhanko.pdf_utils.reader import PdfFileReader
from pyhanko.sign import timestamps
from pyhanko.sign.timestamps.dummy_client import DummyTimeStamper
from pyhanko_certvalidator import ValidationContext
from pyhanko_certvalidator.registry import SimpleCertificateStore
from reportlab.pdfgen import canvas

from app.modules.firma import pades_lt


@pytest.fixture
def signing_material(tmp_path):
    now = datetime.now(timezone.utc)
    root_key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    signer_key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    tsa_key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    root_name = x509.Name([x509.NameAttribute(NameOID.COMMON_NAME, "Megalodon ephemeral test root")])

    root = (
        x509.CertificateBuilder()
        .subject_name(root_name).issuer_name(root_name)
        .public_key(root_key.public_key()).serial_number(x509.random_serial_number())
        .not_valid_before(now - timedelta(days=1)).not_valid_after(now + timedelta(days=30))
        .add_extension(x509.BasicConstraints(ca=True, path_length=0), critical=True)
        .add_extension(x509.KeyUsage(
            digital_signature=True, content_commitment=False, key_encipherment=False,
            data_encipherment=False, key_agreement=False, key_cert_sign=True,
            crl_sign=True, encipher_only=False, decipher_only=False,
        ), critical=True)
        .add_extension(
            x509.SubjectKeyIdentifier.from_public_key(root_key.public_key()),
            critical=False,
        )
        .sign(root_key, hashes.SHA256())
    )

    signer_name = x509.Name([x509.NameAttribute(NameOID.COMMON_NAME, "Ephemeral PDF signer")])
    signer_cert = (
        x509.CertificateBuilder()
        .subject_name(signer_name).issuer_name(root_name)
        .public_key(signer_key.public_key()).serial_number(x509.random_serial_number())
        .not_valid_before(now - timedelta(days=1)).not_valid_after(now + timedelta(days=7))
        .add_extension(x509.BasicConstraints(ca=False, path_length=None), critical=True)
        .add_extension(
            x509.CRLDistributionPoints([
                x509.DistributionPoint(
                    full_name=[x509.UniformResourceIdentifier("http://crl.test.invalid/root.crl")],
                    relative_name=None,
                    reasons=None,
                    crl_issuer=None,
                )
            ]),
            critical=False,
        )
        .add_extension(
            x509.AuthorityKeyIdentifier.from_issuer_public_key(root_key.public_key()),
            critical=False,
        )
        .add_extension(x509.KeyUsage(
            digital_signature=True, content_commitment=True, key_encipherment=False,
            data_encipherment=False, key_agreement=False, key_cert_sign=False,
            crl_sign=False, encipher_only=False, decipher_only=False,
        ), critical=True)
        .sign(root_key, hashes.SHA256())
    )

    tsa_name = x509.Name([x509.NameAttribute(NameOID.COMMON_NAME, "Ephemeral RFC 3161 TSA")])
    tsa_cert = (
        x509.CertificateBuilder()
        .subject_name(tsa_name).issuer_name(root_name)
        .public_key(tsa_key.public_key()).serial_number(x509.random_serial_number())
        .not_valid_before(now - timedelta(days=1)).not_valid_after(now + timedelta(days=7))
        .add_extension(x509.BasicConstraints(ca=False, path_length=None), critical=True)
        .add_extension(
            x509.CRLDistributionPoints([
                x509.DistributionPoint(
                    full_name=[x509.UniformResourceIdentifier("http://crl.test.invalid/root.crl")],
                    relative_name=None,
                    reasons=None,
                    crl_issuer=None,
                )
            ]),
            critical=False,
        )
        .add_extension(x509.KeyUsage(
            digital_signature=True, content_commitment=False, key_encipherment=False,
            data_encipherment=False, key_agreement=False, key_cert_sign=False,
            crl_sign=False, encipher_only=False, decipher_only=False,
        ), critical=True)
        .add_extension(
            x509.ExtendedKeyUsage([ExtendedKeyUsageOID.TIME_STAMPING]), critical=True,
        )
        .sign(root_key, hashes.SHA256())
    )

    crl = (
        x509.CertificateRevocationListBuilder()
        .issuer_name(root_name)
        .last_update(now - timedelta(hours=1))
        .next_update(now + timedelta(days=1))
        .add_extension(
            x509.AuthorityKeyIdentifier.from_issuer_public_key(root_key.public_key()),
            critical=False,
        )
        .add_extension(x509.CRLNumber(1), critical=False)
        .sign(root_key, hashes.SHA256())
    )
    crl_asn1 = asn1_crl.CertificateList.load(crl.public_bytes(serialization.Encoding.DER))

    cert_path = tmp_path / "signer.cer"
    key_path = tmp_path / "signer.key"
    root_path = tmp_path / "root.pem"
    cert_path.write_bytes(signer_cert.public_bytes(serialization.Encoding.DER))
    key_path.write_bytes(signer_key.private_bytes(
        serialization.Encoding.DER,
        serialization.PrivateFormat.PKCS8,
        serialization.BestAvailableEncryption(b"test-only-password"),
    ))
    root_path.write_bytes(root.public_bytes(serialization.Encoding.PEM))

    tsa_key_der = tsa_key.private_bytes(
        serialization.Encoding.DER,
        serialization.PrivateFormat.PKCS8,
        serialization.NoEncryption(),
    )
    return {
        "cert_path": str(cert_path),
        "key_path": str(key_path),
        "root_path": str(root_path),
        "password": "test-only-password",
        "root_asn1": asn1_x509.Certificate.load(root.public_bytes(serialization.Encoding.DER)),
        "tsa_asn1": asn1_x509.Certificate.load(tsa_cert.public_bytes(serialization.Encoding.DER)),
        "tsa_key_info": PrivateKeyInfo.load(tsa_key_der),
        "crl": crl_asn1,
    }


@pytest.fixture
def signed_pdf_source(tmp_path):
    path = tmp_path / "source.pdf"
    output = canvas.Canvas(str(path))
    output.drawString(48, 720, "PAdES repeatable acceptance fixture")
    output.showPage()
    output.save()
    return path


def test_pades_lt_and_lta_verify_three_independent_attempts_and_reject_tampering(
    tmp_path, monkeypatch, signing_material, signed_pdf_source,
):
    material = signing_material
    def validation_context(**_kwargs):
        context = ValidationContext(
            trust_roots=[material["root_asn1"]],
            revocation_mode="require",
            allow_fetching=False,
            crls=[material["crl"]],
            ocsps=[],
        )
        return context

    dummy_tsa = DummyTimeStamper(
        tsa_cert=material["tsa_asn1"],
        tsa_key=material["tsa_key_info"],
        certs_to_embed=SimpleCertificateStore(),
        fixed_dt=datetime.now(timezone.utc),
    )
    monkeypatch.setattr(timestamps, "HTTPTimeStamper", lambda _url: dummy_tsa)
    monkeypatch.setattr(pades_lt, "build_firma_validation_context", validation_context)

    signer = pades_lt.PAdESLTSigner(
        material["cert_path"],
        material["key_path"],
        material["password"],
        tsa_url="http://tsa.invalid.test",
        trust_roots=[material["root_path"]],
        intermediate_certs=[],
    )
    try:
        for use_lta in (False, True):
            for attempt in range(1, 4):
                output = tmp_path / f"attempt-{int(use_lta)}-{attempt}.pdf"
                result = signer.sign_pades_lt(
                    str(signed_pdf_source),
                    str(output),
                    field_name=f"Signature-{int(use_lta)}-{attempt}",
                    use_lta=use_lta,
                )
                assert result["success"] is True
                assert result["verified"] is True
                assert result["validation"]["signature_intact"] is True
                assert result["validation"]["signature_trusted"] is True
                assert result["validation"]["timestamp_trusted"] is True
                assert result["validation"]["ltv_profile_valid"] is True
                assert result["validation"]["revocation_data_embedded"] is True
                assert (
                    result["validation"]["dss_crl_entries"]
                    + result["validation"]["dss_ocsp_entries"]
                ) > 0
                assert result["profile"] == ("PAdES-B-LTA" if use_lta else "PAdES-B-LT")
                with output.open("rb") as stream:
                    reader = PdfFileReader(stream)
                    signatures = reader.embedded_signatures
                    doc_timestamps = [
                        sig for sig in signatures if str(sig.sig_object_type) == "/DocTimeStamp"
                    ]
                    assert len(doc_timestamps) == int(use_lta)

        if use_lta:
            archive = tmp_path / "attempt-1-1.pdf"
            updated = signer.lta_update(str(archive))
            assert updated["success"] is True
            assert updated["verified"] is True
            assert updated["validation"]["ltv_profile_valid"] is True
            with archive.open("rb") as stream:
                updated_reader = PdfFileReader(stream)
                assert sum(str(item.sig_object_type) == "/DocTimeStamp"
                    for item in updated_reader.embedded_signatures) == 2

        tampered = tmp_path / "tampered.pdf"
        original = bytearray((tmp_path / "attempt-0-3.pdf").read_bytes())
        original[len(original) // 2] ^= 0x01
        tampered.write_bytes(original)
        with pytest.raises(pades_lt.PAdESLTError, match="integridad|validación"):
            signer.validate_signed_pdf(
                str(tampered),
                field_name="Signature-0-3",
                use_lta=False,
            )
    finally:
        signer.cleanup()
