#!/usr/bin/env bash
set -euo pipefail

mkdir -p /app/build
cobc -x -free -O2 -o /app/build/ach_reconcile /app/src/ach_reconcile.cbl
