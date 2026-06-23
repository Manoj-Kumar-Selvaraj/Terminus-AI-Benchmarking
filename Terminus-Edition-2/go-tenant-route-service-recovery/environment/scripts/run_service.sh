#!/usr/bin/env bash
set -euo pipefail
mkdir -p /app/build /app/out
go build -o /app/build/routerd /app/cmd/routerd
/app/build/routerd
