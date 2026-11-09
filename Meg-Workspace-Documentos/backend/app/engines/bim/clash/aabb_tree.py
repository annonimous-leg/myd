# Copyright © 2026 Cristian Rodriguez
# All rights reserved.
# Unauthorized copying, modification, distribution, or use is prohibited
# without prior written permission.

"""
Árbol AABB estático para clash detection en lote.

Adaptado de la lógica de dynamic_tree.c de portar_3D (b3PartitionMid /
b3BuildTree / b3DynamicTree_Query), simplificado a propósito: el
original es un árbol DINÁMICO para cuerpos que se mueven cada frame de
una simulación de físicas -- inserción incremental con selección de
hermano por SAH (b3FindBestSibling), rotaciones de rebalanceo
(b3RotateNodes), proxies con margen inflado para no reconstruir en cada
movimiento (b3DynamicTree_MoveProxy/EnlargeProxy), múltiples árboles por
tipo de cuerpo. Los elementos BIM son estáticos durante un análisis de
clash -- no hay nada que mover -- así que se implementa solo lo que
aplica: construcción masiva de una sola vez (bulk-build) y consulta de
traslape.

Partición por MEDIANA en el eje más largo (equivalente conceptual a
b3PartitionMid, línea 1479 del original) en vez del binned-SAH completo
de b3PartitionSAH. Decisión deliberada: a la escala de un modelo BIM
(cientos a pocos miles de elementos) la diferencia de calidad de árbol
entre mediana y SAH-binned es marginal para consultas de traslape, y
mediana es mucho más simple de verificar como correcta.
"""
from __future__ import annotations
from dataclasses import dataclass
from typing import List, Tuple
import numpy as np


@dataclass
class _Nodo:
    aabb_min: np.ndarray
    aabb_max: np.ndarray
    izquierda: int = -1
    derecha: int = -1
    indice_hoja: int = -1  # -1 si es nodo interno


def _se_traslapan(a_min, a_max, b_min, b_max) -> bool:
    return bool(np.all(a_min <= b_max) and np.all(b_min <= a_max))


class AABBTree:
    """Árbol AABB estático de construcción única, para consultas de
    traslape entre N cajas conocidas de antemano (broad phase)."""

    def __init__(self, mins: np.ndarray, maxs: np.ndarray):
        """mins/maxs: arreglos (N,3). Si el análisis usa tolerancia, hay
        que expandir las cajas ANTES de construir el árbol (el árbol
        mismo no sabe de tolerancia, solo hace traslape de cajas) --
        ver MotorClash._preparar_cajas."""
        mins = np.asarray(mins, dtype=float)
        maxs = np.asarray(maxs, dtype=float)
        if mins.shape != maxs.shape or (mins.ndim == 2 and mins.shape[1] != 3):
            raise ValueError("mins/maxs deben ser arreglos (N,3) del mismo shape")
        self.n = mins.shape[0]
        self.mins = mins
        self.maxs = maxs
        self.nodos: List[_Nodo] = []
        self.raiz = self._construir(list(range(self.n))) if self.n > 0 else -1

    def _construir(self, indices: List[int]) -> int:
        cajas_min = self.mins[indices]
        cajas_max = self.maxs[indices]
        env_min = cajas_min.min(axis=0)
        env_max = cajas_max.max(axis=0)

        if len(indices) == 1:
            self.nodos.append(_Nodo(env_min, env_max, indice_hoja=indices[0]))
            return len(self.nodos) - 1

        extension = env_max - env_min
        eje = int(np.argmax(extension))
        centros = (cajas_min[:, eje] + cajas_max[:, eje]) * 0.5
        orden = np.argsort(centros, kind="stable")
        mitad = len(indices) // 2
        izq = [indices[i] for i in orden[:mitad]]
        der = [indices[i] for i in orden[mitad:]]

        # Caso degenerado (todos los centros iguales en este eje, ej.
        # elementos apilados exactamente): evita que izq o der queden
        # vacíos, lo que causaría recursión infinita.
        if not izq or not der:
            izq, der = indices[:mitad] or indices[:1], indices[mitad:] or indices[1:]

        id_izq = self._construir(izq)
        id_der = self._construir(der)
        self.nodos.append(_Nodo(env_min, env_max, izquierda=id_izq, derecha=id_der))
        return len(self.nodos) - 1

    def consultar(self, q_min: np.ndarray, q_max: np.ndarray) -> List[int]:
        """Todas las hojas cuya caja traslapa con [q_min, q_max]."""
        resultado: List[int] = []
        if self.raiz == -1:
            return resultado
        pila = [self.raiz]
        while pila:
            idx = pila.pop()
            nodo = self.nodos[idx]
            if not _se_traslapan(nodo.aabb_min, nodo.aabb_max, q_min, q_max):
                continue
            if nodo.indice_hoja != -1:
                resultado.append(nodo.indice_hoja)
            else:
                pila.append(nodo.izquierda)
                pila.append(nodo.derecha)
        return resultado

    def pares_traslapados(self) -> List[Tuple[int, int]]:
        """Todos los pares (i,j), i<j, cuyas cajas se traslapan."""
        pares = set()
        for i in range(self.n):
            for j in self.consultar(self.mins[i], self.maxs[i]):
                if j != i:
                    pares.add((i, j) if i < j else (j, i))
        return sorted(pares)
