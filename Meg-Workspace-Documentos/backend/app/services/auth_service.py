# Copyright © 2026 Cristian Rodriguez
# All rights reserved.
# Unauthorized copying, modification, distribution, or use is prohibited
# without prior written permission.

"""
AuthService - Autenticación multi-tenant con JWT y rotación segura de refresh.

Este servicio ahora:
- emite access/refresh con jti real,
- registra una familia de refresh por sesión,
- verifica revocación de access tokens,
- rota refresh tokens de forma segura,
- y detecta reuso de refresh tokens.
"""
from __future__ import annotations

from datetime import datetime, timedelta, timezone
from typing import Optional, Tuple
from uuid import UUID, uuid4
import hashlib

import structlog

import bcrypt
import jwt
from jwt.exceptions import PyJWTError
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import settings
from app.core.errors import (
    ErrorCode,
    MegalodonException,
    RefreshReuseDetectedException,
    SecurityControlUnavailableException,
    TokenRevocadoException,
)
from app.core.token_revocation import (
    is_jti_revoked,
    register_refresh_family,
    revoke_refresh_family,
    rotate_refresh_family,
)
from app.models.user import Invitation, InvitationStatus, Tenant, User, UserRole

# Roles que un ADMIN de tenant puede otorgar por invitación. SUPERADMIN
# es modo "god admin" de plataforma (ver app/core/entitlements.py:
# requiere_godadmin) -- nunca se concede por autoservicio ni por
# invitación, solo por acción directa de plataforma (DB/CLI).
ROLES_INVITABLES = (
    UserRole.ADMIN,
    UserRole.TECNICO,
    UserRole.REVISOR,
    UserRole.LECTOR,
    UserRole.INVITADO,
)
INVITATION_TTL = timedelta(days=7)

logger = structlog.get_logger()


def _ensure_aware_utc(dt: datetime) -> datetime:
    if dt.tzinfo is None:
        return dt.replace(tzinfo=timezone.utc)
    return dt.astimezone(timezone.utc)


