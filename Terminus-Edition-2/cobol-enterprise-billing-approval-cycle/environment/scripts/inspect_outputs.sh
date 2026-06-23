#!/usr/bin/env bash
set -euo pipefail
for path in \
  /app/out/invoice_register.dat \
  /app/out/approval_trace.dat \
  /app/out/billing_summary.txt \
  /app/out/checkpoint.dat; do
  if [[ -f "$path" ]]; then
    echo "== $path =="
    cat "$path"
  fi
done
