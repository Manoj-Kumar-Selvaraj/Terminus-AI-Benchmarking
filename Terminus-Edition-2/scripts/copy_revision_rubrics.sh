#!/usr/bin/env bash
# Copy rubric.txt for all manifest tasks into revision-batch-rubrics/ for UI paste.
set -euo pipefail
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
MANIFEST="$ROOT/Revision-ChatGpt/needs_revision_pulls/portal_ids_manifest.tsv"
OUT="$ROOT/revision-batch-rubrics"
mkdir -p "$OUT"
declare -A seen=()
while IFS=$'\t' read -r _sid folder status; do
  [[ "$status" != "LOCAL_OK" || -n "${seen[$folder]:-}" ]] && continue
  seen[$folder]=1
  src="$ROOT/$folder/rubric.txt"
  if [[ -f "$src" ]]; then
    cp "$src" "$OUT/${folder}.rubric.txt"
    echo "copied $folder"
  else
    echo "MISSING rubric $folder"
  fi
done < "$MANIFEST"
echo "Rubrics -> $OUT"
