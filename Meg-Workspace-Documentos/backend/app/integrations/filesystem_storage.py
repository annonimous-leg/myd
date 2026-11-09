"""Real shared filesystem storage for development/staging BIM acceptance."""
import asyncio
import os
import shutil
from pathlib import Path
import tempfile
from app.config import settings
from app.core.errors import ErrorCode, MegalodonException


class FilesystemBIMStorage:
    def path(self, key):
        root = Path(settings.BIM_LOCAL_STORAGE_PATH).resolve()
        path = (root / key).resolve()
        if not key or Path(key).is_absolute() or root not in path.parents:
            raise MegalodonException(ErrorCode.ARCHIVO_ERROR, 'Ruta de archivo inválida')
        return path

    async def subir(self, key, contenido, content_type='application/octet-stream', *, overwrite=True):
        target = self.path(key)
        def write():
            target.parent.mkdir(parents=True, exist_ok=True)
            temporary = None
            try:
                with tempfile.NamedTemporaryFile(dir=target.parent, delete=False) as stream:
                    temporary = stream.name
                    if hasattr(contenido, "read"):
                        shutil.copyfileobj(contenido, stream, length=1024 * 1024)
                    else:
                        stream.write(contenido)
                    stream.flush()
                    os.fsync(stream.fileno())
                if overwrite:
                    os.replace(temporary, target)
                else:
                    os.link(temporary, target)
            finally:
                if temporary and os.path.exists(temporary):
                    os.unlink(temporary)
        await asyncio.to_thread(write)
        return key

    async def descargar(self, key):
        return await asyncio.to_thread(self.path(key).read_bytes)

    async def eliminar(self, keys):
        for key in keys:
            await asyncio.to_thread(self.path(key).unlink, missing_ok=True)
