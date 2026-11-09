# Copyright © 2026 Cristian Rodriguez
# All rights reserved.
# Unauthorized copying, modification, distribution, or use is prohibited
# without prior written permission.

"""
LegacyService - Adaptadores para compatibilidad con sistemas anteriores.
Mapeo de modelos, transformación de payloads y normalización de estados.
"""
from typing import Dict, Any, Optional, List
from uuid import UUID

from app.core.errors import MegalodonException, ErrorCode


class ModelAdapter:
    """Adaptador de modelos legacy a modelo actual."""

    # Mapeo de nombres de campos legacy → actuales
    FIELD_MAPPINGS = {
        "num_expediente": "identificador",
        "titulo_obra": "titulo",
        "monto_total": "monto_contrato",
        "dias_ejecucion": "plazo_dias",
        "dependencia": "organo",
        "area_requirente": "unidad_administrativa",
        "fecha_inicio": "fecha_inicio_esperada",
        "fecha_termino": "fecha_fin_esperada",
    }

    # Mapeo de estados legacy → estados actuales
    STATUS_MAPPINGS = {
        "ACTIVO": "EN_EJECUCION",
        "CERRADO": "FINALIZADO",
        "CANCELADO": "CANCELADO",
        "PENDIENTE": "BORRADOR",
        "EN_PROCESO": "EN_REVISION",
        "APROBADO": "APROBADO",
        "RECHAZADO": "RECHAZADO",
    }

    @classmethod
    def transform_payload(cls, payload: Dict[str, Any]) -> Dict[str, Any]:
        """Transforma un payload legacy al formato actual."""
        transformed = {}
        for old_key, value in payload.items():
            new_key = cls.FIELD_MAPPINGS.get(old_key, old_key)
            transformed[new_key] = value
        return transformed

    @classmethod
    def normalize_status(cls, legacy_status: str) -> str:
        """Normaliza un estado legacy al estado canónico actual."""
        return cls.STATUS_MAPPINGS.get(legacy_status.upper(), legacy_status)

    @classmethod
    def denormalize_status(cls, current_status: str) -> str:
        """Convierte un estado actual al formato legacy."""
        reverse_map = {v: k for k, v in cls.STATUS_MAPPINGS.items()}
        return reverse_map.get(current_status, current_status)


class EndpointAdapter:
    """Adaptador de endpoints legacy a endpoints actuales."""

    # Mapeo de rutas legacy → actuales
    ROUTE_MAPPINGS = {
        "/api/expedientes/legacy": "/api/v1/expedientes",
        "/api/presupuestos/legacy": "/api/v1/presupuestos",
        "/api/documentos/legacy": "/api/v1/documentos",
        "/api/contratos/legacy": "/api/v1/contratos",
    }

    @classmethod
    def map_route(cls, legacy_route: str) -> str:
        """Mapea una ruta legacy a la ruta actual."""
        return cls.ROUTE_MAPPINGS.get(legacy_route, legacy_route)


class DataMigrationHelper:
    """Helper para migración de datos desde sistemas legacy."""

    @staticmethod
    def validate_legacy_data(data: Dict[str, Any], required_fields: List[str]) -> List[str]:
        """Valida que los datos legacy tengan los campos requeridos."""
        missing = []
        for field in required_fields:
            if field not in data or data[field] is None:
                missing.append(field)
        return missing

    @staticmethod
    def generate_migration_report(
        total_records: int,
        migrated: int,
        errors: List[Dict[str, Any]],
    ) -> Dict[str, Any]:
        """Genera un reporte de migración."""
        return {
            "total_registros": total_records,
            "migrados": migrated,
            "errores": len(errors),
            "tasa_exito": (migrated / total_records * 100) if total_records > 0 else 0,
            "detalle_errores": errors[:100],  # Limitar a 100 errores
        }
