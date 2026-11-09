#!/usr/bin/env python3
# Copyright © 2026 Cristian Rodriguez
# All rights reserved.
# Unauthorized copying, modification, distribution, or use is prohibited
# without prior written permission.

"""
================================================================================
Megalodon PAdES-LT Signer — Firma PDF de Larga Duración (sin mocks)
================================================================================
Implementación completa de PAdES-B-LT y PAdES-B-LTA usando pyHanko.
Incluye:
  • Firma RSA-SHA256 con certificado e.firma SAT
  • Sello de tiempo RFC 3161 desde TSA configurable
  • Incrustación de info de revocación (OCSP/CRL) en DSS
  • Validación de contexto X.509
  • Compatible con plataformas mexicanas que exijan PAdES-LT

Dependencias:
    pip install pyhanko pyhanko-certvalidator

Nota: pyHanko requiere que la clave y certificado estén en formato PEM
      o PFX. Este módulo convierte automáticamente desde .cer/.key SAT.
"""

import os
import sys
import tempfile
import warnings
from pathlib import Path
from typing import Optional, List, Union

from cryptography import x509
from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.primitives.asymmetric import padding
from cryptography.hazmat.backends import default_backend

from app.modules.firma.validation_context import build_firma_validation_context

# pyHanko imports


class PAdESLTError(Exception):
    """Error verificable durante firma PAdES-LT/LTA."""


def _import_pyhanko():
    try:
        from pyhanko.sign import signers, timestamps
        from pyhanko.sign.fields import SigSeedSubFilter
        from pyhanko.pdf_utils.incremental_writer import IncrementalPdfFileWriter
        from pyhanko_certvalidator import ValidationContext
        from pyhanko_certvalidator.fetchers.requests_fetchers import RequestsFetcherBackend
        return signers, timestamps, SigSeedSubFilter, IncrementalPdfFileWriter, ValidationContext, RequestsFetcherBackend
    except Exception as exc:  # pragma: no cover - dependencia opcional
        raise PAdESLTError(
            "pyHanko no está disponible en este entorno; la firma PAdES-LT/LTA requiere esa dependencia"
        ) from exc

