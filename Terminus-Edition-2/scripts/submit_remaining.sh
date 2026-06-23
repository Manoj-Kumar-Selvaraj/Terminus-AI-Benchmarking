#!/usr/bin/env bash
set -euo pipefail
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
cd "$ROOT"
STB=/root/.local/bin/stb
pairs=(
  "bash-lab-sample-credit-reconciler c03df315-93af-48c5-8bfb-b0698a89a4e3"
  "cobol-bowling-league-fee-reversal 614060df-358c-4b96-90cc-df886c4b7626"
  "cobol-campground-site-deposit-matcher 4c5dfbec-ccbc-42d4-9a00-58689b5c2c2b"
  "pl1-cobol-atm-risk-release-router 016a6fe0-145e-47f3-aa17-a60ec540b97b"
  "ruby-cloud-reservation-burst-credit-ledger e53ff9bd-3058-4ad7-adda-d60f391febba"
  "ruby-cooking-class-voucher-matcher 2f7859e8-3f19-41e8-a8ee-ccab57078449"
  "ruby-courier-cod-remittance-reconciler d567814d-307d-48a2-bb01-be833ea1108e"
  "ruby-go-bash-vineyard-club-shipment-credit-router ded8127e-956c-4ff9-bfca-204878d5e85b"
  "ruby-music-royalty-live-settlement-router ff495811-7b4a-4021-883f-137894ae6a76"
  "ruby-parking-garage-session-adjustment-clearing a6e6c9e7-43c7-4409-bff2-ddd358bbc492"
)
for pair in "${pairs[@]}"; do
  folder="${pair%% *}"
  id="${pair##* }"
  echo "==== SUBMIT $folder ($id) ===="
  "$STB" submissions update "$folder" -s "$id" --time 90
  echo
done
