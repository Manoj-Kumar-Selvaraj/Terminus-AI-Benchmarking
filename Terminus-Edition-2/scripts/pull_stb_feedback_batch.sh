#!/usr/bin/env bash
# Pull fresh STB feedback for manual_revision_batch tasks and archive locally.
set -euo pipefail
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
MAP="$ROOT/Revision-ChatGpt/manual_revision_batch_20260612/submission_mapping.tsv"
ARCHIVE="$ROOT/Revision-ChatGpt/portal_feedback"
STB="/root/.local/bin/stb"
LOG="$ROOT/revision-manual-batch-20260612/stb_pull_$(date +%Y%m%d_%H%M%S).log"
mkdir -p "$ARCHIVE"
exec > >(tee -a "$LOG") 2>&1

echo "=== STB feedback pull $(date -Iseconds) ==="
if ! "$STB" keys verify >/dev/null 2>&1; then
  echo "WARN: stb keys verify failed — attempting stb keys refresh"
  "$STB" keys refresh || true
fi

ok=0
fail=0
while IFS=$'\t' read -r sid folder; do
  [[ "$sid" == "submission_id" ]] && continue
  [[ -z "$sid" ]] && continue
  dest="$ARCHIVE/audit_${sid}"
  mkdir -p "$dest"
  echo "--- $folder ($sid) ---"
  if "$STB" submissions feedback "$sid" 2>&1; then
    # Find newest feedback dir under /tmp
    fb_dir="$(ls -dt /tmp/feedback_${sid}_* 2>/dev/null | head -1 || true)"
    if [[ -n "$fb_dir" && -d "$fb_dir" ]]; then
      cp -f "$fb_dir/notes.txt" "$dest/notes.txt" 2>/dev/null || true
      cp -f "$fb_dir/agent_review.txt" "$dest/agent_review.txt" 2>/dev/null || true
      echo "  archived from $fb_dir"
      ((ok++)) || true
    else
      echo "  WARN: no /tmp/feedback_${sid}_* dir found after pull"
      ((fail++)) || true
    fi
  else
    echo "  FAIL: stb submissions feedback $sid"
    ((fail++)) || true
  fi
done < "$MAP"
echo "=== STB PULL DONE ok=$ok fail=$fail log=$LOG ==="
