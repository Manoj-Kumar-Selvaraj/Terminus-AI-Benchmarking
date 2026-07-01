#!/usr/bin/env bash
set -Eeuo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
mkdir -p /app/recovery
cp "${SCRIPT_DIR}/main.go" /app/recovery/main.go
/usr/local/go/bin/gofmt -w /app/recovery/main.go
