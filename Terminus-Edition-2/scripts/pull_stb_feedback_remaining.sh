#!/usr/bin/env bash
set -euo pipefail
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
MAP="$ROOT/Revision-ChatGpt/manual_revision_batch_20260612/submission_mapping.tsv"
ARCHIVE="$ROOT/Revision-ChatGpt/portal_feedback"
STB="/root/.local/bin/stb"
ok=0
skip=0
fail=0
while IFS=$'\t' read -r sid folder; do
  [[ "$sid" == "submission_id" ]] && continue
  [[ -z "$sid" ]] && continue
  dest="$ARCHIVE/audit_${sid}"
  if [[ -f "$dest/notes.txt" ]]; then
    mtime=$(stat -c %Y "$dest/notes.txt" 2>/dev/null || echo 0)
    now=$(date +%s)
    age=$((now - mtime))
    if (( age < 7200 )); then
      echo "SKIP (fresh) $folder"
      ((skip++)) || true
      continue
    fi
  fi
  echo "PULL $folder ($sid)"
  mkdir -p "$dest"
  if "$STB" submissions feedback "$sid"; then
    fb=$(ls -dt /tmp/feedback_${sid}_* 2>/dev/null | head -1 || true)
    if [[ -n "$fb" && -f "$fb/notes.txt" ]]; then
      cp -f "$fb/notes.txt" "$dest/notes.txt"
      cp -f "$fb/agent_review.txt" "$dest/agent_review.txt" 2>/dev/null || true
      echo "  OK"
      ((ok++)) || true
    else
      echo "  WARN no feedback dir"
      ((fail++)) || true
    fi
  else
    echo "  FAIL"
    ((fail++)) || true
  fi
  sleep 1
done < "$MAP"
echo "DONE ok=$ok skip=$skip fail=$fail"
