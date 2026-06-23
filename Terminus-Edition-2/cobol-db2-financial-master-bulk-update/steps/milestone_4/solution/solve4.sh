#!/usr/bin/env bash
set -Eeuo pipefail
cd /app
export PATH="/usr/local/go/bin:${PATH}"
bash "/steps/milestone_3/solution/solve3.sh"
export PATH="/usr/local/go/bin:${PATH}"
cp "$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)/profile_m4.go" /app/internal/finbulk/profile.go
go build -o /app/build/finbulk /app/cmd/finbulk
