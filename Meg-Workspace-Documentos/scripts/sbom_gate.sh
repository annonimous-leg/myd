#!/usr/bin/env bash
set -euo pipefail
ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
OUT="$ROOT/artifacts/sbom"
mkdir -p "$OUT"

command -v syft >/dev/null 2>&1 || { echo "syft is required for the production SBOM gate" >&2; exit 2; }
syft dir:"$ROOT" -o cyclonedx-json > "$OUT/megalodon.cyclonedx.json"
