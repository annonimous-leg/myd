# Copyright © 2026 Cristian Rodriguez
# All rights reserved.
# Unauthorized copying, modification, distribution, or use is prohibited
# without prior written permission.

"""
SearchService - Servicio de búsqueda avanzada y semántica.
Búsqueda full-text, por metadatos, y clasificación de documentos.
"""
from typing import List, Optional, Dict, Any
from uuid import UUID
from datetime import datetime

from sqlalchemy import select, and_, or_, desc, func, text
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.documento import DocumentoCDE, EstadoDocumento, TipoDocumento
from app.models.expediente import ExpedienteObra
from app.models.presupuesto import Presupuesto, Partida, Concepto
from app.models.contrato import Contrato
from app.models.licitacion import Licitacion
from app.core.errors import MegalodonException, ErrorCode


class SearchService:
    """Servicio de búsqueda avanzada multi-dominio.

    Soporta búsqueda por:
    - Texto completo (nombre, descripción, contenido extraído)
    - Metadatos estructurados
    - Filtros combinados
    - Clasificación por relevancia
    """

    def __init__(self, db: AsyncSession):
        self.db = db

    async def busqueda_global(
        self,
        query: str,
        *,
        dominios: Optional[List[str]] = None,
        tenant_id: Optional[UUID] = None,
        fecha_inicio: Optional[datetime] = None,
        fecha_fin: Optional[datetime] = None,
        skip: int = 0,
        limit: int = 50,
    ) -> Dict[str, Any]:
        """Búsqueda global across todos los dominios.

        Dominios: documentos, expedientes, presupuestos, contratos, licitaciones.
        """
        dominios = dominios or ["documentos", "expedientes", "presupuestos", "contratos", "licitaciones"]
        resultados = []
        total_por_dominio = {}

        if "documentos" in dominios:
            docs = await self._buscar_documentos(
                query, tenant_id=tenant_id, fecha_inicio=fecha_inicio, fecha_fin=fecha_fin
            )
            total_por_dominio["documentos"] = len(docs)
            resultados.extend([{**r, "dominio": "documento"} for r in docs])

        if "expedientes" in dominios:
            exps = await self._buscar_expedientes(
                query, tenant_id=tenant_id, fecha_inicio=fecha_inicio, fecha_fin=fecha_fin
            )
            total_por_dominio["expedientes"] = len(exps)
            resultados.extend([{**r, "dominio": "expediente"} for r in exps])

        if "presupuestos" in dominios:
            pres = await self._buscar_presupuestos(
                query, tenant_id=tenant_id, fecha_inicio=fecha_inicio, fecha_fin=fecha_fin
            )
            total_por_dominio["presupuestos"] = len(pres)
            resultados.extend([{**r, "dominio": "presupuesto"} for r in pres])

        if "contratos" in dominios:
            contrs = await self._buscar_contratos(
                query, tenant_id=tenant_id, fecha_inicio=fecha_inicio, fecha_fin=fecha_fin
            )
            total_por_dominio["contratos"] = len(contrs)
            resultados.extend([{**r, "dominio": "contrato"} for r in contrs])

        if "licitaciones" in dominios:
            lics = await self._buscar_licitaciones(
                query, tenant_id=tenant_id, fecha_inicio=fecha_inicio, fecha_fin=fecha_fin
            )
            total_por_dominio["licitaciones"] = len(lics)
            resultados.extend([{**r, "dominio": "licitacion"} for r in lics])

        # Ordenar por relevancia (simulada por fecha para ahora)
        resultados.sort(key=lambda x: x.get("created_at", ""), reverse=True)

        total = len(resultados)
        paginados = resultados[skip:skip + limit]

        return {
            "query": query,
            "total": total,
            "skip": skip,
            "limit": limit,
            "total_por_dominio": total_por_dominio,
            "resultados": paginados,
        }

    async def _buscar_documentos(
        self,
        query: str,
        tenant_id: Optional[UUID] = None,
        fecha_inicio: Optional[datetime] = None,
        fecha_fin: Optional[datetime] = None,
    ) -> List[Dict]:
        """Búsqueda en documentos.

        BUG ORIGINAL: tenant_id se recibía como parámetro pero nunca se
        usaba en la query -- cualquier búsqueda regresaba documentos de
        TODOS los tenants."""
        sql = select(DocumentoCDE).where(
            or_(
                DocumentoCDE.nombre.ilike(f"%{query}%"),
                DocumentoCDE.descripcion.ilike(f"%{query}%"),
            )
        )
        if tenant_id is not None:
            sql = sql.where(DocumentoCDE.tenant_id == tenant_id)
        if fecha_inicio:
            sql = sql.where(DocumentoCDE.created_at >= fecha_inicio)
        if fecha_fin:
            sql = sql.where(DocumentoCDE.created_at <= fecha_fin)

        result = await self.db.execute(sql.limit(20))
        docs = result.scalars().all()

        return [
            {
                "id": str(d.id),
                "titulo": d.nombre,
                "descripcion": d.descripcion,
                "tipo": d.tipo.value if hasattr(d.tipo, 'value') else str(d.tipo),
                "estado": d.estado.value if hasattr(d.estado, 'value') else str(d.estado),
                "created_at": d.created_at.isoformat() if d.created_at else None,
                "relevancia": self._calcular_relevancia(query, d.nombre, d.descripcion),
            }
            for d in docs
        ]

    async def _buscar_expedientes(
        self,
        query: str,
        tenant_id: Optional[UUID] = None,
        fecha_inicio: Optional[datetime] = None,
        fecha_fin: Optional[datetime] = None,
    ) -> List[Dict]:
        """Búsqueda en expedientes.

        BUG ORIGINAL: mismo patrón -- tenant_id nunca se aplicaba."""
        sql = select(ExpedienteObra).where(
            or_(
                ExpedienteObra.titulo.ilike(f"%{query}%"),
                ExpedienteObra.identificador.ilike(f"%{query}%"),
                ExpedienteObra.descripcion.ilike(f"%{query}%"),
            )
        )
        if tenant_id is not None:
            sql = sql.where(ExpedienteObra.tenant_id == tenant_id)
        if fecha_inicio:
            sql = sql.where(ExpedienteObra.created_at >= fecha_inicio)
        if fecha_fin:
            sql = sql.where(ExpedienteObra.created_at <= fecha_fin)

        result = await self.db.execute(sql.limit(20))
        exps = result.scalars().all()

        return [
            {
                "id": str(e.id),
                "titulo": e.titulo,
                "identificador": e.identificador,
                "descripcion": e.descripcion,
                "estado": e.estado.value if hasattr(e.estado, 'value') else str(e.estado),
                "created_at": e.created_at.isoformat() if e.created_at else None,
                "relevancia": self._calcular_relevancia(query, e.titulo, e.descripcion),
            }
            for e in exps
        ]

    async def _buscar_presupuestos(
        self,
        query: str,
        tenant_id: Optional[UUID] = None,
        fecha_inicio: Optional[datetime] = None,
        fecha_fin: Optional[datetime] = None,
    ) -> List[Dict]:
        """Búsqueda en presupuestos y conceptos.

        BUG ORIGINAL: mismo patrón de fuga -- sin filtro de tenant.
        Presupuesto/Concepto no tienen tenant_id propio (no usan
        TenantMixin); se llega al tenant vía join con ExpedienteObra
        (Presupuesto.expediente_id, y para Concepto a través de
        Partida.presupuesto_id).
        """
        # Buscar en presupuestos
        sql = select(Presupuesto).where(
            or_(
                Presupuesto.identificador.ilike(f"%{query}%"),
                Presupuesto.nombre.ilike(f"%{query}%"),
            )
        )
        if tenant_id is not None:
            sql = sql.join(ExpedienteObra, ExpedienteObra.id == Presupuesto.expediente_id).where(
                ExpedienteObra.tenant_id == tenant_id
            )
        if fecha_inicio:
            sql = sql.where(Presupuesto.created_at >= fecha_inicio)
        if fecha_fin:
            sql = sql.where(Presupuesto.created_at <= fecha_fin)

        result = await self.db.execute(sql.limit(10))
        pres = result.scalars().all()

        # Buscar en conceptos
        sql_conceptos = select(Concepto).where(
            or_(
                Concepto.clave.ilike(f"%{query}%"),
                Concepto.descripcion.ilike(f"%{query}%"),
            )
        )
        if tenant_id is not None:
            sql_conceptos = (
                sql_conceptos
                .join(Partida, Partida.id == Concepto.partida_id)
                .join(Presupuesto, Presupuesto.id == Partida.presupuesto_id)
                .join(ExpedienteObra, ExpedienteObra.id == Presupuesto.expediente_id)
                .where(ExpedienteObra.tenant_id == tenant_id)
            )
        result_c = await self.db.execute(sql_conceptos.limit(10))
        conceptos = result_c.scalars().all()

        resultados = []
        for p in pres:
            resultados.append({
                "id": str(p.id),
                "titulo": p.nombre or p.identificador,
                "descripcion": f"Presupuesto {p.identificador}",
                "tipo": "presupuesto",
                "estado": p.estado.value if hasattr(p.estado, 'value') else str(p.estado),
                "created_at": p.created_at.isoformat() if p.created_at else None,
                "relevancia": self._calcular_relevancia(query, p.identificador, p.nombre),
            })

        for c in conceptos:
            resultados.append({
                "id": str(c.id),
                "titulo": f"{c.clave} - {c.descripcion[:50]}",
                "descripcion": f"Concepto de presupuesto",
                "tipo": "concepto",
                "estado": "ACTIVO",
                "created_at": c.created_at.isoformat() if c.created_at else None,
                "relevancia": self._calcular_relevancia(query, c.clave, c.descripcion),
            })

        return resultados

    async def _buscar_contratos(
        self,
        query: str,
        tenant_id: Optional[UUID] = None,
        fecha_inicio: Optional[datetime] = None,
        fecha_fin: Optional[datetime] = None,
    ) -> List[Dict]:
        """Búsqueda en contratos.

        BUG ORIGINAL: mismo patrón -- sin filtro de tenant."""
        sql = select(Contrato).where(
            or_(
                Contrato.numero_contrato.ilike(f"%{query}%"),
                Contrato.objeto.ilike(f"%{query}%"),
            )
        )
        if tenant_id is not None:
            sql = sql.where(Contrato.tenant_id == tenant_id)
        if fecha_inicio:
            sql = sql.where(Contrato.created_at >= fecha_inicio)
        if fecha_fin:
            sql = sql.where(Contrato.created_at <= fecha_fin)

        result = await self.db.execute(sql.limit(20))
        contrs = result.scalars().all()

        return [
            {
                "id": str(c.id),
                "titulo": c.numero_contrato,
                "descripcion": c.objeto,
                "tipo": "contrato",
                "estado": c.estado.value if hasattr(c.estado, 'value') else str(c.estado),
                "created_at": c.created_at.isoformat() if c.created_at else None,
                "relevancia": self._calcular_relevancia(query, c.numero_contrato, c.objeto),
            }
            for c in contrs
        ]

    async def _buscar_licitaciones(
        self,
        query: str,
        tenant_id: Optional[UUID] = None,
        fecha_inicio: Optional[datetime] = None,
        fecha_fin: Optional[datetime] = None,
    ) -> List[Dict]:
        """Búsqueda en licitaciones.

        BUG ORIGINAL: mismo patrón -- sin filtro de tenant."""
        sql = select(Licitacion).where(
            or_(
                Licitacion.numero_licitacion.ilike(f"%{query}%"),
                Licitacion.objeto.ilike(f"%{query}%"),
            )
        )
        if tenant_id is not None:
            sql = sql.where(Licitacion.tenant_id == tenant_id)
        if fecha_inicio:
            sql = sql.where(Licitacion.created_at >= fecha_inicio)
        if fecha_fin:
            sql = sql.where(Licitacion.created_at <= fecha_fin)

        result = await self.db.execute(sql.limit(20))
        lics = result.scalars().all()

        return [
            {
                "id": str(l.id),
                "titulo": l.numero_licitacion,
                "descripcion": l.objeto,
                "tipo": "licitacion",
                "estado": l.estado,
                "created_at": l.created_at.isoformat() if l.created_at else None,
                "relevancia": self._calcular_relevancia(query, l.numero_licitacion, l.objeto),
            }
            for l in lics
        ]

    def _calcular_relevancia(self, query: str, titulo: Optional[str], descripcion: Optional[str]) -> float:
        """Calcula un score de relevancia simple (0-1)."""
        query_lower = query.lower()
        score = 0.0

        if titulo and query_lower in titulo.lower():
            score += 0.6
            if titulo.lower().startswith(query_lower):
                score += 0.2

        if descripcion and query_lower in descripcion.lower():
            score += 0.2

        return min(score, 1.0)

    async def busqueda_por_tags(
        self,
        tags: List[str],
        *,
        tenant_id: Optional[UUID] = None,
        operador: str = "AND",
        skip: int = 0,
        limit: int = 100,
    ) -> Dict[str, Any]:
        """Búsqueda de documentos por tags.

        operador: "AND" (todos los tags) o "OR" (cualquier tag).

        BUG ORIGINAL: ni siquiera recibía tenant_id -- listaba TODOS los
        documentos de TODOS los tenants para filtrar por tags en Python.
        """
        if not tags:
            return {"total": 0, "resultados": []}
        if tenant_id is None:
            raise ValueError("tenant_id es obligatorio para buscar documentos por tags")

        sql = select(DocumentoCDE).where(DocumentoCDE.tenant_id == tenant_id)
        result = await self.db.execute(sql)
        documentos = result.scalars().all()

        resultados = []
        for d in documentos:
            doc_tags = []
            if d.metadatos and "tags" in d.metadatos:
                doc_tags = d.metadatos["tags"]

            if operador == "AND":
                match = all(tag in doc_tags for tag in tags)
            else:
                match = any(tag in doc_tags for tag in tags)

            if match:
                resultados.append({
                    "id": str(d.id),
                    "nombre": d.nombre,
                    "tipo": d.tipo.value if hasattr(d.tipo, 'value') else str(d.tipo),
                    "tags": doc_tags,
                    "created_at": d.created_at.isoformat() if d.created_at else None,
                })

        total = len(resultados)
        paginados = resultados[skip:skip + limit]

        return {
            "tags": tags,
            "operador": operador,
            "total": total,
            "skip": skip,
            "limit": limit,
            "resultados": paginados,
        }

    async def sugerencias_autocompletar(
        self,
        query: str,
        *,
        tenant_id: Optional[UUID] = None,
        dominio: str = "documentos",
        limit: int = 10,
    ) -> List[str]:
        """Sugerencias de autocompletado para búsqueda.

        BUG ORIGINAL: sin tenant_id -- sugería nombres de documentos/
        expedientes de otros tenants."""
        if len(query) < 2:
            return []

        sugerencias = []

        if dominio == "documentos":
            sql = select(DocumentoCDE.nombre).where(DocumentoCDE.nombre.ilike(f"%{query}%"))
            if tenant_id is not None:
                sql = sql.where(DocumentoCDE.tenant_id == tenant_id)
            result = await self.db.execute(sql.limit(limit))
            sugerencias = [r[0] for r in result.all() if r[0]]

        elif dominio == "expedientes":
            sql = select(ExpedienteObra.titulo).where(ExpedienteObra.titulo.ilike(f"%{query}%"))
            if tenant_id is not None:
                sql = sql.where(ExpedienteObra.tenant_id == tenant_id)
            result = await self.db.execute(sql.limit(limit))
            sugerencias = [r[0] for r in result.all() if r[0]]

        return sugerencias
