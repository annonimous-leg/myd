# Copyright © 2026 Cristian Rodriguez
# All rights reserved.
# Unauthorized copying, modification, distribution, or use is prohibited
# without prior written permission.

"""
Calendario laboral mexicano según LFT Art. 74.
"""
from dataclasses import dataclass
from datetime import date, timedelta
from typing import List, Optional


@dataclass
class DiaFestivo:
    fecha: date
    nombre: str
    es_inamovible: bool = True


class CalendarioLaboral:
    """Gestión de días hábiles conforme a la LFT."""

    FESTIVOS_FIJOS = [
        (1, 1, "Año Nuevo"),
        (5, 1, "Día del Trabajo"),
        (9, 16, "Independencia de México"),
        (12, 25, "Navidad"),
    ]

    def __init__(self, year: Optional[int] = None):
        self.year = year or date.today().year
        self.festivos = self._generar_festivos()

    def _generar_festivos(self) -> List[DiaFestivo]:
        festivos = []
        for mes, dia, nombre in self.FESTIVOS_FIJOS:
            festivos.append(DiaFestivo(date(self.year, mes, dia), nombre))

        # Primer lunes de febrero (Constitución)
        festivos.append(DiaFestivo(self._primer_lunes(2), "Día de la Constitución"))

        # Tercer lunes de marzo (Benito Juárez)
        tercer_lunes_marzo = self._primer_lunes(3) + timedelta(days=14)
        festivos.append(DiaFestivo(tercer_lunes_marzo, "Natalicio de Benito Juárez"))

        # Tercer lunes de noviembre (Revolución)
        tercer_lunes_nov = self._primer_lunes(11) + timedelta(days=14)
        festivos.append(DiaFestivo(tercer_lunes_nov, "Revolución Mexicana"))

        return festivos

    def _primer_lunes(self, month: int) -> date:
        d = date(self.year, month, 1)
        while d.weekday() != 0:
            d += timedelta(days=1)
        return d

    def es_dia_habil(self, fecha: date) -> bool:
        if fecha.weekday() >= 5:  # Sábado o domingo
            return False
        return not any(f.fecha == fecha for f in self.festivos)

    def siguiente_dia_habil(self, fecha: date) -> date:
        d = fecha + timedelta(days=1)
        while not self.es_dia_habil(d):
            d += timedelta(days=1)
        return d

    def sumar_dias_habiles(self, fecha: date, dias: int) -> date:
        d = fecha
        for _ in range(dias):
            d = self.siguiente_dia_habil(d)
        return d

    def dias_habiles_entre(self, inicio: date, fin: date) -> int:
        count = 0
        d = inicio
        while d <= fin:
            if self.es_dia_habil(d):
                count += 1
            d += timedelta(days=1)
        return count

    def dia_habil_anterior(self, fecha: date) -> date:
        d = fecha - timedelta(days=1)
        while not self.es_dia_habil(d):
            d -= timedelta(days=1)
        return d

    def restar_dias_habiles(self, fecha: date, dias: int) -> date:
        d = fecha
        for _ in range(dias):
            d = self.dia_habil_anterior(d)
        return d
