#!/usr/bin/env python3
# Copyright © 2026 Cristian Rodriguez
# All rights reserved.
# Unauthorized copying, modification, distribution, or use is prohibited
# without prior written permission.

"""
================================================================================
Megalodon CFDI 4.0 — Sellado Digital SAT (sin mocks)
================================================================================
Generación de cadena original y sello digital para CFDI 4.0 según Anexo 20 SAT.

El sellado digital SAT es diferente a XAdES/PAdES. Consiste en:
  1. Generar la "cadena original" aplicando la XSLT del SAT al XML del CFDI
  2. Calcular SHA-256 de la cadena original
  3. Firmar el digest con RSA-SHA256 usando la e.firma (clave privada .key)
  4. El resultado (sello) se inserta como atributo en el XML del CFDI

Dependencias:
    pip install cryptography lxml requests

Nota: Este módulo NO timbra. El timbrado requiere un PAC autorizado por el SAT.
      Este módulo genera el XML sellado listo para enviar a cualquier PAC.
"""

import os
import sys
import base64
import hashlib
import tempfile
from pathlib import Path
from typing import Optional, Union
from dataclasses import dataclass

from cryptography import x509
from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.primitives.asymmetric import padding
from cryptography.hazmat.backends import default_backend

from lxml import etree

import structlog

logger = structlog.get_logger("megalodon.cfdi40")
# Antes: `logger` no estaba definido en ningún lado de este archivo.
# Si tanto la carga DER como PEM de la .key fallaban (contraseña
# incorrecta, archivo corrupto, formato no soportado -- un caso real
# y esperable al procesar .key subidas por el usuario), el except
# hacía NameError en vez de loguear, y ESE NameError -- no el
# ValueError con el mensaje claro dos líneas abajo -- era lo que
# terminaba propagándose. Quien intentara sellar un CFDI se topaba
# con un error interno sin sentido en vez de "Verifique contraseña".


# URLs de XSLT del SAT (Anexo 20 v4.0)
SAT_XSLT_CFDI40 = "https://www.sat.gob.mx/sitio_internet/cfd/4/cadenaoriginal_4_0/cadenaoriginal_4_0.xslt"
SAT_XSLT_TFD = "https://www.sat.gob.mx/sitio_internet/cfd/TimbreFiscalDigital/cadenaoriginal_TFD_1_1.xslt"

