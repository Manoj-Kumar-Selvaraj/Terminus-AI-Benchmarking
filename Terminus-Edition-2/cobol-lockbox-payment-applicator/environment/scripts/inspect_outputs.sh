#!/usr/bin/env bash
set -euo pipefail

test -f /app/out/lockbox_report.csv && sed -n '1,20p' /app/out/lockbox_report.csv
test -f /app/out/lockbox_summary.txt && cat /app/out/lockbox_summary.txt
