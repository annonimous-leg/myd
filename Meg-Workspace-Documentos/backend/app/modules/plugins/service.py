# Copyright © 2026 Cristian Rodriguez
# All rights reserved.
# Unauthorized copying, modification, distribution, or use is prohibited
# without prior written permission.

"""
PluginsService - Sistema de plugins extensible.
Registro, carga y ejecución de plugins de terceros.
"""
from typing import Dict, Any, Optional, List, Callable
from enum import Enum
from datetime import datetime


class PluginType(str, Enum):
    """Tipos de plugins soportados."""
    REPORTE = "REPORTE"
    VALIDACION = "VALIDACION"
    EXPORTACION = "EXPORTACION"
    IMPORTACION = "IMPORTACION"
    NOTIFICACION = "NOTIFICACION"
    WIDGET = "WIDGET"


class PluginStatus(str, Enum):
    """Estados de un plugin."""
    REGISTRADO = "REGISTRADO"
    ACTIVO = "ACTIVO"
    INACTIVO = "INACTIVO"
    ERROR = "ERROR"


class Plugin:
    """Definición de un plugin."""

    def __init__(
        self,
        id: str,
        nombre: str,
        version: str,
        tipo: PluginType,
        autor: str,
        descripcion: str,
        entry_point: str,
        config: Optional[Dict[str, Any]] = None,
    ):
        self.id = id
        self.nombre = nombre
        self.version = version
        self.tipo = tipo
        self.autor = autor
        self.descripcion = descripcion
        self.entry_point = entry_point
        self.config = config or {}
        self.estado = PluginStatus.REGISTRADO
        self.fecha_registro = datetime.utcnow().isoformat()
        self.ultima_ejecucion = None
        self.hooks: Dict[str, List[Callable]] = {}

    def registrar_hook(self, evento: str, handler: Callable) -> None:
        """Registra un handler para un evento."""
        if evento not in self.hooks:
            self.hooks[evento] = []
        self.hooks[evento].append(handler)

    def ejecutar_hooks(self, evento: str, contexto: Dict[str, Any]) -> List[Any]:
        """Ejecuta todos los hooks registrados para un evento."""
        resultados = []
        for handler in self.hooks.get(evento, []):
            try:
                resultado = handler(contexto)
                resultados.append(resultado)
            except Exception as e:
                resultados.append({"error": str(e)})
        return resultados


class PluginsService:
    """Servicio de gestión de plugins."""

    def __init__(self):
        self._plugins: Dict[str, Plugin] = {}

    def registrar(self, plugin: Plugin) -> None:
        """Registra un nuevo plugin."""
        self._plugins[plugin.id] = plugin

    def obtener(self, plugin_id: str) -> Optional[Plugin]:
        """Obtiene un plugin por ID."""
        return self._plugins.get(plugin_id)

    def listar(self, tipo: Optional[PluginType] = None) -> List[Dict[str, Any]]:
        """Lista plugins, opcionalmente filtrados por tipo."""
        plugins = self._plugins.values()
        if tipo:
            plugins = [p for p in plugins if p.tipo == tipo]

        return [
            {
                "id": p.id,
                "nombre": p.nombre,
                "version": p.version,
                "tipo": p.tipo.value,
                "autor": p.autor,
                "estado": p.estado.value,
                "fecha_registro": p.fecha_registro,
            }
            for p in plugins
        ]

    def activar(self, plugin_id: str) -> bool:
        """Activa un plugin."""
        if plugin_id in self._plugins:
            self._plugins[plugin_id].estado = PluginStatus.ACTIVO
            return True
        return False

    def desactivar(self, plugin_id: str) -> bool:
        """Desactiva un plugin."""
        if plugin_id in self._plugins:
            self._plugins[plugin_id].estado = PluginStatus.INACTIVO
            return True
        return False

    def ejecutar_plugin(self, plugin_id: str, contexto: Dict[str, Any]) -> Dict[str, Any]:
        """Ejecuta un plugin con el contexto dado."""
        plugin = self._plugins.get(plugin_id)
        if not plugin:
            return {"error": "Plugin no encontrado"}

        if plugin.estado != PluginStatus.ACTIVO:
            return {"error": f"Plugin no está activo (estado: {plugin.estado.value})"}

        plugin.ultima_ejecucion = datetime.utcnow().isoformat()

        # Ejecutar hooks del tipo "ejecutar"
        resultados = plugin.ejecutar_hooks("ejecutar", contexto)

        return {
            "plugin_id": plugin_id,
            "nombre": plugin.nombre,
            "resultados": resultados,
            "timestamp": plugin.ultima_ejecucion,
        }


# Instancia singleton
plugins_service = PluginsService()
