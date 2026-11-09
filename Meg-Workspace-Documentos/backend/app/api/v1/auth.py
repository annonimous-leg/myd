# Copyright © 2026 Cristian Rodriguez
# All rights reserved.
# Unauthorized copying, modification, distribution, or use is prohibited
# without prior written permission.

"""
Endpoints de autenticación conectados a AuthService.
"""
from app.core.rate_limit import rate_limit_standard, rate_limit_strict
import re
from typing import List, Optional
from datetime import datetime
from uuid import UUID
import logging

from fastapi import APIRouter, Depends, HTTPException, Request, Response, status
from fastapi.security import OAuth2PasswordRequestForm
from pydantic import BaseModel, EmailStr, Field
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import settings
from app.core.deps import REFRESH_COOKIE_NAME, SESSION_COOKIE_NAME, get_current_user, get_db, oauth2_scheme
from app.core.entitlements import requiere_rol
from app.services.auth_service import AuthService
from app.models.user import Invitation, User, UserRole


def _slugify(value: str) -> str:
    slug = re.sub(r"[^a-z0-9]+", "-", value.strip().lower()).strip("-")
    return slug or "org"

logger = logging.getLogger(__name__)


router = APIRouter()


class BrowserSession(BaseModel):
    """La sesión web solo expone su duración; las credenciales van en cookies."""
    expires_in: int


class Token(BaseModel):
    access_token: str
    token_type: str
    refresh_token: str
    expires_in: int


class UserRegister(BaseModel):
    """Alta pública = crear una organización (tenant) NUEVA.

    SEGURIDAD (cierre de auditoría, punto B): esta ruta ya NO acepta
    `tenant_id` ni `role` desde el cliente. Antes cualquiera que
    conociera (o adivinara) el UUID de un tenant ajeno podía unirse a
    él y pedir directamente `role: "admin"` o `"superadmin"`. Ahora
    /register SOLO puede crear una organización propia nueva, y quien
    la crea siempre queda como ADMIN de ESA organización -- nunca
    SUPERADMIN (ver app/core/entitlements.py: SUPERADMIN es rol de
    plataforma, no se autoasigna). Para sumar gente a un tenant que ya
    existe, un ADMIN de ese tenant debe invitarla (POST /invitations)
    y la invitada canjea el token en POST /register/invite.
    """
    email: EmailStr
    password: str = Field(..., min_length=8)
    full_name: str = Field(..., min_length=3, max_length=255)
    company_name: str = Field(..., min_length=2, max_length=255)
    company_slug: Optional[str] = Field(None, min_length=2, max_length=100)
    company_rfc: Optional[str] = Field(None, max_length=13)


class InvitationCreate(BaseModel):
    email: EmailStr
    role: UserRole = UserRole.TECNICO


class InvitationOut(BaseModel):
    id: UUID
    email: str
    role: str
    status: str
    expires_at: datetime
    invite_token: Optional[str] = Field(
        None,
        description="Solo presente en la respuesta de creación. No se puede recuperar después.",
    )

    class Config:
        from_attributes = True


class InviteRegister(BaseModel):
    invite_token: str = Field(..., min_length=16)
    password: str = Field(..., min_length=8)
    full_name: str = Field(..., min_length=3, max_length=255)


class UserOut(BaseModel):
    id: UUID
    email: str
    full_name: str
    role: str
    is_active: bool

    class Config:
        from_attributes = True


class RefreshRequest(BaseModel):
    # Browser: refresh vive en cookie httpOnly. SDK/CLI: puede enviarlo en body.
    refresh_token: Optional[str] = None


def _set_browser_cookies(response: Response, access_token: str, refresh_token: str) -> None:
    """Only the browser session endpoints issue ambient credentials."""
    response.set_cookie(
        key=SESSION_COOKIE_NAME, value=access_token, httponly=True,
        secure=settings.is_production, samesite="lax",
        max_age=settings.ACCESS_TOKEN_EXPIRE_MINUTES * 60, path="/",
    )
    response.set_cookie(
        key=REFRESH_COOKIE_NAME, value=refresh_token, httponly=True,
        secure=settings.is_production, samesite="strict",
        max_age=settings.REFRESH_TOKEN_EXPIRE_DAYS * 86400, path="/api/v1/auth",
    )


@router.post("/session/login", response_model=BrowserSession)
@router.post("/login", response_model=Token)
async def login(
    request: Request,
    response: Response,
    form_data: OAuth2PasswordRequestForm = Depends(),
    db: AsyncSession = Depends(get_db),
    _rate_limit: bool = Depends(rate_limit_strict),
):
    auth_service = AuthService(db)
    user = await auth_service.authenticate(form_data.username, form_data.password)

    if not user:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Usuario o contraseña incorrectos",
            headers={"WWW-Authenticate": "Bearer"},
        )

    access_token, refresh_token = await auth_service.issue_token_pair(user)

    response.headers["Cache-Control"] = "no-store"
    if request.url.path.endswith("/session/login"):
        _set_browser_cookies(response, access_token, refresh_token)

    return Token(
        access_token=access_token,
        token_type="bearer",
        refresh_token=refresh_token,
        expires_in=settings.ACCESS_TOKEN_EXPIRE_MINUTES * 60,
    )


