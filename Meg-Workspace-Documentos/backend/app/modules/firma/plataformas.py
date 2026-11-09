# Copyright © 2026 Cristian Rodriguez
# All rights reserved.
# Unauthorized copying, modification, distribution, or use is prohibited
# without prior written permission.

"""
Reglas de formato de firma requeridas por cada plataforma gubernamental
mexicana de licitación/contratación.

Extraído de megalodon_efirma_core.py (clase PlatformAdapter) -- se porta
solo la tabla de reglas por plataforma, no el resto de EfirmaCore
(carga de certificado y firma XAdES/PAdES ya viven en
firma_electronica.py / pades_lt.py de este mismo backend).

Por qué importa: cada plataforma exige un formato de firma distinto para
el mismo tipo de documento (ej. CompraNet pide XAdES-EPES para la
proposición técnica pero PAdES-LT para el contrato). Firmar con el
formato equivocado significa que la plataforma rechaza el documento -- no
es un detalle cosmético.
"""
from enum import Enum
from typing import Dict, List


class PlataformaLicitacion(str, Enum):
    """Plataformas de licitación mexicanas soportadas."""
    COMPRANET = "compranet"        # SFP -- XAdES-EPES XML
    COMPRAS_MX = "compras_mx"      # Plataforma unificada federal
    IMSS = "imss"
    INFONAVIT = "infonavit"
    SEOP_GENERICO = "seop_generico"  # Secretaría de Obras Públicas estatal (genérico)
    CFE = "cfe"
    PEMEX = "pemex"
    PERSONALIZADA = "personalizada"


# document_type -> formato de firma requerido
REGLAS_POR_PLATAFORMA: Dict[PlataformaLicitacion, Dict[str, str]] = {
    PlataformaLicitacion.COMPRANET: {
        "proposicion_tecnica": "xades_epes_enveloped",
        "proposicion_economica": "xades_epes_enveloped",
        "anexos": "pades_basic",
        "contrato": "pades_lt",
    },
    PlataformaLicitacion.COMPRAS_MX: {
        "proposicion": "xades_epes_enveloped",
        "anexos": "pades_lt",
        "garantia": "xades_epes_enveloped",
    },
    PlataformaLicitacion.IMSS: {
        "proposicion": "xades_epes_enveloped",
        "contrato": "pades_lt",
    },
    PlataformaLicitacion.INFONAVIT: {
        "proposicion": "xades_epes_enveloped",
        "anexos": "pades_lt",
    },
    PlataformaLicitacion.SEOP_GENERICO: {
        "proposicion": "xades_epes_enveloped",
        "anexos": "pades_basic",
    },
    PlataformaLicitacion.CFE: {
        "proposicion": "xades_epes_enveloped",
        "anexos": "pades_lt",
    },
    PlataformaLicitacion.PEMEX: {
        "proposicion": "xades_epes_enveloped",
        "contrato": "pades_lt",
    },
    PlataformaLicitacion.PERSONALIZADA: {
        "default": "xades_epes_enveloped",
    },
}


def formato_requerido(plataforma: PlataformaLicitacion, tipo_documento: str) -> str:
    """Formato de firma que exige una plataforma para un tipo de documento.

    Si la plataforma no tiene regla explícita para ese tipo de documento,
    cae al 'default' de esa plataforma, o a xades_epes_enveloped como
    último recurso (es el formato más comúnmente exigido).
    """
    reglas = REGLAS_POR_PLATAFORMA.get(plataforma, {})
    return reglas.get(tipo_documento.lower()) or reglas.get("default", "xades_epes_enveloped")


def advertencias_previas_a_firma(
    plataforma: PlataformaLicitacion,
    dias_para_vencer: int,
) -> List[str]:
    """Advertencias antes de firmar, según qué tan próximo esté a vencer
    el certificado y reglas específicas de la plataforma."""
    advertencias: List[str] = []

    if dias_para_vencer <= 0:
        advertencias.append("CERTIFICADO EXPIRADO -- no podrá firmar en ninguna plataforma.")
    elif dias_para_vencer <= 30:
        advertencias.append(f"El certificado vence en {dias_para_vencer} días. Renueve vía SAT ID.")

    if plataforma == PlataformaLicitacion.COMPRANET and dias_para_vencer <= 0:
        advertencias.append("CompraNet rechaza certificados expirados. Tramite renovación antes de continuar.")

    return advertencias
