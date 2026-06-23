#!/usr/bin/env bash
set -uo pipefail
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
cd "$ROOT"
STB="${STB:-/root/.local/bin/stb}"

submit() {
  local sid="$1"
  local task="$2"
  local oracle="${3:-0}"
  echo "===== $task ($sid) ====="
  if [[ "$oracle" == "1" ]]; then
    if [[ "$task" == go-* ]]; then
      bash "$ROOT/scripts/oracle_cumulative_go.sh" "$task" || { echo "ORACLE FAIL"; return 1; }
    elif [[ "$task" == cobol-* || "$task" == pl1-* ]]; then
      bash "$ROOT/scripts/oracle_cumulative_cobol.sh" "$task" || { echo "ORACLE FAIL"; return 1; }
    fi
    echo "ORACLE PASS"
  fi
  if "$STB" submissions update "$task" -s "$sid" --time 90 --no-send-to-reviewer; then
    echo "SUBMIT OK"
  else
    echo "SUBMIT FAIL"
    return 1
  fi
  echo
}

submit "2f7859e8-3f19-41e8-a8ee-ccab57078449" "ruby-cooking-class-voucher-matcher" 0
submit "ff495811-7b4a-4021-883f-137894ae6a76" "ruby-music-royalty-live-settlement-router" 0
submit "0ce68f84-80d0-42d5-8844-b190faed2581" "go-live-auction-bid-reversal-ledger" 1
submit "016a6fe0-145e-47f3-aa17-a60ec540b97b" "pl1-cobol-atm-risk-release-router" 1
submit "ded8127e-956c-4ff9-bfca-204878d5e85b" "ruby-go-bash-vineyard-club-shipment-credit-router" 0
