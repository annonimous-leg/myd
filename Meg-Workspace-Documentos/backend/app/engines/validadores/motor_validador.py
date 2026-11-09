# Copyright © 2026 Cristian Rodriguez
# All rights reserved.
# Unauthorized copying, modification, distribution, or use is prohibited
# without prior written permission.

"""
Motor de validación determinista de propuestas de licitación.

Reescrito por completo: el motor anterior no hacía ninguna validación
real -- "validar" un RFC significaba únicamente checar que midiera 12 o
13 caracteres (`len(rfc) == 12 or 13`), sin tocar ninguna regla de
negocio real (SAT, IMSS, INFONAVIT, FSR, maquinaria, sobrecostos, etc.).

Portado fielmente de los 10 validadores reales en megalodon_costos_v3_1.py
(clases ValidadorSAT32D, ValidadorSeguridadSocial, ValidadorFirmaElectronica,
ValidadorFactorSalarioReal, ValidadorCostosHorariosMaquinaria,
ValidadorSobrecostos, ValidadorCongruenciaTemporal,
ValidadorGarantiaCumplimiento, ValidadorPublicacionSIRECO,
ValidadorRequisitosParticipacion) + el orquestador MotorDeterministaLicitaciones.

Regla de negocio importante que se preserva tal cual: si un validador
"crítico" (es_critica=True, que son todos en el original) falla, la
evaluación se detiene ahí mismo y la propuesta queda DESCALIFICADA -- no
seguía evaluando el resto. Esto es fiel al comportamiento original, no una
simplificación.
"""
from dataclasses import dataclass, asdict, field
from datetime import date, datetime, timezone
from typing import Any, Dict, List, Optional

from app.core.constants import CONSTANTES


def _now_utc() -> datetime:
    return datetime.now(timezone.utc)


@dataclass
class ResultadoValidacion:
    id_regla: str
    seccion: str
    estatus: str  # PASA | FALLA | NO_APLICA
    valor_detectado: str
    valor_esperado: str
    evidencia: str

    def __post_init__(self):
        if self.estatus not in ("PASA", "FALLA", "NO_APLICA"):
            raise ValueError(f"Estatus inválido: {self.estatus}")

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


class ValidadorBase:
    id_regla: str = ""
    seccion: str = ""
    es_critica: bool = True

    def evaluar(self, datos: Dict[str, Any]) -> ResultadoValidacion:
        raise TypeError(f"{self.__class__.__name__} no implementa el contrato de evaluación determinista.")


class ValidadorSAT32D(ValidadorBase):
    """Opinión de cumplimiento SAT (Art. 32-D CFF)."""
    id_regla = "REG-FIS-32D"
    seccion = "Legal-Fiscal"
    es_critica = True

    def evaluar(self, datos):
        fiscal = datos.get("fiscal", {})
        opinion_sentido = str(fiscal.get("opinion_sat_sentido", "")).upper()
        fecha_emision_str = str(fiscal.get("opinion_sat_fecha", ""))

        if opinion_sentido != "POSITIVA":
            return ResultadoValidacion(
                "REG-FIS-32D-SENTIDO", self.seccion, "FALLA",
                valor_detectado=opinion_sentido, valor_esperado="POSITIVA",
                evidencia="La Opinión de Cumplimiento SAT no es estrictamente POSITIVA (Art. 32-D CFF).",
            )
        try:
            fecha_emision = datetime.strptime(fecha_emision_str, "%Y-%m-%d").date()
            dias_antiguedad = (date.today() - fecha_emision).days
            if dias_antiguedad > CONSTANTES.VIGENCIA_OPINION_SAT_DIAS:
                return ResultadoValidacion(
                    "REG-FIS-32D-VIGENCIA", self.seccion, "FALLA",
                    valor_detectado=f"{dias_antiguedad} días",
                    valor_esperado=f"<= {CONSTANTES.VIGENCIA_OPINION_SAT_DIAS} días",
                    evidencia="La opinión del SAT excede la antigüedad máxima permitida.",
                )
        except ValueError:
            return ResultadoValidacion(
                self.id_regla, self.seccion, "FALLA",
                valor_detectado="Formato inválido", valor_esperado="YYYY-MM-DD",
                evidencia="Fecha de emisión del SAT ilegible o corrupta.",
            )
        return ResultadoValidacion(
            self.id_regla, self.seccion, "PASA",
            "POSITIVA y Vigente", "POSITIVA y Vigente",
            "Cumple Art. 32-D CFF y vigencia RMF 2026.",
        )