@router.post("/register", response_model=UserOut, status_code=status.HTTP_201_CREATED)
async def register(
    data: UserRegister,
    db: AsyncSession = Depends(get_db),
    _rate_limit: bool = Depends(rate_limit_strict),
):
    """Crea una organización nueva y su usuario administrador.

    Para unirse a una organización EXISTENTE, usa una invitación
    (ver POST /auth/register/invite) -- esta ruta pública nunca une a
    un tenant que no acabas de crear tú mismo.
    """
    auth_service = AuthService(db)
    slug = _slugify(data.company_slug or data.company_name)
    tenant, admin = await auth_service.create_tenant(
        name=data.company_name,
        slug=slug,
        rfc=data.company_rfc,
        admin_email=data.email,
        admin_password=data.password,
        admin_full_name=data.full_name,
    )
    return admin


@router.post("/register/invite", response_model=UserOut, status_code=status.HTTP_201_CREATED)
async def register_via_invite(
    data: InviteRegister,
    db: AsyncSession = Depends(get_db),
    _rate_limit: bool = Depends(rate_limit_strict),
):
    """Canjea una invitación y crea el usuario dentro del tenant que
    la emitió, con el rol exacto que la invitación fijó.
    """
    auth_service = AuthService(db)
    user = await auth_service.register_user_via_invite(
        token=data.invite_token,
        password=data.password,
        full_name=data.full_name,
    )
    return user


@router.post(
    "/invitations",
    response_model=InvitationOut,
    status_code=status.HTTP_201_CREATED,
)
async def create_invitation(
    data: InvitationCreate,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
    _role_check: None = Depends(requiere_rol(UserRole.ADMIN, UserRole.SUPERADMIN)),
    _rate_limit: bool = Depends(rate_limit_strict),
):
    """Invita a alguien al tenant del usuario autenticado. Solo un
    ADMIN o SUPERADMIN del tenant puede invitar, y nunca con rol
    SUPERADMIN (ver ROLES_INVITABLES en app/services/auth_service.py).
    """
    auth_service = AuthService(db)
    invitation, raw_token = await auth_service.create_invitation(
        tenant_id=current_user.tenant_id,
        email=data.email,
        role=data.role,
        invited_by=current_user,
    )
    return InvitationOut(
        id=invitation.id,
        email=invitation.email,
        role=invitation.role,
        status=invitation.status,
        expires_at=invitation.expires_at,
        invite_token=raw_token,
    )


@router.get("/invitations", response_model=List[InvitationOut])
async def list_invitations(
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
    _role_check: None = Depends(requiere_rol(UserRole.ADMIN, UserRole.SUPERADMIN)), _rate_limit: bool = Depends(rate_limit_standard),
):
    """Lista las invitaciones del tenant del usuario autenticado (sin
    exponer el token -- ese solo se ve una vez, al crearla)."""
    result = await db.execute(
        select(Invitation)
        .where(Invitation.tenant_id == current_user.tenant_id)
        .order_by(Invitation.expires_at.desc())
    )
    return [
        InvitationOut(
            id=inv.id,
            email=inv.email,
            role=inv.role,
            status=inv.status,
            expires_at=inv.expires_at,
            invite_token=None,
        )
        for inv in result.scalars().all()
    ]


@router.post("/session/refresh", response_model=BrowserSession)
@router.post("/refresh", response_model=Token)
async def refresh_token(
    request: Request,
    response: Response,
    data: Optional[RefreshRequest] = None,
    db: AsyncSession = Depends(get_db),
    _rate_limit: bool = Depends(rate_limit_strict),
):
    if request.url.path.endswith("/session/refresh"):
        refresh_value = request.cookies.get(REFRESH_COOKIE_NAME)
    else:
        # El contrato SDK exige credenciales explícitas; no expone cookies a JS.
        refresh_value = data.refresh_token if data else None
    if not refresh_value:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Refresh token requerido")
    auth_service = AuthService(db)
    access_token, new_refresh = await auth_service.refresh_access_token(refresh_value)

    response.headers["Cache-Control"] = "no-store"
    if request.url.path.endswith("/session/refresh"):
        _set_browser_cookies(response, access_token, new_refresh)

    return Token(
        access_token=access_token,
        token_type="bearer",
        refresh_token=new_refresh,
        expires_in=settings.ACCESS_TOKEN_EXPIRE_MINUTES * 60,
    )


class LogoutRequest(BaseModel):
    # Opcional: si el cliente también guarda el refresh_token aparte
    # (SDK/CLI sin cookies), lo manda aquí para revocarlo también.
    refresh_token: Optional[str] = None


@router.post("/logout")
async def logout(
    request: Request,
    response: Response,
    body: Optional[LogoutRequest] = None,
    token: Optional[str] = Depends(oauth2_scheme),
    _rate_limit: bool = Depends(rate_limit_strict),
):
    """Cierra la sesión elegida con la misma prioridad que la autenticación."""
    from app.services.session_service import logout_session
    access_token = token or request.cookies.get(SESSION_COOKIE_NAME)
    refresh_value = (body.refresh_token if body else None)
    if not token and not refresh_value:
        refresh_value = request.cookies.get(REFRESH_COOKIE_NAME)
    await logout_session(access_token, refresh_value)
    if not token:
        response.delete_cookie(key=SESSION_COOKIE_NAME, path="/")
        response.delete_cookie(key=REFRESH_COOKIE_NAME, path="/api/v1/auth")
    return {"status": "ok"}


@router.get("/me", response_model=UserOut)
async def get_me(current_user=Depends(get_current_user), _rate_limit: bool = Depends(rate_limit_standard)):
    return current_user
