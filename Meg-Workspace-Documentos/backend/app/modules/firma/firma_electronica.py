# Copyright © 2026 Cristian Rodriguez
# All rights reserved.
# Unauthorized copying, modification, distribution, or use is prohibited
# without prior written permission.

"""
Módulo de firma electrónica avanzada (FIEL) y PAdES para documentos PDF.
Soporta: firma con certificado X.509, sello de tiempo, LTV (Long Term Validation).
"""
import base64
import hashlib
import io
import logging
import os
import tempfile
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Optional, Dict, Any, List, Tuple
from pathlib import Path
from uuid import uuid4

from cryptography import x509
from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.primitives.asymmetric import rsa, padding
from cryptography.hazmat.backends import default_backend

from app.core.errors import MegalodonException, ErrorCode
from app.modules.firma.pades_lt import PAdESLTSigner
from app.modules.firma.validation_context import (
    FIRMA_REVOCATION_MODE,
    build_firma_validation_context,
)

logger = logging.getLogger(__name__)


@dataclass
class CertificadoFIEL:
    """Certificado FIEL del SAT."""
    rfc: str
    nombre: str
    certificado_pem: str
    llave_pem: Optional[str]
    vigencia_inicio: datetime
    vigencia_fin: datetime
    serial_number: str
    emisor: str
    es_fiel: bool
    es_csd: bool


@dataclass
class FirmaDocumento:
    """Resultado de firma de documento."""
    documento_id: str
    firmante_rfc: str
    firmante_nombre: str
    fecha_firma: datetime
    algoritmo: str
    hash_documento: str
    firma_digital: str
    certificado_serial: str
    sello_tiempo: Optional[str]
    es_valida: bool
    metadatos: Dict[str, Any]


