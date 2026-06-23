#!/usr/bin/env bash
set -euo pipefail
exec /usr/local/go/bin/go run ./cmd/gatewayd -config /app/config/gateway.json
