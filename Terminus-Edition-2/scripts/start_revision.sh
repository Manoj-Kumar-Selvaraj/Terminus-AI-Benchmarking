#!/usr/bin/env bash
set -euo pipefail

usage() {
  cat <<'EOF'
Usage:
  bash scripts/start_revision.sh --task <task-name> --submission <submission-id>

Options:
  --no-pull        Do not fetch feedback; regenerate REVISION_BRIEF.md only.
  --validate       Run preflight and oracle after creating the brief.
  --zip            Rebuild upload zip after validation/setup.
  --check          Run check_revision_completion.py at the end.
  --allow-unchecked
                  Pass --allow-unchecked to check_revision_completion.py.
  --override <text>
                  Write text to All-New-Feedbacks/<task>/USER_OVERRIDES.md
                  before generating the brief. May be passed multiple times.
  -h, --help       Show this help.

Default behavior:
  1. Refresh All-New-Feedbacks/<task>
  2. Generate All-New-Feedbacks/<task>/REVISION_BRIEF.md
  3. Print the exact prompt to paste into the agent
EOF
}

TASK_NAME=""
SUBMISSION_ID=""
DO_PULL=1
DO_VALIDATE=0
DO_ZIP=0
DO_CHECK=0
ALLOW_UNCHECKED=0
OVERRIDES=()

while [[ $# -gt 0 ]]; do
  case "$1" in
    --task)
      TASK_NAME="${2:-}"
      shift 2
      ;;
    --submission|--id)
      SUBMISSION_ID="${2:-}"
      shift 2
      ;;
    --no-pull)
      DO_PULL=0
      shift
      ;;
    --validate)
      DO_VALIDATE=1
      shift
      ;;
    --zip)
      DO_ZIP=1
      shift
      ;;
    --check)
      DO_CHECK=1
      shift
      ;;
    --allow-unchecked)
      ALLOW_UNCHECKED=1
      shift
      ;;
    --override)
      OVERRIDES+=("${2:-}")
      shift 2
      ;;
    -h|--help)
      usage
      exit 0
      ;;
    *)
      echo "Unknown argument: $1" >&2
      usage >&2
      exit 2
      ;;
  esac
done

if [[ -z "$TASK_NAME" ]]; then
  usage >&2
  exit 2
fi

if [[ "$DO_PULL" -eq 1 && -z "$SUBMISSION_ID" ]]; then
  echo "--submission is required unless --no-pull is used." >&2
  exit 2
fi

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
ROOT_DIR="$(cd "$SCRIPT_DIR/.." && pwd)"
cd "$ROOT_DIR"

if [[ "$DO_PULL" -eq 1 ]]; then
  bash scripts/pull_auto_eval_logs_fresh.sh --task "$TASK_NAME" --submission "$SUBMISSION_ID"
fi

if [[ "${#OVERRIDES[@]}" -gt 0 ]]; then
  FEEDBACK_DIR="All-New-Feedbacks/$TASK_NAME"
  mkdir -p "$FEEDBACK_DIR"
  {
    echo "# User Overrides"
    echo
    for item in "${OVERRIDES[@]}"; do
      echo "- $item"
    done
  } > "$FEEDBACK_DIR/USER_OVERRIDES.md"
fi

python scripts/summarize_fresh_feedback.py --task "$TASK_NAME"

if [[ "$DO_VALIDATE" -eq 1 ]]; then
  python scripts/preflight_task.py "$TASK_NAME"
  USE_DIRECT_HARBOR=1 bash scripts/terminus2_cli.sh oracle "./$TASK_NAME"
fi

if [[ "$DO_ZIP" -eq 1 ]]; then
  bash scripts/zip.sh --task "$TASK_NAME" --out new-task-upload
fi

if [[ "$DO_CHECK" -eq 1 ]]; then
  CHECK_ARGS=(--task "$TASK_NAME")
  if [[ "$ALLOW_UNCHECKED" -eq 1 ]]; then
    CHECK_ARGS+=(--allow-unchecked)
  fi
  python scripts/check_revision_completion.py "${CHECK_ARGS[@]}"
fi

cat <<EOF

================================================================================
Paste this prompt into the agent:
================================================================================

Follow documentation/REVISION_AGENT_BIBLE.md exactly.

Task: $TASK_NAME
Submission: ${SUBMISSION_ID:-<submission-id>}

Use only:
- All-New-Feedbacks/$TASK_NAME/REVISION_BRIEF.md
- $TASK_NAME/

Fix every actionable issue in the brief. Do not read old Auto-Eval-Logs unless
I explicitly ask. Keep edits scoped. Run preflight, oracle, rebuild the upload
zip with scripts/zip.sh, and run check_revision_completion.py. Do not final
answer until validation is complete or a blocker is explicit. If oracle failed
in portal or fails locally, read all fresh oracle/difficulty evidence under
All-New-Feedbacks/$TASK_NAME/ before deciding the fix is complete.

If fresh difficulty says the task was not tested because oracle failed but local
oracle passes, still fix every actionable review warning that could affect the
next upload, rerun oracle after those edits, and report the exact newest oracle
log and newest zip path.

Always inspect the task-instruction / instruction-sufficiency summary in the
fresh reports, even when difficulty is hard and oracle passes. Confirm every
new or changed test assertion is documented in milestone instructions or
referenced /app/docs contracts before zipping.

Do not treat the difficulty label as the whole report. Review solvable/oracle
status, agent pass rates and abnormal failures, the task-instruction summary,
instruction sufficiency, unpassed or flaky tests, and skipped runs. Report
"difficulty report: reviewed" and
"instruction sufficiency: reviewed / updated" in the final answer.

If the brief contains a "User Overrides" section, it supersedes conflicting
feedback from reports.

================================================================================
Brief:
All-New-Feedbacks/$TASK_NAME/REVISION_BRIEF.md
================================================================================
EOF
