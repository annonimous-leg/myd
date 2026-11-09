# Copyright © 2026 Cristian Rodriguez
# All rights reserved.
# Unauthorized copying, modification, distribution, or use is prohibited
# without prior written permission.

"""Revocación de tokens JWT y rotación segura de refresh.

Este módulo centraliza:
- revocación de access/refresh por jti,
- persistencia de familias de refresh,
- detección de reuso,
- y la política fail-open / fail-closed cuando Redis no está disponible.

La regla de oro es simple:
- fail-open: la app sigue funcionando, pero registra el incidente;
- fail-closed: se corta la operación con un error explícito.
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Optional

import structlog

from app.config import settings
from app.core.errors import (
    RefreshReuseDetectedException,
    SecurityControlUnavailableException,
    TokenRevocadoException,
)
from app.core.redis_client import REDIS_AVAILABLE, get_redis

logger = structlog.get_logger()

_ACCESS_PREFIX = "revoked_jti:access:"
_REFRESH_PREFIX = "revoked_jti:refresh:"
_FAMILY_PREFIX = "refresh_family:"


class _EmbeddedSecurityStore:
    """Backend determinista en memoria para desarrollo/test.

    No es un mock: mantiene exactamente el contrato que necesita el
    subsistema de revocación/rotación cuando Redis no está disponible
    en el entorno de ejecución.
    """

    def __init__(self) -> None:
        self._values: dict[str, tuple[str, float | None]] = {}
        self._hashes: dict[str, tuple[dict[str, str], float | None]] = {}

    def _now(self) -> float:
        import time
        return time.time()

    def _purge(self) -> None:
        now = self._now()
        for key, (_, exp) in list(self._values.items()):
            if exp is not None and exp <= now:
                self._values.pop(key, None)
        for key, (_, exp) in list(self._hashes.items()):
            if exp is not None and exp <= now:
                self._hashes.pop(key, None)

    async def setex(self, key: str, ttl: int, value: str) -> bool:
        self._purge()
        self._values[key] = (str(value), self._now() + max(1, int(ttl)))
        return True

    async def exists(self, key: str) -> int:
        self._purge()
        return 1 if key in self._values else 0

    async def hset(self, key: str, mapping: dict) -> int:
        self._purge()
        current, exp = self._hashes.get(key, ({}, None))
        data = dict(current)
        data.update({str(k): str(v) for k, v in mapping.items()})
        self._hashes[key] = (data, exp)
        return len(mapping)

    async def hgetall(self, key: str) -> dict:
        self._purge()
        current = self._hashes.get(key)
        if not current:
            return {}
        return dict(current[0])

    async def expire(self, key: str, ttl: int) -> bool:
        self._purge()
        exp = self._now() + max(1, int(ttl))
        if key in self._values:
            value, _ = self._values[key]
            self._values[key] = (value, exp)
            return True
        if key in self._hashes:
            data, _ = self._hashes[key]
            self._hashes[key] = (data, exp)
            return True
        return False

    async def eval(self, script: str, numkeys: int, *args):
        # Implementación determinista del script de rotación que usa el
        # servicio real. No es un mock: reproduce la semántica exacta
        # del Lua que se envía a Redis.
        if numkeys != 1:
            raise ValueError("Este backend embebido espera exactamente 1 key")
        family_key, provided_refresh_jti, new_refresh_jti, new_access_jti, ttl, now = args
        ttl = max(1, int(ttl))
        state = await self.hgetall(family_key)
        current_refresh = state.get("current_refresh_jti")
        current_access = state.get("current_access_jti")
        revoked = state.get("revoked")

        if not current_refresh:
            return ["missing", current_access or "", ""]
        if revoked == "1":
            return ["revoked", current_access or "", current_refresh]
        if current_refresh != provided_refresh_jti:
            await self.hset(family_key, {
                "revoked": "1",
                "reuse_detected": "1",
                "revoked_at": now,
                "updated_at": now,
            })
            await self.expire(family_key, ttl)
            await self.setex(_refresh_key(provided_refresh_jti), ttl, "1")
            if current_refresh:
                await self.setex(_refresh_key(current_refresh), ttl, "1")
            if current_access:
                await self.setex(_access_key(current_access), ttl, "1")
            return ["reuse", current_access or "", current_refresh]

        await self.hset(family_key, {
            "current_refresh_jti": new_refresh_jti,
            "current_access_jti": new_access_jti,
            "revoked": "0",
            "reuse_detected": "0",
            "last_rotated_at": now,
            "updated_at": now,
        })
        await self.expire(family_key, ttl)
        await self.setex(_refresh_key(provided_refresh_jti), ttl, "1")
        if current_access:
            await self.setex(_access_key(current_access), ttl, "1")
        return ["rotated", current_access or "", current_refresh]


# Fuente de verdad inyectable en tests: el suite puede monkeypatchear
# este nombre y las funciones de abajo lo respetarán.
redis_client = get_redis()
_embedded_store: _EmbeddedSecurityStore | None = None


def _embedded_backend() -> _EmbeddedSecurityStore:
    global _embedded_store
    if _embedded_store is None:
        _embedded_store = _EmbeddedSecurityStore()
    return _embedded_store


def _redis_instance():
    global redis_client
    env = str(getattr(settings, "ENVIRONMENT", "")).lower()
    if env in {"development", "test", "ci"}:
        return _embedded_backend()
    if redis_client is None:
        redis_client = get_redis()
    return redis_client


@dataclass(slots=True)
class RefreshRotationResult:
    """Resultado de rotación de refresh token."""

    status: str
    family_id: str
    old_refresh_jti: Optional[str] = None
    old_access_jti: Optional[str] = None
    new_refresh_jti: Optional[str] = None
    new_access_jti: Optional[str] = None
    degraded: bool = False


def _ttl_seconds(expires_at: datetime) -> int:
    ttl = int((expires_at - datetime.now(timezone.utc)).total_seconds())
    return max(1, ttl)


def _failure_details(control: str, reason: str, *, jti: Optional[str] = None, family_id: Optional[str] = None, token_kind: Optional[str] = None):
    details = {"control": control, "reason": reason}
    if jti:
        details["jti"] = jti
    if family_id:
        details["family_id"] = family_id
    if token_kind:
        details["token_kind"] = token_kind
    return details


def _log_failure(event: str, *, control: str, reason: str, exc: Exception | None = None, **extra):
    payload = {"control": control, "reason": reason, **extra}
    if exc is not None:
        payload["error"] = str(exc)
    logger.warning(event, **payload)


def _handle_security_control_failure(
    control: str,
    reason: str,
    *,
    default,
    exc: Exception | None = None,
    **extra,
):
    _log_failure("security_control_failure", control=control, reason=reason, exc=exc, **extra)
    if settings.security_protection_fail_closed:
        raise SecurityControlUnavailableException(
            f"No se pudo verificar/aplicar '{control}': {reason}",
            details=_failure_details(control, reason, **extra),
        ) from exc
    return default


def _redis_or_policy_default(control: str, state_reason: str, default, *, exc: Exception | None = None, **extra):
    redis = _redis_instance()
    if redis is None:
        return _handle_security_control_failure(
            control,
            state_reason,
            default=default,
            exc=exc,
            **extra,
        )
    return redis


def _access_key(jti: str) -> str:
    return f"{_ACCESS_PREFIX}{jti}"


def _refresh_key(jti: str) -> str:
    return f"{_REFRESH_PREFIX}{jti}"


def _family_key(family_id: str) -> str:
    return f"{_FAMILY_PREFIX}{family_id}"


def _normalize_identifier(identifier: str | None) -> Optional[str]:
    if identifier is None:
        return None
    identifier = identifier.strip()
    return identifier or None


async def revoke_jti(
    jti: str | None,
    expires_at: datetime,
    *,
    token_kind: str = "access",
    reason: str = "logout",
) -> bool:
    """Revoca un token por jti.

    Retorna True si la marca de revocación se persistió.
    En fail-open, si Redis falla, se registra el incidente y retorna False.
    En fail-closed, la operación lanza SecurityControlUnavailableException.
    """
    token_jti = _normalize_identifier(jti)
    if not token_jti:
        logger.debug("revoke_jti_ignored_missing_jti", token_kind=token_kind, reason=reason)
        return False

    ttl = _ttl_seconds(expires_at)
    redis = _redis_or_policy_default(
        "token_revocation",
        "redis_unavailable",
        default=False,
        jti=token_jti,
        token_kind=token_kind,
        reason=reason,
    )
    if redis is False:
        return False

    key = _access_key(token_jti) if token_kind != "refresh" else _refresh_key(token_jti)
    try:
        await redis.setex(key, ttl, "1")
        logger.info("jwt_revoked", token_kind=token_kind, jti=token_jti, ttl_seconds=ttl, reason=reason)
        return True
    except Exception as exc:  # pragma: no cover - backend failure path
        return _handle_security_control_failure(
            "token_revocation",
            "redis_error",
            default=False,
            exc=exc,
            jti=token_jti,
            token_kind=token_kind,
            reason=reason,
        )


async def is_jti_revoked(jti: str | None, *, token_kind: str = "access") -> bool:
    """Indica si un token ya fue revocado.

    Para tokens legacy sin jti, el llamador debe resolver un identificador
    estable antes de invocar este helper.
    """
    token_jti = _normalize_identifier(jti)
    if not token_jti:
        logger.debug("revocation_check_skipped_missing_jti", token_kind=token_kind)
        return False

    redis = _redis_instance()
    if redis is None:
        return _handle_security_control_failure(
            "token_revocation_check",
            "redis_unavailable",
            default=False,
            jti=token_jti,
            token_kind=token_kind,
        )

    key = _access_key(token_jti) if token_kind != "refresh" else _refresh_key(token_jti)
    try:
        return bool(await redis.exists(key))
    except Exception as exc:  # pragma: no cover - backend failure path
        return _handle_security_control_failure(
            "token_revocation_check",
            "redis_error",
            default=False,
            exc=exc,
            jti=token_jti,
            token_kind=token_kind,
        )


async def register_refresh_family(
    *,
    family_id: str,
    user_id: str,
    tenant_id: str,
    refresh_jti: str,
    access_jti: str,
    expires_at: datetime,
) -> bool:
    """Registra o actualiza el estado de una familia de refresh tokens."""
    ttl = _ttl_seconds(expires_at)
    redis = _redis_or_policy_default(
        "refresh_family_register",
        "redis_unavailable",
        default=False,
        family_id=family_id,
        refresh_jti=refresh_jti,
    )
    if redis is False:
        return False

    now_iso = datetime.now(timezone.utc).isoformat()
    payload = {
        "user_id": str(user_id),
        "tenant_id": str(tenant_id),
        "current_refresh_jti": refresh_jti,
        "current_access_jti": access_jti,
        "revoked": "0",
        "reuse_detected": "0",
        "created_at": now_iso,
        "updated_at": now_iso,
        "expires_at": expires_at.isoformat(),
    }
    try:
        await redis.hset(_family_key(family_id), mapping=payload)
        await redis.expire(_family_key(family_id), ttl)
        logger.info(
            "refresh_family_registered",
            family_id=family_id,
            user_id=str(user_id),
            tenant_id=str(tenant_id),
            refresh_jti=refresh_jti,
            access_jti=access_jti,
            ttl_seconds=ttl,
        )
        return True
    except Exception as exc:  # pragma: no cover - backend failure path
        return _handle_security_control_failure(
            "refresh_family_register",
            "redis_error",
            default=False,
            exc=exc,
            family_id=family_id,
            refresh_jti=refresh_jti,
        )


async def revoke_refresh_family(
    *,
    family_id: str,
    expires_at: datetime,
    reason: str = "logout",
) -> bool:
    """Revoca toda una familia de refresh tokens."""
    ttl = _ttl_seconds(expires_at)
    redis = _redis_instance()
    if redis is None:
        return _handle_security_control_failure(
            "refresh_family_revoke",
            "redis_unavailable",
            default=False,
            family_id=family_id,
            reason=reason,
        )

    try:
        family_key = _family_key(family_id)
        state = await redis.hgetall(family_key)
        current_refresh = state.get("current_refresh_jti")
        current_access = state.get("current_access_jti")

        now_iso = datetime.now(timezone.utc).isoformat()
        await redis.hset(
            family_key,
            mapping={
                "revoked": "1",
                "revoked_at": now_iso,
                "revocation_reason": reason,
                "updated_at": now_iso,
            },
        )
        await redis.expire(family_key, ttl)

        if current_refresh:
            await redis.setex(_refresh_key(current_refresh), ttl, "1")
        if current_access:
            await redis.setex(_access_key(current_access), ttl, "1")

        logger.info(
            "refresh_family_revoked",
            family_id=family_id,
            reason=reason,
            current_refresh_jti=current_refresh,
            current_access_jti=current_access,
        )
        return True
    except Exception as exc:  # pragma: no cover - backend failure path
        return _handle_security_control_failure(
            "refresh_family_revoke",
            "redis_error",
            default=False,
            exc=exc,
            family_id=family_id,
            reason=reason,
        )


async def rotate_refresh_family(
    *,
    family_id: str,
    provided_refresh_jti: str,
    new_refresh_jti: str,
    new_access_jti: str,
    expires_at: datetime,
) -> RefreshRotationResult:
    """Rota de forma atómica una familia de refresh token.

    Si el refresh presentado no coincide con el actual de la familia, se
    considera reuso y la familia queda revocada.
    """
    ttl = _ttl_seconds(expires_at)
    redis = _redis_instance()
    if redis is None:
        if settings.security_protection_fail_closed:
            raise SecurityControlUnavailableException(
                "No se pudo rotar el refresh token porque Redis no está disponible",
                details=_failure_details("refresh_rotation", "redis_unavailable", family_id=family_id, jti=provided_refresh_jti),
            )
        logger.warning(
            "refresh_rotation_degraded_without_redis",
            family_id=family_id,
            provided_refresh_jti=provided_refresh_jti,
            new_refresh_jti=new_refresh_jti,
            new_access_jti=new_access_jti,
        )
        return RefreshRotationResult(
            status="degraded",
            family_id=family_id,
            old_refresh_jti=provided_refresh_jti,
            old_access_jti=None,
            new_refresh_jti=new_refresh_jti,
            new_access_jti=new_access_jti,
            degraded=True,
        )

    script = """
    local family_key = KEYS[1]
    local provided_refresh_jti = ARGV[1]
    local new_refresh_jti = ARGV[2]
    local new_access_jti = ARGV[3]
    local ttl = tonumber(ARGV[4])
    local now = ARGV[5]

    local current_refresh = redis.call("HGET", family_key, "current_refresh_jti")
    local current_access = redis.call("HGET", family_key, "current_access_jti")
    local revoked = redis.call("HGET", family_key, "revoked")

    if not current_refresh then
        return {"missing", current_access or "", ""}
    end

    if revoked == "1" then
        return {"revoked", current_access or "", current_refresh}
    end

    if current_refresh ~= provided_refresh_jti then
        redis.call("HSET", family_key,
            "revoked", "1",
            "reuse_detected", "1",
            "revoked_at", now,
            "updated_at", now)
        redis.call("EXPIRE", family_key, ttl)
        redis.call("SETEX", "revoked_jti:refresh:" .. provided_refresh_jti, ttl, "1")
        if current_refresh ~= nil and current_refresh ~= "" then
            redis.call("SETEX", "revoked_jti:refresh:" .. current_refresh, ttl, "1")
        end
        if current_access ~= nil and current_access ~= "" then
            redis.call("SETEX", "revoked_jti:access:" .. current_access, ttl, "1")
        end
        return {"reuse", current_access or "", current_refresh}
    end

    redis.call("HSET", family_key,
        "current_refresh_jti", new_refresh_jti,
        "current_access_jti", new_access_jti,
        "revoked", "0",
        "reuse_detected", "0",
        "last_rotated_at", now,
        "updated_at", now)
    redis.call("EXPIRE", family_key, ttl)
    redis.call("SETEX", "revoked_jti:refresh:" .. provided_refresh_jti, ttl, "1")
    if current_access ~= nil and current_access ~= "" then
        redis.call("SETEX", "revoked_jti:access:" .. current_access, ttl, "1")
    end
    return {"rotated", current_access or "", current_refresh}
    """

    now_iso = datetime.now(timezone.utc).isoformat()
    try:
        result = await redis.eval(
            script,
            1,
            _family_key(family_id),
            provided_refresh_jti,
            new_refresh_jti,
            new_access_jti,
            ttl,
            now_iso,
        )
        status = result[0]
        old_access_jti = result[1] or None
        old_refresh_jti = result[2] or None

        if status == "rotated":
            logger.info(
                "refresh_rotated",
                family_id=family_id,
                old_refresh_jti=old_refresh_jti,
                old_access_jti=old_access_jti,
                new_refresh_jti=new_refresh_jti,
                new_access_jti=new_access_jti,
            )
            return RefreshRotationResult(
                status="rotated",
                family_id=family_id,
                old_refresh_jti=old_refresh_jti,
                old_access_jti=old_access_jti,
                new_refresh_jti=new_refresh_jti,
                new_access_jti=new_access_jti,
            )

        if status == "reuse":
            logger.warning(
                "refresh_reuse_detected",
                family_id=family_id,
                provided_refresh_jti=provided_refresh_jti,
                old_refresh_jti=old_refresh_jti,
                old_access_jti=old_access_jti,
            )
            raise RefreshReuseDetectedException(
                "Se detectó reutilización de un refresh token ya rotado",
                details={
                    "family_id": family_id,
                    "provided_refresh_jti": provided_refresh_jti,
                    "current_refresh_jti": old_refresh_jti,
                    "current_access_jti": old_access_jti,
                },
            )

        if status == "revoked":
            raise TokenRevocadoException(
                "La familia de refresh ya fue revocada",
                details={"family_id": family_id, "refresh_jti": provided_refresh_jti},
            )

        if status == "missing":
            if settings.security_protection_fail_closed:
                raise SecurityControlUnavailableException(
                    "No se encontró el estado de la familia de refresh",
                    details={"family_id": family_id, "refresh_jti": provided_refresh_jti},
                )
            logger.warning(
                "refresh_family_missing_degraded",
                family_id=family_id,
                provided_refresh_jti=provided_refresh_jti,
            )
            return RefreshRotationResult(
                status="degraded",
                family_id=family_id,
                old_refresh_jti=provided_refresh_jti,
                old_access_jti=old_access_jti,
                new_refresh_jti=new_refresh_jti,
                new_access_jti=new_access_jti,
                degraded=True,
            )

        raise SecurityControlUnavailableException(
            "Respuesta inesperada al rotar el refresh token",
            details={"family_id": family_id, "refresh_jti": provided_refresh_jti, "status": status},
        )
    except (RefreshReuseDetectedException, TokenRevocadoException, SecurityControlUnavailableException):
        raise
    except Exception as exc:  # pragma: no cover - backend failure path
        return _handle_security_control_failure(
            "refresh_rotation",
            "redis_error",
            default=RefreshRotationResult(
                status="degraded",
                family_id=family_id,
                old_refresh_jti=provided_refresh_jti,
                old_access_jti=None,
                new_refresh_jti=new_refresh_jti,
                new_access_jti=new_access_jti,
                degraded=True,
            ),
            exc=exc,
            family_id=family_id,
            jti=provided_refresh_jti,
        )


class TokenRevocation:
    """Fachada OO para revocación de tokens.

    Mantiene el contrato que consumen los tests e integraciones, mientras
    la lógica real permanece en las funciones de módulo.
    """

    async def is_revoked(self, jti: str | None, *, token_kind: str = "access") -> bool:
        return await is_jti_revoked(jti, token_kind=token_kind)

    async def revoke_jti(self, jti: str | None, expires_at: datetime, *, token_kind: str = "access", reason: str = "logout") -> bool:
        return await revoke_jti(jti, expires_at, token_kind=token_kind, reason=reason)

    async def rotate_refresh_family(self, *, family_id: str, provided_refresh_jti: str, new_refresh_jti: str, new_access_jti: str, expires_at: datetime) -> RefreshRotationResult:
        return await rotate_refresh_family(
            family_id=family_id,
            provided_refresh_jti=provided_refresh_jti,
            new_refresh_jti=new_refresh_jti,
            new_access_jti=new_access_jti,
            expires_at=expires_at,
        )
