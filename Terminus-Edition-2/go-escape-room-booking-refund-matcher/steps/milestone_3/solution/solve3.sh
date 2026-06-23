#!/usr/bin/env bash
set -euo pipefail
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
mkdir -p /app/internal/reconcile /app/cmd/reconcile
cp "$SCRIPT_DIR/main.go" /app/cmd/reconcile/main.go
cp "$SCRIPT_DIR/oracle_reconcile.go" /app/internal/reconcile/reconcile.go
/usr/local/go/bin/gofmt -w /app/cmd/reconcile/main.go /app/internal/reconcile/reconcile.go
