#!/usr/bin/env bash
# Fetch portal feedback for all tasks in queue_45_manifest.txt
set -uo pipefail
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
STB="/root/.local/bin/stb"
MANIFEST="$ROOT/Revision-ChatGpt/queue_45_manifest.txt"
OUT="$ROOT/Revision-ChatGpt/portal_feedback"
LOG="$ROOT/.terminus_logs/fetch_queue_45_$(date +%Y%m%d_%H%M%S).log"
mkdir -p "$OUT"
exec > >(tee -a "$LOG") 2>&1

ok=0
fail=0

while IFS=$'\t' read -r sid folder _; do
  [[ -z "$sid" || "$sid" =~ ^# ]] && continue
  [[ ! "$sid" =~ ^[a-f0-9]{8}-[a-f0-9]{4}-[a-f0-9]{4}-[a-f0-9]{4}-[a-f0-9]{12}$ ]] && continue
  sid="${sid//$'\r'/}"
  folder="${folder//$'\r'/}"
  echo "===== FETCH $sid ($folder) ====="
  if "$STB" submissions feedback "$sid" 2>&1 | tail -3; then
    latest=$(ls -td /tmp/feedback_${sid}_* 2>/dev/null | head -1)
    if [[ -n "$latest" && -f "$latest/notes.txt" ]]; then
      dest="$OUT/audit_${sid}"
      mkdir -p "$dest"
      cp "$latest/notes.txt" "$dest/"
      [[ -f "$latest/agent_review.txt" ]] && cp "$latest/agent_review.txt" "$dest/"
      echo "saved -> $dest"
      ((ok++)) || true
    else
      echo "FAIL no feedback files"
      ((fail++)) || true
    fi
  else
    echo "FAIL stb feedback"
    ((fail++)) || true
  fi
  sleep 1
done < "$MANIFEST"

echo "=== DONE ok=$ok fail=$fail log=$LOG ==="
