#!/usr/bin/env bash
set -euo pipefail
: "${DATABASE_URL:?DATABASE_URL is required}"
: "${BACKUP_DIR:?BACKUP_DIR is required}"
mkdir -p "$BACKUP_DIR"
STAMP="$(date -u +%Y%m%dT%H%M%SZ)"
FILE="$BACKUP_DIR/megalodon_${STAMP}.dump"
pg_dump --format=custom --no-owner --no-privileges "$DATABASE_URL" > "$FILE"
sha256sum "$FILE" > "$FILE.sha256"
echo "$FILE"
