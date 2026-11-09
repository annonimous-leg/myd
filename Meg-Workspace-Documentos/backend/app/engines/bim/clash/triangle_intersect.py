# Copyright © 2026 Cristian Rodriguez
# All rights reserved.
# Unauthorized copying, modification, distribution, or use is prohibited
# without prior written permission.

"""
Test geométrico triángulo-triángulo: intersección exacta (Möller, 1997,
"A Fast Triangle-Triangle Intersection Test") y distancia mínima cuando
no se traslapan pero se pide tolerancia > 0.

Esto NO viene de portar_3D -- se confirmó leyendo mesh_contact.c que ahí
`shapeB` siempre es una primitiva convexa (esfera/cápsula/hull), nunca
otra malla arbitraria. Malla-contra-malla es exactamente lo que un clash
BIM necesita (pared cóncava contra ducto cóncavo), así que se implementa
aquí con algoritmos públicos estándar de geometría computacional.
"""
from __future__ import annotations
from dataclasses import dataclass
from typing import Optional
import numpy as np

_EPS = 1e-9


@dataclass
class ResultadoParTriangulos:
    distancia: float
    punto_a: np.ndarray
    punto_b: np.ndarray
    se_traslapan: bool


def _cerca_segmento_segmento(p1, q1, p2, q2):
    """Puntos más cercanos entre segmento p1-q1 y segmento p2-q2.
    Algoritmo estándar (Ericson, 'Real-Time Collision Detection', 5.1.9)."""
    d1 = q1 - p1
    d2 = q2 - p2
    r = p1 - p2
    a = np.dot(d1, d1)
    e = np.dot(d2, d2)
    f = np.dot(d2, r)

    if a <= _EPS and e <= _EPS:
        return float(np.linalg.norm(p1 - p2)), p1.copy(), p2.copy()

    if a <= _EPS:
        s = 0.0
        t = np.clip(f / e, 0.0, 1.0)
    else:
        c = np.dot(d1, r)
        if e <= _EPS:
            t = 0.0
            s = np.clip(-c / a, 0.0, 1.0)
        else:
            b = np.dot(d1, d2)
            denom = a * e - b * b
            if denom > _EPS:
                s = np.clip((b * f - c * e) / denom, 0.0, 1.0)
            else:
                s = 0.0
            t = (b * s + f) / e
            if t < 0.0:
                t = 0.0
                s = np.clip(-c / a, 0.0, 1.0)
            elif t > 1.0:
                t = 1.0
                s = np.clip((b - c) / a, 0.0, 1.0)

    c1 = p1 + d1 * s
    c2 = p2 + d2 * t
    return float(np.linalg.norm(c1 - c2)), c1, c2


def _cerca_punto_triangulo(p, a, b, c):
    """Punto más cercano a p sobre el triángulo (a,b,c), por proyección
    baricéntrica con recorte a bordes/vértices (Ericson, 5.1.5)."""
    ab = b - a
    ac = c - a
    ap = p - a
    d1 = np.dot(ab, ap)
    d2 = np.dot(ac, ap)
    if d1 <= 0 and d2 <= 0:
        return a.copy()

    bp = p - b
    d3 = np.dot(ab, bp)
    d4 = np.dot(ac, bp)
    if d3 >= 0 and d4 <= d3:
        return b.copy()

    vc = d1 * d4 - d3 * d2
    if vc <= 0 and d1 >= 0 and d3 <= 0:
        v = d1 / (d1 - d3)
        return a + v * ab

    cp = p - c
    d5 = np.dot(ab, cp)
    d6 = np.dot(ac, cp)
    if d6 >= 0 and d5 <= d6:
        return c.copy()

    vb = d5 * d2 - d1 * d6
    if vb <= 0 and d2 >= 0 and d6 <= 0:
        w = d2 / (d2 - d6)
        return a + w * ac

    va = d3 * d6 - d5 * d4
    if va <= 0 and (d4 - d3) >= 0 and (d5 - d6) >= 0:
        w = (d4 - d3) / ((d4 - d3) + (d5 - d6))
        return b + w * (c - b)

    denom = 1.0 / (va + vb + vc)
    v = vb * denom
    w = vc * denom
    return a + ab * v + ac * w


def _distancia_minima(tri_a, tri_b):
    """Distancia mínima entre dos triángulos que NO se traslapan: mínimo
    sobre las 9 combinaciones de aristas (segmento-segmento) y los 6
    vértices contra el triángulo opuesto (punto-triángulo)."""
    mejor_d = float("inf")
    mejor_pa = mejor_pb = None

    aristas_a = [(tri_a[0], tri_a[1]), (tri_a[1], tri_a[2]), (tri_a[2], tri_a[0])]
    aristas_b = [(tri_b[0], tri_b[1]), (tri_b[1], tri_b[2]), (tri_b[2], tri_b[0])]
    for pa1, qa1 in aristas_a:
        for pb2, qb2 in aristas_b:
            d, ca, cb = _cerca_segmento_segmento(pa1, qa1, pb2, qb2)
            if d < mejor_d:
                mejor_d, mejor_pa, mejor_pb = d, ca, cb

    for v in tri_a:
        cb = _cerca_punto_triangulo(v, tri_b[0], tri_b[1], tri_b[2])
        d = float(np.linalg.norm(v - cb))
        if d < mejor_d:
            mejor_d, mejor_pa, mejor_pb = d, v.copy(), cb

    for v in tri_b:
        ca = _cerca_punto_triangulo(v, tri_a[0], tri_a[1], tri_a[2])
        d = float(np.linalg.norm(v - ca))
        if d < mejor_d:
            mejor_d, mejor_pa, mejor_pb = d, ca, v.copy()

    return mejor_d, mejor_pa, mejor_pb


