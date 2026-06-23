#!/usr/bin/env bash
# Standard TE2 submission zip (validates layout, excludes rubric.txt by default).
# Wrapper around zip_task.sh — always use this script instead of ad-hoc zip commands.
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
ROOT_DIR="$(cd "$SCRIPT_DIR/.." && pwd)"

usage() {
  cat <<'EOF'
Usage:
  ./scripts/zip.sh <task_folder_name> [--out <dir>] [--include-rubric]

  ./scripts/zip.sh --task <task_dir> [--out <dir>] [--zip-name <name.zip>] [--include-rubric]
  ./scripts/zip.sh --root <tasks_root> [--out <dir>] [--include-rubric]
  ./scripts/zip.sh --tasks-file <file> [--root <dir>] [--out <dir>] [--include-rubric]

Shorthand:
  ./scripts/zip.sh my-task-name
    → zips ./my-task-name into submission_zips/ (rubric.txt excluded)

All modes delegate to scripts/zip_task.sh.
EOF
}

if [[ $# -eq 0 ]]; then
  usage >&2
  exit 1
fi

if [[ "$1" == "-h" || "$1" == "--help" ]]; then
  usage
  exit 0
fi

if [[ $# -ge 1 && "$1" != --* ]]; then
  task_name="$1"
  shift
  task_dir="${ROOT_DIR}/${task_name}"
  if [[ ! -d "$task_dir" ]]; then
    echo "Task dir not found: $task_dir" >&2
    exit 1
  fi
  out_dir="${ROOT_DIR}/submission_zips"
  include_rubric=()
  while [[ $# -gt 0 ]]; do
    case "$1" in
      --out)
        out_dir="${2:-}"
        shift 2
        ;;
      --include-rubric)
        include_rubric=(--include-rubric)
        shift
        ;;
      *)
        echo "Unknown arg: $1" >&2
        usage >&2
        exit 1
        ;;
    esac
  done
  exec bash "$SCRIPT_DIR/zip_task.sh" --task "$task_dir" --out "$out_dir" "${include_rubric[@]}"
fi

exec bash "$SCRIPT_DIR/zip_task.sh" "$@"
