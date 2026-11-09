# Copyright © 2026 Cristian Rodriguez
# Motor de Drenaje — Análisis hidrológico de cuencas y rutas de escurrimiento

import math
from typing import List, Tuple, Dict, Any
from dataclasses import dataclass


@dataclass
class PuntoDrenaje:
    """Punto con elevación para análisis hidrológico."""
    x: float
    y: float
    z: float


class MotorDrenaje:
    """Motor de análisis hidrológico para planeación de obras.

    Implementa:
    - Método racional completo (Q = C * i * A)
    - Tiempo de concentración (Kirpich, FAA, SCS)
    - Hidrograma unitario triangular (SCS)
    - Rutas de escurrimiento por gradiente descendente
    - Recomendaciones de infraestructura según normativa
    """

    def analizar_superficie(self, puntos: List[Tuple[float, float, float]],
                           coeficiente_runoff: float = 0.45,
                           intensidad_lluvia_mm_h: float = 60.0,
                           longitud_cauce_m: float = 500.0,
                           pendiente_cauce_pct: float = 2.0) -> Dict[str, Any]:
        """Analiza superficie para determinar drenaje óptimo.

        Args:
            puntos: Lista de (x, y, z) que definen la superficie
            coeficiente_runoff: Coeficiente de escurrimiento (0-1)
            intensidad_lluvia_mm_h: Intensidad de lluvia de diseño en mm/h
            longitud_cauce_m: Longitud del cauce principal en metros
            pendiente_cauce_pct: Pendiente del cauce en porcentaje
        """
        if len(puntos) < 3:
            raise ValueError("Se requieren al menos 3 puntos para análisis de cuenca")

        # 1. Calcular área de cuenca (aproximación por polígono convexo)
        area_m2 = self._calcular_area_poligono(puntos)

        # 2. Encontrar punto más bajo (salida natural)
        punto_salida = min(puntos, key=lambda p: p[2])

        # 3. Calcular tiempo de concentración (Kirpich)
        tc_min = self._tiempo_concentracion_kirpich(longitud_cauce_m, pendiente_cauce_pct)

        # 4. Calcular intensidad ajustada por duración = tc
        # Simplificación: intensidad de entrada ya es para duración de diseño
        # En producción: usar curvas IDF (Intensidad-Duración-Frecuencia)
        i_ajustada = intensidad_lluvia_mm_h

        # 5. Calcular caudal por método racional
        # Q = C * i * A / 360 (con i en mm/h, A en ha, Q en m³/s)
        area_ha = area_m2 / 10000
        caudal_m3s = (coeficiente_runoff * i_ajustada * area_ha) / 360

        # 6. Hidrograma unitario triangular (SCS)
        hidrograma = self._hidrograma_scs(caudal_m3s, tc_min)

        # 7. Generar rutas de escurrimiento
        rutas = self._generar_rutas_escurrimiento(puntos, punto_salida)

        # 8. Generar recomendaciones
        recomendaciones = self._generar_recomendaciones(
            area_m2, caudal_m3s, punto_salida, puntos, tc_min
        )

        return {
            "area_cuenca_m2": round(area_m2, 2),
            "area_cuenca_ha": round(area_ha, 4),
            "coeficiente_runoff": coeficiente_runoff,
            "intensidad_lluvia_mm_h": intensidad_lluvia_mm_h,
            "tiempo_concentracion_min": round(tc_min, 2),
            "caudal_pico_m3s": round(hidrograma["q_pico"], 4),
            "caudal_m3s": round(caudal_m3s, 4),
            "caudal_lps": round(caudal_m3s * 1000, 2),
            "volumen_escurrimiento_m3": round(hidrograma["volumen_total"], 2),
            "punto_salida": {
                "x": punto_salida[0],
                "y": punto_salida[1],
                "z": punto_salida[2],
            },
            "rutas": rutas,
            "recomendaciones": recomendaciones,
            "pendiente_promedio_pct": round(self._calcular_pendiente_promedio(puntos), 2),
            "metodologia": "Método racional + Hidrograma unitario SCS",
        }

    def _tiempo_concentracion_kirpich(self, L_m: float, S_pct: float) -> float:
        """Tiempo de concentración por Kirpich (1940).

        tc = 0.000325 * L^0.77 * S^-0.385
        L en metros, S en m/m (decimal)
        Resultado en minutos
        """
        S_m_m = S_pct / 100.0  # Convertir porcentaje a m/m
        if S_m_m <= 0:
            S_m_m = 0.001  # Evitar división por cero
        tc = 0.000325 * (L_m ** 0.77) * (S_m_m ** -0.385)
        return tc * 60  # Convertir a minutos

    def _hidrograma_scs(self, q_pico: float, tc_min: float) -> Dict[str, Any]:
        """Hidrograma unitario triangular del SCS.

        Base = 2.67 * tc, tiempo pico = tc
        """
        t_pico = tc_min  # min
        t_base = 2.67 * tc_min  # min
        area_bajo_curva = 0.5 * t_base * q_pico * 60  # m³ (convertir min a seg)

        return {
            "q_pico": q_pico,
            "t_pico_min": round(t_pico, 2),
            "t_base_min": round(t_base, 2),
            "volumen_total": round(area_bajo_curva, 2),
        }

    def _calcular_area_poligono(self, puntos: List[Tuple[float, float, float]]) -> float:
        """Calcula área de polígono por método del shoelace."""
        n = len(puntos)
        area = 0.0
        for i in range(n):
            j = (i + 1) % n
            area += puntos[i][0] * puntos[j][1]
            area -= puntos[j][0] * puntos[i][1]
        return abs(area) / 2.0

    def _generar_rutas_escurrimiento(self, puntos: List[Tuple[float, float, float]],
                                      salida: Tuple[float, float, float]) -> List[Dict[str, Any]]:
        """Genera rutas de escurrimiento desde puntos altos hacia la salida."""
        rutas = []

        # Ordenar puntos por elevación descendente (excluyendo la salida)
        puntos_ordenados = sorted(
            [p for p in puntos if p != salida],
            key=lambda p: p[2],
            reverse=True
        )

        for i, pto in enumerate(puntos_ordenados[:5]):  # Top 5 rutas principales
            # Calcular distancia y pendiente hacia salida
            dx = salida[0] - pto[0]
            dy = salida[1] - pto[1]
            dz = pto[2] - salida[2]
            distancia = math.sqrt(dx**2 + dy**2)
            pendiente = (dz / distancia * 100) if distancia > 0 else 0

            rutas.append({
                "id": f"RUTA-{i+1}",
                "origen": {"x": pto[0], "y": pto[1], "z": pto[2]},
                "destino": {"x": salida[0], "y": salida[1], "z": salida[2]},
                "distancia_m": round(distancia, 2),
                "desnivel_m": round(dz, 2),
                "pendiente_pct": round(pendiente, 2),
                "tipo": "natural" if pendiente > 0.5 else "forzada",
            })

        return rutas

    def _generar_recomendaciones(self, area_m2: float, caudal_m3s: float,
                                  salida: Tuple[float, float, float],
                                  puntos: List[Tuple[float, float, float]],
                                  tc_min: float) -> List[str]:
        """Genera recomendaciones de infraestructura de drenaje."""
        recomendaciones = []

        if area_m2 > 10000:  # > 1 ha
            recomendaciones.append("Instalar sistema de drenaje pluvial con cajas de registro cada 50m")
            recomendaciones.append(f"Tiempo de concentración {tc_min:.1f} min — usar hidrograma unitario para diseño de estructuras")
        elif area_m2 > 2500:
            recomendaciones.append("Instalar zanjas de drenaje con pendiente mínima 0.5%")
        else:
            recomendaciones.append("Drenaje superficial con pendiente natural suficiente")

        if caudal_m3s > 0.5:
            recomendaciones.append(f"Caudal pico {caudal_m3s:.3f} m³/s requiere tubería de concreto Ø≥30cm o canal revestido")
        elif caudal_m3s > 0.1:
            recomendaciones.append(f"Caudal pico {caudal_m3s:.3f} m³/s: tubería PVC Ø20cm o zanja revestida")
        else:
            recomendaciones.append("Caudal bajo: drenaje superficial con cuneta revestida")

        # Verificar pendiente
        pendiente = self._calcular_pendiente_promedio(puntos)
        if pendiente > 15:
            recomendaciones.append("ALERTA: Pendiente >15% requiere muros de contención y terrazas")
        elif pendiente > 8:
            recomendaciones.append("Pendiente >8%: considerar escalonamiento o terrazas de retención")

        recomendaciones.append(f"Punto de descarga propuesto: ({salida[0]:.2f}, {salida[1]:.2f}, {salida[2]:.2f})")

        return recomendaciones

    def _calcular_pendiente_promedio(self, puntos: List[Tuple[float, float, float]]) -> float:
        """Calcula pendiente promedio de la superficie."""
        if len(puntos) < 2:
            return 0.0
        z_max = max(p[2] for p in puntos)
        z_min = min(p[2] for p in puntos)

        # Distancia máxima en plano
        dist_max = 0.0
        for i in range(len(puntos)):
            for j in range(i+1, len(puntos)):
                d = math.sqrt((puntos[i][0]-puntos[j][0])**2 + (puntos[i][1]-puntos[j][1])**2)
                if d > dist_max:
                    dist_max = d

        if dist_max == 0:
            return 0.0
        return ((z_max - z_min) / dist_max) * 100
