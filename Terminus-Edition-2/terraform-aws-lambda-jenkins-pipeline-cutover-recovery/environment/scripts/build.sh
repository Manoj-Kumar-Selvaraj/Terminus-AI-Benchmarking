#!/usr/bin/env bash
set -Eeuo pipefail
cd /app
mkdir -p /app/bin
/usr/local/go/bin/go build -o /app/bin/pipelinectl /app/cmd/pipelinectl
