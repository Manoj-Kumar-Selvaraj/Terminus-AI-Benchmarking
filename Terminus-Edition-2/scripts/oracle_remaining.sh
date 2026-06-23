#!/usr/bin/env bash
set -euo pipefail
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
cd "$ROOT"
CLI="$ROOT/scripts/terminus2_cli.sh"

run_bash_cobol() {
  local task="$1"
  echo "==== ORACLE $task ===="
  if [[ "$task" == bash-* ]]; then
    bash scripts/oracle_cumulative_bash.sh "$task" 2>&1 | tail -8
  else
    bash scripts/oracle_cumulative_cobol.sh "$task" 2>&1 | tail -8
  fi
  echo
}

run_ruby() {
  local task="$1"
  echo "==== ORACLE $task ===="
  USE_DIRECT_HARBOR=1 "$CLI" oracle "./$task" 2>&1 | tail -12
  echo
}

for t in bash-lab-sample-credit-reconciler cobol-bowling-league-fee-reversal cobol-campground-site-deposit-matcher pl1-cobol-atm-risk-release-router; do
  run_bash_cobol "$t"
done

for t in ruby-cloud-reservation-burst-credit-ledger ruby-cooking-class-voucher-matcher ruby-courier-cod-remittance-reconciler ruby-go-bash-vineyard-club-shipment-credit-router ruby-music-royalty-live-settlement-router ruby-parking-garage-session-adjustment-clearing; do
  run_ruby "$t"
done
