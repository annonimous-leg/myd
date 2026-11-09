# Copyright © 2026 Cristian Rodriguez
# All rights reserved.
# Unauthorized copying, modification, distribution, or use is prohibited
# without prior written permission.

"""
BVH por-malla: acelera el narrow phase evitando comparar todos los
triángulos de una malla contra todos los de otra a fuerza bruta.

Mismo patrón de bulk-build por mediana que aabb_tree.py, aplicado a nivel
triángulo en vez de elemento completo. Inspirado en la idea de mesh.c de
que cada malla tenga su propio árbol de cajas para consultas espaciales
(b3BuildRecursive/b3QueryMesh) -- no portado línea por línea, ese código
también resuelve pesos por material y soldado de vértices que no
aplican aquí; solo se tomó el patrón de "malla con su propio BVH".
"""
from __future__ import annotations
from typing import Tuple
import numpy as np

from app.engines.bim.clash.aabb_tree import AABBTree


def construir_bvh_malla(vertices: np.ndarray, caras: np.ndarray) -> Tuple[AABBTree, np.ndarray]:
    """vertices: (V,3) float. caras: (T,3) índices de vértice por
    triángulo. Regresa el árbol de cajas por-triángulo y los vértices
    de cada triángulo ya resueltos (T,3,3), para no repetir el
    fancy-indexing en cada consulta."""
    if len(caras) == 0:
        return AABBTree(np.zeros((0, 3)), np.zeros((0, 3))), np.zeros((0, 3, 3))
    tri_verts = vertices[caras]  # (T,3,3)
    mins = tri_verts.min(axis=1)
    maxs = tri_verts.max(axis=1)
    arbol = AABBTree(mins, maxs)
    return arbol, tri_verts


def pares_triangulos_candidatos(
    arbol_a: AABBTree, tri_verts_a: np.ndarray,
    arbol_b: AABBTree, tri_verts_b: np.ndarray,
    margen: float = 0.0,
):
    """Índices de pares de triángulos (i de A, j de B) cuyas cajas se
    traslapan (expandidas por `margen`, la tolerancia del análisis).
    Consulta el árbol de B con la caja de cada hoja de A -- más simple
    que una traversal simultánea de dos árboles, a costa de algo de
    trabajo redundante; aceptable a la escala de una malla BIM."""
    pares = []
    if arbol_a.n == 0 or arbol_b.n == 0:
        return pares
    for i in range(arbol_a.n):
        q_min = arbol_a.mins[i] - margen
        q_max = arbol_a.maxs[i] + margen
        for j in arbol_b.consultar(q_min, q_max):
            pares.append((i, j))
    return pares
