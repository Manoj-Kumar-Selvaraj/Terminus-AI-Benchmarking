#!/usr/bin/env bash
set -Eeuo pipefail

# --------------------------------------------------------------------------------------------------
# Terminus Edition 2 task validation/oracle/zip helper
#
# Supports both:
#   1. Existing task folders:
#      - optionally refreshes the task with replace_task_from_latest_zip.sh
#   2. New tasks whose repo folder does not exist:
#      - finds the newest matching ZIP
#      - safely extracts it into REPO_ROOT/<task-name>
#
# Usage:
#   ./run_task_revision.sh <task-name>
#
# Examples:
#   ./run_task_revision.sh go-edge-gateway-tls-recovery
#   TASK_ZIP=/mnt/c/Users/Manoj/Downloads/go-edge-gateway-tls-recovery.zip \
#     ./run_task_revision.sh go-edge-gateway-tls-recovery
#   SKIP_REPLACE=1 ./run_task_revision.sh go-edge-gateway-tls-recovery
#
# Optional environment overrides:
#   REPO_ROOT="/mnt/d/Manoj/Projects/Portfolio/TerminalBench/Terminus-Edition-2"
#   ZIP_OUT_DIR="new-task-upload"
#   TASK_ZIP="/absolute/path/to/task.zip"
#   ZIP_SEARCH_DIRS="/path/one:/path/two"
#   LOG_DIR="Revision-ChatGpt"
#   SKIP_REPLACE=1
#   ZIP_EVEN_IF_ORACLE_FAIL=1
#
# Windows output folder corresponding to the default:
#   D:\Manoj\Projects\Portfolio\TerminalBench\Terminus-Edition-2\new-task-upload
# --------------------------------------------------------------------------------------------------

TASK="${1:-}"

REPO_ROOT="${REPO_ROOT:-/mnt/d/Manoj/Projects/Portfolio/TerminalBench/Terminus-Edition-2}"
ZIP_OUT_DIR="${ZIP_OUT_DIR:-new-task-upload}"
LOG_DIR="${LOG_DIR:-Revision-ChatGpt}"

die() {
    echo
    echo "❌ ERROR: $*" >&2
    exit 1
}

info() {
    echo
    echo "===================================================================================================="
    echo "✅ $*"
    echo "===================================================================================================="
}

warn() {
    echo
    echo "⚠️  $*" >&2
}

require_executable() {
    local file="$1"
    [[ -x "$file" ]] || die "Required executable not found or not executable: $file"
}

require_command() {
    local command_name="$1"
    command -v "$command_name" >/dev/null 2>&1 \
        || die "Required command not found in PATH: $command_name"
}

on_error() {
    local line_no="$1"
    local command="$2"
    echo
    echo "❌ Script failed at line ${line_no}" >&2
    echo "Command: ${command}" >&2
    echo "Task: ${TASK:-not-set}" >&2
    exit 1
}
trap 'on_error "$LINENO" "$BASH_COMMAND"' ERR

TEMP_PATHS=()

cleanup() {
    local path
    for path in "${TEMP_PATHS[@]:-}"; do
        [[ -n "$path" ]] && rm -rf -- "$path"
    done
}
trap cleanup EXIT

