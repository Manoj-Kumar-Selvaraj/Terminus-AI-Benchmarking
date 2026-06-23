#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

cd /app

GO=/usr/local/go/bin/go
if [ ! -x "$GO" ]; then
  GO=go
fi

"$GO" run "$SCRIPT_DIR/patch_m2.go"

/app/scripts/run_batch.sh
test -s /app/out/adjustment_report.csv
test -s /app/out/adjustment_summary.json
