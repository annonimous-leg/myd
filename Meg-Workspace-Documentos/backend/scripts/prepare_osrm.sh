#!/usr/bin/env bash
# Create self-hosted OSRM routing graphs from an operator-supplied OSM extract.
# NO public OSRM demo server, NO automatic downloading of data.
set -Eeuo pipefail

if [[ $# -ne 1 || ! "$1" =~ ^[A-Za-z0-9_-]+$ ]]; then
  echo "Usage: bash scripts/prepare_osrm.sh <dataset-basename>" >&2
  echo "Place data/osrm/<dataset-basename>.osm.pbf first." >&2
  exit 2
fi

dataset="$1"
script_dir="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"
backend_dir="$(cd -- "$script_dir/.." && pwd)"
data_dir="$backend_dir/data/osrm"
pbf="$data_dir/$dataset.osm.pbf"
image="${OSRM_IMAGE:-ghcr.io/project-osrm/osrm-backend:26.10}"

if [[ ! -s "$pbf" ]]; then
  echo "OSM extract not found: $pbf" >&2
  exit 1
fi
if ! command -v docker >/dev/null 2>&1; then
  echo "Docker is required for the pinned OSRM build" >&2
  exit 1
fi

# Running as the current user avoids root-owned output on the host.
run_osrm() {
  docker run --rm --user "$(id -u):$(id -g)" \
    -v "$data_dir:/data" "$image" "$@"
}

echo "Processing $pbf using $image (driving profile; OSM ODbL 1.0)"
run_osrm osrm-extract -p /opt/car.lua "/data/$dataset.osm.pbf"
run_osrm osrm-partition "/data/$dataset.osrm"
run_osrm osrm-customize "/data/$dataset.osrm"

# No fake success based on Docker exit status alone.
if [[ ! -s "$data_dir/$dataset.osrm.partition" ]]; then
  echo "OSRM partition output missing; inspect preprocessing logs" >&2
  exit 1
fi

echo "OSRM preprocessing complete. Use OSRM_DATASET_BASENAME=$dataset."
echo "Review dataset license, date, geographic coverage and graph statistics before deployment."
