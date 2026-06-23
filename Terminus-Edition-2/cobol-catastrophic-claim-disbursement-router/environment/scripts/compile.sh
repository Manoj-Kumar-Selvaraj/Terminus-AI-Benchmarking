#!/usr/bin/env bash
set -euo pipefail
mkdir -p /app/build
cobc -x -free -o /app/build/catclaim_router /app/src/catclaim_router.cbl