class ValidadorSeguridadSocial(ValidadorBase):
    """Opinión de cumplimiento IMSS / INFONAVIT."""
    id_regla = "REG-FIS-32D-SEG-SOCIAL"
    seccion = "Legal-Fiscal"
    es_critica = True

    def evaluar(self, datos):
        fiscal = datos.get("fiscal", {})
        opinion_imss = str(fiscal.get("opinion_imss_sentido", "")).upper()
        opinion_infonavit = str(fiscal.get("opinion_infonavit_sentido", "")).upper()

        if opinion_imss != "POSITIVA":
            return ResultadoValidacion(
                self.id_regla, self.seccion, "FALLA",
                valor_detectado=f"IMSS: {opinion_imss}", valor_esperado="IMSS: POSITIVA",
                evidencia="Opinión de cumplimiento patronal IMSS negativa.",
            )
        if opinion_infonavit != "POSITIVA":
            return ResultadoValidacion(
                self.id_regla, self.seccion, "FALLA",
                valor_detectado=f"INFONAVIT: {opinion_infonavit}", valor_esperado="INFONAVIT: POSITIVA",
                evidencia="Opinión de cumplimiento INFONAVIT negativa.",
            )
        return ResultadoValidacion(
            self.id_regla, self.seccion, "PASA",
            "IMSS/INFONAVIT POSITIVA", "IMSS/INFONAVIT POSITIVA",
            "Cumple obligaciones de seguridad social.",
        )


class ValidadorFirmaElectronica(ValidadorBase):
    """Firma electrónica avanzada (e.firma) en los anexos."""
    id_regla = "REG-ADM-EFIRMA"
    seccion = "Administrativa"
    es_critica = True

    def evaluar(self, datos):
        if not datos.get("administrativo", {}).get("efirma_valida", False):
            return ResultadoValidacion(
                self.id_regla, self.seccion, "FALLA",
                valor_detectado="Ausente/Inválida", valor_esperado="Válida",
                evidencia="Anexos carecen de firma electrónica avanzada (e.firma) íntegra.",
            )
        return ResultadoValidacion(
            self.id_regla, self.seccion, "PASA",
            "Válida", "Válida", "Documentación correctamente firmada.",
        )


class ValidadorFactorSalarioReal(ValidadorBase):
    """FSR = PS × (TP/TL) + (TP/TL) -- valida la aritmética declarada."""
    id_regla = "REG-ECO-FSR"
    seccion = "Económica"
    es_critica = True

    def evaluar(self, datos):
        fsr = datos.get("economico", {}).get("analisis_fsr", {})
        tp = float(fsr.get("tp_dias_pagados", 0))
        tl = float(fsr.get("tl_dias_laborados", 0))
        ps = float(fsr.get("ps_fraccion_imss_infonavit", 0))
        fsr_decl = float(fsr.get("fsr_calculado_por_licitante", 0))

        if tp < CONSTANTES.DIAS_PAGADOS_MINIMO:
            return ResultadoValidacion(
                "REG-ECO-FSR-TP", self.seccion, "FALLA",
                valor_detectado=f"{tp} días", valor_esperado=f">= {CONSTANTES.DIAS_PAGADOS_MINIMO} días",
                evidencia="Días pagados por debajo del mínimo legal.",
            )
        if tl > CONSTANTES.DIAS_LABORADOS_MAXIMO:
            return ResultadoValidacion(
                "REG-ECO-FSR-TL", self.seccion, "FALLA",
                valor_detectado=f"{tl} días", valor_esperado=f"<= {CONSTANTES.DIAS_LABORADOS_MAXIMO} días",
                evidencia="Días laborados exceden límite legal.",
            )
        if tl <= 0:
            return ResultadoValidacion(
                self.id_regla, self.seccion, "FALLA",
                valor_detectado="Tl = 0", valor_esperado="Tl > 0",
                evidencia="División entre cero.",
            )
        fsr_calc = round(ps * (tp / tl) + (tp / tl), 4)
        if abs(fsr_decl - fsr_calc) > CONSTANTES.TOLERANCIA_FSR_ARITMETICO:
            return ResultadoValidacion(
                self.id_regla, self.seccion, "FALLA",
                valor_detectado=f"FSR declarado: {fsr_decl}", valor_esperado=f"FSR calculado: {fsr_calc}",
                evidencia="Discrepancia aritmética en FSR excede tolerancia.",
            )
        return ResultadoValidacion(
            self.id_regla, self.seccion, "PASA",
            f"FSR: {fsr_decl}", f"FSR: {fsr_calc}",
            "Factor de Salario Real validado aritméticamente.",
        )


