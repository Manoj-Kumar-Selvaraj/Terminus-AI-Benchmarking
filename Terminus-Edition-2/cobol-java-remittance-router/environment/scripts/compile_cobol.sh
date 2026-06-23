#!/usr/bin/env bash
set -euo pipefail
mkdir -p /app/build
cobc -x -free -o /app/build/remit_reconcile /app/src/remit_reconcile.cbl