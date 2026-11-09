
# Copyright © 2026 Cristian Rodriguez
# All rights reserved.
# Unauthorized copying, modification, distribution, or use is prohibited
# without prior written permission.

"""Heurísticas puras para BIM 4D/5D.

El objetivo de este módulo es aislar lógica determinista y testeable
que no depende de la base de datos ni de terceros. Así el motor de
programación BIM puede estimar duraciones por grupo de trabajo de una
forma reproducible y sin acoplarse a un ORM concreto.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Iterable, Protocol


class ElementoBIMLike(Protocol):
    area: float | None
    volumen: float | None
    longitud: float | None


@dataclass(frozen=True)
class ResumenGrupoBIM4D:
    cantidad_elementos: int
    peso_geometrico_total: float
    peso_geometrico_promedio: float


def peso_geometrico_elemento(elemento: ElementoBIMLike) -> float:
    """Retorna una magnitud positiva para ponderar un elemento BIM.

    Se prioriza la cantidad geométrica disponible en el siguiente
    orden: área, volumen y longitud. Si no hay ninguna, se usa 1.0
    para no dejar al elemento fuera del cálculo 4D.
    """
    for attr in ("area", "volumen", "longitud"):
        value = getattr(elemento, attr, None)
        if value not in (None, 0, 0.0):
            try:
                return abs(float(value))
            except (TypeError, ValueError):
                continue
    return 1.0


def resumir_grupo_bim4d(elementos: Iterable[ElementoBIMLike]) -> ResumenGrupoBIM4D:
    elementos_list = list(elementos)
    cantidad = len(elementos_list)
    if cantidad == 0:
        return ResumenGrupoBIM4D(0, 0.0, 0.0)
    peso_total = sum(peso_geometrico_elemento(e) for e in elementos_list)
    return ResumenGrupoBIM4D(
        cantidad_elementos=cantidad,
        peso_geometrico_total=peso_total,
        peso_geometrico_promedio=peso_total / cantidad,
    )


def estimar_duracion_4d(
    *,
    elementos: Iterable[ElementoBIMLike],
    dias_base: float,
    promedio_cantidad_grupo: float,
    promedio_peso_grupo: float,
    factor_minimo: float = 0.5,
    factor_maximo: float = 3.0,
) -> float:
    """Estima una duración 4D con base en tamaño y peso geométrico.

    La salida no pretende reemplazar el criterio de programación de
    obra: solo evita que todas las actividades hereden exactamente la
    misma duración, y hace que el cronograma reaccione al volumen real
    del grupo de trabajo.
    """
    resumen = resumir_grupo_bim4d(elementos)
    if resumen.cantidad_elementos == 0:
        return round(max(dias_base, 0.1), 1)

    promedio_cantidad_grupo = max(float(promedio_cantidad_grupo or 0.0), 1.0)
    promedio_peso_grupo = max(float(promedio_peso_grupo or 0.0), 1.0)

    factor_cantidad = resumen.cantidad_elementos / promedio_cantidad_grupo
    factor_peso = resumen.peso_geometrico_promedio / promedio_peso_grupo
    factor_compuesto = (factor_cantidad * 0.6) + (factor_peso * 0.4)
    factor_compuesto = max(factor_minimo, min(factor_compuesto, factor_maximo))
    return round(max(dias_base, 0.1) * factor_compuesto, 1)
