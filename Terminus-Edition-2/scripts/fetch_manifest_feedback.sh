#!/usr/bin/env bash
# Fetch portal feedback for all LOCAL_OK tasks in portal_ids_manifest.tsv
set -uo pipefail
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
STB="/root/.local/bin/stb"
MANIFEST="$ROOT/Revision-ChatGpt/needs_revision_pulls/portal_ids_manifest.tsv"
OUT="$ROOT/Revision-ChatGpt/portal_feedback"
LOG="$ROOT/Revision-ChatGpt/revision_batch_logs/fetch_feedback_$(date +%Y%m%d_%H%M%S).log"
mkdir -p "$OUT" "$(dirname "$LOG")"
exec > >(tee -a "$LOG") 2>&1

ok=0
skip=0
fail=0

while IFS=$'\t' read -r sid folder status; do
  [[ -z "$sid" || "$sid" =~ ^# ]] && continue
  [[ "$status" != "LOCAL_OK" ]] && continue
  sid="${sid//$'\r'/}"
  folder="${folder//$'\r'/}"
  dest="$OUT/audit_${sid}"
  if [[ -f "$dest/notes.txt" ]]; then
    echo "SKIP $folder ($sid) — cached"
    ((skip++)) || true
    continue
  fi
  echo "===== FETCH $folder ($sid) ====="
  if "$STB" submissions feedback "$sid" 2>&1 | tail -5; then
    latest=$(ls -td /tmp/feedback_${sid}_* 2>/dev/null | head -1)
    if [[ -n "$latest" && -f "$latest/notes.txt" ]]; then
      mkdir -p "$dest"
      cp "$latest/notes.txt" "$dest/"
      [[ -f "$latest/agent_review.txt" ]] && cp "$latest/agent_review.txt" "$dest/"
      echo "saved -> $dest"
      ((ok++)) || true
    else
      echo "FAIL no feedback files for $sid"
      ((fail++)) || true
    fi
  else
    echo "FAIL stb feedback $sid"
    ((fail++)) || true
  fi
  sleep 1
done < "$MANIFEST"

echo "=== DONE ok=$ok skip=$skip fail=$fail log=$LOG ==="
