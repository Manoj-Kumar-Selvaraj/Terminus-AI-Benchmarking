#!/usr/bin/env bash
set -euo pipefail
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
OUT="/mnt/d/Manoj/Projects/Portfolio/TerminalBench/Terminus-Edition-2/Revision-ChatGpt/portal_feedback"
mkdir -p "$OUT"
for pair in "${pairs[@]}"; do
  task="${pair%% *}"
  id="${pair##* }"
  echo "======== $task ($id) ========"
  "$STB" submissions feedback "$id" 2>&1 | tail -4
  FB=$(ls -dt /tmp/feedback_${id}_* 2>/dev/null | head -1)
  {
    echo "=== agent_review ==="
    cat "$FB/agent_review.txt" 2>/dev/null || echo "(missing)"
    echo "=== notes ==="
    cat "$FB/notes.txt" 2>/dev/null || echo "(missing)"
  } > "$OUT/feedback_${task}_${id}.txt"
  echo "saved $OUT/feedback_${task}_${id}.txt"
  echo
done
