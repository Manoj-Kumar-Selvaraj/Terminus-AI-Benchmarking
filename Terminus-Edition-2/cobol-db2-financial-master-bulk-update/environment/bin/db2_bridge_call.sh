#!/usr/bin/env bash
set -eu
if [ -f /tmp/finbulk_bridge.env ]; then
    set -a
    # shellcheck disable=SC1091
    . /tmp/finbulk_bridge.env
    set +a
fi
export PYTHONPATH="/app/tools"
export BRIDGE_RESULT="${BRIDGE_RESULT:-/tmp/finbulk_bridge.out}"
export BRIDGE_DB="${BRIDGE_DB:-${FINBULK_DB:-}}"
export BRIDGE_OUT="${BRIDGE_OUT:-${FINBULK_OUT:-}}"
export BRIDGE_BATCH="${BRIDGE_BATCH:-${FINBULK_BATCH:-}}"
exec python3 /app/tools/db2_bridge.py "$@"
