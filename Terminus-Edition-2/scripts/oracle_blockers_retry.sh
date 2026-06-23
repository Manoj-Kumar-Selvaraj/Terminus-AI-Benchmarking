#!/usr/bin/env bash
set -uo pipefail
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
TASKS=(
  go-live-auction-bid-reversal-ledger
  ruby-go-bash-vineyard-club-shipment-credit-router
  cobol-campground-site-deposit-matcher
)
for t in "${TASKS[@]}"; do
  echo "===== ORACLE $t ====="
  bash "$ROOT/scripts/terminus2_cli.sh" oracle "$ROOT/$t" || true
done
