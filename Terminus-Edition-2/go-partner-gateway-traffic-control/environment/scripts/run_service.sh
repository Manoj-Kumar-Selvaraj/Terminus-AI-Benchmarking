#!/usr/bin/env bash
set -Eeuo pipefail
exec /usr/local/go/bin/go run ./cmd/gatewayd
