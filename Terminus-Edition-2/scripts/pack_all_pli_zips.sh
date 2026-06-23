#!/usr/bin/env bash
set -euo pipefail
ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
OUT="${ROOT}/submission_zips"
mkdir -p "$OUT"
for t in "$ROOT"/pli-*; do
  [[ -d "$t" && -f "$t/task.toml" ]] || continue
  name="$(basename "$t")"
  echo "Zipping $name"
  bash "$ROOT/scripts/zip.sh" --task "$t" --out "$OUT" --zip-name "${name}.zip"
done
echo "All PL/I zips in $OUT (stable names: <task>.zip)"
