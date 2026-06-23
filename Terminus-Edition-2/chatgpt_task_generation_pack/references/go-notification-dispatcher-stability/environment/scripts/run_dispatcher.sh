#!/usr/bin/env bash
set -euo pipefail
cd /app
/usr/local/go/bin/go build -o /app/build/notifierd ./cmd/notifierd
exec /app/build/notifierd
