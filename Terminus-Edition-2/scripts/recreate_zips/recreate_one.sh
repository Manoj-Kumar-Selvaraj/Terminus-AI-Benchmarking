#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
ROOT_DIR="$(cd "${SCRIPT_DIR}/../.." && pwd)"
OUT_DIR="${ROOT_DIR}/submission_zips"
ZIP_SCRIPT="${ROOT_DIR}/scripts/zip_tasks_linux.sh"
INCLUDE_RUBRIC=0

usage() {
  cat <<'EOF'
Recreate a single task zip.

Usage:
  scripts/recreate_zips/recreate_one.sh <task-name> [--out <dir>] [--include-rubric]

Behavior:
  - Deletes existing <task>.zip first
  - Creates a fresh <task>.zip
EOF
}

[[ $# -ge 1 ]] || { usage >&2; exit 1; }

TASK=""
if [[ "$1" != --* ]]; then
  TASK="$1"
  shift
fi

[[ -n "$TASK" ]] || { usage >&2; exit 1; }

while [[ $# -gt 0 ]]; do
  case "$1" in
    --out)
      OUT_DIR="${2:-}"
      shift 2
      ;;
    --include-rubric)
      INCLUDE_RUBRIC=1
      shift
      ;;
    -h|--help)
      usage
      exit 0
      ;;
    *)
      echo "Unknown argument: $1" >&2
      usage >&2
      exit 1
      ;;
  esac
done

mkdir -p "$OUT_DIR"
[[ -f "$ZIP_SCRIPT" ]] || { echo "Zip script not found: $ZIP_SCRIPT" >&2; exit 1; }
rm -f "$OUT_DIR/${TASK}.zip"

args=(--out "$OUT_DIR" "$TASK")
if [[ "$INCLUDE_RUBRIC" -eq 1 ]]; then
  args=(--out "$OUT_DIR" --include-rubric "$TASK")
fi

bash "$ZIP_SCRIPT" "${args[@]}"

echo "Recreated: $OUT_DIR/${TASK}.zip"