class ValidadorCostosHorariosMaquinaria(ValidadorBase):
    """Costo horario de maquinaria: combustible, operación e integración."""
    id_regla = "REG-ECO-MAQUINARIA"
    seccion = "Económica"
    es_critica = True

    def __init__(self, precio_diesel_zona_sin_iva: float = CONSTANTES.PRECIO_DIESEL_REFERENCIA):
        self.diesel_ref = precio_diesel_zona_sin_iva

    def evaluar(self, datos):
        maq = datos.get("economico", {}).get("analisis_maquinaria", {})
        codigo = str(maq.get("codigo_equipo", "N/A"))
        combustible = float(maq.get("cargo_combustible", 0))
        precio_comb = float(maq.get("precio_litro_combustible_declarado", 0))
        operacion = float(maq.get("cargo_operacion", 0))
        total = float(maq.get("costo_horario_total", 0))
        fijos = float(maq.get("total_cargos_fijos", 0))
        lubricantes = float(maq.get("cargo_lubricantes", 0))
        horas_anual = float(maq.get("horas_uso_anual", 0))

        if horas_anual < CONSTANTES.HORAS_USO_ANUAL_MIN or horas_anual > CONSTANTES.HORAS_USO_ANUAL_MAX:
            return ResultadoValidacion(
                self.id_regla, self.seccion, "FALLA",
                valor_detectado=f"{horas_anual} hrs/año",
                valor_esperado=f"{CONSTANTES.HORAS_USO_ANUAL_MIN}-{CONSTANTES.HORAS_USO_ANUAL_MAX} hrs/año",
                evidencia=f"Equipo {codigo}: Horas de uso anual fuera de parámetros técnicos.",
            )
        if combustible <= 0 and maq.get("requiere_combustible", True):
            return ResultadoValidacion(
                "REG-ECO-MAQ-GAS", self.seccion, "FALLA",
                valor_detectado=f"${combustible}", valor_esperado="> $0.00",
                evidencia=f"Equipo {codigo}: Cargo por combustible en cero.",
            )
        if abs(precio_comb - self.diesel_ref) > CONSTANTES.TOLERANCIA_PRECIO_COMBUSTIBLE:
            return ResultadoValidacion(
                "REG-ECO-MAQ-GAS", self.seccion, "FALLA",
                valor_detectado=f"${precio_comb}/litro",
                valor_esperado=f"${self.diesel_ref} +/- ${CONSTANTES.TOLERANCIA_PRECIO_COMBUSTIBLE}",
                evidencia=f"Equipo {codigo}: Precio combustible fuera de rango.",
            )
        if operacion <= 0:
            return ResultadoValidacion(
                "REG-ECO-MAQ-OPE", self.seccion, "FALLA",
                valor_detectado=f"${operacion}", valor_esperado="> $0.00",
                evidencia=f"Equipo {codigo}: Omisión del cargo por operador.",
            )
        suma = fijos + combustible + lubricantes + operacion
        if abs(total - suma) > CONSTANTES.TOLERANCIA_COSTO_HORARIO:
            return ResultadoValidacion(
                self.id_regla, self.seccion, "FALLA",
                valor_detectado=f"${total}", valor_esperado=f"${round(suma, 2)}",
                evidencia=f"Equipo {codigo}: Error de integración aritmética.",
            )
        return ResultadoValidacion(
            self.id_regla, self.seccion, "PASA",
            f"${total}", f"${total}", f"Equipo {codigo} solvente.",
        )


