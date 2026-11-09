# Copyright © 2026 Cristian Rodriguez
# All rights reserved.
# Unauthorized copying, modification, distribution, or use is prohibited
# without prior written permission.

"""
Sistema de errores de Megalodon.
Jerarquía de excepciones con códigos normativos.
"""
import functools
from typing import Any, Awaitable, Callable, Dict, Optional, TypeVar
from enum import Enum

import structlog
from fastapi import HTTPException
from pydantic import ValidationError
from sqlalchemy.exc import IntegrityError, NoResultFound

logger = structlog.get_logger()

_T = TypeVar("_T")


class Severity(str, Enum):
    DEBUG = "DEBUG"
    INFO = "INFO"
    WARNING = "WARNING"
    ERROR = "ERROR"
    CRITICAL = "CRITICAL"


class ErrorCode(str, Enum):
    # Códigos 0-99: Genéricos / transversales
    # NOT_FOUND agregado 2026-09-01: se usaba en ErrorCode.NOT_FOUND desde
    # compliance_service.py, contrato_service.py, licitacion_service.py,
    # catalogo_apu_service.py y catalogo_conceptos_service.py (al menos 5
    # archivos) sin existir en este enum -- cada "no encontrado" en esas
    # rutas producía AttributeError en tiempo de ejecución (500) en vez del
    # 404 que el código claramente pretendía devolver. No es parte de los
    # hallazgos F-01..F-08 de la auditoría; se encontró al tocar este mismo
    # archivo para F-04.
    NOT_FOUND = "GEN-0000"
    # BAD_REQUEST agregado 2026-09-08: mismo problema que NOT_FOUND, esta
    # vez con ErrorCode.BAD_REQUEST -- usado en licitacion_service.py (7
    # veces, incluida TODA la validación de transición de estado de
    # licitación: "no se puede editar en este estado", "transición no
    # permitida", "requiere folio y bases", "debe registrar junta de
    # aclaraciones", etc.), contrato_service.py y
    # procurement/service.py, sin existir en este enum. Cada una de esas
    # validaciones de negocio -- justo las que protegen la integridad del
    # flujo de licitación -- producía AttributeError (500) en vez del 400
    # que el código pretendía devolver. Encontrado al conectar
    # MotorEvaluacion a licitacion_service.py.
    BAD_REQUEST = "GEN-0001"
    CONFLICT = "GEN-0002"
    PERMISO_DENEGADO = "GEN-0003"

    # Códigos 1000-1999: Normativos
    NORMATIVO_GENERICO = "NOR-1000"
    LOPSRM_VIOLATION = "NOR-1001"
    LAASSP_VIOLATION = "NOR-1002"
    LFT_VIOLATION = "NOR-1003"
    CFF_VIOLATION = "NOR-1004"

    # Códigos 2000-2999: Firma y Criptografía / Autenticación
    FIRMA_INVALIDA = "FIR-2000"
    CERTIFICADO_EXPIRADO = "FIR-2001"
    FIEL_NO_VALIDA = "FIR-2002"
    AUTH_ERROR = "AUT-2000"
    TOKEN_REVOCADO = "AUT-2001"
    REFRESH_REUSE_DETECTED = "AUT-2002"
    SECURITY_CONTROL_UNAVAILABLE = "AUT-2003"
    INVITACION_INVALIDA = "AUT-2004"
    INVITACION_EXPIRADA = "AUT-2005"
    ROL_NO_PERMITIDO = "AUT-2006"
    TAREA_NO_ENCONTRADA = "AUT-2007"

    # Códigos 3000-3999: Interoperabilidad
    INTEROP_ERROR = "INT-3000"
    PDN_NO_DISPONIBLE = "INT-3001"
    COMPRANET_ERROR = "INT-3002"

    # Códigos 4000-4999: Costos y Presupuestos
    COSTEO_ERROR = "CST-4000"
    FSR_INVALIDO = "CST-4001"
    MAQUINARIA_COSTO_INVALIDO = "CST-4002"
    SOBRECOSTO_FUERA_RANGO = "CST-4003"
    PRESUPUESTO_ERROR = "CST-4004"

    # Códigos 5000-5999: Jurídico
    JURIDICO_GENERICO = "JUR-5000"
    PROCEDIMIENTO_NO_DETERMINADO = "JUR-5001"
    REQUISITO_FALTANTE = "JUR-5002"

    # Códigos 6000-6999: BIM
    BIM_ERROR = "BIM-6000"
    IFC_INVALIDO = "BIM-6001"
    CUANTIFICACION_ERROR = "BIM-6002"
    CLASH_DETECTION_ERROR = "BIM-6003"

    # Códigos 7000-7999: Documentos y Archivos
    ARCHIVO_ERROR = "ARC-7000"
    DOCUMENTO_NO_ENCONTRADO = "ARC-7001"

    # Códigos 8000-8999: Monte Carlo / Riesgo
    MONTECARLO_ERROR = "RSC-8000"
    PARAMETRO_INVALIDO = "RSC-8001"

    # Códigos 9000-9999: Validación Determinista
    VALIDACION_FALLIDA = "VAL-9000"
    SAT_OPINION_NEGATIVA = "VAL-9001"
    IMSS_OPINION_NEGATIVA = "VAL-9002"
    INFONAVIT_OPINION_NEGATIVA = "VAL-9003"

    # Códigos 10000-10999: Topografía
    TOPOGRAFIA_ERROR = "TOP-10000"
    PUNTOS_INSUFICIENTES = "TOP-10001"
    SUPERFICIE_NO_ENCONTRADA = "TOP-10002"


