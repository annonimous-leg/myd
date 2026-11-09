"""Cifrado simétrico para payloads efímeros (wormhole dead-drops).

FASE 3 (2026-08-02). La clave Fernet se deriva de SECRET_KEY (el mismo
secreto que ya comparten Megalodon y Tezcatlipoca para JWT) vía
HKDF-SHA256, en vez de pedir un secreto nuevo que alguien tendría que
recordar rotar por separado.

Efecto secundario intencional: si SECRET_KEY rota, los dead-drops
cifrados con la clave anterior dejan de poder descifrarse. Para un
dead-drop (TTL máximo 24h) eso es aceptable -- es justo el tipo de dato
que no debería sobrevivir una rotación de secretos de cualquier forma.
No lo uses para nada con retención más larga que eso sin revisar este
supuesto primero.
"""
import base64

from app.config import settings
from cryptography.fernet import Fernet, InvalidToken
from cryptography.hazmat.primitives import hashes
from cryptography.hazmat.primitives.kdf.hkdf import HKDF

_HKDF_INFO = b"tezcatlipoca-wormhole-dead-drop-v1"
_HKDF_SALT = b"megalodon-tezcatlipoca-fase3"


def _derive_fernet_key(secret_key: str) -> bytes:
    hkdf = HKDF(
        algorithm=hashes.SHA256(),
        length=32,
        salt=_HKDF_SALT,
        info=_HKDF_INFO,
    )
    raw = hkdf.derive(secret_key.encode("utf-8"))
    return base64.urlsafe_b64encode(raw)


def _get_fernet() -> Fernet:
    secret_key = settings.SECRET_KEY
    if not secret_key:
        raise RuntimeError(
            "SECRET_KEY no está configurado -- no se puede cifrar/descifrar "
            "payloads de dead-drop sin él."
        )
    return Fernet(_derive_fernet_key(secret_key))


def encrypt_payload(plaintext: str) -> bytes:
    return _get_fernet().encrypt(plaintext.encode("utf-8"))


def decrypt_payload(ciphertext: bytes) -> str:
    """Levanta cryptography.fernet.InvalidToken si el secreto rotó o el
    dato está corrupto -- el llamador debe tratarlo como 'ya no
    disponible', no como error 500 genérico."""
    return _get_fernet().decrypt(ciphertext).decode("utf-8")
