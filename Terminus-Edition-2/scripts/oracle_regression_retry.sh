#!/usr/bin/env bash
set -uo pipefail
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
TASKS=(
  cobol-bowling-league-fee-reversal
  cobol-campground-site-deposit-matcher
  cobol-hospital-claim-denial-reconciler
  cobol-municipal-return-clearing
  cobol-pension-contribution-reversal
  cobol-telehealth-session-credit-clearing
  cobol-utility-meter-adjustment-clearing
  go-clinic-visit-credit-matcher
  go-conference-sponsor-rebate-matcher
  go-parking-citation-credit-matcher
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
echo "=== REGRESSION RETRY pass=$pass fail=$fail ==="
