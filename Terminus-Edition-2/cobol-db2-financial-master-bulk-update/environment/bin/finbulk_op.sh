#!/usr/bin/env bash
set -eu
op="${1:?operation required}"
shift
{
  printf 'BRIDGE_DB=%s\n' "${FINBULK_DB:-}"
  printf 'BRIDGE_OUT=%s\n' "${FINBULK_OUT:-}"
  if [[ -n "${FINBULK_BATCH:-}" ]]; then
    printf 'BRIDGE_BATCH=%s\n' "${FINBULK_BATCH}"
  fi
  while [[ $# -gt 0 ]]; do
    printf '%s\n' "$1"
    shift
  done
} > /tmp/finbulk_bridge.env
exec bash /app/bin/db2_bridge_call.sh "$op"