class PAdESLTSigner:
    """
    Firmador PAdES-LT/LTA para documentos PDF usando e.firma del SAT.
    """

    # TSAs públicos conocidos (configurables)
    DEFAULT_TSA_URLS = [
        "http://timestamp.digicert.com",           # DigiCert (global)
        "http://tsa.starfieldtech.com",            # Starfield
        "http://timestamp.globalsign.com/scripts/timstamp.dll",  # GlobalSign
    ]

    def __init__(self, cer_path: str, key_path: str, password: str,
                 tsa_url: Optional[str] = None,
                 trust_roots: Optional[List[str]] = None,
                 intermediate_certs: Optional[List[str]] = None):
        """
        Inicializa firmador PAdES-LT.

        Args:
            cer_path: Ruta al .cer del SAT
            key_path: Ruta al .key cifrado del SAT
            password: Contraseña de la .key
            tsa_url: URL del TSA (Time Stamping Authority). Si None, usa defaults.
            trust_roots: Bundles PEM revisados de raíces para firmantes y TSA.
            intermediate_certs: Bundles PEM de intermedios; no son anclas.
        """
        self.cer_path = Path(cer_path)
        self.key_path = Path(key_path)
        self.password = password.encode("utf-8") if isinstance(password, str) else password
        self.tsa_url = tsa_url
        self.trust_roots = trust_roots
        self.intermediate_certs = intermediate_certs

        self._cert: Optional[x509.Certificate] = None
        self._private_key = None
        self._pyhanko_signer = None
        self._timestamper = None

        self._load_crypto_materials()
        try:
            self._setup_pyhanko()
        except BaseException:
            self.cleanup()
            raise

    def _load_crypto_materials(self) -> None:
        """Carga .cer y descifra .key del SAT."""
        if not self.cer_path.exists():
            raise PAdESLTError(f"Certificado no encontrado: {self.cer_path}")
        if not self.key_path.exists():
            raise PAdESLTError(f"Clave privada no encontrada: {self.key_path}")

        # Cargar certificado
        cer_data = self.cer_path.read_bytes()
        try:
            self._cert = x509.load_der_x509_certificate(cer_data, default_backend())
        except Exception:
            self._cert = x509.load_pem_x509_certificate(cer_data, default_backend())

        # Cargar clave privada
        key_data = self.key_path.read_bytes()
        last_err = None
        for loader in [
            lambda: serialization.load_der_private_key(key_data, password=self.password, backend=default_backend()),
            lambda: serialization.load_pem_private_key(key_data, password=self.password, backend=default_backend()),
        ]:
            try:
                self._private_key = loader()
                break
            except Exception as e:
                last_err = e
        if not self._private_key:
            raise PAdESLTError(f"No se pudo descifrar .key: {last_err}")

    def _setup_pyhanko(self) -> None:
        """
        Prepara el signer de pyHanko.
        pyHanko puede cargar desde PEM o PFX. Convertimos a PEM en memoria.
        """
        # Exportar certificado y clave a archivos temporales PEM
        self._temp_dir = Path(tempfile.mkdtemp(prefix="megalodon_pades_"))

        cert_pem = self._cert.public_bytes(serialization.Encoding.PEM)
        key_pem = self._private_key.private_bytes(
            encoding=serialization.Encoding.PEM,
            format=serialization.PrivateFormat.TraditionalOpenSSL,
            encryption_algorithm=serialization.NoEncryption()
        )

        self._cert_pem_path = self._temp_dir / "cert.pem"
        self._key_pem_path = self._temp_dir / "key.pem"
        self._cert_pem_path.write_bytes(cert_pem)
        self._key_pem_path.write_bytes(key_pem)
        self._key_pem_path.chmod(0o600)

        signers, timestamps, SigSeedSubFilter, IncrementalPdfFileWriter, ValidationContext, RequestsFetcherBackend = _import_pyhanko()

        # Cargar en pyHanko
        self._pyhanko_signer = signers.SimpleSigner.load(
            key_file=str(self._key_pem_path),
            cert_file=str(self._cert_pem_path),
            ca_chain_files=self.intermediate_certs or [],
            key_passphrase=None  # Ya desciframos nosotros
        )

        if self._pyhanko_signer is None:
            raise PAdESLTError("No se pudo cargar el material criptográfico en pyHanko")

        # Configurar TSA
        tsa_url = self.tsa_url or self.DEFAULT_TSA_URLS[0]
        self._timestamper = timestamps.HTTPTimeStamper(tsa_url)

    def validate_signed_pdf(
        self,
        pdf_path: str,
        *,
        field_name: str,
        use_lta: bool,
    ) -> dict:
        """Validate CMS, signer/TSA trust, DSS revocation and the PAdES profile.

        Trust roots are explicit. CRL/OCSP objects are read from the PDF DSS
        and supplied to both classic and AdES validation; missing revocation
        evidence remains a hard failure.
        """
        import asyncio
        from pyhanko.pdf_utils.reader import PdfFileReader
        from pyhanko.sign.validation import validate_pdf_signature
        from app.config import settings
        from app.modules.firma.validation_context import load_firma_certificates

        try:
            from pyhanko.sign.validation.dss import DocumentSecurityStore

            with open(pdf_path, "rb") as signed_stream:
                reader = PdfFileReader(signed_stream)
                embedded = list(reader.embedded_signatures)
                signature = next(
                    (
                        item for item in embedded
                        if item.field_name == field_name
                        and str(item.sig_object_type) == "/Sig"
                    ),
                    None,
                )
                if signature is None:
                    raise PAdESLTError(
                        f"No se encontró la firma PDF esperada ({field_name})."
                    )

                # Let pyHanko decode its own PDF indirect objects. DSS arrays
                # contain PDF references, not ASN.1 values; read_dss() maps
                # them into the library's DocumentSecurityStore abstraction.
                dss = DocumentSecurityStore.read_dss(reader)
                crl_entries = list(dss.crls or [])
                ocsp_entries = list(dss.ocsps or [])
                revocation_data = bool(crl_entries or ocsp_entries)
                if not revocation_data:
                    raise PAdESLTError(
                        "El DSS no contiene evidencia OCSP/CRL incrustada para validación de largo plazo."
                    )

                roots = load_firma_certificates(
                    self.trust_roots if self.trust_roots is not None
                    else settings.FIEL_TRUST_ROOT_PATHS
                )
                intermediates = load_firma_certificates(
                    self.intermediate_certs if self.intermediate_certs is not None
                    else settings.FIEL_INTERMEDIATE_CERT_PATHS
                )
                if not roots:
                    raise PAdESLTError(
                        "La validación PAdES requiere trust anchors explícitos; "
                        "no se usa el almacén de certificados del sistema."
                    )
                validation_context_kwargs = {
                    "trust_roots": roots,
                    "other_certs": intermediates,
                    "revocation_mode": "require",
                    "allow_fetching": settings.FIEL_ALLOW_REVOCATION_FETCHING,
                }
                if settings.FIEL_ALLOW_REVOCATION_FETCHING:
                    from pyhanko_certvalidator.fetchers.requests_fetchers import RequestsFetcherBackend
                    validation_context_kwargs["fetcher_backend"] = RequestsFetcherBackend()
                verification_context = dss.as_validation_context(
                    validation_context_kwargs
                )
                status = validate_pdf_signature(
                    signature,
                    signer_validation_context=verification_context,
                    ts_validation_context=verification_context,
                )
                if not status.intact:
                    raise PAdESLTError("La integridad criptográfica del PDF firmado no es válida.")
                if not status.valid:
                    raise PAdESLTError("La firma CMS del PDF no es criptográficamente válida.")
                if not status.trusted:
                    raise PAdESLTError(
                        "La cadena X.509 del firmante/TSA no termina en una raíz configurada "
                        "o carece de evidencia de revocación vigente."
                    )

                timestamp_status = getattr(status, "timestamp_validity", None)
                if (
                    timestamp_status is None
                    or not timestamp_status.intact
                    or not timestamp_status.valid
                    or not timestamp_status.trusted
                ):
                    raise PAdESLTError(
                        "El sello RFC 3161 de la firma falta o no supera integridad, confianza y revocación."
                    )

                document_timestamps = [
                    item for item in embedded
                    if str(item.sig_object_type) == "/DocTimeStamp"
                ]
                if use_lta and not document_timestamps:
                    raise PAdESLTError(
                        "PAdES-B-LTA exige al menos un DocumentTimeStamp posterior al DSS."
                    )

                ltv_profile_valid = bool(
                    status.intact and status.valid and status.trusted
                    and timestamp_status.intact and timestamp_status.valid
                    and timestamp_status.trusted and revocation_data
                )
                ades_verdict = None
                if use_lta:
                    # Use ETSI EN 319 102-1 validation with distinct signer
                    # and TSA policies. Feed parsed DSS objects as local
                    # knowledge to support strict, offline historical checks.
                    from pyhanko.sign.validation.ades import ades_lta_validation
                    from pyhanko.sign.validation.policy_decl import (
                        LocalKnowledge,
                        PdfSignatureValidationSpec,
                        RevinfoOnlineFetchingRule,
                        RevocationInfoGatheringSpec,
                        SignatureValidationSpec,
                    )
                    from pyhanko_certvalidator.context import CertValidationPolicySpec
                    from pyhanko_certvalidator.policy_decl import (
                        CertRevTrustPolicy,
                        REQUIRE_REVINFO,
                    )
                    from pyhanko_certvalidator.registry import SimpleTrustManager

                    roots = load_firma_certificates(
                        self.trust_roots if self.trust_roots is not None
                        else settings.FIEL_TRUST_ROOT_PATHS
                    )
                    intermediates = load_firma_certificates(
                        self.intermediate_certs if self.intermediate_certs is not None
                        else settings.FIEL_INTERMEDIATE_CERT_PATHS
                    )
                    if not roots:
                        raise PAdESLTError(
                            "PAdES-LTA requiere al menos un trust anchor explícito; "
                            "no se usa el almacén del sistema."
                        )
                    trust_manager = SimpleTrustManager.build(
                        trust_roots=roots,
                        extra_trust_roots=[],
                    )
                    revocation_policy = CertRevTrustPolicy(REQUIRE_REVINFO)
                    signer_policy = CertValidationPolicySpec(
                        trust_manager=trust_manager,
                        revinfo_policy=revocation_policy,
                    )
                    tsa_policy = CertValidationPolicySpec(
                        trust_manager=trust_manager,
                        revinfo_policy=revocation_policy,
                    )
                    if settings.FIEL_ALLOW_REVOCATION_FETCHING:
                        from pyhanko_certvalidator.fetchers.requests_fetchers import RequestsFetcherBackend
                        fetching_policy = RevocationInfoGatheringSpec(
                            online_fetching_rule=RevinfoOnlineFetchingRule.ALWAYS_FETCH,
                            fetcher_backend=RequestsFetcherBackend(),
                        )
                    else:
                        fetching_policy = RevocationInfoGatheringSpec(
                            online_fetching_rule=RevinfoOnlineFetchingRule.LOCAL_ONLY,
                        )
                    spec = PdfSignatureValidationSpec(
                        SignatureValidationSpec(
                            cert_validation_policy=signer_policy,
                            ts_cert_validation_policy=tsa_policy,
                            revinfo_gathering_policy=fetching_policy,
                            local_knowledge=LocalKnowledge(
                                known_certs=intermediates,
                            ),
                        )
                    )
                    lta_result = asyncio.run(ades_lta_validation(signature, spec))
                    ades_verdict = getattr(
                        getattr(lta_result, "ades_subindic", None), "name", None
                    )
                    lta_status = getattr(lta_result, "api_status", None)
                    ltv_profile_valid = bool(
                        ades_verdict == "OK"
                        and lta_status is not None
                        and lta_status.bottom_line
                    )
                    if not ltv_profile_valid:
                        raise PAdESLTError(
                            "La validación AdES PAdES-LTA no fue satisfactoria: "
                            + str(ades_verdict or "sin dictamen")
                        )

                if not ltv_profile_valid:
                    raise PAdESLTError(
                        "La validación PAdES-LT no confirmó firma, timestamp y evidencia de revocación."
                    )

                return {
                    "signature_intact": bool(status.intact),
                    "signature_valid": bool(status.valid),
                    "signature_trusted": bool(status.trusted),
                    "timestamp_present": timestamp_status is not None,
                    "timestamp_valid": bool(timestamp_status and timestamp_status.valid),
                    "timestamp_trusted": bool(timestamp_status and timestamp_status.trusted),
                    "dss_present": True,
                    "revocation_data_embedded": revocation_data,
                    "dss_crl_entries": len(crl_entries),
                    "dss_ocsp_entries": len(ocsp_entries),
                    "document_timestamps": len(document_timestamps),
                    "document_timestamps_valid": (
                        len(document_timestamps) if use_lta else 0
                    ),
                    "ltv_profile_valid": ltv_profile_valid,
                    "ltv_validation": "PADES_LTA" if use_lta else "PADES_LT",
                    "ades_validation": use_lta,
                    "ades_verdict": ades_verdict,
                }
        except PAdESLTError:
            raise
        except Exception as exc:
            raise PAdESLTError(
                "No se pudo verificar de forma independiente la firma PAdES, "
                "su cadena de confianza, el timestamp o la evidencia LTV."
            ) from exc

    def sign_pades_lt(self, input_pdf: str, output_pdf: str,
                      field_name: str = "Signature1",
                      reason: str = "Firma con e.firma SAT / Megalodon",
                      location: str = "Mexico",
                      use_lta: bool = False) -> dict:
        """Create PAdES-LT/LTA, then verify it before publishing the output.

        The output is staged beside its destination and atomically promoted
        only after cryptographic, trust, timestamp, DSS and LTV checks pass.
        """
        try:
            signers, timestamps, SigSeedSubFilter, IncrementalPdfFileWriter, ValidationContext, RequestsFetcherBackend = _import_pyhanko()
            vc = build_firma_validation_context(
                trust_root_paths=self.trust_roots,
                intermediate_cert_paths=self.intermediate_certs,
            )
        except Exception as e:
            raise PAdESLTError(
                "No se pudo construir un ValidationContext verificable para PAdES-LT/LTA. "
                "La firma se rechaza sin raíces y política de revocación explícitas."
            ) from e

        signature_meta = signers.PdfSignatureMetadata(
            field_name=field_name,
            md_algorithm="sha256",
            subfilter=SigSeedSubFilter.PADES,
            validation_context=vc,
            embed_validation_info=True,
            use_pades_lta=use_lta,
            reason=reason,
            location=location,
        )

        destination = Path(output_pdf)
        if not destination.parent.exists():
            raise PAdESLTError("El directorio de salida del PDF firmado no existe.")
        staged_fd, staged_name = tempfile.mkstemp(
            prefix=f".{destination.name}.", suffix=".pades-tmp", dir=str(destination.parent)
        )
        os.close(staged_fd)
        staged_path = Path(staged_name)
        try:
            with open(input_pdf, "rb") as inf, open(staged_path, "wb") as outf:
                writer = IncrementalPdfFileWriter(inf)
                signers.sign_pdf(
                    writer,
                    signature_meta=signature_meta,
                    signer=self._pyhanko_signer,
                    timestamper=self._timestamper,
                    output=outf,
                )
                outf.flush()
                os.fsync(outf.fileno())

            validation = self.validate_signed_pdf(
                str(staged_path),
                field_name=field_name,
                use_lta=use_lta,
            )
            os.replace(staged_path, destination)
        except BaseException:
            staged_path.unlink(missing_ok=True)
            raise

        return {
            "success": True,
            "verified": True,
            "validation": validation,
            "output_path": str(destination.resolve()),
            "profile": "PAdES-B-LTA" if use_lta else "PAdES-B-LT",
            "tsa_url": self.tsa_url or self.DEFAULT_TSA_URLS[0],
            "digest": "sha256",
            "validation_info_embedded": True,
            "document_timestamp": use_lta,
        }

    def lta_update(self, pdf_path: str, output_path: Optional[str] = None) -> dict:
        """Atomically append and independently verify an archival timestamp."""
        from pyhanko.pdf_utils.reader import PdfFileReader
        from pyhanko.sign import PdfTimeStamper

        source = Path(pdf_path)
        destination = Path(output_path) if output_path else source
        if not source.is_file() or not destination.parent.exists():
            raise PAdESLTError("El PDF de origen o el directorio de salida no existe.")
        staged_path = None
        try:
            with source.open("rb") as stream:
                reader = PdfFileReader(stream)
                embedded = list(reader.embedded_signatures)
                signature = next((item for item in embedded
                    if str(item.sig_object_type) == "/Sig"), None)
                if signature is None:
                    raise PAdESLTError("No se puede actualizar LTA sin una firma PDF previa.")
                field_name = signature.field_name
                base_is_lta = any(str(item.sig_object_type) == "/DocTimeStamp"
                                  for item in embedded)
            previous_validation = self.validate_signed_pdf(
                str(source), field_name=field_name, use_lta=base_is_lta)
            _, _, _, IncrementalPdfFileWriter, _, _ = _import_pyhanko()
            from pyhanko.sign.validation.dss import DocumentSecurityStore
            from app.config import settings
            from app.modules.firma.validation_context import load_firma_certificates
            with source.open("rb") as rev_stream:
                rev_reader = PdfFileReader(rev_stream)
                dss = DocumentSecurityStore.read_dss(rev_reader)
                if not (dss.crls or dss.ocsps):
                    raise PAdESLTError(
                        "No se puede renovar LTA sin evidencia OCSP/CRL vigente en el DSS."
                    )
                roots = load_firma_certificates(
                    self.trust_roots if self.trust_roots is not None
                    else settings.FIEL_TRUST_ROOT_PATHS
                )
                intermediates = load_firma_certificates(
                    self.intermediate_certs if self.intermediate_certs is not None
                    else settings.FIEL_INTERMEDIATE_CERT_PATHS
                )
                if not roots:
                    raise PAdESLTError(
                        "La renovación LTA requiere trust anchors explícitos."
                    )
                context_kwargs = {
                    "trust_roots": roots,
                    "other_certs": intermediates,
                    "revocation_mode": "require",
                    "allow_fetching": settings.FIEL_ALLOW_REVOCATION_FETCHING,
                }
                if settings.FIEL_ALLOW_REVOCATION_FETCHING:
                    from pyhanko_certvalidator.fetchers.requests_fetchers import RequestsFetcherBackend
                    context_kwargs["fetcher_backend"] = RequestsFetcherBackend()
                context = dss.as_validation_context(context_kwargs)
            staged_fd, staged_name = tempfile.mkstemp(
                prefix=f".{destination.name}.", suffix=".lta-tmp", dir=str(destination.parent))
            os.close(staged_fd)
            staged_path = Path(staged_name)
            timestamper = PdfTimeStamper(self._timestamper)
            with source.open("rb") as inf, staged_path.open("wb") as outf:
                timestamper.timestamp_pdf(
                    IncrementalPdfFileWriter(inf), md_algorithm="sha256",
                    validation_context=context, output=outf)
                outf.flush()
                os.fsync(outf.fileno())
            validation = self.validate_signed_pdf(
                str(staged_path), field_name=field_name, use_lta=True)
            os.replace(staged_path, destination)
            staged_path = None
        except PAdESLTError:
            raise
        except Exception as exc:
            raise PAdESLTError(
                "No se pudo actualizar ni verificar la cadena PAdES-LTA.") from exc
        finally:
            if staged_path is not None:
                staged_path.unlink(missing_ok=True)
        return {
            "success": True, "verified": True,
            "output_path": str(destination.resolve()), "action": "LTA_update",
            "tsa_url": self.tsa_url or self.DEFAULT_TSA_URLS[0],
            "previous_validation": previous_validation, "validation": validation,
        }

    def cleanup(self):
        """Borra archivos temporales PEM."""
        import shutil
        if hasattr(self, '_temp_dir') and self._temp_dir.exists():
            shutil.rmtree(self._temp_dir, ignore_errors=True)

    def __del__(self):
        self.cleanup()


# =============================================================================
# CLI / TEST
# =============================================================================

if __name__ == "__main__":
    import argparse
    parser = argparse.ArgumentParser(description="Megalodon PAdES-LT Signer")
    parser.add_argument("--cer", required=True)
    parser.add_argument("--key", required=True)
    parser.add_argument("--password", required=True)
    parser.add_argument("--input", required=True)
    parser.add_argument("--output", required=True)
    parser.add_argument("--tsa", default=None, help="URL del TSA")
    parser.add_argument("--lta", action="store_true", help="Generar PAdES-B-LTA")
    parser.add_argument("--lta-update", action="store_true", help="Actualizar timestamp LTA")
    args = parser.parse_args()

    signer = PAdESLTSigner(args.cer, args.key, args.password, tsa_url=args.tsa)

    if args.lta_update:
        result = signer.lta_update(args.input, args.output)
    else:
        result = signer.sign_pades_lt(args.input, args.output, use_lta=args.lta)

    import json
    print(json.dumps(result, indent=2, ensure_ascii=False))
    signer.cleanup()
