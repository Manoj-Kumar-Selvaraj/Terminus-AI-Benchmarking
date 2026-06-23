#!/usr/bin/env bash
set -euo pipefail
cd "$(dirname "$0")/.."
STB="${STB:-/root/.local/bin/stb}"

declare -A IDS=(
  [go-escape-room-booking-refund-matcher]=cd26e7aa-9fec-4514-8630-ebac4dccb8dc
  [cobol-scooter-ride-surcharge-reversal]=9cf95132-6a14-4ba3-8c22-75bc7cfda012
  [cobol-campground-site-deposit-matcher]=4c5dfbec-ccbc-42d4-9a00-58689b5c2c2b
  [go-datacenter-rack-hold-release]=4a47ab27-ad8c-4b15-a274-5686e033c14e
  [cobol-pension-contribution-reversal]=c3865f7a-4e9b-4107-9c92-7ff3a75c70c6
  [bash-lab-sample-credit-reconciler]=c03df315-93af-48c5-8bfb-b0698a89a4e3
  [go-warehouse-pickwave-shortage-matcher]=14002f67-d5f4-4a3e-b796-23abeb4ef571
  [go-travel-booking-adjustment-matcher]=a4606faa-24d7-4862-93b5-c50700980896
  [ruby-cloud-reservation-burst-credit-ledger]=e53ff9bd-3058-4ad7-adda-d60f391febba
)

while IFS= read -r task; do
  [[ -z "$task" || "$task" =~ ^# ]] && continue
  id="${IDS[$task]:-}"
  if [[ -z "$id" ]]; then
    echo "SKIP $task (no submission ID in map — submit manually)"
    continue
  fi
  echo "=== Resubmit $task ($id) ==="
  if ! "$STB" submissions update "$task" -s "$id" --time 90 --no-send-to-reviewer 2>&1; then
    echo "WARN: resubmit failed for $task (may be EVALUATION_PENDING)"
  fi
done < batch10_tasks.txt
