#!/usr/bin/env bash
set -euo pipefail

mkdir -p /app/build
cobc -x -free -O2 -o /app/build/lockbox_apply /app/src/lockbox_apply.cbl