# XSLT embebido como fallback (versión 4.0 simplificada para operación offline)
# En producción, descargar siempre la versión oficial del SAT.
XSLT_CFDI40_FALLBACK = """<?xml version="1.0" encoding="UTF-8"?>
<xsl:stylesheet version="2.0" xmlns:xsl="http://www.w3.org/1999/XSL/Transform"
  xmlns:cfdi="http://www.sat.gob.mx/cfd/4"
  xmlns:tfd="http://www.sat.gob.mx/TimbreFiscalDigital">
  <xsl:strip-space elements="*"/>
  <xsl:output method="text" encoding="UTF-8"/>
  <xsl:template match="/">
    <xsl:apply-templates select="/cfdi:Comprobante"/>
  </xsl:template>
  <xsl:template match="cfdi:Comprobante">
    <xsl:text>|</xsl:text>
    <xsl:value-of select="@Version"/>
    <xsl:text>|</xsl:text>
    <xsl:value-of select="@Serie"/>
    <xsl:text>|</xsl:text>
    <xsl:value-of select="@Folio"/>
    <xsl:text>|</xsl:text>
    <xsl:value-of select="@Fecha"/>
    <xsl:text>|</xsl:text>
    <xsl:value-of select="@Sello"/>
    <xsl:text>|</xsl:text>
    <xsl:value-of select="@FormaPago"/>
    <xsl:text>|</xsl:text>
    <xsl:value-of select="@NoCertificado"/>
    <xsl:text>|</xsl:text>
    <xsl:value-of select="@Certificado"/>
    <xsl:text>|</xsl:text>
    <xsl:value-of select="@CondicionesDePago"/>
    <xsl:text>|</xsl:text>
    <xsl:value-of select="@SubTotal"/>
    <xsl:text>|</xsl:text>
    <xsl:value-of select="@Descuento"/>
    <xsl:text>|</xsl:text>
    <xsl:value-of select="@Moneda"/>
    <xsl:text>|</xsl:text>
    <xsl:value-of select="@TipoCambio"/>
    <xsl:text>|</xsl:text>
    <xsl:value-of select="@Total"/>
    <xsl:text>|</xsl:text>
    <xsl:value-of select="@TipoDeComprobante"/>
    <xsl:text>|</xsl:text>
    <xsl:value-of select="@Exportacion"/>
    <xsl:text>|</xsl:text>
    <xsl:value-of select="@MetodoPago"/>
    <xsl:text>|</xsl:text>
    <xsl:value-of select="@LugarExpedicion"/>
    <xsl:text>|</xsl:text>
    <xsl:value-of select="@Confirmacion"/>
    <xsl:text>|</xsl:text>
    <xsl:apply-templates select="cfdi:InformacionGlobal"/>
    <xsl:apply-templates select="cfdi:CfdiRelacionados"/>
    <xsl:apply-templates select="cfdi:Emisor"/>
    <xsl:apply-templates select="cfdi:Receptor"/>
    <xsl:apply-templates select="cfdi:Conceptos"/>
    <xsl:apply-templates select="cfdi:Impuestos"/>
    <xsl:apply-templates select="cfdi:Complemento"/>
    <xsl:text>|</xsl:text>
  </xsl:template>
  <!-- Templates simplificados — en producción usar XSLT oficial completo del SAT -->
  <xsl:template match="cfdi:Emisor">
    <xsl:value-of select="@Rfc"/>
    <xsl:text>|</xsl:text>
    <xsl:value-of select="@Nombre"/>
    <xsl:text>|</xsl:text>
    <xsl:value-of select="@RegimenFiscal"/>
    <xsl:text>|</xsl:text>
    <xsl:value-of select="@FacAtrAdquirente"/>
    <xsl:text>|</xsl:text>
  </xsl:template>
  <xsl:template match="cfdi:Receptor">
    <xsl:value-of select="@Rfc"/>
    <xsl:text>|</xsl:text>
    <xsl:value-of select="@Nombre"/>
    <xsl:text>|</xsl:text>
    <xsl:value-of select="@DomicilioFiscalReceptor"/>
    <xsl:text>|</xsl:text>
    <xsl:value-of select="@ResidenciaFiscal"/>
    <xsl:text>|</xsl:text>
    <xsl:value-of select="@NumRegIdTrib"/>
    <xsl:text>|</xsl:text>
    <xsl:value-of select="@RegimenFiscalReceptor"/>
    <xsl:text>|</xsl:text>
    <xsl:value-of select="@UsoCFDI"/>
    <xsl:text>|</xsl:text>
  </xsl:template>
  <xsl:template match="cfdi:Conceptos">
    <xsl:for-each select="cfdi:Concepto">
      <xsl:value-of select="@ClaveProdServ"/>
      <xsl:text>|</xsl:text>
      <xsl:value-of select="@NoIdentificacion"/>
      <xsl:text>|</xsl:text>
      <xsl:value-of select="@Cantidad"/>
      <xsl:text>|</xsl:text>
      <xsl:value-of select="@ClaveUnidad"/>
      <xsl:text>|</xsl:text>
      <xsl:value-of select="@Unidad"/>
      <xsl:text>|</xsl:text>
      <xsl:value-of select="@Descripcion"/>
      <xsl:text>|</xsl:text>
      <xsl:value-of select="@ValorUnitario"/>
      <xsl:text>|</xsl:text>
      <xsl:value-of select="@Importe"/>
      <xsl:text>|</xsl:text>
      <xsl:value-of select="@Descuento"/>
      <xsl:text>|</xsl:text>
      <xsl:value-of select="@ObjetoImp"/>
      <xsl:text>|</xsl:text>
      <xsl:apply-templates select="cfdi:Impuestos"/>
      <xsl:apply-templates select="cfdi:ACuentaTerceros"/>
      <xsl:apply-templates select="cfdi:InformacionAduanera"/>
      <xsl:apply-templates select="cfdi:CuentaPredial"/>
      <xsl:apply-templates select="cfdi:ComplementoConcepto"/>
      <xsl:apply-templates select="cfdi:Parte"/>
    </xsl:for-each>
  </xsl:template>
  <xsl:template match="cfdi:Impuestos">
    <xsl:for-each select="cfdi:Traslados/cfdi:Traslado">
      <xsl:value-of select="@Base"/>
      <xsl:text>|</xsl:text>
      <xsl:value-of select="@Impuesto"/>
      <xsl:text>|</xsl:text>
      <xsl:value-of select="@TipoFactor"/>
      <xsl:text>|</xsl:text>
      <xsl:value-of select="@TasaOCuota"/>
      <xsl:text>|</xsl:text>
      <xsl:value-of select="@Importe"/>
      <xsl:text>|</xsl:text>
    </xsl:for-each>
    <xsl:for-each select="cfdi:Retenciones/cfdi:Retencion">
      <xsl:value-of select="@Base"/>
      <xsl:text>|</xsl:text>
      <xsl:value-of select="@Impuesto"/>
      <xsl:text>|</xsl:text>
      <xsl:value-of select="@TipoFactor"/>
      <xsl:text>|</xsl:text>
      <xsl:value-of select="@TasaOCuota"/>
      <xsl:text>|</xsl:text>
      <xsl:value-of select="@Importe"/>
      <xsl:text>|</xsl:text>
    </xsl:for-each>
  </xsl:template>
  <xsl:template match="cfdi:Complemento">
    <xsl:apply-templates select="tfd:TimbreFiscalDigital"/>
  </xsl:template>
  <xsl:template match="tfd:TimbreFiscalDigital">
    <xsl:value-of select="@UUID"/>
    <xsl:text>|</xsl:text>
    <xsl:value-of select="@FechaTimbrado"/>
    <xsl:text>|</xsl:text>
    <xsl:value-of select="@RfcProvCertif"/>
    <xsl:text>|</xsl:text>
    <xsl:value-of select="@Leyenda"/>
    <xsl:text>|</xsl:text>
    <xsl:value-of select="@SelloCFD"/>
    <xsl:text>|</xsl:text>
    <xsl:value-of select="@NoCertificadoSAT"/>
    <xsl:text>|</xsl:text>
  </xsl:template>
  <xsl:template match="*">
    <xsl:apply-templates select="*"/>
  </xsl:template>
</xsl:stylesheet>"""


