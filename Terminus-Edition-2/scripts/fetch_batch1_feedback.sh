#!/usr/bin/env bash
set -uo pipefail
STB="${STB:-/root/.local/bin/stb}"
ROOT="/mnt/d/Manoj/Projects/Portfolio/TerminalBench/Terminus-Edition-2"
OUT="$ROOT/Revision-ChatGpt/portal_feedback"
mkdir -p "$OUT"

fetch_one() {
  local id="$1"
  local task="$2"
  echo "Fetching feedback for $task ($id)..."
  {
    echo "=== FEEDBACK ==="
    "$STB" submissions feedback "$id" 2>&1
    echo ""
    echo "=== VIEW ==="
    "$STB" submissions view "$id" 2>&1
  } > "$OUT/feedback_${task}_${id}.txt"
}

fetch_one "cd26e7aa-9fec-4514-8630-ebac4dccb8dc" "go-escape-room-booking-refund-matcher"
fetch_one "9cf95132-6a14-4ba3-8c22-75bc7cfda012" "cobol-scooter-ride-surcharge-reversal"
fetch_one "4c5dfbec-ccbc-42d4-9a00-58689b5c2c2b" "cobol-campground-site-deposit-matcher"

# Search for invoice and photography in full list
echo "=== SEARCH invoice/photography ===" > "$OUT/search_invoice_photography.txt"
"$STB" submissions list -p bfe79c33-8ab0-4061-9849-08d3207c9927 --show-folder-names 2>&1 | grep -iE "invoice|photography" >> "$OUT/search_invoice_photography.txt" || echo "NOT_FOUND" >> "$OUT/search_invoice_photography.txt"

echo "Done."
