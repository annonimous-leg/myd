# Copyright © 2026 Cristian Rodriguez
# All rights reserved.
# Unauthorized copying, modification, distribution, or use is prohibited
# without prior written permission.

"""
Schemas de autenticación.
"""
from typing import Optional
from pydantic import BaseModel, EmailStr, Field

from app.models.user import UserRole


class Token(BaseModel):
    access_token: str
    token_type: str = "bearer"
    refresh_token: str
    expires_in: int


class TokenPayload(BaseModel):
    sub: Optional[str] = None
    exp: Optional[int] = None


# F-05 de la auditoría 2026-09-01: el hallazgo decía que POST /register
# (api/v1/auth.py) recibía este UserRegister (tenant_id/rfc/curp/role) pero
# intentaba leer data.company_name/company_slug/company_rfc, que no existen
# aquí -- concluyendo que el alta pública estaba rota.
#
# Verificado leyendo api/v1/auth.py de punta a punta: ese router NUNCA
# importa nada de este módulo. Define su PROPIA clase local `UserRegister`
# (con company_name/company_slug/company_rfc, y sin tenant_id/role -- ver el
# docstring de esa clase, que documenta por qué se le quitaron esos dos
# campos: antes permitían unirse a un tenant ajeno y autoasignarse
# role="admin"/"superadmin"). Todo el módulo api/v1/auth.py está construido
# así: Token, UserRegister, UserOut, RefreshRequest también están
# redefinidos localmente ahí y ninguno importa de aquí. En runtime, POST
# /register usa la clase local (ya correcta) -- no esta.
#
# El UserRegister que vivía aquí (tenant_id + role client-settable) es
# exactamente la forma insegura que ese docstring dice haber corregido, y
# nada en el backend la importaba (grep sin resultados fuera de este
# archivo y su re-export en schemas/__init__.py). Se eliminó en vez de
# corregirla para no dejar dos versiones del mismo contrato -- una seria y
# vigente en api/v1/auth.py, otra vieja e insegura aquí que un import futuro
# (o una auditoría automática, como esta) podría tomar por la real.


class UserOut(BaseModel):
    id: str
    email: str
    full_name: str
    role: str
    is_active: bool
    tenant_id: str

    class Config:
        from_attributes = True


class UserUpdate(BaseModel):
    full_name: Optional[str] = None
    role: Optional[UserRole] = None
    is_active: Optional[bool] = None


class RefreshRequest(BaseModel):
    refresh_token: str


class LoginRequest(BaseModel):
    email: EmailStr
    password: str
