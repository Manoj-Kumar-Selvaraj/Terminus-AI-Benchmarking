#!/usr/bin/env bash
set -uo pipefail
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
TASKS=(
  go-conference-sponsor-rebate-matcher
  cobol-vendor-return-settlement
  go-marketplace-payout-matcher
  ruby-courier-cod-remittance-reconciler
  go-datacenter-rack-hold-release
  go-property-lease-deposit-reconciler
  go-childcare-attendance-refund-matcher
)
pass=0
fail=0
for t in "${TASKS[@]}"; do
  echo "===== ORACLE $t ====="
  if bash "$ROOT/scripts/terminus2_cli.sh" oracle "$ROOT/$t"; then
    pass=$((pass + 1))
  else
    fail=$((fail + 1))
    echo "FAILED $t"
  fi
done
echo "=== NEW TASKS ORACLE pass=$pass fail=$fail ==="
exit "$fail"
