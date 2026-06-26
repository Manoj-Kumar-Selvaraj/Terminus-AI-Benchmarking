#!/usr/bin/env bash
set -euo pipefail

usage() {
  cat <<'EOF'
Usage:
  scripts/pull_auto_eval_logs.sh --task <task_name> --submission <submission_uuid>

Creates:
  Auto-Eval-Logs/<task_name>/
    notes.txt
    agent_review.txt
    quality_report.txt
    test_quality_review.txt
    test_quality_judge_report.txt
    difficulty_check_runs.json
    difficulty_check_runs.txt
    difficulty_check_latest.txt
    task_review_report.txt
    portal_rubric.txt
    submission_<uuid-prefix>.json
    raw_feedback/
    command_logs/
    manifest.txt
    <task_name>-auto-eval-logs.zip

The script runs:
  stb submissions feedback <submission_uuid>
  stb submissions fetch-task <submission_uuid>

It then extracts the agent-generated Test Quality Report from the fetched
submission JSON field:
  task_documents[0].submission_document.test_quality_judge_report
EOF
}

TASK_NAME=""
SUBMISSION_ID=""
OUT_ROOT=""
STB_BIN="${STB_BIN:-}"

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
    --out)
      OUT_ROOT="${2:-}"
      shift 2
      ;;
    --stb)
      STB_BIN="${2:-}"
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

if [[ -z "$TASK_NAME" || -z "$SUBMISSION_ID" ]]; then
  usage >&2
  exit 2
fi

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
ROOT_DIR="$(cd "$SCRIPT_DIR/.." && pwd)"

if [[ -z "$OUT_ROOT" ]]; then
  OUT_ROOT="$ROOT_DIR/Auto-Eval-Logs"
