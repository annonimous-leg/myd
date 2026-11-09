# Copyright © 2026 Cristian Rodriguez
# All rights reserved.
# Unauthorized copying, modification, distribution, or use is prohibited
# without prior written permission.

"""
DocumentoModuleService - Servicio de gestión documental avanzada.
Versionado, clasificación, búsqueda y control de documentos del CDE.
"""
from typing import List, Optional, Dict, Any
from uuid import UUID
from datetime import datetime

from sqlalchemy import select, and_, or_, desc, func
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.documento import DocumentoCDE, EstadoDocumento, TipoDocumento
from app.models.audit_ledger import AuditLedger, TipoAccion
from app.services.base import BaseService
from app.services.documento_service import DocumentoService
from app.core.errors import MegalodonException, ErrorCode


class DocumentoModuleService:
    """Servicio de gestión documental del módulo CDE.

    Envuelve y extiende DocumentoService con funcionalidades de:
    - Clasificación automática
    - Detección de duplicados
    - Búsqueda avanzada
    - Control de versiones
    """

    def __init__(self, db: AsyncSession):
        self.db = db
        self.base_service = DocumentoService(db)

    async def clasificar_documento(
        self,
        documento_id: UUID,
        tipo_sugerido: Optional[TipoDocumento] = None,
        confianza: Optional[float] = None,
    ) -> DocumentoCDE:
        """Clasifica un documento por tipo usando OCR + reglas."""
        doc = await self.base_service.get(documento_id)
        if not doc:
            raise MegalodonException(
                ErrorCode.DOCUMENTO_NO_ENCONTRADO,
                f"Documento {documento_id} no encontrado",
            )

        # Si se proporciona tipo sugerido, aplicarlo
        if tipo_sugerido:
            doc.tipo = tipo_sugerido
            doc.metadatos = {
                **(doc.metadatos or {}),
                "clasificacion_automatica": True,
                "confianza_clasificacion": confianza or 0.85,
                "fecha_clasificacion": datetime.utcnow().isoformat(),
            }
            await self.db.commit()
            await self.db.refresh(doc)

        return doc

    async def detectar_duplicados(
        self,
        expediente_id: UUID,
        *,
        umbral_similitud: float = 0.95,
    ) -> List[Dict[str, Any]]:
        """Detecta documentos duplicados o muy similares en un expediente.

        Compara por hash de contenido y metadatos.
        """
        result = await self.db.execute(
            select(DocumentoCDE)
            .where(DocumentoCDE.expediente_id == expediente_id)
            .where(DocumentoCDE.estado != EstadoDocumento.OBSOLETO)
        )
        documentos = result.scalars().all()

        duplicados = []
        vistos = {}

        for doc in documentos:
            # Clave de comparación: hash + nombre normalizado
            clave = f"{doc.hash_sha256 or ''}_{(doc.nombre or '').lower().strip()}"
            if clave in vistos and clave:
                duplicados.append({
                    "documento_original_id": str(vistos[clave]),
                    "documento_duplicado_id": str(doc.id),
                    "nombre": doc.nombre,
                    "tipo": doc.tipo.value if hasattr(doc.tipo, 'value') else str(doc.tipo),
                    "similitud": 1.0 if doc.hash_sha256 else 0.9,
                })
            else:
                vistos[clave] = doc.id

        return duplicados

    async def busqueda_avanzada(
        self,
        *,
        query: Optional[str] = None,
        tipo: Optional[TipoDocumento] = None,
        estado: Optional[EstadoDocumento] = None,
        expediente_id: Optional[UUID] = None,
        tenant_id: Optional[UUID] = None,
        fecha_inicio: Optional[datetime] = None,
        fecha_fin: Optional[datetime] = None,
        tags: Optional[List[str]] = None,
        skip: int = 0,
        limit: int = 100,
    ) -> Dict[str, Any]:
        """Búsqueda avanzada de documentos con múltiples filtros."""
        # BUG ORIGINAL: esta búsqueda no tenía NINGÚN filtro de tenant --
        # a diferencia de search.py y ExpedienteModuleService.buscar_expedientes
        # (que sí tenían el parámetro y solo les faltaba que el router lo
        # pasara), aquí el parámetro ni existía. Se agrega igual que en los
        # otros dos, y el router lo pasa siempre con current_user.tenant_id.
        sql_query = select(DocumentoCDE)
        filters = []

        if tenant_id:
            filters.append(DocumentoCDE.tenant_id == tenant_id)

        if query:
            # Búsqueda por nombre y descripción (usando ILIKE para case-insensitive)
            filters.append(
                or_(
                    DocumentoCDE.nombre.ilike(f"%{query}%"),
                    DocumentoCDE.descripcion.ilike(f"%{query}%"),
                )
            )

        if tipo:
            filters.append(DocumentoCDE.tipo == tipo)

        if estado:
            filters.append(DocumentoCDE.estado == estado)

        if expediente_id:
            filters.append(DocumentoCDE.expediente_id == expediente_id)

        if fecha_inicio:
            filters.append(DocumentoCDE.created_at >= fecha_inicio)

        if fecha_fin:
            filters.append(DocumentoCDE.created_at <= fecha_fin)

        if tags:
            # Buscar documentos que contengan TODOS los tags
            for tag in tags:
                filters.append(
                    DocumentoCDE.metadatos.contains({"tags": [tag]})
                )

        if filters:
            sql_query = sql_query.where(and_(*filters))

        # Count total
        count_result = await self.db.execute(
            select(func.count(DocumentoCDE.id)).where(and_(*filters) if filters else True)
        )
        total = count_result.scalar()

        # Paginated results
        sql_query = sql_query.order_by(desc(DocumentoCDE.created_at)).offset(skip).limit(limit)
        result = await self.db.execute(sql_query)
        documentos = result.scalars().all()

        return {
            "total": total,
            "skip": skip,
            "limit": limit,
            "resultados": [
                {
                    "id": str(d.id),
                    "nombre": d.nombre,
                    "tipo": d.tipo.value if hasattr(d.tipo, 'value') else str(d.tipo),
                    "estado": d.estado.value if hasattr(d.estado, 'value') else str(d.estado),
                    "version": d.version,
                    "expediente_id": str(d.expediente_id) if d.expediente_id else None,
                    "creado_por_id": str(d.creado_por_id) if d.creado_por_id else None,
                    "created_at": d.created_at.isoformat() if d.created_at else None,
                    "metadatos": d.metadatos,
                }
                for d in documentos
            ],
        }

    async def crear_version_documento(
        self,
        documento_id: UUID,
        *,
        nuevo_contenido_url: str,
        cambios_descripcion: Optional[str] = None,
        creado_por_id: Optional[UUID] = None,
    ) -> DocumentoCDE:
        """Crea una nueva versión de un documento existente.

        El documento original se archiva y se crea uno nuevo con versión incrementada.
        """
        doc = await self.base_service.get(documento_id)
        if not doc:
            raise MegalodonException(
                ErrorCode.DOCUMENTO_NO_ENCONTRADO,
                f"Documento {documento_id} no encontrado",
            )

        # Archivar versión anterior
        doc.estado = EstadoDocumento.ARCHIVADO
        doc.metadatos = {
            **(doc.metadatos or {}),
            "archivado_por_version": True,
            "fecha_archivado": datetime.utcnow().isoformat(),
        }

        # Crear nueva versión
        nueva_version = await self.base_service.create({
            "nombre": doc.nombre,
            "descripcion": doc.descripcion,
            "tipo": doc.tipo,
            "estado": EstadoDocumento.BORRADOR,
            "version": (doc.version or 1) + 1,
            "contenido_url": nuevo_contenido_url,
            "expediente_id": doc.expediente_id,
            "contrato_id": doc.contrato_id,
            "metadatos": {
                "version_anterior_id": str(doc.id),
                "cambios": cambios_descripcion,
                "tags": doc.metadatos.get("tags", []) if doc.metadatos else [],
            },
        }, creado_por_id=creado_por_id)

        await self.db.commit()
        return nueva_version

    async def obtener_arbol_versiones(
        self,
        documento_id: UUID,
    ) -> List[Dict[str, Any]]:
        """Obtiene el árbol de versiones de un documento."""
        # Primero encontrar la raíz
        doc = await self.base_service.get(documento_id)
        if not doc:
            return []

        # Buscar todas las versiones del mismo nombre en el mismo expediente
        result = await self.db.execute(
            select(DocumentoCDE)
            .where(DocumentoCDE.expediente_id == doc.expediente_id)
            .where(DocumentoCDE.nombre == doc.nombre)
            .order_by(DocumentoCDE.version)
        )
        versiones = result.scalars().all()

        return [
            {
                "id": str(v.id),
                "version": v.version,
                "estado": v.estado.value if hasattr(v.estado, 'value') else str(v.estado),
                "contenido_url": v.contenido_url,
                "created_at": v.created_at.isoformat() if v.created_at else None,
                "creado_por_id": str(v.creado_por_id) if v.creado_por_id else None,
            }
            for v in versiones
        ]

    async def estadisticas_documentales(
        self,
        expediente_id: Optional[UUID] = None,
        tenant_id: Optional[UUID] = None,
    ) -> Dict[str, Any]:
        """Estadísticas del repositorio documental.

        INVARIANTE: Si tenant_id se proporciona, TODOS los documentos se filtran
        por tenant via join con ExpedienteObra.
        """
        from app.models.expediente import ExpedienteObra
        query = select(DocumentoCDE).join(ExpedienteObra, DocumentoCDE.expediente_id == ExpedienteObra.id)
        filters = [ExpedienteObra.tenant_id == tenant_id] if tenant_id else []

        if expediente_id:
            filters.append(DocumentoCDE.expediente_id == expediente_id)

        if filters:
            query = query.where(and_(*filters))

        result = await self.db.execute(query)
        documentos = result.scalars().all()

        por_tipo = {}
        por_estado = {}
        total_versiones = 0

        for d in documentos:
            tipo_key = d.tipo.value if hasattr(d.tipo, 'value') else str(d.tipo)
            estado_key = d.estado.value if hasattr(d.estado, 'value') else str(d.estado)
            por_tipo[tipo_key] = por_tipo.get(tipo_key, 0) + 1
            por_estado[estado_key] = por_estado.get(estado_key, 0) + 1
            total_versiones += d.version or 1

        return {
            "total_documentos": len(documentos),
            "total_versiones": total_versiones,
            "por_tipo": por_tipo,
            "por_estado": por_estado,
            "promedio_versiones": round(total_versiones / len(documentos), 2) if documentos else 0,
        }
