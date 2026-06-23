#!/usr/bin/env bash
set -uo pipefail
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
STB="/root/.local/bin/stb"
OUT="$ROOT/Revision-ChatGpt/portal_feedback"
mkdir -p "$OUT"

while IFS=$'\t' read -r sid platform _; do
  [[ -z "$sid" || "$sid" =~ ^# ]] && continue
  platform="${platform//$'\r'/}"
  echo "FETCH $sid $platform"
  if "$STB" submissions feedback "$sid" 2>&1 | tail -2; then
    latest=$(ls -td /tmp/feedback_${sid}_* 2>/dev/null | head -1)
    if [[ -n "$latest" && -f "$latest/notes.txt" ]]; then
      dest="$OUT/audit_${sid}"
      mkdir -p "$dest"
      cp "$latest/notes.txt" "$dest/"
      [[ -f "$latest/agent_review.txt" ]] && cp "$latest/agent_review.txt" "$dest/"
      echo "  saved -> $dest"
    fi
  else
    echo "  FAIL"
  fi
  sleep 1
done < "$ROOT/needs_revision_mapped.txt"

echo "DONE"
