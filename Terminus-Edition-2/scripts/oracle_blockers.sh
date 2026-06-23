#!/usr/bin/env bash
set -uo pipefail
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
TASKS=(
  go-marina-slip-credit-matcher
  go-live-auction-bid-reversal-ledger
  ruby-go-bash-vineyard-club-shipment-credit-router
  cobol-campground-site-deposit-matcher
  cobol-utility-return-reconciliation
)
pass=0 fail=0
for t in "${TASKS[@]}"; do
  echo "===== ORACLE $t ====="
  if bash "$ROOT/scripts/terminus2_cli.sh" oracle "$ROOT/$t"; then
    ((pass++)) || true
  else
    ((fail++)) || true
  fi
done
echo "=== BLOCKERS pass=$pass fail=$fail ==="
