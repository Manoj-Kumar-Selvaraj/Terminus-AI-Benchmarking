#!/usr/bin/env bash
# Submit a task via stb using a standards-compliant zip from scripts/zip.sh.
# Default: rubric.txt stays in the task folder but is excluded from the upload zip.
set -euo pipefail

task="${1:?task folder name}"
sid="${2:?submission id}"
minutes="${3:-90}"
root="$(cd "$(dirname "$0")/.." && pwd)"
task_dir="${root}/${task}"
stb="${STB_BIN:-/root/.local/bin/stb}"
zip_script="${root}/scripts/zip.sh"

if [[ ! -d "$task_dir" ]]; then
  echo "ERROR: task dir not found: $task_dir" >&2
  exit 1
fi

if [[ ! -x "$zip_script" && ! -f "$zip_script" ]]; then
  echo "ERROR: missing zip script: $zip_script" >&2
  exit 1
fi

zip_work="$(mktemp -d)"
staging="$(mktemp -d)"
zip_file="${zip_work}/${task}.zip"

cleanup() {
  rm -rf "$zip_work" "$staging"
}
trap cleanup EXIT

echo "📦 Building submission zip with scripts/zip.sh (rubric excluded)..."
bash "$zip_script" --task "$task_dir" --out "$zip_work" --zip-name "${task}.zip"

echo "📂 Staging zip contents for stb upload..."
unzip -q "$zip_file" -d "$staging"

cd "$root"
"$stb" submissions update "$staging" -s "$sid" --time "$minutes"
