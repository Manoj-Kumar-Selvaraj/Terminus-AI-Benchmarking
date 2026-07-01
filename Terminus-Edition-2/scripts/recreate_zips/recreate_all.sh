#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
ROOT_DIR="$(cd "${SCRIPT_DIR}/../.." && pwd)"
TASKS_FILE="${SCRIPT_DIR}/tasks.txt"
OUT_DIR="${ROOT_DIR}/submission_zips"
ZIP_SCRIPT="${ROOT_DIR}/scripts/zip_tasks_linux.sh"
INCLUDE_RUBRIC=0

usage() {
  cat <<'EOF'
Recreate all submission zips from task list.

Usage:
  scripts/recreate_zips/recreate_all.sh [--out <dir>] [--tasks-file <file>] [--include-rubric]

Behavior:
  - Deletes existing <task>.zip first
  - Creates a fresh <task>.zip
EOF
}

while [[ $# -gt 0 ]]; do
  case "$1" in
    --out)
      OUT_DIR="${2:-}"
      shift 2
      ;;
    --tasks-file)
      TASKS_FILE="${2:-}"
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

[[ -f "$TASKS_FILE" ]] || { echo "Tasks file not found: $TASKS_FILE" >&2; exit 1; }
[[ -f "$ZIP_SCRIPT" ]] || { echo "Zip script not found: $ZIP_SCRIPT" >&2; exit 1; }
mkdir -p "$OUT_DIR"

while IFS= read -r task || [[ -n "$task" ]]; do
  task="${task//$'\r'/}"
  task="${task%%#*}"
  task="$(echo "$task" | xargs)"
  [[ -n "$task" ]] || continue

  zip_path="$OUT_DIR/${task}.zip"
  rm -f "$zip_path"
done < "$TASKS_FILE"

args=(--tasks-file "$TASKS_FILE" --out "$OUT_DIR")
if [[ "$INCLUDE_RUBRIC" -eq 1 ]]; then
  args+=(--include-rubric)
fi

bash "$ZIP_SCRIPT" "${args[@]}"

echo "Recreated zips in: $OUT_DIR"