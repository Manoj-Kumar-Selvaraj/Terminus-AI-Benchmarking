#!/usr/bin/env bash
set -euo pipefail

usage() {
  cat <<'EOF'
Usage:
  scripts/pull_auto_eval_logs_fresh.sh --task <task_name> --submission <submission_uuid>

Options:
  --out <dir>       Override fresh output root. Defaults to All-New-Feedbacks.
  --stb <path>      Override stb executable path.
  -h, --help        Show this help.

Leaves Auto-Eval-Logs history untouched. Refreshes All-New-Feedbacks/<task_name>
by deleting only that fresh folder, then runs pull_auto_eval_logs.sh so the
fresh folder contains only reports for the requested submission.
EOF
}

TASK_NAME=""
SUBMISSION_ID=""
OUT_ROOT=""
STB_ARG=()

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
      STB_ARG=("$1" "$2")
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

case "$TASK_NAME" in
  ""|.|..|*/*|*\\*)
    echo "Unsafe task name for report deletion: $TASK_NAME" >&2
    exit 2
    ;;
esac

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
ROOT_DIR="$(cd "$SCRIPT_DIR/.." && pwd)"

if [[ -z "$OUT_ROOT" ]]; then
  OUT_ROOT="$ROOT_DIR/All-New-Feedbacks"
elif [[ "$OUT_ROOT" != /* ]]; then
  OUT_ROOT="$ROOT_DIR/$OUT_ROOT"
fi

mkdir -p "$OUT_ROOT"
OUT_ROOT_REAL="$(cd "$OUT_ROOT" && pwd -P)"
DEST="$OUT_ROOT_REAL/$TASK_NAME"

case "$DEST" in
  "$OUT_ROOT_REAL"/*) ;;
  *)
    echo "Refusing to delete path outside output root: $DEST" >&2
    exit 2
    ;;
esac

if [[ -e "$DEST" ]]; then
  echo "Removing existing fresh feedback folder: $DEST"
  rm -rf -- "$DEST"
fi

"$SCRIPT_DIR/pull_auto_eval_logs.sh" \
  --task "$TASK_NAME" \
  --submission "$SUBMISSION_ID" \
  --out "$OUT_ROOT_REAL" \
  "${STB_ARG[@]}"

PYTHONIOENCODING=utf-8 python3 - "$DEST" "$TASK_NAME" <<'PY'
import json
import shutil
import sys
import zipfile
from pathlib import Path

dest = Path(sys.argv[1])
task_name = sys.argv[2]

json_paths = sorted(dest.glob("submission_*.json"))
if not json_paths:
    raise SystemExit(
        "No submission_*.json found in fresh feedback. "
        "The pull likely failed; refusing to generate an incomplete latest-only report."
    )

data = json.loads(json_paths[0].read_text(encoding="utf-8"))
sources = {}


def extract_human_reviewer_feedback() -> str:
    sections = []

    direct_fields = (
        ("user_reviews", data.get("user_reviews")),
        ("review_document", data.get("review_document")),
        ("review_documents", data.get("review_documents")),
        ("accept_notes", data.get("accept_notes")),
        ("rebuttal_notes", data.get("rebuttal_notes")),
        ("ec_override_feedback", data.get("ec_override_feedback")),
    )

    for name, value in direct_fields:
        if value in (None, "", [], {}):
            continue
        if isinstance(value, str):
            rendered = value.strip()
        else:
            rendered = json.dumps(value, indent=2, ensure_ascii=False)
        if rendered:
            sections.append((name, rendered))

    def walk(obj, path=""):
        if isinstance(obj, dict):
            for key, value in obj.items():
                key_path = f"{path}.{key}" if path else key
                key_lower = key.lower()
                if any(token in key_lower for token in ("human", "reviewer", "manual")):
                    if (
                        key in {"reviewer_feedback_config", "manual_success_criteria"}
                        or key.startswith("checkbox_")
                        or isinstance(value, bool)
                    ):
                        pass
                    elif value not in (None, "", [], {}):
                        if isinstance(value, str):
                            rendered = value.strip()
                        else:
                            rendered = json.dumps(value, indent=2, ensure_ascii=False)
                        if rendered:
                            sections.append((key_path, rendered))
                walk(value, key_path)
        elif isinstance(obj, list):
            for index, value in enumerate(obj):
                walk(value, f"{path}[{index}]")

    walk(data)

    deduped = []
    seen = set()
    for name, rendered in sections:
        marker = (name, rendered)
        if marker in seen:
            continue
        seen.add(marker)
        deduped.append((name, rendered))

    lines = [
        "Human reviewer feedback",
        "=======================",
        "",
    ]
    if not deduped:
        lines.append("No separate human reviewer feedback was found in the fetched submission JSON.")
        lines.append("Portal revision notes, if present, remain in notes.txt.")
        return "\n".join(lines)

    for index, (name, rendered) in enumerate(deduped, start=1):
        lines.extend([f"{index}. {name}", "-" * (len(name) + len(str(index)) + 2), rendered.rstrip(), ""])
    return "\n".join(lines).rstrip()


def write(name: str, value) -> None:
    if value is None:
        return
    if not isinstance(value, str):
        value = json.dumps(value, indent=2, ensure_ascii=False)
    (dest / name).write_text(value.rstrip() + "\n", encoding="utf-8")


def collect_reports():
    test_quality = []
    task_reviews = []
    quality_summaries = []
    difficulty_checks = []

    for ei, evaluation in enumerate(data.get("evaluations") or []):
        children = ((evaluation.get("overall_evaluation_result") or {}).get("children_results") or [])
        for ci, child in enumerate(children):
            output_data = ((child.get("metadata") or {}).get("output_data") or {})

            formatted = output_data.get("formatted_report")
            if isinstance(formatted, str) and "TEST QUALITY REVIEW" in formatted:
                test_quality.append((ei, ci, formatted))

            review = output_data.get("review")
            if isinstance(review, str) and "REVIEW REPORT" in review:
                task_reviews.append((ei, ci, review))

            summary = output_data.get("quality_check_summary")
            if isinstance(summary, str):
                quality_summaries.append((ei, ci, summary))

            if child.get("name") == "difficulty_check" or any(
                key in output_data for key in ("agents", "difficulty", "solvable", "tests_results", "text_summary")
            ):
                if isinstance(output_data, dict) and output_data:
                    difficulty_checks.append((ei, ci, output_data))

    return test_quality, task_reviews, quality_summaries, difficulty_checks


test_quality, task_reviews, quality_summaries, difficulty_checks = collect_reports()
if test_quality:
    ei, ci, text = test_quality[-1]
    write("test_quality_judge_report.txt", text)
    write("test_quality_review.txt", text)
    sources["test_quality_judge_report.txt"] = f"evaluations[{ei}].children_results[{ci}]"
    sources["test_quality_review.txt"] = f"evaluations[{ei}].children_results[{ci}]"

if task_reviews:
    ei, ci, text = task_reviews[-1]
    write("task_review_report.txt", text)
    sources["task_review_report.txt"] = f"evaluations[{ei}].children_results[{ci}]"

if quality_summaries:
    ei, ci, text = quality_summaries[-1]
    write("quality_report.txt", text)
    sources["quality_report.txt"] = f"evaluations[{ei}].children_results[{ci}]"

if difficulty_checks:
    ei, ci, latest = difficulty_checks[-1]
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
    sources["difficulty_check_latest.txt"] = f"evaluations[{ei}].children_results[{ci}]"

if sources:
    source_lines = [
        "Latest report sources",
        "=====================",
        "",
        "These files were selected from the newest matching evaluation child in the fetched submission JSON.",
        "",
    ]
    source_lines.extend(f"{name}: {source}" for name, source in sorted(sources.items()))
    write("report_sources.txt", "\n".join(source_lines))

write("human_reviewer_feedback.txt", extract_human_reviewer_feedback())

for name in (
    "all_quality_reports.txt",
    "all_task_review_reports.txt",
    "all_test_quality_reports.txt",
    "difficulty_check_runs.json",
    "difficulty_check_runs.txt",
    "latest_difficulty_source.txt",
    "latest_quality_source.txt",
    "latest_task_review_source.txt",
    "latest_test_quality_source.txt",
):
    path = dest / name
    if path.exists():
        path.unlink()

for path in dest.glob("submission_*.json"):
    path.unlink()

for dirname in ("fetch_task", "raw_feedback"):
    path = dest / dirname
    if path.exists():
        shutil.rmtree(path)

readme = """Fresh auto-eval feedback
========================

This folder is a curated latest-only view for the requested task/submission.
Historical and aggregate report pulls should remain under Auto-Eval-Logs.

Read first:
- notes.txt
- agent_review.txt
- task_review_report.txt
- test_quality_judge_report.txt
- quality_report.txt
- difficulty_check_latest.txt
- code_quality_check_results.txt
- human_reviewer_feedback.txt

report_sources.txt records which evaluation child supplied each selected report.
"""
write("README.txt", readme)

manifest = dest / "manifest.txt"
if manifest.exists():
    head = []
    for line in manifest.read_text(encoding="utf-8").splitlines():
        if line == "files:":
            break
        head.append(line)
    lines = head + ["latest_only=true", "", "files:"]
    for path in sorted(dest.rglob("*")):
        if path.is_file() and path.name != f"{task_name}-auto-eval-logs.zip":
            lines.append(str(path))
    manifest.write_text("\n".join(lines) + "\n", encoding="utf-8")

zip_path = dest / f"{task_name}-auto-eval-logs.zip"
if zip_path.exists():
    zip_path.unlink()
with zipfile.ZipFile(zip_path, "w", compression=zipfile.ZIP_DEFLATED) as zf:
    for path in sorted(dest.rglob("*")):
        if path.is_file() and path != zip_path:
            zf.write(path, path.relative_to(dest))
PY

echo "Latest-only fresh reports saved to: $DEST"