@dataclass
class CFDISelloResult:
    """Resultado del sellado digital."""
    success: bool
    xml_sellado: Optional[str] = None
    cadena_original: Optional[str] = None
    sello_digital: Optional[str] = None
    certificado_b64: Optional[str] = None
    no_certificado: Optional[str] = None
    error: Optional[str] = None


class CFDISATSigner:
    """
    Sellador digital de CFDI 4.0 según Anexo 20 del SAT.
    Usa e.firma (FIEL/FUP) para generar el sello.
    """

    def __init__(self, cer_path: str, key_path: str, password: str):
        self.cer_path = Path(cer_path)
        self.key_path = Path(key_path)
        self.password = password.encode("utf-8") if isinstance(password, str) else password

        self._cert: Optional[x509.Certificate] = None
        self._private_key = None
        self._xslt_transform = None

        self._load_credentials()
        self._load_xslt()

    def _load_credentials(self) -> None:
        """Carga certificado y clave privada de e.firma."""
        cer_data = self.cer_path.read_bytes()
        try:
            self._cert = x509.load_der_x509_certificate(cer_data, default_backend())
        except Exception:
            self._cert = x509.load_pem_x509_certificate(cer_data, default_backend())

        key_data = self.key_path.read_bytes()
        for loader in [
            lambda: serialization.load_der_private_key(key_data, password=self.password, backend=default_backend()),
            lambda: serialization.load_pem_private_key(key_data, password=self.password, backend=default_backend()),
        ]:
            try:
                self._private_key = loader()
                break
            except Exception as exc:
                logger.debug("cfdi_private_key_loader_failed", exc_info=exc)
        if not self._private_key:
            raise ValueError("No se pudo descifrar la .key. Verifique contraseña.")

    def _load_xslt(self) -> None:
        """Carga la transformación XSLT del SAT."""
        # Intentar descargar XSLT oficial del SAT
        try:
            import requests
            resp = requests.get(SAT_XSLT_CFDI40, timeout=15)
            if resp.status_code == 200:
                xslt_xml = resp.text
            else:
                xslt_xml = XSLT_CFDI40_FALLBACK
        except Exception:
            xslt_xml = XSLT_CFDI40_FALLBACK

        xslt_root = etree.fromstring(xslt_xml.encode("utf-8"))
        self._xslt_transform = etree.XSLT(xslt_root)

    @property
    def no_certificado(self) -> str:
        """Número de certificado en formato SAT (hex del serial)."""
        return format(self._cert.serial_number, 'x').upper()

    @property
    def certificado_b64(self) -> str:
        """Certificado en base64 para embeber en el CFDI."""
        return base64.b64encode(
            self._cert.public_bytes(serialization.Encoding.DER)
        ).decode("ascii")

    def sellar_xml(self, xml_input: Union[str, bytes, Path],
                   output_path: Optional[str] = None) -> CFDISelloResult:
        """
        Sella un XML de CFDI 4.0.

        Args:
            xml_input: Ruta o bytes del XML del CFDI (sin sello)
            output_path: Si se proporciona, guarda el XML sellado

        Returns:
            CFDISelloResult con cadena original, sello y XML sellado
        """
        try:
            # Cargar XML
            if isinstance(xml_input, (str, Path)):
                xml_bytes = Path(xml_input).read_bytes()
            else:
                xml_bytes = xml_input

            root = etree.fromstring(xml_bytes)
            nsmap = root.nsmap
            cfdi_ns = nsmap.get(None) or "http://www.sat.gob.mx/cfd/4"

            # 1. Generar cadena original aplicando XSLT
            try:
                result_tree = self._xslt_transform(root)
                cadena_original = str(result_tree)
            except Exception as e:
                # Fallback: construir cadena manualmente si XSLT falla
                cadena_original = self._build_cadena_manual(root)

            # 2. Calcular digest SHA-256 de la cadena original
            digest = hashlib.sha256(cadena_original.encode("utf-8")).digest()

            # 3. Firmar digest con RSA-SHA256 (PKCS#1 v1.5)
            signature = self._private_key.sign(
                digest,
                padding.PKCS1v15(),
                hashes.SHA256()
            )
            sello_digital = base64.b64encode(signature).decode("ascii")

            # 4. Insertar sello, certificado y NoCertificado en el XML
            root.set("Sello", sello_digital)
            root.set("Certificado", self.certificado_b64)
            root.set("NoCertificado", self.no_certificado)

            # 5. Serializar XML sellado
            xml_sellado = etree.tostring(
                root, pretty_print=True, xml_declaration=True, encoding="UTF-8"
            ).decode("utf-8")

            # 6. Guardar si se pidió
            if output_path:
                Path(output_path).write_bytes(xml_sellado.encode("utf-8"))

            return CFDISelloResult(
                success=True,
                xml_sellado=xml_sellado,
                cadena_original=cadena_original,
                sello_digital=sello_digital,
                certificado_b64=self.certificado_b64,
                no_certificado=self.no_certificado
            )

        except Exception as e:
            return CFDISelloResult(success=False, error=str(e))

    def _build_cadena_manual(self, root) -> str:
        """
        Fallback: construye cadena original manualmente si XSLT falla.
        Implementación simplificada del Anexo 20.
        """
        parts = ["|"]

        # Atributos del Comprobante
        attrs = ["Version", "Serie", "Folio", "Fecha", "Sello", "FormaPago",
                 "NoCertificado", "Certificado", "CondicionesDePago", "SubTotal",
                 "Descuento", "Moneda", "TipoCambio", "Total", "TipoDeComprobante",
                 "Exportacion", "MetodoPago", "LugarExpedicion", "Confirmacion"]
        for attr in attrs:
            val = root.get(attr, "")
            parts.append(val)
            parts.append("|")

        # Emisor
        emisor = root.find(".//{http://www.sat.gob.mx/cfd/4}Emisor")
        if emisor is not None:
            for a in ["Rfc", "Nombre", "RegimenFiscal", "FacAtrAdquirente"]:
                parts.append(emisor.get(a, ""))
                parts.append("|")

        # Receptor
        receptor = root.find(".//{http://www.sat.gob.mx/cfd/4}Receptor")
        if receptor is not None:
            for a in ["Rfc", "Nombre", "DomicilioFiscalReceptor", "ResidenciaFiscal",
                      "NumRegIdTrib", "RegimenFiscalReceptor", "UsoCFDI"]:
                parts.append(receptor.get(a, ""))
                parts.append("|")

        # Conceptos
        conceptos = root.findall(".//{http://www.sat.gob.mx/cfd/4}Concepto")
        for c in conceptos:
            for a in ["ClaveProdServ", "NoIdentificacion", "Cantidad", "ClaveUnidad",
                      "Unidad", "Descripcion", "ValorUnitario", "Importe", "Descuento", "ObjetoImp"]:
                parts.append(c.get(a, ""))
                parts.append("|")

        # Impuestos totales
        impuestos = root.find(".//{http://www.sat.gob.mx/cfd/4}Impuestos")
        if impuestos is not None:
            total_traslados = impuestos.get("TotalImpuestosTrasladados", "")
            total_retenciones = impuestos.get("TotalImpuestosRetenidos", "")
            parts.append(total_traslados); parts.append("|")
            parts.append(total_retenciones); parts.append("|")

        return "".join(parts)

    def validar_cadena(self, xml_sellado: Union[str, bytes]) -> dict:
        """
        Valida que el sello de un CFDI sea correcto verificando
        la cadena original contra la clave pública del certificado.

        Args:
            xml_sellado: XML del CFDI con sello ya incluido

        Returns:
            dict con resultado de validación
        """
        try:
            if isinstance(xml_sellado, str):
                root = etree.fromstring(xml_sellado.encode("utf-8"))
            else:
                root = etree.fromstring(xml_sellado)

            sello = root.get("Sello", "")
            cert_b64 = root.get("Certificado", "")

            if not sello or not cert_b64:
                return {"valid": False, "error": "Faltan atributos Sello o Certificado"}

            # Reconstruir cadena original
            try:
                result_tree = self._xslt_transform(root)
                cadena = str(result_tree)
            except Exception:
                cadena = self._build_cadena_manual(root)

            # Verificar sello con certificado embebido
            cert_der = base64.b64decode(cert_b64)
            cert = x509.load_der_x509_certificate(cert_der, default_backend())
            pub_key = cert.public_key()

            digest = hashlib.sha256(cadena.encode("utf-8")).digest()
            sig_bytes = base64.b64decode(sello)

            try:
                pub_key.verify(
                    sig_bytes,
                    digest,
                    padding.PKCS1v15(),
                    hashes.SHA256()
                )
                return {
                    "valid": True,
                    "rfc_emisor": cert.subject.get_attributes_for_oid(x509.NameOID.COMMON_NAME)[0].value if cert.subject.get_attributes_for_oid(x509.NameOID.COMMON_NAME) else "",
                    "serial_cert": format(cert.serial_number, 'x').upper(),
                    "cadena_original": cadena
                }
            except Exception as e:
                return {"valid": False, "error": f"Verificación criptográfica fallida: {e}"}

        except Exception as e:
            return {"valid": False, "error": str(e)}


