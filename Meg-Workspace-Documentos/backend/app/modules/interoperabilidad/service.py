# Copyright © 2026 Cristian Rodriguez
# All rights reserved.
# Unauthorized copying, modification, distribution, or use is prohibited
# without prior written permission.

"""
InteroperabilidadService - Conectores genéricos para integraciones.
Framework extensible para conectar con sistemas externos.
"""
from typing import Dict, Any, Optional, List
from enum import Enum
from datetime import datetime

from app.core.errors import MegalodonException, ErrorCode


class TipoConector(str, Enum):
    """Tipos de conectores soportados."""
    REST = "REST"
    SOAP = "SOAP"
    GRAPHQL = "GRAPHQL"
    WEBHOOK = "WEBHOOK"
    SFTP = "SFTP"
    DATABASE = "DATABASE"


class EstadoConector(str, Enum):
    """Estados de un conector."""
    ACTIVO = "ACTIVO"
    INACTIVO = "INACTIVO"
    ERROR = "ERROR"
    DEPRECADO = "DEPRECADO"


class ConectorConfig:
    """Configuración de un conector."""

    def __init__(
        self,
        nombre: str,
        tipo: TipoConector,
        base_url: str,
        headers: Optional[Dict[str, str]] = None,
        timeout: int = 30,
        retry_attempts: int = 3,
        auth_type: Optional[str] = None,
        auth_config: Optional[Dict[str, Any]] = None,
    ):
        self.nombre = nombre
        self.tipo = tipo
        self.base_url = base_url
        self.headers = headers or {}
        self.timeout = timeout
        self.retry_attempts = retry_attempts
        self.auth_type = auth_type
        self.auth_config = auth_config or {}
        self.estado = EstadoConector.ACTIVO
        self.ultima_verificacion = None
        self.ultimo_error = None


class InteroperabilidadService:
    """Servicio de gestión de conectores de interoperabilidad."""

    def __init__(self):
        self._conectores: Dict[str, ConectorConfig] = {}

    def registrar_conector(self, config: ConectorConfig) -> None:
        """Registra un nuevo conector."""
        self._conectores[config.nombre] = config

    def obtener_conector(self, nombre: str) -> Optional[ConectorConfig]:
        """Obtiene la configuración de un conector."""
        return self._conectores.get(nombre)

    def listar_conectores(self) -> List[Dict[str, Any]]:
        """Lista todos los conectores registrados."""
        return [
            {
                "nombre": c.nombre,
                "tipo": c.tipo.value,
                "base_url": c.base_url,
                "estado": c.estado.value,
                "ultima_verificacion": c.ultima_verificacion,
                "ultimo_error": c.ultimo_error,
            }
            for c in self._conectores.values()
        ]

    def actualizar_estado(
        self,
        nombre: str,
        estado: EstadoConector,
        error: Optional[str] = None,
    ) -> None:
        """Actualiza el estado de un conector."""
        if nombre in self._conectores:
            self._conectores[nombre].estado = estado
            self._conectores[nombre].ultima_verificacion = datetime.utcnow().isoformat()
            if error:
                self._conectores[nombre].ultimo_error = error

    def verificar_conector(self, nombre: str) -> Dict[str, Any]:
        """Verifica la disponibilidad de un conector.

        Esta implementación evita humo aleatorio: si no hay conector o la
        configuración es incompleta, devuelve el estado real de configuración.
        Si el conector está registrado y no está deprecado, se reporta como
        disponible solo a nivel de configuración; el probe activo real debe
        implementarse por adaptador concreto cuando exista endpoint/health
        específico.
        """
        conector = self._conectores.get(nombre)
        if not conector:
            return {"nombre": nombre, "disponible": False, "error": "Conector no registrado"}

        disponible = bool(conector.base_url.strip()) and conector.estado != EstadoConector.DEPRECADO
        if disponible:
            self.actualizar_estado(nombre, EstadoConector.ACTIVO)
        else:
            self.actualizar_estado(nombre, EstadoConector.ERROR, "Conector no configurado o deprecado")

        return {
            "nombre": nombre,
            "disponible": disponible,
            "estado": conector.estado.value,
            "tipo": conector.tipo.value,
            "ultima_verificacion": conector.ultima_verificacion,
            "health_check": "configuracional",
        }


# Instancia singleton del servicio
interoperabilidad_service = InteroperabilidadService()
