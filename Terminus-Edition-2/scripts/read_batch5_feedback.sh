#!/usr/bin/env bash
set -euo pipefail
ids=(
  d1e88ac6-156b-4394-b5b2-40ae5ea971ab
  a4606faa-24d7-4862-93b5-c50700980896
  a8dc31b4-f77c-4eaa-b549-6a485a0b08df
  14002f67-d5f4-4a3e-b796-23abeb4ef571
  5757965d-dc2a-441f-9656-5563bfd6d14b
)
for id in "${ids[@]}"; do
  FB=$(ls -dt /tmp/feedback_${id}_* 2>/dev/null | head -1)
  echo "======== $id ========"
  echo "--- agent_review ---"
  cat "$FB/agent_review.txt" 2>/dev/null || echo "(missing)"
  echo "--- notes ---"
  cat "$FB/notes.txt" 2>/dev/null || echo "(missing)"
  echo
done
