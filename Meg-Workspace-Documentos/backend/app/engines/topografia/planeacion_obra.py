# Copyright © 2026 Cristian Rodriguez
# Motor de Planeación de Obra Avanzada — Integra volumen, drenaje y terrazas

import math
from typing import List, Tuple, Dict, Any
from dataclasses import dataclass

from app.engines.topografia.volumenes import MotorVolumenes
from app.engines.topografia.drenaje import MotorDrenaje


@dataclass
class Terraza:
    """Terraza calculada para planeación."""
    id: str
    cota_base: float
    cota_cresta: float
    area_m2: float
    volumen_relleno_m3: float
    volumen_corte_m3: float
    pendiente_pct: float


class MotorPlaneacionObraAvanzada:
    """Motor de planeación integrada de obra.

    Combina:
    - Cálculo de volúmenes de movimiento de tierras
    - Análisis hidrológico de drenaje
    - Diseño de terrazas para estabilidad
    - Recomendación de taludes

    Produce un plan completo de preparación del terreno.
    """

    def __init__(self):
        self.motor_volumenes = MotorVolumenes()
        self.motor_drenaje = MotorDrenaje()

    def generar_plan(self, puntos: List[Tuple[float, float, float]],
                     cota_objetivo: float,
                     salto_terrazas: float = 0.5,
                     tarifas: Dict[str, float] | None = None) -> Dict[str, Any]:
        """Genera plan de preparación del terreno.

        Args:
            puntos: Nube de puntos (x, y, z) del terreno existente
            cota_objetivo: Cota de plataforma deseada
            salto_terrazas: Diferencia de cota entre terrazas consecutivas
        """
        if len(puntos) < 3:
            raise ValueError("Se requieren al menos 3 puntos")

        # 1. Calcular volúmenes contra cota objetivo
        volumen = self._calcular_volumen(puntos, cota_objetivo)

        # 2. Diseñar terrazas
        terrazas = self._disenar_terrazas(puntos, cota_objetivo, salto_terrazas)

        # 3. Análisis de drenaje
        drenaje = self.motor_drenaje.analizar_superficie(puntos)

        # 4. Recomendar talud
        talud = self._recomendar_talud(puntos, terrazas)

        # 5. Calcular área total
        area_m2 = self._calcular_area(puntos)

        return {
            "volumen": {
                "area_analizada_m2": round(area_m2, 2),
                "corte_m3": round(volumen["corte"], 2),
                "relleno_m3": round(volumen["relleno"], 2),
                "neto_m3": round(volumen["neto"], 2),
                "factor_balance": round(volumen["relleno"] / volumen["corte"], 2) if volumen["corte"] > 0 else 0,
            },
            "terrazas": [self._terraza_to_dict(t) for t in terrazas],
            "drenaje": {
                "caudal_m3s": drenaje["caudal_m3s"],
                "area_cuenca_ha": drenaje["area_cuenca_ha"],
                "rutas_principales": len(drenaje["rutas"]),
                "recomendaciones": drenaje["recomendaciones"],
            },
            "talud_recomendado": talud,
            "cota_objetivo": cota_objetivo,
            "salto_terrazas": salto_terrazas,
            "estimacion_costo_m2": self._estimar_costo(volumen, terrazas, drenaje, tarifas or {}),
        }

    def _calcular_volumen(self, puntos: List[Tuple[float, float, float]],
                          cota_objetivo: float) -> Dict[str, float]:
        """Calcula volúmenes de corte y relleno contra cota objetivo."""
        corte = 0.0
        relleno = 0.0

        # Área aproximada por polígono
        area = self._calcular_area(puntos)

        # Para cada punto, calcular diferencia vs cota objetivo
        # Simplificación: usamos el promedio de diferencias * área
        diffs = [p[2] - cota_objetivo for p in puntos]

        for d in diffs:
            if d > 0:
                # Punto está arriba de la cota → hay que cortar
                corte += d * (area / len(puntos))
            elif d < 0:
                # Punto está abajo → hay que rellenar
                relleno += abs(d) * (area / len(puntos))

        return {
            "corte": corte,
            "relleno": relleno,
            "neto": corte - relleno,
        }

    def _disenar_terrazas(self, puntos: List[Tuple[float, float, float]],
                          cota_objetivo: float,
                          salto: float) -> List[Terraza]:
        """Diseña terrazas escalonadas según topografía."""
        z_min = min(p[2] for p in puntos)
        z_max = max(p[2] for p in puntos)

        terrazas = []

        # Si el rango es pequeño, una sola terraza
        if z_max - z_min < salto * 2:
            area = self._calcular_area(puntos)
            vol = self._calcular_volumen(puntos, cota_objetivo)
            terrazas.append(Terraza(
                id="TZ-01",
                cota_base=min(z_min, cota_objetivo),
                cota_cresta=max(z_max, cota_objetivo),
                area_m2=area,
                volumen_relleno_m3=vol["relleno"],
                volumen_corte_m3=vol["corte"],
                pendiente_pct=self._calcular_pendiente_promedio(puntos),
            ))
            return terrazas

        # Múltiples terrazas
        n_terrazas = max(1, int((z_max - z_min) / salto))
        for i in range(n_terrazas):
            cota_base = z_min + i * salto
            cota_cresta = min(cota_base + salto, z_max)

            # Puntos que caen en esta franja
            puntos_terraza = [p for p in puntos if cota_base <= p[2] < cota_cresta]
            if not puntos_terraza:
                continue

            area = self._calcular_area(puntos_terraza)
            vol = self._calcular_volumen(puntos_terraza, (cota_base + cota_cresta) / 2)

            terrazas.append(Terraza(
                id=f"TZ-{i+1:02d}",
                cota_base=cota_base,
                cota_cresta=cota_cresta,
                area_m2=area,
                volumen_relleno_m3=vol["relleno"],
                volumen_corte_m3=vol["corte"],
                pendiente_pct=self._calcular_pendiente_promedio(puntos_terraza),
            ))

        return terrazas

    def _recomendar_talud(self, puntos: List[Tuple[float, float, float]],
                          terrazas: List[Terraza]) -> float:
        """Recomienda talud según pendiente y altura de terrazas."""
        pendiente = self._calcular_pendiente_promedio(puntos)

        if pendiente > 20:
            return 2.0  # Talud 2:1 para pendientes muy pronunciadas
        elif pendiente > 10:
            return 1.5  # Talud 1.5:1
        elif pendiente > 5:
            return 1.0  # Talud 1:1
        else:
            return 1.0  # Talud mínimo 1:1 para estabilidad en obra civil

    def _calcular_area(self, puntos: List[Tuple[float, float, float]]) -> float:
        """Área por método del shoelace."""
        n = len(puntos)
        area = 0.0
        for i in range(n):
            j = (i + 1) % n
            area += puntos[i][0] * puntos[j][1]
            area -= puntos[j][0] * puntos[i][1]
        return abs(area) / 2.0

    def _calcular_pendiente_promedio(self, puntos: List[Tuple[float, float, float]]) -> float:
        """Pendiente promedio en porcentaje."""
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

    def _terraza_to_dict(self, t: Terraza) -> Dict[str, Any]:
        return {
            "id": t.id,
            "cota_base": t.cota_base,
            "cota_cresta": t.cota_cresta,
            "area_m2": round(t.area_m2, 2),
            "volumen_relleno_m3": round(t.volumen_relleno_m3, 2),
            "volumen_corte_m3": round(t.volumen_corte_m3, 2),
            "pendiente_pct": round(t.pendiente_pct, 2),
        }

    def _estimar_costo(self, volumen: Dict[str, float], terrazas: List[Terraza],
                       drenaje: Dict[str, Any], tarifas: Dict[str, float]) -> float:
        """Calcula el costo unitario a partir de tarifas APU vigentes.

        No contiene tarifas embebidas: el servicio debe resolverlas desde el
        catálogo tenant-aware antes de llegar al motor.
        """
        required = {"corte_m3", "relleno_m3", "drenaje_m2"}
        missing = sorted(required - set(tarifas))
        if missing:
            raise ValueError(f"Faltan tarifas de catálogo para planeación: {missing}")

        costo_corte_m3 = float(tarifas["corte_m3"])
        costo_relleno_m3 = float(tarifas["relleno_m3"])
        costo_drenaje_m2 = float(tarifas["drenaje_m2"])
        if any(v < 0 for v in (costo_corte_m3, costo_relleno_m3, costo_drenaje_m2)):
            raise ValueError("Las tarifas de catálogo no pueden ser negativas")

        total_corte = volumen["corte"] * costo_corte_m3
        total_relleno = volumen["relleno"] * costo_relleno_m3
        total_drenaje = drenaje["area_cuenca_ha"] * 10000 * costo_drenaje_m2

        area_total = sum(t.area_m2 for t in terrazas) if terrazas else 1
        costo_total = total_corte + total_relleno + total_drenaje

        return round(costo_total / area_total, 2) if area_total > 0 else 0
