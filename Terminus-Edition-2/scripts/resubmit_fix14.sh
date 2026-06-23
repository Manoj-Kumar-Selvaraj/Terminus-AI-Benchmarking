#!/usr/bin/env bash
# Resubmit the 14 tasks fixed after revision audit.
set -uo pipefail
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
cd "$ROOT"
STB="${STB:-/root/.local/bin/stb}"

declare -A TASKS=(
  [4c5dfbec-ccbc-42d4-9a00-58689b5c2c2b]=cobol-campground-site-deposit-matcher
  [e3d6e72f-a4f5-4711-abf2-c6017be93d8b]=cobol-healthcare-return-reversal
  [182bded9-a7c1-4d04-b7ed-5c6c68438086]=cobol-municipal-return-clearing
  [9cf95132-6a14-4ba3-8c22-75bc7cfda012]=cobol-scooter-ride-surcharge-reversal
  [6bf2639b-67a5-488b-bb07-b58418183299]=cobol-telehealth-session-credit-clearing
  [69bfcc57-1663-4bd1-9e50-e70710641ed7]=go-aquarium-pass-credit-matcher
  [7fb1a57c-eab9-4eca-aa80-2431ba4a189c]=go-bike-share-trip-credit-matcher
  [4a47ab27-ad8c-4b15-a274-5686e033c14e]=go-datacenter-rack-hold-release
  [24b7ce75-a875-48c4-8809-844a084b22d4]=go-device-warranty-claim-matcher
  [d1e88ac6-156b-4394-b5b2-40ae5ea971ab]=go-marketplace-payout-matcher
  [e53ff9bd-3058-4ad7-adda-d60f391febba]=ruby-cloud-reservation-burst-credit-ledger
  [ded8127e-956c-4ff9-bfca-204878d5e85b]=ruby-go-bash-vineyard-club-shipment-credit-router
  [ff495811-7b4a-4021-883f-137894ae6a76]=ruby-music-royalty-live-settlement-router
  [a6e6c9e7-43c7-4409-bff2-ddd358bbc492]=ruby-parking-garage-session-adjustment-clearing
)

run_oracle() {
  local task="$1"
  if [[ "$task" == go-* ]]; then
    bash "$ROOT/scripts/oracle_cumulative_go.sh" "$task"
  elif [[ "$task" == cobol-* || "$task" == pl1-* ]]; then
    bash "$ROOT/scripts/oracle_cumulative_cobol.sh" "$task"
  else
    return 0
  fi
}

for sid in "${!TASKS[@]}"; do
  task="${TASKS[$sid]}"
  echo "===== $task ($sid) ====="
  if [[ "$task" == go-* || "$task" == cobol-* ]]; then
    if run_oracle "$task"; then echo "ORACLE PASS"; else echo "ORACLE FAIL"; continue; fi
  fi
  if "$STB" submissions update "$task" -s "$sid" --time 90 --no-send-to-reviewer; then
    echo "SUBMIT OK"
  else
    echo "SUBMIT FAIL"
  fi
  echo
  sleep 2
done
