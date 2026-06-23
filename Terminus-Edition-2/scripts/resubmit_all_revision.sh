#!/usr/bin/env bash
# Resubmit all 30 NEEDS_REVISION tasks (non-fitness) after local fixes.
set -uo pipefail
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
cd "$ROOT"
STB="${STB:-/root/.local/bin/stb}"
LOG="$ROOT/.terminus_logs/resubmit_all_revision_$(date +%Y%m%d_%H%M%S).log"
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

run_oracle() {
  local task="$1"
  local olog="$ROOT/.terminus_logs/oracle_${task}.log"
  if [[ "$task" == go-* ]]; then
    bash "$ROOT/scripts/oracle_cumulative_go.sh" "$task" > "$olog" 2>&1
  elif [[ "$task" == cobol-* || "$task" == pl1-* ]]; then
    bash "$ROOT/scripts/oracle_cumulative_cobol.sh" "$task" > "$olog" 2>&1
  elif [[ "$task" == bash-* ]]; then
    bash "$ROOT/scripts/oracle_cumulative_bash.sh" "$task" > "$olog" 2>&1
  elif [[ "$task" == ruby-* ]]; then
    # ruby tasks: no local cumulative oracle script; skip
    return 0
  else
    return 0
  fi
}

ok=0
fail=0
skip=0

while IFS=$'\t' read -r sid platform_name _; do
  [[ -z "$sid" || "$sid" =~ ^# ]] && continue
  platform_name="${platform_name//$'\r'/}"
  task="$(local_folder "$platform_name")"
  if [[ ! -d "$ROOT/$task" ]]; then
    echo "SKIP $sid $platform_name -> $task (no folder)"
    ((skip++)) || true
    continue
  fi
  echo "===== $task ($sid) ====="
  if [[ "$task" == go-* || "$task" == cobol-* || "$task" == pl1-* || "$task" == bash-* ]]; then
    if run_oracle "$task"; then
      echo "ORACLE PASS"
    else
      echo "ORACLE FAIL (see .terminus_logs/oracle_${task}.log)"
      tail -20 "$ROOT/.terminus_logs/oracle_${task}.log" 2>/dev/null || true
      ((fail++)) || true
      echo
      continue
    fi
  fi
  if "$STB" submissions update "$task" -s "$sid" --time 90 --no-send-to-reviewer; then
    echo "SUBMIT OK"
    ((ok++)) || true
  else
    echo "SUBMIT FAIL"
    ((fail++)) || true
  fi
  echo
  sleep 2
done < "$ROOT/needs_revision_mapped.txt"

echo "=== DONE ok=$ok fail=$fail skip=$skip log=$LOG ==="
