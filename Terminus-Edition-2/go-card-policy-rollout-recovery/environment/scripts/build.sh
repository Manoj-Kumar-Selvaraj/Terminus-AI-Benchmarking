#!/usr/bin/env bash
set -Eeuo pipefail
cd /app
mkdir -p /app/bin
/usr/local/go/bin/go build -trimpath -o /app/bin/rolloutctl ./cmd/rolloutctl
/usr/local/go/bin/go build -trimpath -o /app/bin/gatewayd ./cmd/gatewayd