class ValidadorSobrecostos(ValidadorBase):
    """Cascada de indirectos -> financiamiento -> utilidad -> factor total."""
    id_regla = "REG-ECO-SOBRECOSTOS"
    seccion = "Económica - Sobrecostos"
    es_critica = True

    def __init__(self, tasa_tie_referencia: float = CONSTANTES.TASA_TIE_REFERENCIA):
        self.tie_ref = tasa_tie_referencia

    def evaluar(self, datos):
        sc = datos.get("economico", {}).get("analisis_sobrecostos", {})
        ind_oficina = float(sc.get("pct_indirecto_oficina", 0))
        ind_campo = float(sc.get("pct_indirecto_campo", 0))
        utilidad = float(sc.get("pct_utilidad", 0))
        financiamiento = float(sc.get("pct_financiamiento", 0))
        adicionales = float(sc.get("pct_cargos_adicionales", 0))
        factor_decl = float(sc.get("factor_sobrecosto_total_declarado", 1.0))
        tasa_interes = float(sc.get("tasa_interes_utilizada", 0))

        if ind_oficina <= 0 or ind_campo <= 0:
            return ResultadoValidacion(
                "REG-ECO-IND-DESGLOSE", self.seccion, "FALLA",
                valor_detectado=f"Oficina: {ind_oficina*100}%, Campo: {ind_campo*100}%",
                valor_esperado="Ambos > 0%",
                evidencia="No se desglosaron indirectos.",
            )
        if utilidad <= 0:
            return ResultadoValidacion(
                "REG-ECO-UTILIDAD-NETA", self.seccion, "FALLA",
                valor_detectado=f"{utilidad*100}%", valor_esperado="> 0%",
                evidencia="Utilidad <= 0%: propuesta insolvente.",
            )
        if tasa_interes <= 0:
            return ResultadoValidacion(
                self.id_regla, self.seccion, "FALLA",
                valor_detectado=f"{tasa_interes*100}%", valor_esperado="> 0%",
                evidencia="Tasa de interés omitida.",
            )
        if abs(tasa_interes - self.tie_ref) > 0.05:
            return ResultadoValidacion(
                self.id_regla, self.seccion, "FALLA",
                valor_detectado=f"Tasa: {tasa_interes*100}%",
                valor_esperado=f"TIE Ref: {self.tie_ref*100}% (±5%)",
                evidencia="Tasa de interés fuera de condiciones reales del mercado.",
            )

        f_ind = 1 + (ind_oficina + ind_campo)
        f_fin = f_ind * (1 + financiamiento)
        f_ut = f_fin * (1 + utilidad)
        factor_calc = round(f_ut + adicionales, 4)

        if abs(factor_decl - factor_calc) > CONSTANTES.TOLERANCIA_FACTOR_SOBRECOSTO:
            return ResultadoValidacion(
                "REG-ECO-SOBRECOSTO-CASCADA", self.seccion, "FALLA",
                valor_detectado=f"Factor: {factor_decl}", valor_esperado=f"Factor: {factor_calc}",
                evidencia="Error en cascada indirectos->financiamiento->utilidad.",
            )
        return ResultadoValidacion(
            self.id_regla, self.seccion, "PASA",
            f"Factor: {factor_decl}", f"Factor: {factor_calc}",
            "Sobrecostos validados en cascada.",
        )


class ValidadorCongruenciaTemporal(ValidadorBase):
    """Congruencia entre el programa de obra y el resto de la propuesta."""
    id_regla = "REG-TEC-CONGRUENCIA-TEMP"
    seccion = "Técnica"
    es_critica = True

    def evaluar(self, datos):
        tecnico = datos.get("tecnico", {})
        incongruencias = tecnico.get("incongruencias_detectadas", [])
        if incongruencias:
            return ResultadoValidacion(
                self.id_regla, self.seccion, "FALLA",
                valor_detectado=f"{len(incongruencias)} incongruencias",
                valor_esperado="0 incongruencias",
                evidencia=f"Incongruencia temporal: {incongruencias[0]}",
            )
        return ResultadoValidacion(
            self.id_regla, self.seccion, "PASA",
            "0 incongruencias", "0 incongruencias",
            "Programas de obra congruentes.",
        )


