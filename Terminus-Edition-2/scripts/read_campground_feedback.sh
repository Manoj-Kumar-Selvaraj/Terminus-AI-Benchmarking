#!/usr/bin/env bash
set -euo pipefail
FB="$(ls -td /tmp/feedback_4c5dfbec* 2>/dev/null | head -1)"
echo "FB=$FB"
for f in agent_review.txt notes.txt; do
  echo "=== $f ==="
  cat "$FB/$f" 2>/dev/null || true
done
