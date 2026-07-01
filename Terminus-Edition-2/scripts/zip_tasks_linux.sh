#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
ROOT_DIR="$(cd "${SCRIPT_DIR}/.." && pwd)"
OUT_DIR="${ROOT_DIR}/submission_zips"
TASKS_FILE=""
INCLUDE_RUBRIC=0

usage() {
  cat <<'EOF'
Linux batch zipper for Terminus tasks.

Usage:
  scripts/zip_tasks_linux.sh [options] <task1> [task2 ...]
  scripts/zip_tasks_linux.sh [options] --tasks-file <file>

Options:
  --tasks-file <file>   File with one task name per line
  --out <dir>           Output directory (default: submission_zips)
  --include-rubric      Include rubric.txt in zip
  -h, --help            Show help

Output naming:
  Always creates deterministic zip names as <task-name>.zip
  (no timestamp/suffix).

Examples:
  scripts/zip_tasks_linux.sh aws-lambda-event-source-mapping-recovery
  scripts/zip_tasks_linux.sh --out submission_zips \
    terraform-aws-eks-addons-irsa-upgrade-recovery \
    terraform-aws-ec2-windows-linux-cutover-plan
  scripts/zip_tasks_linux.sh --tasks-file tasks.txt
EOF
}

TASKS=()

while [[ $# -gt 0 ]]; do
  case "$1" in
    --tasks-file)
      TASKS_FILE="${2:-}"
      shift 2
      ;;
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
    --*)
      echo "Unknown option: $1" >&2
      usage >&2
      exit 1
      ;;
    *)
      TASKS+=("$1")
      shift
      ;;
  esac
done

if [[ -n "$TASKS_FILE" ]]; then
  [[ -f "$TASKS_FILE" ]] || { echo "Tasks file not found: $TASKS_FILE" >&2; exit 1; }
  while IFS= read -r line || [[ -n "$line" ]]; do
    line="${line//$'\r'/}"
    line="${line%%#*}"
    line="$(echo "$line" | xargs)"
    [[ -n "$line" ]] || continue
    TASKS+=("$line")
  done < "$TASKS_FILE"
fi

if [[ ${#TASKS[@]} -eq 0 ]]; then
  echo "No tasks specified." >&2
  usage >&2
  exit 1
fi

mkdir -p "$OUT_DIR"

zip_one_task() {
  local task_dir="$1"
  local out_zip="$2"
  local tmp
  tmp="$(mktemp -d)"
  mkdir -p "$tmp/task"

  if command -v rsync >/dev/null 2>&1; then
    rsync -a \
      --exclude=".git/" \
      --exclude=".snorkel_config" \
      --exclude="__pycache__/" \
      --exclude=".pytest_cache/" \
      --exclude=".mypy_cache/" \
      --exclude=".ruff_cache/" \
      --exclude=".venv/" \
      --exclude="venv/" \
      --exclude=".idea/" \
      --exclude=".vscode/" \
      --exclude="*.pyc" \
      --exclude="*.pyo" \
      --exclude=".DS_Store" \
      "$task_dir"/ "$tmp/task/"
  else
    cp -a "$task_dir"/. "$tmp/task/"
    rm -rf "$tmp/task/.git" "$tmp/task/revision_logs"
    find "$tmp/task" -type d \( -name __pycache__ -o -name .pytest_cache -o -name .mypy_cache -o -name .ruff_cache -o -name .venv -o -name venv -o -name .idea -o -name .vscode \) -prune -exec rm -rf {} + 2>/dev/null || true
    find "$tmp/task" -type f \( -name '*.pyc' -o -name '*.pyo' -o -name .DS_Store -o -name .snorkel_config \) -delete 2>/dev/null || true
  fi

  if [[ "$INCLUDE_RUBRIC" -eq 0 ]]; then
    rm -f "$tmp/task/rubric.txt"
  fi

  rm -f "$out_zip"
  if command -v zip >/dev/null 2>&1; then
    ( cd "$tmp/task" && zip -qr "$out_zip" . )
  elif command -v python3 >/dev/null 2>&1; then
    python3 - "$tmp/task" "$out_zip" <<'PY'
import sys
import zipfile
from pathlib import Path

stage = Path(sys.argv[1])
out_zip = Path(sys.argv[2])
with zipfile.ZipFile(out_zip, "w", compression=zipfile.ZIP_DEFLATED) as zf:
    for path in stage.rglob("*"):
        if path.is_file():
            zf.write(path, path.relative_to(stage).as_posix())
PY
  else
    echo "Neither zip nor python3 is available to create archives." >&2
    rm -rf "$tmp"
    return 1
  fi

  rm -rf "$tmp"
  echo "Created: $out_zip"
}

for task in "${TASKS[@]}"; do
  task_dir="$ROOT_DIR/$task"
  if [[ ! -d "$task_dir" ]]; then
    echo "Task directory not found: $task_dir" >&2
    exit 1
  fi

  zip_name="$(basename "$task").zip"
  zip_one_task "$task_dir" "$OUT_DIR/$zip_name"
done

echo "Done. Created zip(s) in: $OUT_DIR"