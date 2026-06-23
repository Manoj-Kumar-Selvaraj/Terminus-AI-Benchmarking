#!/bin/bash
set -euo pipefail
mkdir -p /app/build /app/out
cobc -x -free -O2 -o /app/build/hangar_adjust_reconcile /app/src/hangar_adjust_reconcile.cbl
/app/build/hangar_adjust_reconcile
