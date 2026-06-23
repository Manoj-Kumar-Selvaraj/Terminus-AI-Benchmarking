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
sleep 1
java @"${JAVA_OPTIONS_FILE:-/app/config/jvm.options}" -jar /app/build/billing-service.jar >/app/run/billing.log 2>&1 &
echo $! >/app/run/billing.pid
