"""Bounded extraction of manifest and signed CSVs; never extracts received SQL."""
from pathlib import Path, PurePosixPath
from zipfile import BadZipFile, ZipFile

from app.services.catalogo_package import CatalogPackageError, SCHEMA

MAX_UPLOAD = 30 * 1024 * 1024
MAX_EXPANDED = 120 * 1024 * 1024
ALLOWED = {'manifest.json'} | {f'data/{table}.csv' for table in SCHEMA}


def extract_package(stream, destination: Path) -> Path:
    try:
        with ZipFile(stream) as archive:
            infos = archive.infolist()
            if len(infos) > 500 or len({i.filename for i in infos}) != len(infos):
                raise CatalogPackageError('ZIP duplicado o con demasiados archivos')
            manifests = [i for i in infos if PurePosixPath(i.filename).name == 'manifest.json']
            if len(manifests) != 1:
                raise CatalogPackageError('El ZIP debe contener un solo manifiesto')
            prefix = str(PurePosixPath(manifests[0].filename).parent)
            prefix = '' if prefix == '.' else prefix + '/'
            chosen = []
            total = 0
            for info in infos:
                path = PurePosixPath(info.filename)
                if path.is_absolute() or '..' in path.parts or '\\' in info.filename:
                    raise CatalogPackageError('Ruta inválida en ZIP')
                if info.is_dir() or not info.filename.startswith(prefix):
                    continue
                relative = info.filename[len(prefix):]
                if relative not in ALLOWED:
                    continue
                total += info.file_size
                if info.flag_bits & 1 or total > MAX_EXPANDED:
                    raise CatalogPackageError('ZIP cifrado o expansión excesiva')
                chosen.append((info, relative))
            if {r for _, r in chosen} != ALLOWED:
                raise CatalogPackageError('Faltan CSV del contrato en el ZIP')
            for info, relative in chosen:
                target = destination / relative
                target.parent.mkdir(parents=True, exist_ok=True)
                target.write_bytes(archive.read(info))
            # Manifests may also sign reports/SQL; verification hashes those
            # files, but never executes them. Copy only signed in-package files.
            from app.services.catalogo_package import strict_json
            manifest = strict_json((destination / 'manifest.json').read_text())
            names = {i.filename: i for i in infos}
            for relative in manifest.get('files', {}):
                path = PurePosixPath(relative)
                if path.is_absolute() or '..' in path.parts or '\\' in relative:
                    raise CatalogPackageError('Ruta inválida en manifiesto')
                if relative in ALLOWED:
                    continue
                info = names.get(prefix + relative)
                if info is None or info.is_dir():
                    raise CatalogPackageError('Archivo firmado ausente')
                total += info.file_size
                if info.flag_bits & 1 or total > MAX_EXPANDED:
                    raise CatalogPackageError('ZIP cifrado o expansión excesiva')
                target = destination / relative
                target.parent.mkdir(parents=True, exist_ok=True)
                target.write_bytes(archive.read(info))
            return destination
    except BadZipFile as exc:
        raise CatalogPackageError('ZIP corrupto') from exc
