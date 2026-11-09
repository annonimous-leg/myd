#!/usr/bin/env bash
set -Eeuo pipefail
umask 077
exec python "$(dirname "${BASH_SOURCE[0]}")/postgres_backup.py" backup
