#!/usr/bin/env bash
set -eu
if [ -f /tmp/finbulk_bridge.env ]; then
    set -a
    # shellcheck disable=SC1091
    . /tmp/finbulk_bridge.env
    set +a
fi
export BRIDGE_RESULT="${BRIDGE_RESULT:-/tmp/finbulk_bridge.out}"
export BRIDGE_DB="${BRIDGE_DB:-${FINBULK_DB:-}}"
export BRIDGE_OUT="${BRIDGE_OUT:-${FINBULK_OUT:-}}"
export BRIDGE_BATCH="${BRIDGE_BATCH:-${FINBULK_BATCH:-}}"
BIN="${DB2_BRIDGE_BIN:-/app/build/db2bridge}"
if [[ ! -x "$BIN" ]]; then
    (cd /app && go build -o "$BIN" ./cmd/db2bridge)
fi
exec "$BIN" "$@"
