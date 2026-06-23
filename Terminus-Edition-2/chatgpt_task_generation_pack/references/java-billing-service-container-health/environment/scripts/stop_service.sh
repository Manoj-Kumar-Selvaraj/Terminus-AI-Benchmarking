#!/usr/bin/env bash
set -euo pipefail
for pidfile in /app/run/billing.pid /app/run/h2.pid; do
  if [ -f "$pidfile" ]; then
    kill "$(cat "$pidfile")" 2>/dev/null || true
    rm -f "$pidfile"
  fi
done