def _signo(x):
    if x > _EPS:
        return 1
    if x < -_EPS:
        return -1
    return 0


def _segmento_triangulo(p0, p1, a, b, c):
    """¿El segmento p0-p1 cruza el interior (o borde) del triángulo
    (a,b,c)? Möller-Trumbore (1997, "Fast, Minimum Storage Ray-Triangle
    Intersection"), adaptado de rayo a segmento acotado (t en [0,1]).
    Es el mismo algoritmo usado en prácticamente todo ray tracer -- se
    prefirió sobre una fórmula de intervalos hecha a mano porque los
    casos límite (extremo del segmento justo sobre el triángulo) caen
    de forma natural en u/v/t en vez de necesitar ramas especiales."""
    ab = b - a
    ac = c - a
    dir_ = p1 - p0
    pvec = np.cross(dir_, ac)
    det = np.dot(ab, pvec)
    if abs(det) < _EPS:
        return None  # segmento paralelo al plano del triángulo
    inv_det = 1.0 / det
    tvec = p0 - a
    u = np.dot(tvec, pvec) * inv_det
    if u < -_EPS or u > 1.0 + _EPS:
        return None
    qvec = np.cross(tvec, ab)
    v = np.dot(dir_, qvec) * inv_det
    if v < -_EPS or u + v > 1.0 + _EPS:
        return None
    t = np.dot(ac, qvec) * inv_det
    if t < -_EPS or t > 1.0 + _EPS:
        return None
    return p0 + dir_ * t


def _se_traslapan_exacto(tri_a, tri_b) -> Optional[tuple]:
    """Test de intersección exacta. Regresa (punto_a, punto_b) --
    extremos representativos del segmento de traslape -- si los
    triángulos se cruzan, o None si no.

    Primero un rechazo rápido por signo de distancia a plano (si los 3
    vértices de A quedan estrictamente del mismo lado del plano de B, o
    viceversa, es imposible que se crucen). Si no se puede rechazar,
    se prueban las 6 aristas (3 de A contra el triángulo B, 3 de B
    contra el triángulo A) con Möller-Trumbore; si CUALQUIERA cruza, hay
    traslape. Esto cubre de forma natural los casos donde un vértice cae
    justo sobre el plano opuesto (t=0 o t=1 en la fórmula), a diferencia
    de un enfoque de intervalos que necesita ramas especiales para eso."""
    a0, a1, a2 = tri_a
    b0, b1, b2 = tri_b

    normal_b = np.cross(b1 - b0, b2 - b0)
    if np.linalg.norm(normal_b) < _EPS:
        return None  # triángulo B degenerado (área ~0), no es geometría BIM válida
    sa = [_signo(np.dot(normal_b, v - b0)) for v in (a0, a1, a2)]
    if sa[0] == sa[1] == sa[2] and sa[0] != 0:
        return None

    normal_a = np.cross(a1 - a0, a2 - a0)
    if np.linalg.norm(normal_a) < _EPS:
        return None  # triángulo A degenerado
    sb = [_signo(np.dot(normal_a, v - a0)) for v in (b0, b1, b2)]
    if sb[0] == sb[1] == sb[2] and sb[0] != 0:
        return None

    if sa == [0, 0, 0]:
        return None  # coplanares: fuera de alcance, ver docstring del módulo

    aristas_a = ((a0, a1), (a1, a2), (a2, a0))
    aristas_b = ((b0, b1), (b1, b2), (b2, b0))
    puntos = []
    for p0, p1 in aristas_a:
        pt = _segmento_triangulo(p0, p1, b0, b1, b2)
        if pt is not None:
            puntos.append(pt)
    for p0, p1 in aristas_b:
        pt = _segmento_triangulo(p0, p1, a0, a1, a2)
        if pt is not None:
            puntos.append(pt)

    if not puntos:
        return None
    return puntos[0], puntos[-1]


def probar_par(tri_a: np.ndarray, tri_b: np.ndarray, tolerancia: float) -> Optional[ResultadoParTriangulos]:
    """tri_a/tri_b: (3,3) arreglos de vértices. None si no hay clash."""
    interseccion = _se_traslapan_exacto(tri_a, tri_b)
    if interseccion is not None:
        p_a, p_b = interseccion
        return ResultadoParTriangulos(distancia=0.0, punto_a=p_a, punto_b=p_b, se_traslapan=True)

    if tolerancia <= 0:
        return None

    d, pa, pb = _distancia_minima(tri_a, tri_b)
    if d <= tolerancia:
        return ResultadoParTriangulos(distancia=d, punto_a=pa, punto_b=pb, se_traslapan=False)
    return None