class MegalodonException(Exception):
    """Excepción base del sistema."""

    def __init__(
        self,
        code: ErrorCode,
        message: str,
        status_code: int = 400,
        details: Optional[Dict[str, Any]] = None,
    ):
        self.code = code
        self.message = message
        self.status_code = status_code
        self.details = details or {}
        super().__init__(message)


class NormativoException(MegalodonException):
    """Violación normativa."""
    def __init__(self, code: ErrorCode, message: str, details: Optional[Dict] = None):
        super().__init__(code, message, 422, details)


class FirmaException(MegalodonException):
    """Error en firma electrónica."""
    def __init__(self, message: str, details: Optional[Dict] = None):
        super().__init__(ErrorCode.FIRMA_INVALIDA, message, 401, details)


class AuthException(MegalodonException):
    """Error base de autenticación / protección de sesión."""
    def __init__(self, code: ErrorCode, message: str, status_code: int = 401, details: Optional[Dict] = None):
        super().__init__(code, message, status_code, details)


class TokenRevocadoException(AuthException):
    """El token ya fue revocado y no debe aceptarse."""
    def __init__(self, message: str = "Token revocado", details: Optional[Dict] = None):
        super().__init__(ErrorCode.TOKEN_REVOCADO, message, 401, details)


class RefreshReuseDetectedException(AuthException):
    """Se detectó reuso de un refresh token ya rotado."""
    def __init__(self, message: str = "Reuso de refresh token detectado", details: Optional[Dict] = None):
        super().__init__(ErrorCode.REFRESH_REUSE_DETECTED, message, 401, details)


class TareaNoEncontradaException(AuthException):
    """El task_id consultado no existe o no pertenece al tenant del
    usuario autenticado. Se responde 404 (no 403) a propósito: no hay
    que confirmarle a un usuario de otro tenant que el task_id que
    adivinó/capturó SÍ existe, solo que no puede accederse."""
    def __init__(self, message: str = "La tarea solicitada no existe", details: Optional[Dict] = None):
        super().__init__(ErrorCode.TAREA_NO_ENCONTRADA, message, 404, details)


class SecurityControlUnavailableException(MegalodonException):
    """La protección de seguridad no pudo verificarse/aplicarse."""
    def __init__(self, message: str, details: Optional[Dict] = None):
        super().__init__(ErrorCode.SECURITY_CONTROL_UNAVAILABLE, message, 503, details)


class ValidacionException(MegalodonException):
    """Error en validación determinista."""
    def __init__(self, code: ErrorCode, message: str, details: Optional[Dict] = None):
        super().__init__(code, message, 422, details)


class BIMException(MegalodonException):
    """Error en procesamiento BIM."""
    def __init__(self, message: str, details: Optional[Dict] = None):
        super().__init__(ErrorCode.BIM_ERROR, message, 400, details)


