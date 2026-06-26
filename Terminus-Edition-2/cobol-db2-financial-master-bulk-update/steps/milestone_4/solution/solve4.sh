#!/usr/bin/env bash
set -Eeuo pipefail
cd /app
export PATH="/usr/local/go/bin:${PATH}"
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cp "${SCRIPT_DIR}/profile_m4.go" /app/internal/finbulk/profile.go
go build -o /app/build/finbulk /app/cmd/finbulk
