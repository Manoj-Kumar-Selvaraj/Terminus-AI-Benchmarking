#!/usr/bin/env bash
set -Eeuo pipefail
cd /app
export PATH="/usr/local/go/bin:${PATH}"
SOL_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cp "${SOL_DIR}/profile_m1.go" /app/internal/finbulk/profile.go
go build -o /app/build/finbulk /app/cmd/finbulk
