# Copyright © 2026 Cristian Rodriguez
# All rights reserved.
# Unauthorized copying, modification, distribution, or use is prohibited
# without prior written permission.

"""
Dependencias compartidas de FastAPI.

Antes de este archivo, cada router en app/api/v1/*.py definía su propia
copia de `get_db()` y `get_current_user()`, y varios importaban un
`engine` que jamás existía en app.models.base -> ImportError al arrancar.

Ahora hay un solo lugar de verdad: la sesión sale de
`app.models.base.AsyncSessionLocal` y el usuario autenticado se resuelve
aquí una sola vez.
"""
from typing import AsyncIterator, Optional
from uuid import UUID

from fastapi import Depends, HTTPException, Request
from fastapi.security import OAuth2PasswordBearer
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.errors import MegalodonException
from app.models.base import AsyncSessionLocal
from app.models.user import User

# auto_error=False: NO tronar aquí si falta el header Bearer -- primero
# se intenta la cookie httpOnly (ver get_current_user). Si al final no
# hay ni cookie ni header, ahí sí se lanza el 401.
oauth2_scheme = OAuth2PasswordBearer(tokenUrl="/api/v1/auth/login", auto_error=False)

# Nombre de la cookie de sesión. Compartido con app/api/v1/auth.py (login
# la setea) y con la lógica de abajo (la lee). httpOnly + Secure en
# producción + SameSite=lax: no la puede leer JS (mitiga robo de token
# por XSS), solo viaja por HTTPS en prod, y se manda en navegación normal
# pero no en requests cross-site que cambian estado (mitiga CSRF básico).
SESSION_COOKIE_NAME = "megalodon_session"
REFRESH_COOKIE_NAME = "megalodon_refresh_token"


async def get_db() -> AsyncIterator[AsyncSession]:
    """Provee una sesión de base de datos por request y garantiza el cierre."""
    async with AsyncSessionLocal() as session:
        yield session


async def get_current_user(
    request: Request,
    token: Optional[str] = Depends(oauth2_scheme),
    db: AsyncSession = Depends(get_db),
) -> User:
    """Resuelve el usuario autenticado a partir del JWT.

    Cookie httpOnly primero (sesión de navegador, más segura contra XSS);
    si no hay cookie, cae al header Authorization: Bearer (clientes de
    API/SDK/CLI que no manejan cookies). Mismo patrón que ya traía
    tezcatlipoca/routers/auth.py -- se replicó aquí a propósito para que
    el login quede consistente en toda la plataforma unificada.
    """
    # An explicit Authorization header is authoritative. This matters for
    # API/SDK clients and also prevents a stale browser cookie from silently
    # replacing the identity selected by a Bearer token.
    final_token = token or request.cookies.get(SESSION_COOKIE_NAME)
    if not final_token:
        raise HTTPException(
            status_code=401,
            detail="No autenticado",
            headers={"WWW-Authenticate": "Bearer"},
        )

    # Import diferido para evitar import circular: auth_service no depende
    # de deps.py, pero se mantiene el patrón por claridad.
    from app.services.auth_service import AuthService

    auth_service = AuthService(db)
    try:
        return await auth_service.get_current_user_from_token(final_token)
    except MegalodonException as e:
        raise HTTPException(status_code=e.status_code, detail=e.message)