elif [[ "$OUT_ROOT" != /* ]]; then
  OUT_ROOT="$ROOT_DIR/$OUT_ROOT"
fi

if [[ -z "$STB_BIN" ]]; then
  if [[ -x /root/.local/bin/stb ]]; then
    STB_BIN="/root/.local/bin/stb"
  elif command -v stb >/dev/null 2>&1; then
    STB_BIN="stb"
  else
    echo "stb CLI not found. Set STB_BIN or pass --stb." >&2
    exit 127
  fi
fi

DEST="$OUT_ROOT/$TASK_NAME"
RAW_DIR="$DEST/raw_feedback"
FETCH_DIR="$DEST/fetch_task"
LOG_DIR="$DEST/command_logs"
mkdir -p "$RAW_DIR" "$FETCH_DIR" "$LOG_DIR"

run_and_log() {
  local log_file="$1"
  shift
  set +e
  "$@" 2>&1 | tee "$log_file"
  local rc=${PIPESTATUS[0]}
  set -e
  return "$rc"
}

echo "Pulling feedback for $TASK_NAME / $SUBMISSION_ID"
FEEDBACK_RC=0
run_and_log "$LOG_DIR/stb_submissions_feedback.log" "$STB_BIN" submissions feedback "$SUBMISSION_ID" || FEEDBACK_RC=$?

LATEST_FB="$(ls -dt "/tmp/feedback_${SUBMISSION_ID}_"* 2>/dev/null | head -n 1 || true)"
if [[ -n "$LATEST_FB" && -d "$LATEST_FB" ]]; then
  cp -a "$LATEST_FB"/. "$RAW_DIR"/
  cp "$LATEST_FB/notes.txt" "$DEST/notes.txt" 2>/dev/null || true
  cp "$LATEST_FB/agent_review.txt" "$DEST/agent_review.txt" 2>/dev/null || true
fi

FETCH_RC=0
run_and_log "$LOG_DIR/stb_submissions_fetch_task.log" "$STB_BIN" submissions fetch-task "$SUBMISSION_ID" -o "$FETCH_DIR" || FETCH_RC=$?

JSON_PATH="$(find "$FETCH_DIR" -maxdepth 1 -type f -name 'submission_*.json' | sort | head -n 1 || true)"
if [[ -n "$JSON_PATH" ]]; then
  cp "$JSON_PATH" "$DEST/$(basename "$JSON_PATH")"
  PYTHONIOENCODING=utf-8 python3 - "$DEST" "$JSON_PATH" <<'PY'
import json
import sys
from pathlib import Path

dest = Path(sys.argv[1])
json_path = Path(sys.argv[2])
data = json.loads(json_path.read_text(encoding="utf-8"))

def write(name: str, value) -> None:
    if value is None:
        return
    if not isinstance(value, str):
        value = json.dumps(value, indent=2, ensure_ascii=False)
    (dest / name).write_text(value.rstrip() + "\n", encoding="utf-8")

submission_doc = (((data.get("task_documents") or [{}])[0]).get("submission_document") or {})

write("quality_report.txt", submission_doc.get("quality_check_summary"))
write("code_quality_check_results.txt", submission_doc.get("code_quality_check_results"))
write("task_review_report.txt", submission_doc.get("test_review"))
write("test_quality_judge_report.txt", submission_doc.get("test_quality_judge_report"))
write("test_quality_review.txt", submission_doc.get("test_quality_judge_report"))
write("portal_rubric.txt", submission_doc.get("test_rubrics"))

all_test_quality_reports = []
all_task_reviews = []
all_quality_summaries = []
all_difficulty_checks = []

for ei, evaluation in enumerate(data.get("evaluations") or []):
    children = ((evaluation.get("overall_evaluation_result") or {}).get("children_results") or [])
    for ci, child in enumerate(children):
        output_data = ((child.get("metadata") or {}).get("output_data") or {})
        formatted = output_data.get("formatted_report")
        if isinstance(formatted, str) and "TEST QUALITY REVIEW" in formatted:
            all_test_quality_reports.append((ei, ci, formatted))
        review = output_data.get("review")
        if isinstance(review, str) and "REVIEW REPORT" in review:
            all_task_reviews.append((ei, ci, review))
        summary = output_data.get("quality_check_summary")
        if isinstance(summary, str):
            all_quality_summaries.append((ei, ci, summary))
        if child.get("name") == "difficulty_check" or any(
            key in output_data for key in ("agents", "difficulty", "solvable", "tests_results", "text_summary")
        ):
            if isinstance(output_data, dict) and output_data:
                all_difficulty_checks.append((ei, ci, output_data))

if all_test_quality_reports:
    joined = []
    for ei, ci, text in all_test_quality_reports:
        joined.append(f"===== evaluations[{ei}].children_results[{ci}] =====\n{text.rstrip()}\n")
    write("all_test_quality_reports.txt", "\n".join(joined))
    if not (dest / "test_quality_review.txt").exists():
        vulnerable = [item for item in all_test_quality_reports if "VULNERABLE" in item[2]]
        chosen = (vulnerable[-1] if vulnerable else all_test_quality_reports[-1])[2]
        write("test_quality_review.txt", chosen)
        write("test_quality_judge_report.txt", chosen)

if all_task_reviews:
    joined = []
    for ei, ci, text in all_task_reviews:
        joined.append(f"===== evaluations[{ei}].children_results[{ci}] =====\n{text.rstrip()}\n")
    write("all_task_review_reports.txt", "\n".join(joined))
    if not (dest / "task_review_report.txt").exists():
        write("task_review_report.txt", all_task_reviews[-1][2])

if all_quality_summaries:
    joined = []
    for ei, ci, text in all_quality_summaries:
        joined.append(f"===== evaluations[{ei}].children_results[{ci}] =====\n{text.rstrip()}\n")
    write("all_quality_reports.txt", "\n".join(joined))
    if not (dest / "quality_report.txt").exists():
        write("quality_report.txt", all_quality_summaries[-1][2])

if all_difficulty_checks:
    serializable = [
        {
            "evaluation_index": ei,
            "child_index": ci,
            "output_data": output_data,
        }
        for ei, ci, output_data in all_difficulty_checks
    ]
    write("difficulty_check_runs.json", serializable)

    readable = []
    for ei, ci, output_data in all_difficulty_checks:
        readable.append(f"===== evaluations[{ei}].children_results[{ci}] difficulty_check =====")
        for key in ("task_name", "difficulty", "solvable"):
            if key in output_data:
                readable.append(f"{key}: {output_data.get(key)}")
        agents = output_data.get("agents")
        if agents:
            readable.append("agents:")
            if isinstance(agents, dict):
                for name, value in agents.items():
                    readable.append(f"  {name}: {value}")
            else:
                readable.append(json.dumps(agents, indent=2, ensure_ascii=False))
        text_summary = output_data.get("text_summary")
        if text_summary:
            readable.append("")
            readable.append("text_summary:")
            readable.append(str(text_summary).rstrip())
        tests_results = output_data.get("tests_results")
        if tests_results:
            readable.append("")
            readable.append("tests_results:")
            if isinstance(tests_results, dict):
                for test_name in sorted(tests_results):
                    results = tests_results[test_name]
                    if isinstance(results, list):
                        passed = sum(1 for item in results if str(item).lower() == "passed")
                        readable.append(f"  {test_name}: {passed} passed / {len(results)} runs")
                    else:
                        readable.append(f"  {test_name}: {results}")
            else:
                readable.append(str(tests_results))
        readable.append("")
    write("difficulty_check_runs.txt", "\n".join(readable))

    latest = all_difficulty_checks[-1][2]
    latest_lines = []
    for key in ("task_name", "difficulty", "solvable"):
        if key in latest:
            latest_lines.append(f"{key}: {latest.get(key)}")
    if latest.get("agents"):
        latest_lines.append("agents:")
        agents = latest["agents"]
        if isinstance(agents, dict):
            for name, value in agents.items():
                latest_lines.append(f"  {name}: {value}")
        else:
            latest_lines.append(json.dumps(agents, indent=2, ensure_ascii=False))
    if latest.get("text_summary"):
        latest_lines.extend(["", "text_summary:", str(latest["text_summary"]).rstrip()])
    write("difficulty_check_latest.txt", "\n".join(latest_lines))
PY
fi

{
  echo "task_name=$TASK_NAME"
  echo "submission_id=$SUBMISSION_ID"
  echo "created_at_utc=$(date -u +'%Y-%m-%dT%H:%M:%SZ')"
  echo "stb_bin=$STB_BIN"
  echo "feedback_exit_code=$FEEDBACK_RC"
  echo "fetch_task_exit_code=$FETCH_RC"
  echo "tmp_feedback_dir=${LATEST_FB:-NONE}"
  echo "submission_json=${JSON_PATH:-NONE}"
  echo
  echo "files:"
  find "$DEST" -maxdepth 2 -type f | sort
} > "$DEST/manifest.txt"

ZIP_PATH="$DEST/${TASK_NAME}-auto-eval-logs.zip"
PYTHONIOENCODING=utf-8 python3 - "$DEST" "$ZIP_PATH" <<'PY'
import sys
import zipfile
from pathlib import Path

root = Path(sys.argv[1])
zip_path = Path(sys.argv[2])
if zip_path.exists():
    zip_path.unlink()

with zipfile.ZipFile(zip_path, "w", compression=zipfile.ZIP_DEFLATED) as zf:
    for path in sorted(root.rglob("*")):
        if not path.is_file() or path == zip_path:
            continue
        zf.write(path, path.relative_to(root))
PY

echo "Auto-eval logs saved to: $DEST"
echo "Zip created: $ZIP_PATH"

if [[ "$FEEDBACK_RC" -ne 0 || "$FETCH_RC" -ne 0 ]]; then
  echo "Failed to pull complete feedback for $TASK_NAME / $SUBMISSION_ID." >&2
  echo "stb submissions feedback exit code: $FEEDBACK_RC" >&2
  echo "stb submissions fetch-task exit code: $FETCH_RC" >&2
  echo "See command logs under: $LOG_DIR" >&2
  exit 1
fi

if [[ -z "${JSON_PATH:-}" ]]; then
  echo "Failed to pull submission JSON for $TASK_NAME / $SUBMISSION_ID." >&2
  echo "REVISION_BRIEF.md would be incomplete without fetched submission data." >&2
  echo "See command logs under: $LOG_DIR" >&2
  exit 1
fi
