# Copyright © 2026 Cristian Rodriguez
# All rights reserved.
# Unauthorized copying, modification, distribution, or use is prohibited
# without prior written permission.

"""
Motor de clash detection para modelos BIM.

Orquesta: broad phase (AABBTree sobre las cajas de cada elemento, ver
aabb_tree.py) -> narrow phase (BVH por-malla + Möller-Trumbore
triángulo-triángulo, ver mesh_bvh.py / triangle_intersect.py).

Límite de cómputo por par de elementos (B3_MAX_MESH_CONTACT_TRIANGLES=256
en el mesh_contact.c original de portar_3D es el mismo patrón defensivo:
un tope duro de pares de triángulos candidatos por par de elementos, para
que una malla patológicamente densa no cuelgue el análisis completo).

Volumen aproximado: NO es un booleano exacto de las mallas (eso
necesitaría una librería de CSG que este proyecto no trae). Se reporta el
volumen de la intersección de los dos AABB de los elementos -- una cota
superior simple y honesta del volumen real de traslape, útil para
priorizar severidad, documentado como aproximado en el modelo de datos.
"""
from dataclasses import dataclass, field
from typing import List, Optional, Tuple
import numpy as np

from app.engines.bim.clash.aabb_tree import AABBTree
from app.engines.bim.clash.mesh_bvh import construir_bvh_malla, pares_triangulos_candidatos
from app.engines.bim.clash.triangle_intersect import probar_par

MAX_PARES_TRIANGULO_POR_ELEMENTO = 20_000  # tope defensivo, ver docstring


@dataclass
class ElementoParaClash:
    """Vista mínima de un ElementoBIM que el motor necesita -- desacopla
    el motor del modelo SQLAlchemy para poder probarlo sin BD."""
    id: str
    tipo: str
    bbox: Tuple[float, float, float, float, float, float]
    malla_vertices: Optional[List[float]]
    malla_caras: Optional[List[int]]


@dataclass
class ResultadoClash:
    elemento_a_id: str
    elemento_b_id: str
    tipo_a: str
    tipo_b: str
    severidad: str  # "DURO" | "BLANDO"
    distancia_m: float
    volumen_aproximado_m3: float
    punto_cercano_a: List[float]
    punto_cercano_b: List[float]
    triangulos_a: List[List[List[float]]]  # hasta MAX_TRIANGULOS_REPORTADOS triángulos [ [x,y,z]x3 ]
    triangulos_b: List[List[List[float]]]


MAX_TRIANGULOS_REPORTADOS = 30  # por lado, para no disparar el tamaño de fila en BD


def _bbox_a_min_max(bbox) -> Tuple[np.ndarray, np.ndarray]:
    b = np.asarray(bbox, dtype=float)
    return b[:3], b[3:]


def _volumen_interseccion_bbox(bbox_a, bbox_b) -> float:
    """Volumen de la intersección de dos cajas alineadas a los ejes.
    0.0 si no se traslapan en algún eje. Ver nota de 'volumen aproximado'
    en el docstring del módulo -- NO es booleano exacto de las mallas."""
    a_min, a_max = _bbox_a_min_max(bbox_a)
    b_min, b_max = _bbox_a_min_max(bbox_b)
    lo = np.maximum(a_min, b_min)
    hi = np.minimum(a_max, b_max)
    extension = np.maximum(hi - lo, 0.0)
    return float(np.prod(extension))


def _malla_valida(elem: ElementoParaClash) -> bool:
    return bool(elem.malla_vertices) and bool(elem.malla_caras) and len(elem.malla_caras) >= 3