resolve_from_repo() {
    local path="$1"
    if [[ "$path" = /* ]]; then
        printf '%s\n' "$path"
    else
        printf '%s\n' "$REPO_ROOT/$path"
    fi
}

find_latest_task_zip() {
    local search_dirs="$1"
    local dir

    IFS=':' read -r -a _zip_dirs <<< "$search_dirs"

    for dir in "${_zip_dirs[@]}"; do
        [[ -d "$dir" ]] || continue

        find "$dir" -maxdepth 3 -type f \
            \( -iname "${TASK}.zip" \
               -o -iname "${TASK}_*.zip" \
               -o -iname "${TASK}-*.zip" \) \
            -printf '%T@ %p\n' 2>/dev/null
    done \
        | sort -nr \
        | head -n 1 \
        | cut -d' ' -f2-
}

import_new_task_from_zip() {
    local zip_file="$1"
    local destination="$2"
    local extract_dir
    local source_dir
    local -a task_tomls

    [[ -f "$zip_file" ]] || die "New-task ZIP not found: $zip_file"
    [[ ! -e "$destination" ]] || die "Destination already exists: $destination"

    extract_dir="$(mktemp -d)"
    TEMP_PATHS+=("$extract_dir")

    info "Importing new task from ZIP"
    echo "Source ZIP:  $zip_file"
    echo "Destination: $destination"

    # Reject absolute paths and '..' traversal before extracting.
    python3 - "$zip_file" "$extract_dir" <<'PY'
import sys
import zipfile
from pathlib import Path, PurePosixPath

zip_path = Path(sys.argv[1])
destination = Path(sys.argv[2])

with zipfile.ZipFile(zip_path) as archive:
    for member in archive.infolist():
        path = PurePosixPath(member.filename)

        if path.is_absolute() or ".." in path.parts:
            raise SystemExit(
                f"Unsafe ZIP member rejected: {member.filename!r}"
            )

    archive.extractall(destination)
PY

    if [[ -f "$extract_dir/$TASK/task.toml" ]]; then
        source_dir="$extract_dir/$TASK"
    elif [[ -f "$extract_dir/task.toml" ]]; then
        source_dir="$extract_dir"
    else
        mapfile -t task_tomls < <(
            find "$extract_dir" -maxdepth 4 -type f -name task.toml | sort
        )

        if [[ "${#task_tomls[@]}" -ne 1 ]]; then
            printf 'Found task.toml candidates:\n' >&2
            printf '  %s\n' "${task_tomls[@]:-none}" >&2
            die "Expected exactly one task.toml inside new-task ZIP"
        fi

        source_dir="$(dirname "${task_tomls[0]}")"
    fi

    mkdir -p "$destination"
    cp -a "$source_dir/." "$destination/"

    [[ -f "$destination/task.toml" ]] \
        || die "Imported task does not contain task.toml: $destination"

    info "New task imported successfully"
}

[[ -n "$TASK" ]] || die "Usage: $0 <task-name>"

require_command python3
require_command find
require_command sort
require_command tee

[[ -d "$REPO_ROOT" ]] || die "Repo root not found: $REPO_ROOT"
cd "$REPO_ROOT"

ZIP_OUT_PATH="$(resolve_from_repo "$ZIP_OUT_DIR")"
TASK_PATH="$REPO_ROOT/$TASK"
TASK_LOG_DIR="$REPO_ROOT/$LOG_DIR"

# New-task ZIP lookup order when TASK_ZIP is not explicitly supplied.
# The Windows Downloads path is included for convenience in WSL.
DEFAULT_DOWNLOAD_DIR="/mnt/c/Users/Manoj/Downloads"
ZIP_SEARCH_DIRS="${ZIP_SEARCH_DIRS:-$ZIP_OUT_PATH:$REPO_ROOT/All-Revision-Tasks:$REPO_ROOT:$DEFAULT_DOWNLOAD_DIR}"

mkdir -p "$TASK_LOG_DIR"
mkdir -p "$ZIP_OUT_PATH"

STAMP="$(date +%Y%m%d_%H%M%S)"
PREFLIGHT_LOG="${TASK_LOG_DIR}/${TASK}_preflight_${STAMP}.log"
ORACLE_LOG="${TASK_LOG_DIR}/${TASK}_oracle_${STAMP}.log"
ZIP_LOG="${TASK_LOG_DIR}/${TASK}_zip_${STAMP}.log"

info "Starting revision/new-task workflow: ${TASK}"

require_executable "./scripts/terminus2_cli.sh"
require_executable "./scripts/zip.sh"

if [[ -d "$TASK_PATH" ]]; then
    if [[ "${SKIP_REPLACE:-0}" == "1" ]]; then
        info "Existing task folder found; replacement skipped"
        echo "Task folder: $TASK_PATH"
    else
        require_executable "./scripts/replace_task_from_latest_zip.sh"

        info "Existing task folder found; replacing from latest ZIP"
        ./scripts/replace_task_from_latest_zip.sh "$TASK"
    fi
else
    info "Task folder is missing; treating it as a new task"

    if [[ -n "${TASK_ZIP:-}" ]]; then
        LATEST_TASK_ZIP="$TASK_ZIP"
        [[ -f "$LATEST_TASK_ZIP" ]] \
            || die "TASK_ZIP does not exist: $LATEST_TASK_ZIP"
    else
        LATEST_TASK_ZIP="$(find_latest_task_zip "$ZIP_SEARCH_DIRS")"
    fi

    if [[ -z "${LATEST_TASK_ZIP:-}" ]]; then
        echo "ZIP search locations:" >&2
        IFS=':' read -r -a _display_dirs <<< "$ZIP_SEARCH_DIRS"
        printf '  %s\n' "${_display_dirs[@]}" >&2
        echo >&2
        echo "You can specify the ZIP directly:" >&2
        echo "TASK_ZIP=/absolute/path/${TASK}.zip $0 $TASK" >&2
        die "No matching ZIP found for new task: $TASK"
    fi

    import_new_task_from_zip "$LATEST_TASK_ZIP" "$TASK_PATH"
fi

[[ -d "$TASK_PATH" ]] || die "Task directory not found: $TASK_PATH"
[[ -f "$TASK_PATH/task.toml" ]] || die "task.toml not found: $TASK_PATH/task.toml"

info "Task directory summary"
find "$TASK_PATH" -maxdepth 2 -type d | sort

EXPECTED_MILESTONES="$(
    python3 - "$TASK_PATH/task.toml" <<'PY'
import re
import sys
from pathlib import Path

text = Path(sys.argv[1]).read_text(encoding="utf-8")

match = re.search(
    r'(?m)^\s*number_of_milestones\s*=\s*(\d+)\s*$',
    text,
)

if match:
    print(match.group(1))
else:
    print(text.count("[[steps]]"))
PY
)"

[[ "$EXPECTED_MILESTONES" =~ ^[0-9]+$ ]] \
    || die "Could not determine milestone count"
[[ "$EXPECTED_MILESTONES" -gt 0 ]] \
    || die "Milestone count is zero"

echo "Expected milestones: $EXPECTED_MILESTONES"

if [[ -f "./scripts/preflight_task.py" ]]; then
    info "Running local preflight"

    set +e
    python3 ./scripts/preflight_task.py "$TASK" 2>&1 | tee "$PREFLIGHT_LOG"
    PREFLIGHT_RC="${PIPESTATUS[0]}"
    set -e

    if [[ "$PREFLIGHT_RC" -ne 0 ]]; then
        die "Preflight failed. Check log: $PREFLIGHT_LOG"
    fi
else
    warn "scripts/preflight_task.py not found; skipping preflight"
fi

# Marker prevents a result.json from an older run from being selected.
ORACLE_MARKER="$(mktemp)"
TEMP_PATHS+=("$ORACLE_MARKER")
touch "$ORACLE_MARKER"

info "Running oracle"

set +e
./scripts/terminus2_cli.sh oracle "./${TASK}" 2>&1 | tee "$ORACLE_LOG"
ORACLE_RC="${PIPESTATUS[0]}"
set -e

if [[ "$ORACLE_RC" -ne 0 ]]; then
    die "Oracle command failed with exit code ${ORACLE_RC}. Check log: $ORACLE_LOG"
fi

info "Parsing oracle result"

ORACLE_MODE="unknown"
ORACLE_REWARD="unknown"
LATEST_RESULT_JSON=""

if [[ -d "$REPO_ROOT/.terminus_logs/$TASK" ]]; then
    LATEST_RESULT_JSON="$(
        find "$REPO_ROOT/.terminus_logs/$TASK" \
            -path "*/result.json" \
            -type f \
            -newer "$ORACLE_MARKER" \
            -printf '%T@ %p\n' 2>/dev/null \
            | sort -nr \
            | head -n 1 \
            | cut -d' ' -f2-
    )"
fi

if [[ -n "${LATEST_RESULT_JSON:-}" && -f "$LATEST_RESULT_JSON" ]]; then
    ORACLE_MODE="harbor_result_json"
    ORACLE_REWARD="$(
        python3 - "$LATEST_RESULT_JSON" <<'PY'
import json
import sys

with open(sys.argv[1], "r", encoding="utf-8") as file:
    data = json.load(file)

reward = "unknown"

verifier_result = data.get("verifier_result", {})
rewards = verifier_result.get("rewards", {})

if isinstance(rewards, dict) and rewards.get("reward") not in (None, ""):
    reward = rewards["reward"]
else:
    for eval_data in data.get("stats", {}).get("evals", {}).values():
        metrics = eval_data.get("metrics") or []

        if metrics and metrics[0].get("mean") is not None:
            reward = metrics[0]["mean"]
            break

        reward_stats = (eval_data.get("reward_stats") or {}).get("reward") or {}

        if reward_stats.get("1.0"):
            reward = "1.0"
            break

        if reward_stats.get("1"):
            reward = "1"
            break

print(reward)
PY
    )"
fi

if [[ "$ORACLE_REWARD" == "unknown" || "$ORACLE_REWARD" == "None" ]]; then
    if grep -qE '^=== .+ milestone_[0-9]+ ===$' "$ORACLE_LOG" 2>/dev/null; then
        ORACLE_MODE="docker_cumulative_log"
        ORACLE_REWARD="$(
            python3 - "$ORACLE_LOG" "$EXPECTED_MILESTONES" <<'PY'
import re
import sys
from pathlib import Path

log_path = Path(sys.argv[1])
expected = int(sys.argv[2])
text = log_path.read_text(encoding="utf-8", errors="replace")

markers = list(
    re.finditer(
        r"^===\s+.+?\s+(milestone_\d+)\s+===$",
        text,
        re.M,
    )
)

if not markers:
    print("unknown")
    raise SystemExit(0)

passed = 0
details = []

for index, marker in enumerate(markers):
    name = marker.group(1)
    start = marker.end()
    end = markers[index + 1].start() if index + 1 < len(markers) else len(text)
    block = text[start:end]

    has_reward_one = re.search(r"(?m)^1\s*$", block) is not None
    has_failure_signal = re.search(
        r"(?i)(=+\s+FAILURES\s+=+|FAILED\s+|ERROR\s+|Traceback|"
        r"reward\.txt.*0|^0\s*$)",
        block,
        re.M,
    ) is not None

    reward = "1" if has_reward_one and not has_failure_signal else "0"
    details.append((name, reward))

    if reward == "1":
        passed += 1

print("Docker cumulative parsed milestone rewards:", file=sys.stderr)

for name, reward in details:
    print(f"  {name}: {reward}", file=sys.stderr)

if len(markers) == expected and passed == expected:
    print("1.0")
else:
    print(f"{passed / expected:.6f}")
PY
        )"
    fi
