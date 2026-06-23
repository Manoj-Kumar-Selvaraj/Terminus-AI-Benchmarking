#!/usr/bin/env bash
set -euo pipefail
cd "$(dirname "$0")/.."
STB=/root/.local/bin/stb
OUT=Revision-ChatGpt/portal_feedback
mkdir -p "$OUT"

fetch_one() {
  local id="$1" task="$2"
  echo "=== FETCH $task ($id) ==="
  "$STB" submissions feedback "$id" 2>&1 | tail -2
  FB=$(ls -dt /tmp/feedback_${id}* 2>/dev/null | head -1)
  DEST="$OUT/revision_check_${task}_${id}.txt"
  {
    echo "=== notes.txt ==="
    cat "$FB/notes.txt" 2>/dev/null
    echo ""
    echo "=== agent_review.txt ==="
    cat "$FB/agent_review.txt" 2>/dev/null
  } > "$DEST"
  echo "Saved: $DEST"
}

fetch_one cd26e7aa-9fec-4514-8630-ebac4dccb8dc go-escape-room-booking-refund-matcher
fetch_one 4c5dfbec-ccbc-42d4-9a00-58689b5c2c2b cobol-campground-site-deposit-matcher
fetch_one 342c074d-9870-49fc-974b-b5ab8149a3f7 go-carwash-subscription-rebate-matcher
fetch_one 4a47ab27-ad8c-4b15-a274-5686e033c14e go-datacenter-rack-hold-release
fetch_one 9cf95132-6a14-4ba3-8c22-75bc7cfda012 cobol-scooter-ride-surcharge-reversal
