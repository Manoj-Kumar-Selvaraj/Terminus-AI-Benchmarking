#!/usr/bin/env bash
set -euo pipefail

/app/scripts/compile.sh
mkdir -p /app/out
rm -f /app/out/denial_report.csv /app/out/denial_summary.txt
/app/build/claim_rollup
