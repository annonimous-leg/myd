"""Build an immutable private SICT package; import with import_catalog_package.

Example: python -m scripts.prepare_sict_catalog --servicios /private/TServicio-2026.pdf --destination /private/edicion
No original PDF or extracted catalogue is committed to the repository.
"""
import argparse
from pathlib import Path
from app.services.sict_catalogo import PROFILES, extract_source, write_package
from app.services.catalogo_package import SCHEMA


def main():
    parser = argparse.ArgumentParser(description='Normalizar tabuladores SICT DGST 2026 con evidencia original')
    for kind in PROFILES: parser.add_argument('--' + kind, type=Path)
    parser.add_argument('--destination', type=Path, required=True)
    args = parser.parse_args()
    if args.destination.exists(): parser.error('El destino ya existe; no se sobrescriben ediciones')
    records = {t: [] for t in SCHEMA}
    for kind in PROFILES:
        pdf = getattr(args, kind)
        if pdf:
            source = extract_source(pdf, kind)
            for table in records: records[table].extend(source[table])
    if not records['fuente']: parser.error('Seleccione al menos un tabulador original')
    write_package(args.destination, records)
    print({t: len(rows) for t, rows in records.items()})


if __name__ == '__main__': main()