class MotorClash:
    """Corre un análisis de clash detection sobre una lista de elementos
    de un mismo ModeloBIM. No toca base de datos -- eso lo hace
    ClashService, que traduce ElementoBIM -> ElementoParaClash y
    persiste los ResultadoClash que este motor regresa."""

    def __init__(self, tolerancia_m: float = 0.0):
        if tolerancia_m < 0:
            raise ValueError("tolerancia_m no puede ser negativa")
        self.tolerancia_m = tolerancia_m
        self._cache_bvh_malla = {}

    def _bvh_malla(self, elem: ElementoParaClash):
        if elem.id not in self._cache_bvh_malla:
            vertices = np.array(elem.malla_vertices, dtype=float).reshape(-1, 3)
            caras = np.array(elem.malla_caras, dtype=int).reshape(-1, 3)
            self._cache_bvh_malla[elem.id] = construir_bvh_malla(vertices, caras)
        return self._cache_bvh_malla[elem.id]

    def detectar(self, elementos: List[ElementoParaClash]) -> List[ResultadoClash]:
        self._cache_bvh_malla.clear()
        if len(elementos) < 2:
            return []

        # --- Broad phase: cajas expandidas por la tolerancia ---
        mins = np.zeros((len(elementos), 3))
        maxs = np.zeros((len(elementos), 3))
        for i, e in enumerate(elementos):
            e_min, e_max = _bbox_a_min_max(e.bbox)
            mins[i] = e_min - self.tolerancia_m
            maxs[i] = e_max + self.tolerancia_m
        arbol = AABBTree(mins, maxs)
        pares_candidatos = arbol.pares_traslapados()

        resultados: List[ResultadoClash] = []
        for i, j in pares_candidatos:
            elem_a, elem_b = elementos[i], elementos[j]

            if not _malla_valida(elem_a) or not _malla_valida(elem_b):
                # Sin malla no se puede hacer narrow phase real. En vez
                # de fingir precisión, se omite el par -- mejor no
                # reportar que reportar un falso positivo/negativo. Ver
                # CLASH_DETECTION_IMPLEMENTADO.md para el detalle.
                continue

            resultado = self._probar_par_elementos(elem_a, elem_b)
            if resultado is not None:
                resultados.append(resultado)

        return resultados

    def _probar_par_elementos(self, elem_a: ElementoParaClash, elem_b: ElementoParaClash) -> Optional[ResultadoClash]:
        bvh_a, tris_a = self._bvh_malla(elem_a)
        bvh_b, tris_b = self._bvh_malla(elem_b)

        candidatos = pares_triangulos_candidatos(bvh_a, tris_a, bvh_b, tris_b, margen=self.tolerancia_m)
        if len(candidatos) > MAX_PARES_TRIANGULO_POR_ELEMENTO:
            candidatos = candidatos[:MAX_PARES_TRIANGULO_POR_ELEMENTO]

        mejor_distancia = float("inf")
        mejor_punto_a = mejor_punto_b = None
        triangulos_clash_a = []
        triangulos_clash_b = []

        for ti, tj in candidatos:
            r = probar_par(tris_a[ti], tris_b[tj], self.tolerancia_m)
            if r is None:
                continue
            if r.distancia < mejor_distancia:
                mejor_distancia = r.distancia
                mejor_punto_a, mejor_punto_b = r.punto_a, r.punto_b
            if len(triangulos_clash_a) < MAX_TRIANGULOS_REPORTADOS:
                triangulos_clash_a.append(tris_a[ti].tolist())
                triangulos_clash_b.append(tris_b[tj].tolist())

        if mejor_punto_a is None:
            return None  # ningún par de triángulos calificó -> broad phase fue falso positivo

        severidad = "DURO" if mejor_distancia <= 1e-9 else "BLANDO"
        volumen = _volumen_interseccion_bbox(elem_a.bbox, elem_b.bbox)

        return ResultadoClash(
            elemento_a_id=elem_a.id,
            elemento_b_id=elem_b.id,
            tipo_a=elem_a.tipo,
            tipo_b=elem_b.tipo,
            severidad=severidad,
            distancia_m=round(mejor_distancia, 6),
            volumen_aproximado_m3=round(volumen, 6),
            punto_cercano_a=[round(float(x), 4) for x in mejor_punto_a],
            punto_cercano_b=[round(float(x), 4) for x in mejor_punto_b],
            triangulos_a=triangulos_clash_a,
            triangulos_b=triangulos_clash_b,
        )
