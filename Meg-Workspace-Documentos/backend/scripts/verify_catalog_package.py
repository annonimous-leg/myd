"""python -m scripts.verify_catalog_package PACKAGE --originals PDF_DIRECTORY"""
import argparse
import json
from pathlib import Path

from app.services.catalogo_package import verify_package


def main():
    parser = argparse.ArgumentParser(description='Verificar fuentes sin ejecutar SQL del paquete')
    parser.add_argument('package', type=Path)
    parser.add_argument('--originals', required=True, type=Path)
    args = parser.parse_args()
    print(json.dumps(verify_package(args.package, args.originals).report(), indent=2))


if __name__ == '__main__':
    main()
