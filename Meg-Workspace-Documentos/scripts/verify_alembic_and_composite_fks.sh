#!/usr/bin/env bash
# Verifica alembic upgrade head + FKs compuestas en PostgreSQL real.
set -euo pipefail

ROOT="$(cd "$(dirname "$0")/.." && pwd)"
BACKEND="$ROOT/backend"
export PYTHONPATH="$BACKEND"
export DATABASE_URL="${DATABASE_URL:-postgresql+asyncpg://megalodon:megalodon@localhost:5432/megalodon}"
export PATH="${PATH}:$HOME/.local/bin"

echo "=== 1. Structlog ==="
python3 -c "import structlog; print('structlog', structlog.__version__)"

echo "=== 2. Alembic upgrade head ==="
cd "$BACKEND"
alembic upgrade head
alembic current

echo "=== 3. Composite FKs (pg_constraint) ==="
PGPASSWORD="${PGPASSWORD:-megalodon}" psql -h "${PGHOST:-localhost}" -U "${PGUSER:-megalodon}" -d "${PGDATABASE:-megalodon}" -f "$ROOT/scripts/verify_composite_fks_postgres.sql"

echo "=== DONE ==="