class ValidadorGarantiaCumplimiento(ValidadorBase):
    """Garantía de cumplimiento (Art. 48 LOPSRM)."""
    id_regla = "REG-LOP-002"
    seccion = "Legal"
    es_critica = True

    def evaluar(self, datos):
        garantias = datos.get("garantias", [])
        cumple = any(g.get("tipo") == "cumplimiento" for g in garantias)
        return ResultadoValidacion(
            self.id_regla, self.seccion,
            "PASA" if cumple else "FALLA",
            valor_detectado=str([g.get("tipo") for g in garantias]),
            valor_esperado="Debe existir garantía de cumplimiento",
            evidencia="Art. 48 LOPSRM",
        )


class ValidadorPublicacionSIRECO(ValidadorBase):
    """Publicación del fallo (Art. 36 LOPSRM)."""
    id_regla = "REG-LOP-005"
    seccion = "Legal"
    es_critica = True

    def evaluar(self, datos):
        fecha_fallo = datos.get("fecha_fallo")
        if not fecha_fallo:
            return ResultadoValidacion(
                self.id_regla, self.seccion, "FALLA",
                "Sin fecha de fallo", "Fecha de fallo requerida", "Art. 36 LOPSRM",
            )
        return ResultadoValidacion(
            self.id_regla, self.seccion, "PASA",
            "Publicado", "Publicado", "Cumple con publicación",
        )


class ValidadorRequisitosParticipacion(ValidadorBase):
    """Requisitos de participación (Art. 29 LAASSP)."""
    id_regla = "REG-LAA-001"
    seccion = "Legal"
    es_critica = True

    def evaluar(self, datos):
        requisitos = datos.get("requisitos_participacion", [])
        cumple = len(requisitos) > 0
        return ResultadoValidacion(
            self.id_regla, self.seccion,
            "PASA" if cumple else "FALLA",
            f"{len(requisitos)} requisitos",
            "Al menos un requisito",
            "Art. 29 LAASSP",
        )


def validadores_default() -> List[ValidadorBase]:
    """Los 10 validadores reales, en el mismo orden que el original."""
    return [
        ValidadorSAT32D(),
        ValidadorSeguridadSocial(),
        ValidadorFirmaElectronica(),
        ValidadorFactorSalarioReal(),
        ValidadorCostosHorariosMaquinaria(),
        ValidadorSobrecostos(),
        ValidadorCongruenciaTemporal(),
        ValidadorGarantiaCumplimiento(),
        ValidadorPublicacionSIRECO(),
        ValidadorRequisitosParticipacion(),
    ]


class MotorDeterministaLicitaciones:
    """Orquesta los validadores contra una propuesta y produce un reporte.

    Regla preservada del original: al primer FALLA de un validador
    crítico, se detiene la evaluación y la propuesta queda DESCALIFICADA
    -- no sigue evaluando el resto (así lo hacía megalodon_costos_v3_1.py).
    """

    def __init__(self, validadores: Optional[List[ValidadorBase]] = None):
        self.validadores: List[ValidadorBase] = validadores or validadores_default()

    def registrar_regla(self, validador: ValidadorBase) -> None:
        self.validadores.append(validador)

    def procesar_propuesta(self, datos_propuesta: Dict[str, Any]) -> Dict[str, Any]:
        reporte: Dict[str, Any] = {
            "rfc_empresa": datos_propuesta.get("rfc_empresa"),
            "estado": "SOLVENTE",
            "bitacora_evaluacion": [],
            "timestamp_evaluacion": _now_utc().isoformat(),
        }
        for validador in self.validadores:
            resultado = validador.evaluar(datos_propuesta)
            reporte["bitacora_evaluacion"].append(resultado.to_dict())
            if resultado.estatus == "FALLA" and validador.es_critica:
                reporte["estado"] = "DESCALIFICADO"
                break
        return reporte

    @staticmethod
    def resumen_por_seccion(reporte: Dict[str, Any]) -> Dict[str, int]:
        conteo: Dict[str, int] = {}
        for b in reporte.get("bitacora_evaluacion", []):
            clave = f"{b.get('seccion', 'Desconocida')}|{b.get('estatus', 'DESCONOCIDO')}"
            conteo[clave] = conteo.get(clave, 0) + 1
        return conteo


