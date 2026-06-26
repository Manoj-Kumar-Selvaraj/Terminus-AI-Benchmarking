#!/usr/bin/env bash
set -Eeuo pipefail
if [[ $# -ne 1 ]]; then
  echo "usage: $0 STATE_DIR" >&2
  exit 2
fi
exec /app/bin/rolloutctl status --state "$1"
