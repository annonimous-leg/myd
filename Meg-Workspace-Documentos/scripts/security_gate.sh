#!/usr/bin/env bash
set -euo pipefail
ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT"

command -v pip-audit >/dev/null 2>&1 || { echo "pip-audit is required" >&2; exit 2; }
command -v bandit >/dev/null 2>&1 || { echo "bandit is required" >&2; exit 2; }

cd backend
pip-audit --strict
bandit -q -r app tezcatlipoca -lll
cd ../frontend/app
npm audit --audit-level=high
