#!/usr/bin/env bash
set -euo pipefail

usage() {
  cat <<'EOF'
Usage:
  Single task:
    ./scripts/zip_task.sh --task <task_dir> [--out <output_dir>] [--zip-name <name.zip>] [--include-rubric]

  Batch mode (all tasks under a folder):
    ./scripts/zip_task.sh --root <tasks_root_dir> [--out <output_dir>] [--include-rubric]

  Batch mode (explicit task names from file):
    ./scripts/zip_task.sh --tasks-file <file> [--root <tasks_root_dir>] [--out <output_dir>] [--include-rubric]

Options:
  --task <dir>          Zip one task directory
  --root <dir>          Discover and zip all child dirs containing task.toml
  --tasks-file <file>   Zip only task names listed in file (one name per line)
  --out <dir>           Directory to place resulting zips (default: current dir)
  --zip-name <file>     Zip filename for single-task mode only
  --include-rubric      Include rubric.txt inside zip (default: excluded)
  -h, --help            Show this help
EOF
}

TASK_DIR=""
ROOT_DIR=""
TASKS_FILE=""
OUT_DIR="."
ZIP_NAME=""
INCLUDE_RUBRIC=0

while [[ $# -gt 0 ]]; do
  case "$1" in
    --task) TASK_DIR="${2:-}"; shift 2 ;;
    --root) ROOT_DIR="${2:-}"; shift 2 ;;
    --tasks-file) TASKS_FILE="${2:-}"; shift 2 ;;
    --out) OUT_DIR="${2:-}"; shift 2 ;;
    --zip-name) ZIP_NAME="${2:-}"; shift 2 ;;
    --include-rubric) INCLUDE_RUBRIC=1; shift ;;
    -h|--help) usage; exit 0 ;;
    *) echo "Unknown arg: $1" >&2; usage; exit 1 ;;
  esac
done

modes=0
[[ -n "$TASK_DIR" ]] && modes=$((modes + 1))
[[ -n "$ROOT_DIR" ]] && [[ -z "$TASKS_FILE" ]] && modes=$((modes + 1))
[[ -n "$TASKS_FILE" ]] && modes=$((modes + 1))

if [[ "$modes" -ne 1 ]]; then
  echo "Use exactly one mode: --task OR --root OR --tasks-file." >&2
  exit 1
fi

if [[ -n "$TASK_DIR" && -n "$ZIP_NAME" && "$ZIP_NAME" != *.zip ]]; then
  echo "--zip-name must end with .zip" >&2
  exit 1
fi

mkdir -p "$OUT_DIR"

validate_task() {
  local dir="$1"
  local milestones req solve_sh dep
  for req in "task.toml" "environment/Dockerfile"; do
    if [[ ! -e "$dir/$req" ]]; then
      echo "Missing required path: $dir/$req" >&2
      return 1
    fi
  done
  milestones="$(grep -E '^[[:space:]]*number_of_milestones[[:space:]]*=' "$dir/task.toml" | head -1 | sed -E 's/.*=[[:space:]]*//' | tr -d '\r')"
  if [[ -z "$milestones" || "$milestones" -le 0 ]]; then
    echo "task.toml must define number_of_milestones >= 1" >&2
    return 1
  fi
  for ((i = 1; i <= milestones; i++)); do
    test_file="steps/milestone_${i}/tests/test_m${i}.py"
    if [[ ! -e "$dir/$test_file" && -e "$dir/steps/milestone_${i}/tests/test_m${i}.rb" ]]; then
      test_file="steps/milestone_${i}/tests/test_m${i}.rb"
    fi
    for req in \
      "steps/milestone_${i}/instruction.md" \
      "steps/milestone_${i}/tests/test.sh" \
      "$test_file" \
      "steps/milestone_${i}/solution/solve.sh"
    do
      if [[ ! -e "$dir/$req" ]]; then
        echo "Missing required path: $dir/$req" >&2
        return 1
      fi
    done
    solve_sh="$dir/steps/milestone_${i}/solution/solve.sh"
    if grep -qE '\$SCRIPT_DIR/solve'"${i}"'\.sh|bash[[:space:]]+"?\$SCRIPT_DIR/solve'"${i}"'\.sh' "$solve_sh"; then
      if [[ ! -e "$dir/steps/milestone_${i}/solution/solve${i}.sh" ]]; then
        echo "Missing required path: $dir/steps/milestone_${i}/solution/solve${i}.sh (referenced by solve.sh)" >&2
        return 1
      fi
    fi
    while IFS= read -r dep; do
      [[ -n "$dep" ]] || continue
      if [[ ! -e "$dir/steps/milestone_${i}/solution/solve${dep}.sh" ]]; then
        echo "Missing required path: $dir/steps/milestone_${i}/solution/solve${dep}.sh (referenced by solve.sh)" >&2
        return 1
      fi
    done < <(grep -E '\$SCRIPT_DIR/solve[0-9]+\.sh|^\s*bash\s+"?\$SCRIPT_DIR/solve[0-9]+\.sh' "$solve_sh" | grep -oE 'solve[0-9]+\.sh' | sed -E 's/solve([0-9]+)\.sh/\1/' | sort -u)
  done
}

