#!/usr/bin/env bash
set -Eeuo pipefail
cd /app
export PATH="/usr/local/go/bin:${PATH}"
bash "/steps/milestone_1/solution/solve1.sh"
export PATH="/usr/local/go/bin:${PATH}"
cp "$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)/profile_m2.go" /app/internal/finbulk/profile.go
go build -o /app/build/finbulk /app/cmd/finbulk
