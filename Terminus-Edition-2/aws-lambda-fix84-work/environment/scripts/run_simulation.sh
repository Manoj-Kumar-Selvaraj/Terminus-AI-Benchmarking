#!/usr/bin/env bash
set -euo pipefail
exec python3 "${APP_ROOT:-/app}/scripts/run_simulation.py" "$@"
