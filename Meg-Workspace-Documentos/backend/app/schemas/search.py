# Copyright © 2026 Cristian Rodriguez
# All rights reserved.
# Unauthorized copying, modification, distribution, or use is prohibited
# without prior written permission.

"""
Schemas Pydantic para el módulo de búsqueda.
"""
from typing import List, Optional, Dict, Any
from pydantic import BaseModel


class SearchResultItem(BaseModel):
    id: str
    titulo: str
    descripcion: Optional[str]
    tipo: str
    estado: Optional[str]
    dominio: str
    created_at: Optional[str]
    relevancia: float


class SearchResponse(BaseModel):
    query: str
    total: int
    skip: int
    limit: int
    total_por_dominio: Dict[str, int]
    resultados: List[SearchResultItem]


class TagSearchResponse(BaseModel):
    tags: List[str]
    operador: str
    total: int
    skip: int
    limit: int
    resultados: List[Dict[str, Any]]
