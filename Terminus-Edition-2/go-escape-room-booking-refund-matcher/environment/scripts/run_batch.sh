#!/usr/bin/env bash
set -euo pipefail
cd /app
mkdir -p /app/build /app/out
/usr/local/go/bin/go build -o /app/build/reconcile /app/cmd/reconcile
/app/build/reconcile
