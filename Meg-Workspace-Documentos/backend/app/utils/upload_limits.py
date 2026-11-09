# Copyright © 2026 Cristian Rodriguez
# All rights reserved.
# Unauthorized copying, modification, distribution, or use is prohibited
# without prior written permission.

"""Lectura de archivos subidos con límite de tamaño real.

Hallazgo (auditoría externa 2026-08-27, verificado leyendo el código):
varias rutas hacían `contenido = await file.read()` -- lee TODO el archivo
a memoria antes de que exista oportunidad de aplicar cualquier límite.
Los límites de configuración (IFC_MAX_FILE_SIZE_MB,
TENDER_SOURCE_MAX_FILE_SIZE_MB) existen, pero en esas rutas no se
consultaban antes de leer -- un usuario autenticado podía enviar un
archivo arbitrariamente grande y el proceso lo cargaba entero a RAM antes
de que hubiera chance de rechazarlo.

`read_upload_with_limit()` reemplaza ese patrón: lee en chunks y aborta en
cuanto se cruza el límite, sin haber materializado el resto del archivo en
memoria. `UploadFile.read()` sin argumento de tamaño no permite
inspeccionar cuánto se ha leído hasta que termina -- por eso se lee en
bloques con `file.read(chunk_size)`, no con una sola llamada.

Confirmado con `grep -rn "await file.read()\\|await archivo.read()" app/api`
que existen 5 puntos de este patrón: bim.py:206 (ya migrado a este
helper), expedientes.py:194, ocr.py:40, topografia.py:233 y 393 (pendientes
-- mismo patrón a aplicar, no se tocaron en esta ronda para no apurar un
cambio en 4 rutas distintas sin revisar el contexto específico de cada una).
"""
from __future__ import annotations

from fastapi import UploadFile

from app.core.errors import ErrorCode, MegalodonException

_DEFAULT_CHUNK_SIZE = 1024 * 1024  # 1 MiB


async def read_upload_with_limit(
    file: UploadFile,
    max_size_mb: int,
    chunk_size: int = _DEFAULT_CHUNK_SIZE,
) -> bytes:
    """Lee `file` en bloques, abortando apenas se exceda `max_size_mb`.

    A diferencia de `await file.read()` seguido de un chequeo de
    `len(contenido)`, esto nunca mantiene en memoria más de
    `max_size_mb + chunk_size` bytes del archivo real antes de rechazarlo
    -- el resto del stream ni se lee.

    Lanza MegalodonException (ARC-7000, 413) si se excede el límite.
    """
    max_bytes = max_size_mb * 1024 * 1024
    chunks: list[bytes] = []
    total = 0

    while True:
        chunk = await file.read(chunk_size)
        if not chunk:
            break
        total += len(chunk)
        if total > max_bytes:
            await file.close()
            raise MegalodonException(
                ErrorCode.ARCHIVO_ERROR,
                f"El archivo '{file.filename}' excede el límite de {max_size_mb} MB permitido.",
                status_code=413,
                details={"limite_mb": max_size_mb, "filename": file.filename},
            )
        chunks.append(chunk)

    return b"".join(chunks)


async def validate_upload_with_limit(
    file: UploadFile,
    max_size_mb: int,
    chunk_size: int = _DEFAULT_CHUNK_SIZE,
) -> int:
    """Validate an UploadFile without accumulating its body in application RAM.

    Starlette already spools multipart UploadFile bodies. This pass counts the
    spooled stream in bounded chunks, rewinds it, and returns the exact byte
    length so storage clients can consume the file object directly.
    """
    max_bytes = max_size_mb * 1024 * 1024
    total = 0
    await file.seek(0)
    try:
        while True:
            chunk = await file.read(chunk_size)
            if not chunk:
                break
            total += len(chunk)
            if total > max_bytes:
                raise MegalodonException(
                    ErrorCode.ARCHIVO_ERROR,
                    f"El archivo '{file.filename}' excede el límite de {max_size_mb} MB permitido.",
                    status_code=413,
                    details={"limite_mb": max_size_mb, "filename": file.filename},
                )
    finally:
        await file.seek(0)
    return total
