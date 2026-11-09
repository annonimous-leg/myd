#!/usr/bin/env bash
# Bootstrap único del path DB-driven de procedimiento + garantías.
# Fail-fast. No inventa datos: solo aplica migración y CSV/corpus seeds.
set -euo pipefail
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
cd "$ROOT"

echo "==> [1/4] alembic upgrade head"
alembic upgrade head

echo "==> [2/4] export CSV seeds (idempotent refresh from ETL sources)"
python scripts/export_procedure_seed_csv.py

echo "==> [3/4] load CSV → procedure_thresholds / exceptions / profiles / garantias"
python -m scripts.load_seeds_from_csv
# incluye thresholds, exceptions, profiles, garantias, catalog

echo "==> [4/4] offline + sqlite runtime tests"
python scripts/verify_procedure_db_driven_offline.py
python -m pytest tests/procurement/test_db_driven_runtime_sqlite.py -q --noconftest

echo "BOOTSTRAP OK"
echo "NOTA: umbrales federales siguen CANDIDATO hasta confirmar Anexo 9 primario."
echo "      recommend-procedure NO materializa procedure_type si es_candidato=true."
