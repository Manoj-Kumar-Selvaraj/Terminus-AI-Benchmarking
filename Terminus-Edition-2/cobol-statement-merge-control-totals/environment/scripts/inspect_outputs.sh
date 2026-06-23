#!/usr/bin/env bash
set -euo pipefail
for path in /app/out/control_totals.dat /app/out/merge_summary.txt /app/out/checkpoint.dat; do
  if [[ -f "$path" ]]; then
    echo "== $path =="
    cat "$path"
  fi
done
