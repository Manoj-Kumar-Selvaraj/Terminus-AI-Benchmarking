#!/usr/bin/env bash
# Round 1: submit all mapped NEEDS_REVISION tasks via submit_task.sh
set -uo pipefail
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
cd "$ROOT"
LOG="$ROOT/.terminus_logs/round1_submit_$(date +%Y%m%d_%H%M%S).log"
exec > >(tee -a "$LOG") 2>&1

declare -A ALIAS=(
  [ruby-music-royalty-live-settlement-ledger]=ruby-music-royalty-live-settlement-router
  [ruby-parking-garage-session-refund-matcher]=ruby-parking-garage-session-adjustment-clearing
  [go-live-auction-bid-reversal-matcher]=go-live-auction-bid-reversal-ledger
  [pl1-cobol-atm-risk-release-reconciler]=pl1-cobol-atm-risk-release-router
  [ruby-cooking-class-voucher-refund-matcher]=ruby-cooking-class-voucher-matcher
  [ruby-go-bash-vineyard-club-credit-ledger]=ruby-go-bash-vineyard-club-shipment-credit-router
  [cobol-escrow-return-reconciler]=cobol-escrow-return-reconciliation
)

ok=0
fail=0

while IFS=$' \t' read -r sid platform_name _rest; do
  [[ -z "$sid" || "$sid" =~ ^# ]] && continue
  sid="${sid//$'\r'/}"
  platform_name="${platform_name//$'\r'/}"
  task="${ALIAS[$platform_name]:-$platform_name}"
  if [[ ! -d "$ROOT/$task" ]]; then
    echo "SKIP $sid $platform_name (no folder)"
    ((fail++)) || true
    continue
  fi
  echo "===== ROUND1 SUBMIT: $task ($sid) ====="
  if bash "$ROOT/scripts/submit_task.sh" "$task" "$sid" 90; then
    echo "SUBMIT OK"
    ((ok++)) || true
  else
    echo "SUBMIT FAIL"
    ((fail++)) || true
  fi
  echo
  sleep 5
done < "$ROOT/needs_revision_mapped.txt"

echo "=== ROUND1 DONE ok=$ok fail=$fail log=$LOG ==="