class InteropException(MegalodonException):
    """Error en interoperabilidad."""
    def __init__(self, message: str, details: Optional[Dict] = None):
        super().__init__(ErrorCode.INTEROP_ERROR, message, 502, details)


# ---------------------------------------------------------------------------
# handle_megalodon_errors
#
# BUG ORIGINAL: siete routers de app/api/v1 (compliance, catalogo_conceptos,
# contratos, legal_consultor, catalogo_apu, licitaciones_obra, licitaciones)
# hacían `from app.core.errors import handle_megalodon_errors` y lo usaban
# como decorador (@handle_megalodon_errors) directo bajo cada @router.*, pero
# la función nunca existía en este módulo. Eso es un ImportError en tiempo de
# carga de esos siete archivos, y como app/api/v1/router.py los importa a
# todos en un único `from app.api.v1 import (...)`, el fallo se propaga y
# tumba el arranque completo del backend (main.py -> router.py -> el primer
# router roto). Se restaura aquí con lógica real, no un passthrough vacío.
#
# Responsabilidad del decorador (se coloca inmediatamente bajo la ruta):
#   1. Deja pasar sin tocar las excepciones que ya vienen correctamente
#      tipadas (MegalodonException, HTTPException): ya tienen código y
#      status_code adecuados y el manejador global de main.py las formatea.
#   2. Traduce errores comunes de datos/validación (pydantic ValidationError,
#      IntegrityError de SQLAlchemy, NoResultFound) a MegalodonException con
#      el status_code HTTP correcto (422/409/404), en vez de dejar que el
#      handler genérico de main.py los convierta a un 500 sin contexto.
#   3. Registra en el log estructurado el nombre del endpoint donde ocurrió
#      el error (el handler global sólo conoce la ruta HTTP, no la función),
#      lo que ayuda a diagnosticar sin exponer detalles internos al cliente.
#   4. Cualquier excepción realmente inesperada se re-empaqueta como
#      MegalodonException genérica (500) para que el sobre JSON de error sea
#      siempre consistente en toda la API.
# ---------------------------------------------------------------------------

def handle_megalodon_errors(
    func: Callable[..., Awaitable[_T]],
) -> Callable[..., Awaitable[_T]]:
    """Decorador de manejo de errores para endpoints async de FastAPI."""

    @functools.wraps(func)
    async def wrapper(*args: Any, **kwargs: Any) -> _T:
        endpoint = getattr(func, "__name__", "endpoint_desconocido")
        try:
            return await func(*args, **kwargs)
        except (MegalodonException, HTTPException):
            # Ya vienen con código/status_code correctos: no se reinterpretan.
            raise
        except ValidationError as exc:
            logger.warning("validacion_fallida", endpoint=endpoint, error=str(exc))
            raise MegalodonException(
                code=ErrorCode.VALIDACION_FALLIDA,
                message="Los datos proporcionados no son válidos.",
                status_code=422,
                details={"errores": exc.errors()},
            ) from exc
        except IntegrityError as exc:
            logger.warning("error_integridad_datos", endpoint=endpoint, error=str(exc))
            raise MegalodonException(
                code=ErrorCode.VALIDACION_FALLIDA,
                message=(
                    "La operación viola una restricción de integridad de "
                    "datos (posible duplicado o referencia inválida)."
                ),
                status_code=409,
            ) from exc
        except NoResultFound as exc:
            logger.info("recurso_no_encontrado", endpoint=endpoint)
            raise MegalodonException(
                code=ErrorCode.DOCUMENTO_NO_ENCONTRADO,
                message="El recurso solicitado no existe.",
                status_code=404,
            ) from exc
        except (KeyError, ValueError) as exc:
            logger.warning("solicitud_invalida", endpoint=endpoint, error=str(exc))
            raise MegalodonException(
                code=ErrorCode.NORMATIVO_GENERICO,
                message=f"Solicitud inválida: {exc}",
                status_code=400,
            ) from exc
        except Exception as exc:  # noqa: BLE001 - último recurso intencional
            logger.error(
                "error_no_manejado_en_endpoint",
                endpoint=endpoint,
                error=str(exc),
                exc_info=True,
            )
            raise MegalodonException(
                code=ErrorCode.NORMATIVO_GENERICO,
                message="Error interno del servidor.",
                status_code=500,
            ) from exc

    return wrapper
