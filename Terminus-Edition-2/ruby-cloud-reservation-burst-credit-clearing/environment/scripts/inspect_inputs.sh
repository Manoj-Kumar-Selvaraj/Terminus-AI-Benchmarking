#!/usr/bin/env bash
set -Eeuo pipefail
for f in /app/data/*.csv /app/config/*.csv; do echo "--- $f"; head -n 5 "$f"; done
