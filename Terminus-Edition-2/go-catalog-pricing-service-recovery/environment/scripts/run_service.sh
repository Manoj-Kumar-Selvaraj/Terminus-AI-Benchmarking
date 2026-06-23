#!/usr/bin/env bash
set -Eeuo pipefail
cd /app
exec /usr/local/go/bin/go run ./cmd/pricingd