class ModuloFirmaElectronica:
    """
    Módulo de firma electrónica conforme a la Ley de Firma Electrónica Avanzada.

    Soporta:
    - Firma con FIEL (e.firma) del SAT
    - Firma PAdES para PDFs
    - Sello de tiempo (TSA)
    - Validación de certificados
    - LTV (Long Term Validation)
    """

    # Mismas TSA públicas que ya usa PAdESLTSigner para firmar PDFs --
    # una sola fuente de verdad en vez de duplicar la lista (ver
    # app/modules/firma/pades_lt.py:DEFAULT_TSA_URLS).
    DEFAULT_TSA_URLS = PAdESLTSigner.DEFAULT_TSA_URLS

    def __init__(self):
        self.algoritmo_hash = hashes.SHA256()
        self.algoritmo_firma = "RSA-SHA256"

    def cargar_certificado_fiel(
        self,
        cert_path: str,
        key_path: Optional[str] = None,
        password: Optional[str] = None,
    ) -> CertificadoFIEL:
        """
        Carga un certificado FIEL desde archivos .cer y .key.
        """
        # Leer certificado
        with open(cert_path, "rb") as f:
            cert_der = f.read()

        cert = x509.load_der_x509_certificate(cert_der, default_backend())

        # Extraer RFC del subject
        subject = cert.subject
        rfc = self._extraer_rfc(subject)
        nombre = self._extraer_nombre(subject)

        # Verificar vigencia
        ahora = datetime.now(timezone.utc)
        vigente = cert.not_valid_before_utc <= ahora <= cert.not_valid_after_utc

        if not vigente:
            raise MegalodonException(
                ErrorCode.CERTIFICADO_EXPIRADO,
                f"Certificado FIEL de {rfc} no vigente. "
                f"Válido de {cert.not_valid_before_utc} a {cert.not_valid_after_utc}",
            )

        cert_pem = cert.public_bytes(serialization.Encoding.PEM).decode()

        key_pem = None
        if key_path and os.path.exists(key_path):
            with open(key_path, "rb") as f:
                key_der = f.read()

            # Desencriptar llave si tiene password
            if key_der:
                from cryptography.hazmat.primitives.serialization import pkcs12
                # La llave FIEL suele estar en formato PKCS#8
                try:
                    private_key = serialization.load_der_private_key(
                        key_der, password=password.encode() if password else None, backend=default_backend()
                    )
                except Exception:
                    private_key = serialization.load_pem_private_key(
                        key_der, password=password.encode() if password else None, backend=default_backend()
                    )

                key_pem = private_key.private_bytes(
                    encoding=serialization.Encoding.PEM,
                    format=serialization.PrivateFormat.PKCS8,
                    encryption_algorithm=serialization.NoEncryption(),
                ).decode()
                if private_key.public_key().public_bytes(
                    serialization.Encoding.DER, serialization.PublicFormat.SubjectPublicKeyInfo
                ) != cert.public_key().public_bytes(
                    serialization.Encoding.DER, serialization.PublicFormat.SubjectPublicKeyInfo
                ):
                    raise MegalodonException(ErrorCode.FIRMA_INVALIDA, "La llave no corresponde al certificado.")

        return CertificadoFIEL(
            rfc=rfc,
            nombre=nombre,
            certificado_pem=cert_pem,
            llave_pem=key_pem,
            vigencia_inicio=cert.not_valid_before_utc,
            vigencia_fin=cert.not_valid_after_utc,
            serial_number=str(cert.serial_number),
            emisor=cert.issuer.rfc4514_string(),
            es_fiel="FIEL" in cert.issuer.rfc4514_string().upper(),
            es_csd="CSD" in cert.issuer.rfc4514_string().upper(),
        )

    def _extraer_rfc(self, subject: x509.Name) -> str:
        """Extrae RFC del subject del certificado."""
        for attr in subject:
            if attr.oid == x509.NameOID.SERIAL_NUMBER:
                return attr.value
        return ""

    def _extraer_nombre(self, subject: x509.Name) -> str:
        """Extrae nombre del subject del certificado."""
        partes = []
        for attr in subject:
            if attr.oid in (x509.NameOID.GIVEN_NAME, x509.NameOID.SURNAME, 
                           x509.NameOID.COMMON_NAME):
                partes.append(attr.value)
        return " ".join(partes)

    def firmar_documento_pdf(
        self,
        pdf_bytes: bytes,
        certificado: CertificadoFIEL,
        razon: str = "Firma de documento de obra pública",
        ubicacion: str = "México",
        contacto: str = "",
        agregar_sello_tiempo: bool = False,
    ) -> bytes:
        """
        Firma un documento PDF con PAdES-LTA (Long Term Validation).

        Usa pyHanko para firma PAdES conforme a ETSI EN 319 142.
        """
        try:
            from pyhanko.sign import signers, fields
            from pyhanko.pdf_utils.incremental_writer import IncrementalPdfFileWriter
            from pyhanko.sign.general import SigningError
        except ImportError:
            raise MegalodonException(
                ErrorCode.FIRMA_INVALIDA,
                "pyHanko no instalado. pip install pyhanko[crypto,extra-pubkey-algos]",
            )

        # Crear firmante
        if not certificado.llave_pem:
            raise MegalodonException(
                ErrorCode.FIRMA_INVALIDA,
                "Se requiere la llave privada para firmar",
            )

        # Cargar certificado y llave
        cert_obj = x509.load_pem_x509_certificate(
            certificado.certificado_pem.encode(), default_backend()
        )

        private_key = serialization.load_pem_private_key(
            certificado.llave_pem.encode(), password=None, backend=default_backend()
        )

        # pyHanko consumes ASN.1 objects, not cryptography's X.509/key wrappers.
        from asn1crypto import x509 as asn1_x509, keys as asn1_keys
        from pyhanko_certvalidator.registry import SimpleCertificateStore
        signer = signers.SimpleSigner(
            signing_key=asn1_keys.PrivateKeyInfo.load(private_key.private_bytes(
                serialization.Encoding.DER, serialization.PrivateFormat.PKCS8, serialization.NoEncryption())),
            signing_cert=asn1_x509.Certificate.load(cert_obj.public_bytes(serialization.Encoding.DER)),
            cert_registry=SimpleCertificateStore(),
        )

        # Firmar PDF
        w = IncrementalPdfFileWriter(io.BytesIO(pdf_bytes))

        field_name = f"FirmaMegalodon_{uuid4().hex}"
        fields.append_signature_field(
            w, sig_field_spec=fields.SigFieldSpec(
                sig_field_name=field_name,
                on_page=0,
                box=(100, 100, 400, 200),
            )
        )

        meta = signers.PdfSignatureMetadata(
            field_name=field_name,
            reason=razon,
            location=ubicacion,
            contact_info=contacto,
            subfilter=fields.SigSeedSubFilter.PADES,
            embed_validation_info=False,
            use_pades_lta=False,
        )

        if agregar_sello_tiempo:
            raise MegalodonException(ErrorCode.FIRMA_INVALIDA, "Use PAdESLTSigner para solicitar TSA y validación de cadena.")

        pdf_signed = signers.PdfSigner(
            meta,
            signer=signer,
        ).sign_pdf(w)

        return pdf_signed.read()

    def validar_firma_pdf(self, pdf_bytes: bytes) -> Dict[str, Any]:
        """Validate current integrity, configured trust and strict revocation.

        Cryptographic validity alone is not acceptance. Historical LTV and SAT
        acceptance are separate assessments and are not inferred here.
        """
        try:
            from pyhanko.sign.validation import validate_pdf_signature, validate_pdf_timestamp
            from pyhanko.sign.validation.status import SignatureCoverageLevel
            from pyhanko.sign.diff_analysis import ModificationLevel
            from pyhanko.pdf_utils.reader import PdfFileReader
        except ImportError:
            raise MegalodonException(ErrorCode.FIRMA_INVALIDA, "pyHanko no instalado")

        reader = PdfFileReader(io.BytesIO(pdf_bytes))
        context = build_firma_validation_context()
        resultados = []
        sellos = []
        for sig_field in reader.embedded_signatures:
            is_timestamp = sig_field.sig_object_type == "/DocTimeStamp"
            destination = sellos if is_timestamp else resultados
            name = sig_field.field_name
            try:
                if is_timestamp:
                    status = validate_pdf_timestamp(sig_field, validation_context=context)
                    accepted = bool(
                        status.valid and status.intact and status.trusted
                        and status.coverage in (
                            SignatureCoverageLevel.ENTIRE_FILE,
                            SignatureCoverageLevel.ENTIRE_REVISION,
                        )
                        and status.modification_level != ModificationLevel.OTHER
                    )
                    error_details = status.summary()
                else:
                    status = validate_pdf_signature(
                        sig_field,
                        signer_validation_context=context,
                        ts_validation_context=context,
                    )
                    accepted = bool(status.bottom_line)
                    error_details = status.pretty_print_details()
                reported_dt = getattr(status, "signer_reported_dt", None)
                destination.append({
                    "campo": name,
                    "valida": accepted,
                    "criptograficamente_valida": bool(status.valid),
                    "intacta": bool(status.intact),
                    "confiable": bool(status.trusted),
                    "aceptacion_completa": accepted,
                    "revocacion": "verificada" if status.trusted else "no_acreditada",
                    "firmante": status.signing_cert.subject.human_friendly if status.signing_cert else None,
                    "fecha_firma": reported_dt.isoformat() if reported_dt else None,
                    "errores": error_details if not accepted else None,
                })
            except Exception as exc:
                destination.append({
                    "campo": name,
                    "valida": False,
                    "criptograficamente_valida": None,
                    "intacta": None,
                    "confiable": False,
                    "aceptacion_completa": False,
                    "revocacion": "no_acreditada",
                    "error": str(exc),
                })

        return {
            "total_firmas": len(resultados),
            "firmas_validas": sum(1 for result in resultados if result["aceptacion_completa"]),
            "detalles": resultados,
            "total_sellos_documentales": len(sellos),
            "sellos_documentales": sellos,
            "aceptacion_completa": bool(resultados) and all(
                result["aceptacion_completa"] for result in resultados + sellos
            ),
            "politica_revocacion": FIRMA_REVOCATION_MODE,
            "alcance_validacion": "actual_cadena_revocacion",
            "validacion_ltv": "no_evaluada",
            "aceptacion_sat": None,
        }

    def firmar_hash_documento(
        self,
        contenido: bytes,
        certificado: CertificadoFIEL,
    ) -> str:
        """
        Firma el hash SHA-256 de un documento (para trazabilidad blockchain).
        Retorna la firma en base64.
        """
        import base64

        if not certificado.llave_pem:
            raise MegalodonException(
                ErrorCode.FIRMA_INVALIDA,
                "Se requiere la llave privada",
            )

        private_key = serialization.load_pem_private_key(
            certificado.llave_pem.encode(), password=None, backend=default_backend()
        )

        hash_doc = hashlib.sha256(contenido).digest()

        firma = private_key.sign(
            hash_doc,
            padding.PSS(
                mgf=padding.MGF1(hashes.SHA256()),
                salt_length=padding.PSS.MAX_LENGTH,
            ),
            hashes.SHA256(),
        )

        return base64.b64encode(firma).decode()

    def verificar_firma_hash(
        self,
        contenido: bytes,
        firma_b64: str,
        certificado_pem: str,
    ) -> bool:
        """Verifica una firma de hash contra un certificado."""
        import base64

        cert = x509.load_pem_x509_certificate(certificado_pem.encode(), default_backend())
        public_key = cert.public_key()

        hash_doc = hashlib.sha256(contenido).digest()
        firma = base64.b64decode(firma_b64)

        try:
            public_key.verify(
                firma,
                hash_doc,
                padding.PSS(
                    mgf=padding.MGF1(hashes.SHA256()),
                    salt_length=padding.PSS.MAX_LENGTH,
                ),
                hashes.SHA256(),
            )
            return True
        except Exception:
            return False

    def generar_sello_tiempo(
        self,
        hash_data: bytes,
        md_algorithm: str = "sha256",
        tsa_url: Optional[str] = None,
    ) -> Optional[str]:
        """
        Genera un sello de tiempo RFC 3161 real contra una TSA (Time
        Stamping Authority) pública o configurada.

        BUG ORIGINAL: NO estaba implementado. Antes devolvía
        datetime.now() como si fuera un sello real -- eso es más
        peligroso que devolver None: un timestamp local no tiene
        respaldo criptográfico de terceros (cualquiera con acceso al
        reloj del servidor lo falsifica) pero se ve idéntico a uno real
        en un expediente legal.

        AHORA: pide un TimeStampToken RFC 3161 real usando el mismo
        cliente HTTP (pyhanko.sign.timestamps.HTTPTimeStamper) que ya
        usa PAdESLTSigner para firmar PDFs -- pero aquí opera
        directamente sobre un hash arbitrario, sin necesidad de envolver
        el dato en un PDF primero. Útil para sellar artefactos que no
        son PDF (un hash en BD, un XML de CFDI, una entrada de log de
        auditoría).

        Se mantiene el contrato original (Optional[str], nunca
        excepción): un sello de tiempo es un refuerzo de robustez legal,
        no debe tumbar el flujo de firma completo si en ese momento
        todas las TSA configuradas están caídas. La diferencia es que
        ahora, cuando SÍ devuelve un valor, es un timestamp RFC 3161
        real y verificable por terceros -- no un placeholder, y cuando
        devuelve None queda en logs el motivo (antes era indistinguible
        de "no se intentó").

        Args:
            hash_data: hash ya calculado del documento/dato a sellar
                (p.ej. hashlib.sha256(contenido).digest()).
            md_algorithm: algoritmo con el que se calculó hash_data
                ("sha256", "sha384", "sha512"). Debe coincidir con el
                algoritmo real (RFC 8933) o la TSA rechazará la petición.
            tsa_url: URL específica de TSA. Si None, se prueban las URLs
                de DEFAULT_TSA_URLS en orden hasta que una responda.

        Returns:
            El TimeStampToken (CMS ContentInfo, DER) codificado en
            base64, o None si ninguna TSA respondió.
        """
        from pyhanko.sign.timestamps import HTTPTimeStamper, TimestampRequestError

        urls = [tsa_url] if tsa_url else list(self.DEFAULT_TSA_URLS)
        ultimo_error: Optional[Exception] = None

        for url in urls:
            try:
                timestamper = HTTPTimeStamper(url, timeout=10)
                token = timestamper.timestamp(hash_data, md_algorithm)
                return base64.b64encode(token.dump()).decode("ascii")
            except (TimestampRequestError, IOError, OSError) as exc:
                ultimo_error = exc
                logger.warning(
                    "tsa_timestamp_intento_fallido",
                    extra={"tsa_url": url, "error": str(exc)},
                )
                continue

        logger.warning(
            "tsa_timestamp_sin_respuesta",
            extra={"tsa_urls_probadas": urls, "ultimo_error": str(ultimo_error)},
        )
        return None
