# Copyright © 2026 Cristian Rodriguez
# Document Compliance Engine — validación determinista de evidencia documental

from datetime import datetime, timezone
from typing import Any, Dict, List

from .domain import RequisitoEstructurado, Hallazgo, NivelRiesgo, TipoRequisito


class DocumentComplianceEngine:
    """Valida requisitos documentales usando únicamente reglas declaradas.

    No contiene porcentajes, leyes, fechas de vigencia ni formatos jurisdiccionales
    embebidos. Esos parámetros llegan en ``RequisitoEstructurado.validaciones``.
    """

    def __init__(self, requisitos: List[RequisitoEstructurado]):
        self.requisitos = requisitos

    def validar(self, documentos_proporcionados: Dict[str, Any]) -> List[Hallazgo]:
        hallazgos: List[Hallazgo] = []
        for req in self.requisitos:
            if req.categoria in (TipoRequisito.ADMINISTRATIVO, TipoRequisito.LEGAL):
                hallazgos.extend(self._validar_requisito(req, documentos_proporcionados))
        hallazgos.extend(self._validar_correspondencia(documentos_proporcionados))
        hallazgos.extend(self._validar_duplicados(documentos_proporcionados))
        hallazgos.extend(self._validar_vigencia(documentos_proporcionados))
        return hallazgos

    def _validar_requisito(self, req: RequisitoEstructurado, docs: Dict[str, Any]) -> List[Hallazgo]:
        hallazgos: List[Hallazgo] = []
        rules = req.validaciones or {}
        for evidencia in req.evidencia_requerida:
            doc = docs.get(evidencia)
            if not doc:
                nivel = NivelRiesgo.CRITICO if req.obligatorio else NivelRiesgo.RELEVANTE
                hallazgos.append(Hallazgo(
                    requisito_codigo=req.codigo, nivel_riesgo=nivel,
                    descripcion=f"Documento requerido ausente: {evidencia}",
                    documento_afectado=evidencia, resultado="FALTANTE_DOCUMENTAL",
                    fundamento=req.fundamento_legal or req.seccion_origen,
                ))
                continue
            if not isinstance(doc, dict):
                continue

            if bool(rules.get("requiere_firma")) and not bool(doc.get("firmado")):
                hallazgos.append(Hallazgo(
                    requisito_codigo=req.codigo, nivel_riesgo=NivelRiesgo.CRITICO,
                    descripcion=f"Documento {evidencia} presente pero sin firma válida",
                    documento_afectado=evidencia, resultado="FIRMA_INVALIDA",
                    fundamento=req.fundamento_legal or req.seccion_origen,
                ))

            if bool(rules.get("requiere_vigencia")):
                self._append_expiry_hallazgo(req, evidencia, doc, hallazgos)

            if bool(rules.get("validar_rfc")):
                rfc = doc.get("rfc")
                if isinstance(doc.get("contenido"), dict):
                    rfc = rfc or doc["contenido"].get("rfc")
                if not self._validar_rfc(rfc):
                    hallazgos.append(Hallazgo(
                        requisito_codigo=req.codigo, nivel_riesgo=NivelRiesgo.CRITICO,
                        descripcion=f"RFC inválido en documento {evidencia}",
                        documento_afectado=evidencia, valor_encontrado=str(rfc) if rfc else None,
                        resultado="RFC_INVALIDO", fundamento=req.fundamento_legal or req.seccion_origen,
                    ))

        return hallazgos

    @staticmethod
    def _append_expiry_hallazgo(req: RequisitoEstructurado, evidencia: str, doc: Dict[str, Any], hallazgos: List[Hallazgo]) -> None:
        vigencia = doc.get("vigencia_hasta")
        if isinstance(vigencia, str):
            try:
                vigencia = datetime.fromisoformat(vigencia.replace("Z", "+00:00"))
            except ValueError:
                return
        if isinstance(vigencia, datetime):
            current = datetime.now(timezone.utc)
            if vigencia.tzinfo is None:
                vigencia = vigencia.replace(tzinfo=timezone.utc)
            if vigencia < current:
                hallazgos.append(Hallazgo(
                    requisito_codigo=req.codigo, nivel_riesgo=NivelRiesgo.CRITICO,
                    descripcion=f"Documento {evidencia} vencido", documento_afectado=evidencia,
                    resultado="VIGENCIA_VENCIDA", fundamento=req.fundamento_legal or req.seccion_origen,
                ))

    def _validar_correspondencia(self, docs: Dict[str, Any]) -> List[Hallazgo]:
        hallazgos: List[Hallazgo] = []
        montos: Dict[str, float] = {}
        for nombre, doc in docs.items():
            if not isinstance(doc, dict):
                continue
            contenido = doc.get("contenido") if isinstance(doc.get("contenido"), dict) else {}
            monto = doc.get("monto", contenido.get("monto"))
            if monto is not None:
                try:
                    montos[nombre] = float(monto)
                except (TypeError, ValueError):
                    continue
        if "catalogo_conceptos" in montos and "oferta_economica" in montos and abs(montos["catalogo_conceptos"] - montos["oferta_economica"]) > 0.01:
            hallazgos.append(Hallazgo(
                requisito_codigo="CORR-MONTO-001", nivel_riesgo=NivelRiesgo.CRITICO,
                descripcion="Discrepancia entre catálogo de conceptos y oferta económica",
                valor_encontrado=f"Catálogo: {montos['catalogo_conceptos']}, Oferta: {montos['oferta_economica']}",
                resultado="INCONSISTENCIA_MONTO", fundamento="Regla de consistencia declarada en el procedimiento",
            ))
        return hallazgos

    def _validar_duplicados(self, docs: Dict[str, Any]) -> List[Hallazgo]:
        hallazgos: List[Hallazgo] = []
        hashes_vistos: Dict[str, str] = {}
        for nombre, doc in docs.items():
            if not isinstance(doc, dict):
                continue
            hash_doc = doc.get("hash") or doc.get("checksum")
            if not hash_doc:
                continue
            if hash_doc in hashes_vistos:
                hallazgos.append(Hallazgo(
                    requisito_codigo="DUP-001", nivel_riesgo=NivelRiesgo.RELEVANTE,
                    descripcion=f"Documento duplicado detectado: {nombre} coincide con {hashes_vistos[hash_doc]}",
                    documento_afectado=nombre, resultado="DOCUMENTO_DUPLICADO",
                    fundamento="Regla de integridad documental declarada en el procedimiento",
                ))
            else:
                hashes_vistos[hash_doc] = nombre
        return hallazgos

    @staticmethod
    def _validar_vigencia(docs: Dict[str, Any]) -> List[Hallazgo]:
        # La vigencia global sólo se comprueba cuando el propio documento la declara
        # y una regla específica la exige; no se infiere obligación jurídica por defecto.
        return []

    @staticmethod
    def _validar_rfc(rfc: Any) -> bool:
        if not isinstance(rfc, str):
            return False
        normalized = rfc.strip().upper()
        if len(normalized) not in (12, 13):
            return False
        # Validación estructural, sin afirmar validez fiscal ante autoridad externa.
        body = normalized[:-3]
        tail = normalized[-3:]
        return body.isalnum() and tail.isalnum() and any(ch.isdigit() for ch in tail)
