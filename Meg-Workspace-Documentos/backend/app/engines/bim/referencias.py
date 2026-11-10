"""Auditoría conservadora de niveles entre modelos IFC independientes.

No transforma coordenadas ni sustituye cotas del autor por cotas de otro
exportador: los nombres solo se emparejan por igualdad, sin adivinar alias.
"""

from __future__ import annotations

import math
from collections.abc import Iterable


def _indexar_niveles(niveles: Iterable[tuple[str, float]]) -> dict[str, tuple[str, float]]:
    result: dict[str, tuple[str, float]] = {}
    for nombre, cota in niveles:
        if not isinstance(nombre, str) or not nombre.strip():
            raise ValueError("Los niveles deben tener nombre no vacío")
        if isinstance(cota, bool) or not isinstance(cota, (int, float)) or not math.isfinite(cota):
            raise ValueError(f"Cota no finita para nivel {nombre!r}")
        key = nombre.strip().casefold()
        if key in result:
            raise ValueError(f"Nivel duplicado o ambiguo: {nombre!r}")
        result[key] = (nombre.strip(), float(cota))
    return result


def cotejar_niveles(
    referencia: Iterable[tuple[str, float]],
    candidato: Iterable[tuple[str, float]],
    *,
    tolerancia_m: float = 0.01,
) -> dict:
    """Compara cotas en metros sin inventar alineaciones ni fusionar niveles.

    Las diferencias y nombres no pareados impiden la confirmación automática;
    un usuario debe resolverlos con la fuente original y su revisión exacta.
    """
    if isinstance(tolerancia_m, bool) or not isinstance(tolerancia_m, (float, int)) or not math.isfinite(tolerancia_m) or tolerancia_m < 0:
        raise ValueError("La tolerancia debe ser finita y no negativa")
    ref = _indexar_niveles(referencia)
    other = _indexar_niveles(candidato)
    differences: list[dict] = []
    matched = 0
    for key, (name, zref) in ref.items():
        if key not in other:
            continue
        _, zother = other[key]
        delta = zother - zref
        if abs(delta) > tolerancia_m:
            differences.append({
                "nombre": name,
                "referencia_m": zref,
                "candidato_m": zother,
                "diferencia_m": round(delta, 6),
            })
        else:
            matched += 1
    only_ref = [name for key, (name, _) in ref.items() if key not in other]
    only_other = [name for key, (name, _) in other.items() if key not in ref]
    return {
        "tolerancia_m": float(tolerancia_m),
        "coincidentes": matched,
        "diferencias": differences,
        "solo_referencia": only_ref,
        "solo_candidato": only_other,
        "apto_para_confirmacion_automatica": bool(ref) and not (differences or only_ref or only_other),
    }
