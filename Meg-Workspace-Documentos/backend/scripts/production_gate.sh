#!/usr/bin/env bash
set -euo pipefail
ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT"
python3 scripts/production_gate.py
if command -v npm >/dev/null 2>&1; then
  cd "$ROOT/../frontend/app"
  npm ci
  npm run build
  npm run lint
fi
echo "PRODUCTION GATE: static/local checks passed; external infra gates must still run against real services."
