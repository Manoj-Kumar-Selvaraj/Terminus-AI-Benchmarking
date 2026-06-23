#!/usr/bin/env bash
set -euo pipefail

mkdir -p /app/out /app/build
GO_BIN="${GO_BIN:-/usr/local/go/bin/go}"
"$GO_BIN" build -o /app/build/reconcile /app/cmd/reconcile
/app/build/reconcile