fi

echo
echo "Oracle mode:        $ORACLE_MODE"
echo "Oracle result.json: ${LATEST_RESULT_JSON:-not found for this run}"
echo "Oracle log:         $ORACLE_LOG"
echo "Oracle reward:      $ORACLE_REWARD"

if [[ "$ORACLE_REWARD" != "1.0" && "$ORACLE_REWARD" != "1" ]]; then
    warn "Oracle reward is not 1.0. This task is not submission-ready yet."

    if [[ "${ZIP_EVEN_IF_ORACLE_FAIL:-0}" != "1" ]]; then
        echo
        echo "Skipping ZIP because oracle did not pass."
        echo "To force ZIP creation anyway, run:"
        echo "ZIP_EVEN_IF_ORACLE_FAIL=1 $0 $TASK"
        exit 1
    fi

    warn "ZIP_EVEN_IF_ORACLE_FAIL=1 is set; continuing despite failed oracle."
fi

info "Creating submission ZIP"

set +e
./scripts/zip.sh --task "$TASK" --out "$ZIP_OUT_PATH" 2>&1 | tee "$ZIP_LOG"
ZIP_RC="${PIPESTATUS[0]}"
set -e

if [[ "$ZIP_RC" -ne 0 ]]; then
    die "ZIP command failed with exit code ${ZIP_RC}. Check log: $ZIP_LOG"
fi

info "Workflow completed"

echo "Task:            $TASK"
echo "Repo root:       $REPO_ROOT"
echo "Task folder:     $TASK_PATH"
echo "Preflight log:   $PREFLIGHT_LOG"
echo "Oracle log:      $ORACLE_LOG"
echo "Oracle mode:     $ORACLE_MODE"
echo "Oracle reward:   $ORACLE_REWARD"
echo "ZIP log:         $ZIP_LOG"
echo "ZIP output path: $ZIP_OUT_PATH"
echo
echo "Windows folder:"
echo 'D:\Manoj\Projects\Portfolio\TerminalBench\Terminus-Edition-2\new-task-upload'
