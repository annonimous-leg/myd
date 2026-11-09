# Copyright © 2026 Cristian Rodriguez
# All rights reserved.
# Unauthorized copying, modification, distribution, or use is prohibited
# without prior written permission.

"""
Constantes legales y normativas de México 2026.
LOPSRM, LAASSP, LFT, CFF, RMF 2026.
"""
from dataclasses import dataclass


@dataclass(frozen=True)
class ConstantesLegales2026:
    """Constantes legales mexicanas para cálculos de obra pública."""

    # ─── LOPSRM / RLOPSRM ────────────────────────────────────
    # CORREGIDO (contra-auditoría V9): esta clase tenía UMBRAL_
    # ADJUDICACION_DIRECTA_OBRA/UMBRAL_INVITACION_TRES_OBRA/
    # UMBRAL_LICITACION_PUBLICA_OBRA/UMBRAL_ADJUDICACION_DIRECTA_
    # ADQUISICION/UMBRAL_INVITACION_TRES_ADQUISICION (montos fijos de un
    # solo nivel) más un método umbrales_por_tipo() que los devolvía.
    # Verificado con grep en todo el backend: NINGÚN motor los usa --
    # motor_juridico.py importa CONSTANTES pero nunca los referencia,
    # motor_costeo.py y motor_validador.py usan otras constantes de esta
    # misma clase (TOLERANCIA_FACTOR_SOBRECOSTO, DIAS_PAGADOS_MINIMO,
    # etc.) pero tampoco éstas. umbrales_por_tipo() no tiene ningún
    # llamador en todo el árbol. Es exactamente el mismo tipo de dato que
    # F-01 corrigió (un umbral de un solo nivel en vez de la tabla real
    # del Anexo 9 del PEF, ya resuelta en JuridicoService/MotorJuridico/
    # umbrales_referencia.py) -- pero código muerto, no alcanzable desde
    # ninguna ruta ejecutable. Se elimina en vez de dejarlo como una
    # segunda fuente normativa fantasma: su sola existencia, con nombres
    # oficiales y valores concretos, es una trampa para que un desarrollo
    # futuro la reintroduzca en un flujo real creyendo que es la fuente
    # correcta.

    # ─── LFT reformada ─────────────────────────────────────────
    DIAS_CALENDARIO: int = 365
    DIAS_AGUINALDO_MINIMO: int = 15
    DIAS_VACACIONES_MINIMO: int = 12
    PRIMA_VACACIONAL_PCT: float = 0.25
    DIAS_PAGADOS_MINIMO: float = 365 + 15 + (12 * 0.25)  # 383.0
    DOMINGOS_ANUAL: int = 52
    DIAS_FESTIVOS_OBLIGATORIOS: int = 7
    DIAS_LABORADOS_MAXIMO: int = 365 - 52 - 7  # 306

    # ─── SAT ─────────────────────────────────────────────────
    VIGENCIA_OPINION_SAT_DIAS: int = 30

    # ─── RLOPSRM Maquinaria ──────────────────────────────────
    HORAS_USO_ANUAL_MIN: int = 500
    HORAS_USO_ANUAL_MAX: int = 3000
    TOLERANCIA_PRECIO_COMBUSTIBLE: float = 1.50

    # ─── Sobrecostos ─────────────────────────────────────────
    TOLERANCIA_FACTOR_SOBRECOSTO: float = 0.0005
    TOLERANCIA_FSR_ARITMETICO: float = 0.001
    TOLERANCIA_COSTO_HORARIO: float = 0.05

    # ─── TIE / Financiamiento ────────────────────────────────
    TASA_TIE_REFERENCIA: float = 0.1125
    PRECIO_DIESEL_REFERENCIA: float = 24.50

    # ─── Factores default ────────────────────────────────────
    FACTOR_INDIRECTO_DEFAULT: float = 0.15
    FACTOR_UTILIDAD_DEFAULT: float = 0.10
    FACTOR_IMPUESTO_DEFAULT: float = 0.16
    FACTOR_RIESGO_DEFAULT: float = 0.02

    @property
    def DIAS_PAGADOS_CALCULADO(self) -> float:
        return self.DIAS_CALENDARIO + self.DIAS_AGUINALDO_MINIMO + (
            self.DIAS_VACACIONES_MINIMO * self.PRIMA_VACACIONAL_PCT
        )


# Singleton
CONSTANTES = ConstantesLegales2026()