# BUG ORIGINAL (fuga entre tenants): 10 routers (bim, compliance,
# documentos, firma, presupuestos, programacion, topografia, audit,
# expedientes_advanced, validadores parcial) reciben `expediente_id`
# directo de la URL y lo pasan al service SIN verificar que ese
# expediente pertenezca al tenant del usuario autenticado. Cada servicio
# de dominio (bim_service, presupuesto_service, topografia_service, etc.)
# solo valida relaciones internas (ej. "el programa pertenece a este
# expediente"), nunca "este expediente pertenece a este tenant" -- así
# que cualquier usuario autenticado de CUALQUIER tenant podía leer o
# escribir documentos/BIM/presupuestos/programas de OTRO tenant con solo
# conocer o adivinar un UUID de expediente ajeno. Esta dependencia cierra
# ese hueco en un solo lugar; se agrega a cada endpoint que tome
# expediente_id en el path.
async def verificar_expediente_tenant(
    expediente_id: UUID,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Verifica que expediente_id pertenezca al tenant del usuario actual.

    Se usa como Depends(...) adicional en cualquier endpoint que reciba
    expediente_id en la URL. Devuelve el expediente (por si el router lo
    quiere reusar) pero su función principal es el side-effect: 404 si el
    expediente no existe O pertenece a otro tenant -- a propósito el mismo
    código en ambos casos (no 403), para no confirmarle a un atacante que
    el UUID sí existe en otro tenant.
    """
    from app.models.expediente import ExpedienteObra

    result = await db.execute(
        select(ExpedienteObra)
        .where(ExpedienteObra.id == expediente_id)
        .where(ExpedienteObra.tenant_id == current_user.tenant_id)
    )
    expediente = result.scalar_one_or_none()
    if not expediente:
        raise HTTPException(status_code=404, detail="Expediente no encontrado")
    return expediente


async def verificar_documento_tenant(
    documento_id: UUID,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Verifica que documento_id pertenezca al tenant del usuario actual.

    Mismo patrón que verificar_expediente_tenant, pero para endpoints que
    reciben documento_id (no expediente_id) en el path -- ej. clasificar,
    nueva versión, árbol de versiones. DocumentoCDE trae tenant_id propio
    vía TenantMixin, así que no hace falta join con expediente.
    """
    from app.models.documento import DocumentoCDE

    result = await db.execute(
        select(DocumentoCDE)
        .where(DocumentoCDE.id == documento_id)
        .where(DocumentoCDE.tenant_id == current_user.tenant_id)
    )
    documento = result.scalar_one_or_none()
    if not documento:
        raise HTTPException(status_code=404, detail="Documento no encontrado")
    return documento



async def verificar_presupuesto_tenant(
    presupuesto_id: UUID,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Verifica que presupuesto_id pertenezca al tenant del usuario actual."""
    from app.models.presupuesto import Presupuesto
    from app.models.expediente import ExpedienteObra

    result = await db.execute(
        select(Presupuesto)
        .join(ExpedienteObra, Presupuesto.expediente_id == ExpedienteObra.id)
        .where(Presupuesto.id == presupuesto_id)
        .where(ExpedienteObra.tenant_id == current_user.tenant_id)
    )
    presupuesto = result.scalar_one_or_none()
    if not presupuesto:
        raise HTTPException(status_code=404, detail="Presupuesto no encontrado")
    return presupuesto


async def verificar_levantamiento_tenant(
    levantamiento_id: UUID,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Verifica que levantamiento_id pertenezca al tenant actual.

    Los endpoints de topografía anidados bajo un levantamiento (puntos,
    importar CSV, triangular) no llevan expediente_id en la URL -- solo
    levantamiento_id. Levantamiento sí trae expediente_id propio (ver
    app.models.topografia), así que se resuelve con un join.
    """
    from app.models.topografia import Levantamiento
    from app.models.expediente import ExpedienteObra

    result = await db.execute(
        select(Levantamiento)
        .join(ExpedienteObra, Levantamiento.expediente_id == ExpedienteObra.id)
        .where(Levantamiento.id == levantamiento_id)
        .where(ExpedienteObra.tenant_id == current_user.tenant_id)
    )
    levantamiento = result.scalar_one_or_none()
    if not levantamiento:
        raise HTTPException(status_code=404, detail="Levantamiento no encontrado")
    return levantamiento


async def verificar_superficie_tenant(
    superficie_id: UUID,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Verifica que superficie_id (una superficie TIN) pertenezca al
    tenant actual. SuperficieTIN ya trae expediente_id denormalizado."""
    from app.models.topografia import SuperficieTIN
    from app.models.expediente import ExpedienteObra

    result = await db.execute(
        select(SuperficieTIN)
        .join(ExpedienteObra, SuperficieTIN.expediente_id == ExpedienteObra.id)
        .where(SuperficieTIN.id == superficie_id)
        .where(ExpedienteObra.tenant_id == current_user.tenant_id)
    )
    superficie = result.scalar_one_or_none()
    if not superficie:
        raise HTTPException(status_code=404, detail="Superficie no encontrada")
    return superficie


from app.core.authorization import WRITE_ROLES, APPROVAL_ROLES, authorize, authorize_by_id


async def require_mutation_access(request: Request, user: User = Depends(get_current_user),
                                  db: AsyncSession = Depends(get_db)):
    if request.method not in {'GET', 'HEAD', 'OPTIONS'}:
        await authorize_by_id(db, user.id, user.tenant_id)


def module_access(app_id: str):
    """Apply the launcher policy to HTTP and authorize mutations by current role."""
    async def dependency(request: Request, user: User = Depends(get_current_user),
                         db: AsyncSession = Depends(get_db)):
        from app.models.user import Tenant
        from app.services.entitlements_service import EntitlementsService
        tenant = await db.get(Tenant, user.tenant_id)
        if tenant is None or not tenant.is_active:
            raise HTTPException(403, "Organización inactiva")
        await EntitlementsService(db).verificar_modulo(tenant, user.role, app_id)
        if request.method not in {"GET", "HEAD", "OPTIONS"}:
            authorize(user)
    return dependency


async def require_approval_role(user: User = Depends(get_current_user)):
    authorize(user, 'approve')
    return user
