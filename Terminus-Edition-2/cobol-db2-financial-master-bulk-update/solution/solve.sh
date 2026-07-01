#!/usr/bin/env bash
set -Eeuo pipefail
cd /app
export PATH="/usr/local/go/bin:${PATH}"

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cp "${SCRIPT_DIR}/profile_m5.go" /app/internal/finbulk/profile.go
cp "${SCRIPT_DIR}/runner_fixed.go" /app/internal/finbulk/runner.go
cp "${SCRIPT_DIR}/main_scope6.go" /app/cmd/finbulk/main.go
cp "${SCRIPT_DIR}/run_finbulk_scope6.sh" /app/bin/run_finbulk.sh
chmod +x /app/bin/run_finbulk.sh
go build -o /app/build/finbulk /app/cmd/finbulk