class AuthService:
    """Servicio de autenticación y autorización."""

    def __init__(self, db: AsyncSession):
        self.db = db

    @staticmethod
    def _role_value(role: str | UserRole) -> str:
        return role.value if hasattr(role, "value") else str(role)

    @staticmethod
    def _legacy_token_identifier(token: str) -> str:
        """Genera un identificador estable para tokens legacy sin jti/sid."""
        digest = hashlib.sha256(token.encode("utf-8")).hexdigest()
        return f"legacy:{digest}"

    def hash_password(self, password: str) -> str:
        """Genera un hash bcrypt real usando el proveedor oficial."""
        return bcrypt.hashpw(
            password.encode("utf-8"),
            bcrypt.gensalt(rounds=12),
        ).decode("utf-8")

    def verify_password(self, plain_password: str, hashed_password: str) -> bool:
        """Verifica un hash bcrypt y nunca interpreta otro formato como válido."""
        try:
            return bcrypt.checkpw(plain_password.encode("utf-8"), hashed_password.encode("utf-8"))
        except (TypeError, ValueError):
            return False

    def create_access_token(
        self,
        user_id: UUID,
        email: str,
        tenant_id: UUID,
        role: str,
        *,
        session_id: Optional[str] = None,
        jti: Optional[str] = None,
        auth_version: int = 0,
    ) -> str:
        """Crea token JWT de acceso con jti real y session id."""
        now = datetime.now(timezone.utc)
        token_jti = jti or str(uuid4())
        token_session_id = session_id or str(uuid4())
        to_encode = {
            "sub": str(user_id),
            "email": email,
            "tenant_id": str(tenant_id),
            "role": role,
            "sid": token_session_id,
            "jti": token_jti,
            "type": "access",
            "auth_version": auth_version,
            "iat": now,
            "exp": now + timedelta(minutes=settings.ACCESS_TOKEN_EXPIRE_MINUTES),
        }
        return jwt.encode(to_encode, settings.SECRET_KEY, algorithm=settings.ALGORITHM)

    def create_refresh_token(
        self,
        user_id: UUID,
        *,
        session_id: Optional[str] = None,
        jti: Optional[str] = None,
        auth_version: int = 0,
    ) -> str:
        """Crea token JWT de refresh con jti real y session id."""
        now = datetime.now(timezone.utc)
        token_jti = jti or str(uuid4())
        token_session_id = session_id or str(uuid4())
        to_encode = {
            "sub": str(user_id),
            "sid": token_session_id,
            "jti": token_jti,
            "type": "refresh",
            "auth_version": auth_version,
            "iat": now,
            "exp": now + timedelta(days=settings.REFRESH_TOKEN_EXPIRE_DAYS),
        }
        return jwt.encode(to_encode, settings.SECRET_KEY, algorithm=settings.ALGORITHM)

    async def issue_token_pair(self, user: User) -> Tuple[str, str]:
        """Emite access + refresh y registra la familia de sesión."""
        session_id = str(uuid4())
        access_jti = str(uuid4())
        refresh_jti = str(uuid4())

        role_value = self._role_value(user.role)
        access_token = self.create_access_token(
            user.id,
            user.email,
            user.tenant_id,
            role_value,
            session_id=session_id,
            jti=access_jti,
            auth_version=user.auth_version,
        )
        refresh_token = self.create_refresh_token(
            user.id,
            session_id=session_id,
            jti=refresh_jti,
            auth_version=user.auth_version,
        )

        expires_at = datetime.now(timezone.utc) + timedelta(days=settings.REFRESH_TOKEN_EXPIRE_DAYS)
        registered = await register_refresh_family(
            family_id=session_id,
            user_id=str(user.id),
            tenant_id=str(user.tenant_id),
            refresh_jti=refresh_jti,
            access_jti=access_jti,
            expires_at=expires_at,
        )
        if not registered:
            # En fail-open puede no haber Redis, pero el par sigue siendo válido.
            logger.warning(
                "refresh_family_not_registered",
                family_id=session_id,
                user_id=str(user.id),
                tenant_id=str(user.tenant_id),
            )

        return access_token, refresh_token

    async def authenticate(self, email: str, password: str) -> Optional[User]:
        """Autentica un usuario por email y contraseña."""
        result = await self.db.execute(select(User).where(User.email == email))
        user = result.scalar_one_or_none()

        if not user:
            return None

        if not self.verify_password(password, user.hashed_password):
            return None

        if not user.is_active:
            return None

        user.last_login = datetime.now(timezone.utc)
        await self.db.commit()
        return user

    async def register_user(
        self,
        *,
        email: str,
        password: str,
        full_name: str,
        tenant_id: UUID,
        rfc: Optional[str] = None,
        curp: Optional[str] = None,
        role: UserRole = UserRole.TECNICO,
    ) -> User:
        """Registra un nuevo usuario."""
        result = await self.db.execute(select(User).where(User.email == email))
        if result.scalar_one_or_none():
            raise MegalodonException(
                ErrorCode.NORMATIVO_GENERICO,
                f"El email {email} ya está registrado",
            )

        result = await self.db.execute(select(Tenant).where(Tenant.id == tenant_id))
        if not result.scalar_one_or_none():
            raise MegalodonException(
                ErrorCode.DOCUMENTO_NO_ENCONTRADO,
                f"Tenant {tenant_id} no encontrado",
            )

        user = User(
            email=email,
            hashed_password=self.hash_password(password),
            full_name=full_name,
            tenant_id=tenant_id,
            rfc=rfc,
            curp=curp,
            role=role,
            is_active=True,
            is_verified=False,
        )

        self.db.add(user)
        await self.db.commit()
        await self.db.refresh(user)
        return user

    async def get_current_user_from_token(self, token: str) -> User:
        """Obtiene usuario desde token JWT y verifica revocación de access."""
        try:
            payload = jwt.decode(token, settings.SECRET_KEY, algorithms=[settings.ALGORITHM])

            if payload.get("type") != "access":
                raise MegalodonException(
                    ErrorCode.FIRMA_INVALIDA,
                    "Token inválido: se requiere un token de acceso, no de refresh.",
                )

            user_id_raw = payload.get("sub")
            if not user_id_raw:
                raise MegalodonException(
                    ErrorCode.FIRMA_INVALIDA,
                    "Token inválido: falta sub.",
                )

            token_jti = payload.get("jti") or self._legacy_token_identifier(token)
            if not payload.get("jti"):
                if settings.security_protection_fail_closed:
                    raise TokenRevocadoException(
                        "Token de acceso legacy sin jti no permitido en modo fail-closed",
                        details={"sub": user_id_raw},
                    )
                logger.warning(
                    "legacy_access_token_without_jti_accepted",
                    sub=user_id_raw,
                    token_jti=token_jti,
                )

            if await is_jti_revoked(token_jti, token_kind="access"):
                raise TokenRevocadoException(
                    "Token de acceso revocado",
                    details={"jti": token_jti},
                )

            user_id = UUID(user_id_raw)
            result = await self.db.execute(select(User).where(User.id == user_id))
            user = result.scalar_one_or_none()

            if not user or not user.is_active:
                raise MegalodonException(
                    ErrorCode.FIRMA_INVALIDA,
                    "Usuario no encontrado o inactivo",
                )

            version = payload.get("auth_version")
            if type(version) is not int or version != user.auth_version:
                raise TokenRevocadoException(
                    "La identidad cambió; se requiere iniciar sesión de nuevo.",
                    details={"sub": user_id_raw},
                )

            payload_tenant_id = payload.get("tenant_id")
            if payload_tenant_id and str(user.tenant_id) != str(payload_tenant_id):
                raise MegalodonException(
                    ErrorCode.FIRMA_INVALIDA,
                    "El token no corresponde al tenant del usuario.",
                )

            return user

        except (PyJWTError, ValueError, TypeError):
            raise MegalodonException(
                ErrorCode.FIRMA_INVALIDA,
                "Token inválido o expirado",
            )

    async def refresh_access_token(self, refresh_token: str) -> Tuple[str, str]:
        """Rota refresh token y emite un nuevo par access/refresh."""
        try:
            payload = jwt.decode(refresh_token, settings.SECRET_KEY, algorithms=[settings.ALGORITHM])

            if payload.get("type") != "refresh":
                raise MegalodonException(
                    ErrorCode.FIRMA_INVALIDA,
                    "Token inválido: se requiere un token de refresh.",
                )

            user_id_raw = payload.get("sub")
            if not user_id_raw:
                raise MegalodonException(
                    ErrorCode.FIRMA_INVALIDA,
                    "Refresh token inválido: falta sub.",
                )

            refresh_jti = payload.get("jti") or self._legacy_token_identifier(refresh_token)
            session_id = payload.get("sid") or payload.get("session_id") or self._legacy_token_identifier(refresh_token)

            if await is_jti_revoked(refresh_jti, token_kind="refresh"):
                raise RefreshReuseDetectedException(
                    "Refresh token ya revocado o reutilizado",
                    details={"jti": refresh_jti, "family_id": session_id},
                )

            user_id = UUID(user_id_raw)
            result = await self.db.execute(select(User).where(User.id == user_id))
            user = result.scalar_one_or_none()

            if not user or not user.is_active:
                raise MegalodonException(
                    ErrorCode.FIRMA_INVALIDA,
                    "Usuario no encontrado o inactivo",
                )

            version = payload.get("auth_version")
            if type(version) is not int or version != user.auth_version:
                raise TokenRevocadoException(
                    "La identidad cambió; se requiere iniciar sesión de nuevo.",
                    details={"sub": user_id_raw},
                )

            tenant_id = str(user.tenant_id)
            role_value = self._role_value(user.role)

            new_access_jti = str(uuid4())
            new_refresh_jti = str(uuid4())
            expires_at = datetime.now(timezone.utc) + timedelta(days=settings.REFRESH_TOKEN_EXPIRE_DAYS)

            rotation = await rotate_refresh_family(
                family_id=session_id,
                provided_refresh_jti=refresh_jti,
                new_refresh_jti=new_refresh_jti,
                new_access_jti=new_access_jti,
                expires_at=expires_at,
            )

            if rotation.degraded:
                # Re-seed del tracking cuando Redis volvió a estar disponible o
                # cuando el backend operó degradado por fail-open.
                logger.warning(
                    "refresh_rotation_degraded",
                    family_id=session_id,
                    user_id=str(user.id),
                    tenant_id=tenant_id,
                )
                await register_refresh_family(
                    family_id=session_id,
                    user_id=str(user.id),
                    tenant_id=tenant_id,
                    refresh_jti=new_refresh_jti,
                    access_jti=new_access_jti,
                    expires_at=expires_at,
                )

            access_token = self.create_access_token(
                user.id,
                user.email,
                user.tenant_id,
                role_value,
                session_id=session_id,
                jti=new_access_jti,
                auth_version=user.auth_version,
            )
            new_refresh = self.create_refresh_token(
                user.id,
                session_id=session_id,
                jti=new_refresh_jti,
                auth_version=user.auth_version,
            )

            return access_token, new_refresh

        except (PyJWTError, ValueError, TypeError):
            raise MegalodonException(
                ErrorCode.FIRMA_INVALIDA,
                "Refresh token inválido o expirado",
            )

    async def create_tenant(
        self,
        *,
        name: str,
        slug: str,
        rfc: Optional[str] = None,
        admin_email: str,
        admin_password: str,
        admin_full_name: str,
    ) -> Tuple[Tenant, User]:
        """Crea un nuevo tenant con usuario administrador."""
        result = await self.db.execute(select(Tenant).where(Tenant.slug == slug))
        if result.scalar_one_or_none():
            raise MegalodonException(
                ErrorCode.NORMATIVO_GENERICO,
                f"El slug '{slug}' ya existe",
            )

        tenant = Tenant(
            name=name,
            slug=slug,
            rfc=rfc,
            is_active=True,
            settings={"plan": "basic", "max_users": 10, "max_expedientes": 100},
        )
        self.db.add(tenant)
        await self.db.flush()

        admin = await self.register_user(
            email=admin_email,
            password=admin_password,
            full_name=admin_full_name,
            tenant_id=tenant.id,
            role=UserRole.ADMIN,
        )

        await self.db.commit()
        return tenant, admin

    @staticmethod
    def _hash_invitation_token(token: str) -> str:
        return hashlib.sha256(token.encode("utf-8")).hexdigest()

    async def create_invitation(
        self,
        *,
        tenant_id: UUID,
        email: str,
        role: UserRole,
        invited_by: User,
    ) -> Tuple[Invitation, str]:
        """Crea una invitación para unirse al tenant del que la emite.

        El rol y el tenant quedan fijos en la invitación -- el usuario
        que la canjea en /register/invite NO puede elegir otro rol ni
        otro tenant. Solo un ADMIN (o SUPERADMIN) puede invitar, y
        nunca se puede invitar con rol SUPERADMIN.
        """
        if invited_by.role not in (UserRole.ADMIN.value, UserRole.SUPERADMIN.value):
            raise MegalodonException(
                ErrorCode.ROL_NO_PERMITIDO,
                "Solo un administrador del tenant puede invitar usuarios.",
                403,
            )
        if role not in ROLES_INVITABLES:
            raise MegalodonException(
                ErrorCode.ROL_NO_PERMITIDO,
                "El rol solicitado no puede otorgarse por invitación.",
                403,
            )

        result = await self.db.execute(
            select(User).where(User.email == email, User.tenant_id == tenant_id)
        )
        if result.scalar_one_or_none():
            raise MegalodonException(
                ErrorCode.NORMATIVO_GENERICO,
                f"{email} ya es usuario de este tenant.",
                409,
            )

        # Invalida cualquier invitación pendiente previa para el mismo
        # email en el mismo tenant, para no dejar tokens viejos vivos.
        result = await self.db.execute(
            select(Invitation).where(
                Invitation.tenant_id == tenant_id,
                Invitation.email == email,
                Invitation.status == InvitationStatus.PENDING,
            )
        )
        for previa in result.scalars().all():
            previa.status = InvitationStatus.REVOKED

        raw_token = uuid4().hex + uuid4().hex  # 64 hex chars, alta entropía
        invitation = Invitation(
            tenant_id=tenant_id,
            email=email,
            role=role.value if isinstance(role, UserRole) else role,
            token_hash=self._hash_invitation_token(raw_token),
            invited_by=invited_by.id,
            status=InvitationStatus.PENDING,
            expires_at=datetime.now(timezone.utc) + INVITATION_TTL,
        )
        self.db.add(invitation)
        await self.db.commit()
        await self.db.refresh(invitation)
        return invitation, raw_token

    async def register_user_via_invite(
        self,
        *,
        token: str,
        password: str,
        full_name: str,
    ) -> User:
        """Registra un usuario canjeando una invitación.

        email, role y tenant_id salen SIEMPRE de la invitación
        persistida, nunca del payload que manda el cliente -- así se
        cierra el hueco de auto-elevación de rol / cross-tenant join
        que tenía el /register público original.
        """
        token_hash = self._hash_invitation_token(token)
        result = await self.db.execute(
            select(Invitation).where(Invitation.token_hash == token_hash)
        )
        invitation = result.scalar_one_or_none()

        if not invitation or invitation.status != InvitationStatus.PENDING:
            raise MegalodonException(
                ErrorCode.INVITACION_INVALIDA,
                "La invitación no existe, ya fue usada o fue revocada.",
                400,
            )
        if _ensure_aware_utc(invitation.expires_at) < datetime.now(timezone.utc):
            invitation.status = InvitationStatus.REVOKED
            await self.db.commit()
            raise MegalodonException(
                ErrorCode.INVITACION_EXPIRADA,
                "La invitación expiró. Pide una nueva.",
                400,
            )

        user = await self.register_user(
            email=invitation.email,
            password=password,
            full_name=full_name,
            tenant_id=invitation.tenant_id,
            role=UserRole(invitation.role),
        )

        invitation.status = InvitationStatus.ACCEPTED
        invitation.accepted_at = datetime.now(timezone.utc)
        await self.db.commit()
        return user
