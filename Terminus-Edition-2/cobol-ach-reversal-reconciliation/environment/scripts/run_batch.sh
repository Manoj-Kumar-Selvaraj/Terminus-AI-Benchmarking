#!/usr/bin/env bash
set -euo pipefail

/app/scripts/compile.sh
mkdir -p /app/out
rm -f /app/out/reversal_report.csv /app/out/reversal_summary.txt
/app/build/ach_reconcile
