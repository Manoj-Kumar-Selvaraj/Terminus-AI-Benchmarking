#!/usr/bin/env bash
set -euo pipefail
mkdir -p /app/out /app/build
/app/scripts/compile.sh
exec /app/build/catclaim_router
