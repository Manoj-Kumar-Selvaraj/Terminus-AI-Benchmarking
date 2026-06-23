#!/usr/bin/env bash
set -euo pipefail
mkdir -p /app/data
exec java -cp /app/build/billing-service.jar org.h2.tools.Server \
  -tcp -tcpPort 9092 -tcpAllowOthers -ifNotExists \
  -baseDir /app/data