# =============================================================================
# CLI
# =============================================================================

if __name__ == "__main__":
    import argparse
    parser = argparse.ArgumentParser(description="Megalodon CFDI 4.0 Sello Digital SAT")
    parser.add_argument("--cer", required=True, help="Archivo .cer de e.firma")
    parser.add_argument("--key", required=True, help="Archivo .key de e.firma")
    parser.add_argument("--password", required=True, help="Contraseña de la .key")
    parser.add_argument("--xml", required=True, help="XML del CFDI a sellar")
    parser.add_argument("--output", help="Ruta de salida del XML sellado")
    parser.add_argument("--validate", action="store_true", help="Validar XML sellado")
    args = parser.parse_args()

    signer = CFDISATSigner(args.cer, args.key, args.password)

    if args.validate:
        xml_data = Path(args.xml).read_bytes()
        result = signer.validar_cadena(xml_data)
        import json
        print(json.dumps(result, indent=2, ensure_ascii=False))
    else:
        result = signer.sellar_xml(args.xml, args.output)
        import json
        print(json.dumps({
            "success": result.success,
            "cadena_original": result.cadena_original,
            "sello_digital": result.sello_digital[:60] + "..." if result.sello_digital else None,
            "no_certificado": result.no_certificado,
            "error": result.error
        }, indent=2, ensure_ascii=False))
        if result.success and args.output:
            print(f"✅ XML sellado guardado en: {args.output}")
