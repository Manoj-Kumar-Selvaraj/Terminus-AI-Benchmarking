#!/usr/bin/env bash
set -Eeuo pipefail
printf '%s\n' '--- controller startup ---'
cat /app/evidence/controller_startup.log
printf '%s\n' '--- retry audit ---'
cat /app/evidence/gateway_audit_after_retry.json
printf '%s\n' '--- worker overlap ---'
cat /app/evidence/dual_worker_trace.log
