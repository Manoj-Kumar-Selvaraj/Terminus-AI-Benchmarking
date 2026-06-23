#!/usr/bin/env bash
set -uo pipefail
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
TASKS=(
  go-pharmacy-coldchain-exception-router
  go-device-warranty-claim-matcher
  ruby-parking-garage-session-adjustment-clearing
  ruby-cloud-reservation-burst-credit-ledger
  go-clinic-visit-credit-matcher
  go-marina-slip-credit-matcher
  go-telemetry-incident-credit-reconciler
  cobol-hospital-claim-denial-reconciler
  go-waterpark-pass-refund-matcher
  ruby-charity-pledge-adjustment-matcher
  go-farmers-market-stall-refund-matcher
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
echo "=== PROSE/DIFF RETRY pass=$pass fail=$fail ==="
