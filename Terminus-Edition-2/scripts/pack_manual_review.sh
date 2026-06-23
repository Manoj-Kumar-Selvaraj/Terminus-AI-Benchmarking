#!/usr/bin/env bash
# Pack a task zip into manual-review-upload/ for manual portal upload.
set -euo pipefail
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
task="${1:?task folder name}"
out_dir="${ROOT}/manual-review-upload"
mkdir -p "$out_dir"
bash "${ROOT}/scripts/zip.sh" --task "${ROOT}/${task}" --out "$out_dir" --zip-name "${task}.zip"
echo "Manual review zip: ${out_dir}/${task}.zip"
