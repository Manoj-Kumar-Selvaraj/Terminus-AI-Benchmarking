#!/usr/bin/env bash
set -euo pipefail
ROOT="/mnt/d/Manoj/Projects/Portfolio/TerminalBench/Terminus-Edition-2"
for ID in "$@"; do
  FB=$(ls -dt "/tmp/feedback_${ID}"* 2>/dev/null | head -1 || true)
  DEST="${ROOT}/Revision-ChatGpt/portal_feedback/audit_${ID}"
  mkdir -p "$DEST"
  if [[ -n "$FB" && -d "$FB" ]]; then
    cp "$FB/notes.txt" "$FB/agent_review.txt" "$DEST/" 2>/dev/null || true
    echo "Archived $ID from $FB"
  else
    echo "No feedback dir for $ID"
  fi
done