zip_one_task() {
  local dir="$1"
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
      "$dir"/ "$tmp/task/"
  else
    cp -a "$dir"/. "$tmp/task/"
    rm -rf "$tmp/task/.git" "$tmp/task/revision_logs"
    find "$tmp/task" -type d \( -name __pycache__ -o -name .pytest_cache -o -name .mypy_cache -o -name .ruff_cache -o -name .venv -o -name venv -o -name .idea -o -name .vscode \) -prune -exec rm -rf {} + 2>/dev/null || true
    find "$tmp/task" -type f \( -name '*.pyc' -o -name '*.pyo' -o -name .DS_Store -o -name .snorkel_config \) -delete 2>/dev/null || true
  fi

  rm -f "$tmp/task/.snorkel_config"
  rm -rf "$tmp/task/revision_logs"

  if [[ "$INCLUDE_RUBRIC" -eq 0 ]]; then
    rm -f "$tmp/task/rubric.txt"
  fi

  rm -f "$out_zip"
  if command -v zip >/dev/null 2>&1; then
    (
      cd "$tmp/task"
      zip -qr "$out_zip" .
    )
  else
  if command -v py >/dev/null 2>&1; then
    py -3 - "$tmp/task" "$out_zip" <<'PY'
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
  elif command -v python >/dev/null 2>&1; then
    python - "$tmp/task" "$out_zip" <<'PY'
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
    echo "Neither zip nor python is available to create archives." >&2
    return 1
  fi
  fi
  rm -rf "$tmp"
  echo "Created: $out_zip"
}

if [[ -n "$TASK_DIR" ]]; then
  if [[ ! -d "$TASK_DIR" ]]; then
    echo "Task dir not found: $TASK_DIR" >&2
    exit 1
  fi
  validate_task "$TASK_DIR"
  task_name="$(basename "$TASK_DIR")"
  stamp="$(date +%Y%m%d_%H%M%S)"
  if [[ -z "$ZIP_NAME" ]]; then
    ZIP_NAME="${task_name}_${stamp}.zip"
  fi
  zip_one_task "$TASK_DIR" "$(realpath "$OUT_DIR")/$ZIP_NAME"
else
  if [[ -n "$TASKS_FILE" ]]; then
    [[ -f "$TASKS_FILE" ]] || { echo "Tasks file not found: $TASKS_FILE" >&2; exit 1; }
    search_root="${ROOT_DIR:-.}"
    [[ -d "$search_root" ]] || { echo "Root dir not found: $search_root" >&2; exit 1; }
    count=0
    while IFS= read -r task_name || [[ -n "$task_name" ]]; do
      task_name="${task_name//$'\r'/}"
      task_name="${task_name//$'\ufeff'/}"
      task_name="${task_name%%#*}"
      task_name="$(echo "$task_name" | xargs)"
      [[ -n "$task_name" ]] || continue
      d="$search_root/$task_name"
      [[ -d "$d" ]] || { echo "Task dir not found: $d" >&2; exit 1; }
      [[ -f "$d/task.toml" ]] || { echo "Not a task dir (missing task.toml): $d" >&2; exit 1; }
      validate_task "$d"
      stamp="$(date +%Y%m%d_%H%M%S)"
      zip_one_task "$d" "$(realpath "$OUT_DIR")/${task_name}_${stamp}.zip"
      count=$((count+1))
    done < "$TASKS_FILE"
    echo "Batch completed from tasks file. Zipped tasks: $count"
  else
    if [[ ! -d "$ROOT_DIR" ]]; then
      echo "Root dir not found: $ROOT_DIR" >&2
      exit 1
    fi
    count=0
    for d in "$ROOT_DIR"/*; do
      [[ -d "$d" ]] || continue
      [[ -f "$d/task.toml" ]] || continue
      validate_task "$d"
      task_name="$(basename "$d")"
      stamp="$(date +%Y%m%d_%H%M%S)"
      zip_one_task "$d" "$(realpath "$OUT_DIR")/${task_name}_${stamp}.zip"
      count=$((count+1))
    done
    echo "Batch completed. Zipped tasks: $count"
  fi
fi