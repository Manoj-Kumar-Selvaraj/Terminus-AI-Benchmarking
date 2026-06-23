#!/usr/bin/env bash
FB=$(ls -dt /tmp/feedback_cd26e7aa* 2>/dev/null | head -1)
echo "Feedback dir: $FB"
echo ""
for f in notes.txt agent_review.txt test_quality_review.txt quality_review.txt difficulty_check.txt; do
  if [[ -f "$FB/$f" ]]; then
    echo "========== $f =========="
    cat "$FB/$f"
    echo ""
  fi
done
echo "========== all files =========="
find "$FB" -maxdepth 1 -type f
