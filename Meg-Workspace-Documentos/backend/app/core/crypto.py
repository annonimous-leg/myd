# Copyright © 2026 Cristian Rodriguez
# All rights reserved.
# Unauthorized copying, modification, distribution, or use is prohibited
# without prior written permission.

"""
Utilidades criptográficas para cifrado, hashing y Merkle trees.

Envelope encryption implementada en esta sesión:
  - cifrar_sobre() genera una DEK (Data Encryption Key) aleatoria por
    documento, cifra el contenido con AES-256-GCM, y devuelve la DEK
    cifrada con la KEK (Key Encryption Key) derivada de la master key
    del sistema. Solo se persiste la DEK cifrada (encrypted_dek) -- la
    DEK en plano nunca toca la BD.
  - descifrar_sobre() recibe la DEK cifrada, la descifra con la KEK, y
    usa la DEK en plano para descifrar el contenido.
  - La KEK se deriva con HKDF (SHA-256) desde la ENCRYPTION_MASTER_KEY
    del entorno. Si no está definida se cae back a SECRET_KEY (no ideal
    para producción, pero no rompe la app en dev). El salt de HKDF es
    el UUID del tenant para que cada tenant tenga su propia KEK lógica.
"""
import hashlib
import hmac
import os
from typing import List, Optional, Tuple

try:
    from cryptography.fernet import Fernet
    from cryptography.hazmat.primitives import hashes
    from cryptography.hazmat.primitives.kdf.pbkdf2 import PBKDF2HMAC
    from cryptography.hazmat.primitives.kdf.hkdf import HKDF
    from cryptography.hazmat.primitives.ciphers.aead import AESGCM
    CRYPTO_AVAILABLE = True
except ImportError:
    CRYPTO_AVAILABLE = False


def calcular_hash_sha256(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def calcular_merkle_root(hashes: List[str]) -> str:
    if not hashes:
        return ""
    current_level = [bytes.fromhex(h) for h in hashes]
    while len(current_level) > 1:
        next_level = []
        for i in range(0, len(current_level), 2):
            left = current_level[i]
            right = current_level[i + 1] if i + 1 < len(current_level) else left
            combined = hashlib.sha256(left + right).digest()
            next_level.append(combined)
        current_level = next_level
    return current_level[0].hex()


# ─── Envelope encryption ──────────────────────────────────────────────────────

def _obtener_master_key_bytes() -> bytes:
    """Lee ENCRYPTION_MASTER_KEY del entorno (>=32 chars). En dev puede
    ser la misma SECRET_KEY, pero en producción DEBEN ser distintas."""
    from app.config import settings
    master = getattr(settings, "ENCRYPTION_MASTER_KEY", None) or settings.SECRET_KEY
    return master.encode()[:32].ljust(32, b"\x00")  # exactamente 32 bytes


def _derivar_kek(tenant_id: str) -> bytes:
    """Deriva una KEK de 256 bits con HKDF, usando tenant_id como info
    para que cada tenant tenga su propia KEK lógica sin necesitar
    múltiples master keys."""
    if not CRYPTO_AVAILABLE:
        raise ImportError("cryptography no instalado")
    hkdf = HKDF(
        algorithm=hashes.SHA256(),
        length=32,
        salt=None,
        info=f"megalodon-kek-{tenant_id}".encode(),
    )
    return hkdf.derive(_obtener_master_key_bytes())


def cifrar_sobre(
    data: bytes,
    tenant_id: str,
) -> Tuple[bytes, bytes, bytes, str]:
    """Cifra `data` con envelope encryption.

    Retorna: (ciphertext, nonce, tag, encrypted_dek_hex)

    - ciphertext/nonce/tag van a Supabase Storage (igual que antes).
    - encrypted_dek_hex se guarda en Documento.encryption_key_enc (columna
      nueva). NUNCA se guarda la DEK en plano.
    """
    if not CRYPTO_AVAILABLE:
        raise ImportError("cryptography no instalado")

    # 1. Generar DEK aleatoria
    dek = AESGCM.generate_key(bit_length=256)  # 32 bytes

    # 2. Cifrar el contenido con la DEK
    aesgcm = AESGCM(dek)
    nonce = os.urandom(12)
    ct_with_tag = aesgcm.encrypt(nonce, data, None)
    tag = ct_with_tag[-16:]
    ciphertext = ct_with_tag[:-16]

    # 3. Cifrar la DEK con la KEK derivada del tenant (wrap)
    kek = _derivar_kek(tenant_id)
    kek_aesgcm = AESGCM(kek)
    wrap_nonce = os.urandom(12)
    encrypted_dek = wrap_nonce + kek_aesgcm.encrypt(wrap_nonce, dek, None)
    encrypted_dek_hex = encrypted_dek.hex()

    return ciphertext, nonce, tag, encrypted_dek_hex


def descifrar_sobre(
    ciphertext: bytes,
    nonce: bytes,
    tag: bytes,
    encrypted_dek_hex: str,
    tenant_id: str,
) -> bytes:
    """Descifra `ciphertext` con envelope encryption.

    Requiere `encrypted_dek_hex` (de Documento.encryption_key_enc) y el
    tenant_id para derivar la KEK correcta.
    """
    if not CRYPTO_AVAILABLE:
        raise ImportError("cryptography no instalado")

    # 1. Unwrap DEK
    kek = _derivar_kek(tenant_id)
    kek_aesgcm = AESGCM(kek)
    encrypted_dek = bytes.fromhex(encrypted_dek_hex)
    wrap_nonce = encrypted_dek[:12]
    dek_ct = encrypted_dek[12:]
    dek = kek_aesgcm.decrypt(wrap_nonce, dek_ct, None)

    # 2. Descifrar contenido
    aesgcm = AESGCM(dek)
    return aesgcm.decrypt(nonce, ciphertext + tag, None)


# ─── Primitivas legacy (usadas por FirmaService, no por DocumentoService) ─────

def cifrar_contenido(data: bytes, key: Optional[bytes] = None) -> Tuple[bytes, bytes, bytes]:
    """Cifrado directo con clave externa (uso: FirmaService). Para documentos
    de usuario usar cifrar_sobre()."""
    if not CRYPTO_AVAILABLE:
        raise ImportError("cryptography no instalado")
    if key is None:
        key = AESGCM.generate_key(bit_length=256)
    aesgcm = AESGCM(key)
    nonce = os.urandom(12)
    ct_with_tag = aesgcm.encrypt(nonce, data, None)
    tag = ct_with_tag[-16:]
    ciphertext = ct_with_tag[:-16]
    return ciphertext, nonce, tag


def descifrar_contenido(ciphertext: bytes, nonce: bytes, tag: bytes, key: Optional[bytes] = None) -> bytes:
    if not CRYPTO_AVAILABLE:
        raise ImportError("cryptography no instalado")
    if key is None:
        raise ValueError("Se requiere clave para descifrar")
    aesgcm = AESGCM(key)
    return aesgcm.decrypt(nonce, ciphertext + tag, None)


def generar_clave_derivada(password: str, salt: Optional[bytes] = None) -> Tuple[bytes, bytes]:
    if not CRYPTO_AVAILABLE:
        raise ImportError("cryptography no instalado")
    import base64
    if salt is None:
        salt = os.urandom(16)
    kdf = PBKDF2HMAC(
        algorithm=hashes.SHA256(),
        length=32,
        salt=salt,
        iterations=480000,
    )
    key = base64.urlsafe_b64encode(kdf.derive(password.encode()))
    return key, salt
