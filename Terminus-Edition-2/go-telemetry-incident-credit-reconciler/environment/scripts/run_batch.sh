#!/bin/bash
set -euo pipefail
mkdir -p /app/build /app/out
GO_BIN="/usr/local/go/bin/go"
if [ ! -x "$GO_BIN" ]; then
    GO_BIN="go"
fi
"$GO_BIN" build -o /app/build/stream-incident-reconcile /app/cmd/reconcile/main.go
/app/build/stream-incident-reconcile
