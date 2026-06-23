#!/usr/bin/env bash
STB=/root/.local/bin/stb
ID="$1"
OUT="/mnt/d/Manoj/Projects/Portfolio/TerminalBench/Terminus-Edition-2/Revision-ChatGpt/portal_feedback"
mkdir -p "$OUT"
"$STB" submissions feedback "$ID" 2>&1 | tail -3
FB=$(ls -dt /tmp/feedback_${ID}* 2>/dev/null | head -1)
TASK="$2"
DEST="$OUT/feedback_${TASK}_${ID}.txt"
{
  echo "=== notes.txt ==="
  cat "$FB/notes.txt" 2>/dev/null
  echo ""
  echo "=== agent_review.txt ==="
  cat "$FB/agent_review.txt" 2>/dev/null
} > "$DEST"
echo "Saved: $DEST"
