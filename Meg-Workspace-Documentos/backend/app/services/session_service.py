"""Cierre de sesiones para todos los consumidores de la identidad MEGALODON."""
from datetime import datetime, timedelta, timezone
import jwt
from jwt.exceptions import PyJWTError
from app.config import settings
from app.core.token_revocation import revoke_jti, revoke_refresh_family


def _claims(token: str | None, kind: str) -> dict | None:
    if not token:
        return None
    try:
        # Un access expirado puede cerrar su familia; nunca autentica una operación.
        claims = jwt.decode(token, settings.SECRET_KEY, algorithms=[settings.ALGORITHM],
            options={"verify_exp": False, "require": ["exp", "sub", "jti", "sid"]})
        return claims if claims.get("type") == kind else None
    except PyJWTError:
        return None


async def logout_session(access_token: str | None, refresh_token: str | None) -> None:
    access = _claims(access_token, "access")
    refresh = _claims(refresh_token, "refresh")
    if access_token and not access:
        return
    if access and refresh and (access["sub"], access["sid"]) != (refresh["sub"], refresh["sid"]):
        refresh = None
    for claims, kind in ((access, "access"), (refresh, "refresh")):
        if claims:
            await revoke_jti(claims["jti"], datetime.fromtimestamp(claims["exp"], timezone.utc),
                token_kind=kind, reason="logout")
    claims = access or refresh
    if claims:
        # El refresh vive más que el access: no reducir la revocación a 30 minutos.
        await revoke_refresh_family(family_id=claims["sid"],
            expires_at=datetime.now(timezone.utc) + timedelta(days=settings.REFRESH_TOKEN_EXPIRE_DAYS),
            reason="logout")
