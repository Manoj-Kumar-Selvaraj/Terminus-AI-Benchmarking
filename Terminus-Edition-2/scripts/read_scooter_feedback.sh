#!/usr/bin/env bash
FB=$(ls -dt /tmp/feedback_9cf95132* 2>/dev/null | head -1)
echo "Feedback dir: $FB"
for f in notes.txt agent_review.txt; do
  if [[ -f "$FB/$f" ]]; then
    echo "========== $f =========="
    cat "$FB/$f"
    echo ""
  fi
done
