"""Ephemeral test-only certificate and PDF; no external PKI or TSA calls."""
from datetime import datetime, timedelta, timezone
from io import BytesIO

from cryptography import x509
from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.primitives.asymmetric import rsa
from reportlab.pdfgen import canvas


def signing_fixture():
    key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    subject = x509.Name([
        x509.NameAttribute(x509.NameOID.COMMON_NAME, "Megalodon test signer"),
        x509.NameAttribute(x509.NameOID.SERIAL_NUMBER, "TEST010101ABC"),
    ])
    now = datetime.now(timezone.utc)
    cert = (x509.CertificateBuilder().subject_name(subject).issuer_name(subject)
            .public_key(key.public_key()).serial_number(x509.random_serial_number())
            .not_valid_before(now - timedelta(days=1)).not_valid_after(now + timedelta(days=1))
            .add_extension(x509.BasicConstraints(ca=False, path_length=None), critical=True)
            .add_extension(x509.KeyUsage(digital_signature=True, content_commitment=True,
                key_encipherment=False, data_encipherment=False, key_agreement=False,
                key_cert_sign=False, crl_sign=False, encipher_only=False, decipher_only=False), critical=True)
            .sign(key, hashes.SHA256()))
    pdf = BytesIO()
    page = canvas.Canvas(pdf)
    page.drawString(40, 720, "Megalodon acceptance document")
    page.save()
    return {
        "pdf": pdf.getvalue(),
        "cer": cert.public_bytes(serialization.Encoding.DER),
        "key": key.private_bytes(serialization.Encoding.DER, serialization.PrivateFormat.PKCS8,
                                 serialization.BestAvailableEncryption(b"test-password")),
        "password": "test-password",
    }
