#!/usr/bin/env bash
set -euo pipefail
ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT"
python3 -m venv --clear .venv
source .venv/bin/activate
python -m pip install --upgrade pip setuptools wheel
python -m pip install --no-cache-dir -e '.[dev]'
python -m pip check
python - <<'PY'
import importlib
mods = [
  'fastapi','sqlalchemy','asyncpg','redis','celery','bcrypt','jwt','geoalchemy2',
  'ifcopenshell','shapely','geopandas','pyproj','numpy','scipy','pandas',
  'pyhanko','pytesseract','PIL','cv2','httpx','aiohttp','supabase','structlog',
  'ee','twilio','pdf2image','websockets'
]
for name in mods:
    importlib.import_module(name)
print('production dependency import gate: OK')
PY
