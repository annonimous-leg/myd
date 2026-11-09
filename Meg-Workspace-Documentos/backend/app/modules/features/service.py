# Copyright © 2026 Cristian Rodriguez
# All rights reserved.
# Unauthorized copying, modification, distribution, or use is prohibited
# without prior written permission.

"""
FeaturesService - Feature flags y toggles del sistema.
Control de funcionalidades por tenant, usuario y entorno.
"""
from typing import Dict, Any, Optional, List
from enum import Enum


class FeatureScope(str, Enum):
    """Ámbito de aplicación de un feature flag."""
    GLOBAL = "GLOBAL"
    TENANT = "TENANT"
    USER = "USER"
    ENTORNO = "ENTORNO"


class FeatureFlag:
    """Definición de un feature flag."""

    def __init__(
        self,
        nombre: str,
        descripcion: str,
        activo: bool = False,
        scope: FeatureScope = FeatureScope.GLOBAL,
        tenant_ids: Optional[List[str]] = None,
        user_ids: Optional[List[str]] = None,
        entornos: Optional[List[str]] = None,
    ):
        self.nombre = nombre
        self.descripcion = descripcion
        self.activo = activo
        self.scope = scope
        self.tenant_ids = tenant_ids or []
        self.user_ids = user_ids or []
        self.entornos = entornos or []


class FeaturesService:
    """Servicio de gestión de feature flags."""

    def __init__(self):
        self._flags: Dict[str, FeatureFlag] = {}
        self._inicializar_flags_default()

    def _inicializar_flags_default(self) -> None:
        """Inicializa los feature flags por defecto del sistema."""
        defaults = [
            FeatureFlag("bim_avanzado", "Funcionalidades avanzadas de BIM", False),
            FeatureFlag("montecarlo_paralelo", "Simulación Monte Carlo en paralelo", True),
            FeatureFlag("ocr_batch", "Procesamiento OCR por lotes", False),
            FeatureFlag("busqueda_semantica", "Búsqueda semántica con embeddings", False),
            FeatureFlag("portal_transparencia", "Portal público de transparencia", True),
            FeatureFlag("exportacion_excel", "Exportación a Excel avanzada", True),
            FeatureFlag("dashboard_realtime", "Dashboard en tiempo real vía WebSocket", True),
            FeatureFlag("firma_biometrica", "Firma con validación biométrica", False),
            FeatureFlag("ia_asistente", "Asistente de IA para consistencia", False),
            FeatureFlag("multi_tenant", "Soporte multi-tenant completo", True),
        ]
        for f in defaults:
            self._flags[f.nombre] = f

    def esta_activo(
        self,
        nombre: str,
        *,
        tenant_id: Optional[str] = None,
        user_id: Optional[str] = None,
        entorno: Optional[str] = None,
    ) -> bool:
        """Verifica si un feature flag está activo para el contexto dado."""
        flag = self._flags.get(nombre)
        if not flag:
            return False

        if flag.scope == FeatureScope.GLOBAL:
            return flag.activo

        if flag.scope == FeatureScope.TENANT and tenant_id:
            return flag.activo and tenant_id in flag.tenant_ids

        if flag.scope == FeatureScope.USER and user_id:
            return flag.activo and user_id in flag.user_ids

        if flag.scope == FeatureScope.ENTORNO and entorno:
            return flag.activo and entorno in flag.entornos

        return flag.activo

    def activar(self, nombre: str) -> None:
        """Activa un feature flag."""
        if nombre in self._flags:
            self._flags[nombre].activo = True

    def desactivar(self, nombre: str) -> None:
        """Desactiva un feature flag."""
        if nombre in self._flags:
            self._flags[nombre].activo = False

    def listar_flags(self) -> List[Dict[str, Any]]:
        """Lista todos los feature flags."""
        return [
            {
                "nombre": f.nombre,
                "descripcion": f.descripcion,
                "activo": f.activo,
                "scope": f.scope.value,
            }
            for f in self._flags.values()
        ]

    def configurar_flag(
        self,
        nombre: str,
        activo: bool,
        scope: Optional[FeatureScope] = None,
        tenant_ids: Optional[List[str]] = None,
        user_ids: Optional[List[str]] = None,
    ) -> None:
        """Configura un feature flag existente."""
        if nombre in self._flags:
            self._flags[nombre].activo = activo
            if scope:
                self._flags[nombre].scope = scope
            if tenant_ids is not None:
                self._flags[nombre].tenant_ids = tenant_ids
            if user_ids is not None:
                self._flags[nombre].user_ids = user_ids


# Instancia singleton
features_service = FeaturesService()
