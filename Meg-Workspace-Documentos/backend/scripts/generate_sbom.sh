#!/usr/bin/env bash
set -Eeuo pipefail
: "${SBOM_OUT:=sbom}"
mkdir -p "$SBOM_OUT"
command -v syft >/dev/null || { echo "syft is required to generate the SBOM" >&2; exit 2; }
syft dir:. -o cyclonedx-json > "$SBOM_OUT/megalodon-backend.cdx.json"
