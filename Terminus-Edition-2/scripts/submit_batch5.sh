#!/usr/bin/env bash
set -euo pipefail
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
cd "$ROOT"
STB=/root/.local/bin/stb
pairs=(
  "go-marketplace-payout-matcher d1e88ac6-156b-4394-b5b2-40ae5ea971ab"
  "go-travel-booking-adjustment-matcher a4606faa-24d7-4862-93b5-c50700980896"
  "go-utility-refund-reconciler a8dc31b4-f77c-4eaa-b549-6a485a0b08df"
  "go-warehouse-pickwave-shortage-matcher 14002f67-d5f4-4a3e-b796-23abeb4ef571"
  "go-waterpark-pass-refund-matcher 5757965d-dc2a-441f-9656-5563bfd6d14b"
)
for pair in "${pairs[@]}"; do
  folder="${pair%% *}"
  id="${pair##* }"
  echo "==== SUBMIT $folder ($id) ===="
  "$STB" submissions update "$folder" -s "$id" --time 90
  echo
done