# ─── Compatibilidad retro: validaciones rápidas por RFC ────────────────
# Las validaciones "sueltas" que ya usaba el frontend (validar_sat,
# validar_imss, etc. solo con RFC) se mantienen, pero ahora son
# explícitamente lo que son: verificación de FORMATO de RFC, no una
# consulta real al SAT/IMSS/INFONAVIT. Eso solo se puede hacer con datos
# reales de opinión de cumplimiento -- ver ValidadorSAT32D /
# ValidadorSeguridadSocial arriba, que sí validan el dato real cuando se
# manda el payload completo vía /validadores/evaluar-completo.
@dataclass
class ResultadoValidacionRFC:
    entidad: str
    valido: bool
    estado: str
    mensaje: str
    detalles: Dict[str, Any] = field(default_factory=dict)
    fecha_validacion: datetime = field(default_factory=_now_utc)


class MotorValidador:
    """Validaciones rápidas de formato de RFC (compatibilidad retro).

    Para la validación real y completa de una propuesta, usar
    MotorDeterministaLicitaciones.procesar_propuesta() con el payload
    completo (fiscal, administrativo, económico, técnico, garantías).
    """

    def validar_sat(self, rfc: str) -> ResultadoValidacionRFC:
        valido = len(rfc) in (12, 13)
        return ResultadoValidacionRFC(
            entidad="SAT", valido=valido,
            estado="FORMATO_VALIDO" if valido else "FORMATO_INVALIDO",
            mensaje="RFC con formato válido (esto NO es una consulta real al SAT)" if valido else "RFC con formato inválido",
            detalles={"rfc": rfc, "longitud": len(rfc)},
        )

    def validar_imss(self, rfc: str) -> ResultadoValidacionRFC:
        valido = len(rfc) in (12, 13)
        return ResultadoValidacionRFC(
            entidad="IMSS", valido=valido,
            estado="FORMATO_VALIDO" if valido else "FORMATO_INVALIDO",
            mensaje="RFC con formato válido (esto NO es una consulta real al IMSS)" if valido else "RFC con formato inválido",
            detalles={"rfc": rfc},
        )

    def validar_infonavit(self, rfc: str) -> ResultadoValidacionRFC:
        valido = len(rfc) in (12, 13)
        return ResultadoValidacionRFC(
            entidad="INFONAVIT", valido=valido,
            estado="FORMATO_VALIDO" if valido else "FORMATO_INVALIDO",
            mensaje="RFC con formato válido (esto NO es una consulta real a INFONAVIT)" if valido else "RFC con formato inválido",
            detalles={"rfc": rfc},
        )

    def validar_fsr(self, fsr: float) -> ResultadoValidacionRFC:
        valido = fsr >= 1.0
        return ResultadoValidacionRFC(
            entidad="FSR", valido=valido,
            estado="RANGO_VALIDO" if valido else "RANGO_INVALIDO",
            mensaje=f"FSR {fsr:.4f} {'en rango esperado' if valido else 'fuera de rango (debe ser >= 1.0)'} (esto NO valida la aritmética contra TP/TL/PS)",
            detalles={"fsr": fsr, "minimo": 1.0},
        )

    def validar_completo(self, rfc: str, fsr: Optional[float] = None) -> List[ResultadoValidacionRFC]:
        resultados = [self.validar_sat(rfc), self.validar_imss(rfc), self.validar_infonavit(rfc)]
        if fsr is not None:
            resultados.append(self.validar_fsr(fsr))
        return resultados
