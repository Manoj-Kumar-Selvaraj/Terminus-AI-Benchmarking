#!/usr/bin/env bash
# Full reviewer resubmit for all 30 NEEDS_REVISION tasks (omit --no-send-to-reviewer).
set -uo pipefail
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
cd "$ROOT"
STB="${STB:-/root/.local/bin/stb}"
LOG="$ROOT/.terminus_logs/resubmit_reviewer_$(date +%Y%m%d_%H%M%S).log"
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

local_folder() {
  local name="$1"
  echo "${ALIAS[$name]:-$name}"
}

ok=0
fail=0

while IFS= read -r line; do
  [[ -z "$line" || "$line" =~ ^# ]] && continue
  sid="${line%% *}"
  platform_name="${line#* }"
  platform_name="${platform_name//$'\r'/}"
  task="$(local_folder "$platform_name")"
  if [[ ! -d "$ROOT/$task" ]]; then
    echo "SKIP $sid $platform_name (no folder $task)"
    ((fail++)) || true
    continue
  fi
  echo "===== REVIEWER SUBMIT: $task ($sid) ====="
  if "$STB" submissions update "$task" -s "$sid" --time 90; then
    echo "SUBMIT OK"
    ((ok++)) || true
  else
    echo "SUBMIT FAIL"
    ((fail++)) || true
  fi
  echo
  sleep 3
done < "$ROOT/needs_revision_mapped.txt"

echo "=== DONE ok=$ok fail=$fail log=$LOG ==="
