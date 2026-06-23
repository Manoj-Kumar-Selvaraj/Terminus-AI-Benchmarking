#!/usr/bin/env bash
set -euo pipefail
mkdir -p /app/data /app/run
if [ -f /app/run/billing.pid ]; then
  kill "$(cat /app/run/billing.pid)" 2>/dev/null || true
fi
if [ -f /app/run/h2.pid ]; then
  kill "$(cat /app/run/h2.pid)" 2>/dev/null || true
fi
bash /app/scripts/start_h2_db.sh >/app/run/h2.log 2>&1 &
echo $! >/app/run/h2.pid
bash /app/scripts/wait_for_h2.sh
java @"${JAVA_OPTIONS_FILE:-/app/config/jvm.options}" -jar /app/build/billing-service.jar >/app/run/billing.log 2>&1 &
echo $! >/app/run/billing.pid
sleep 0.2
if ! kill -0 "$(cat /app/run/billing.pid)" 2>/dev/null; then
  cat /app/run/billing.log >&2
  exit 1
fi
