# Revision Workflow

Use this workflow when a task comes back with revision feedback.

Agents should follow [REVISION_AGENT_BIBLE.md](REVISION_AGENT_BIBLE.md) for the
strict execution rules.

## 1. Pull Fresh Reports

Prefer the fresh-pull wrapper so stale reports do not mix with the latest portal feedback:

```bash
bash scripts/pull_auto_eval_logs_fresh.sh \
  --task <task-name> \
  --submission <submission-id>
```

Or use the single startup wrapper:

```bash
bash scripts/start_revision.sh --task <task-name> --submission <submission-id>
```

By default, `start_revision.sh` also cleans the fresh feedback workspace so
only the requested `All-New-Feedbacks/<task-name>/` folder remains. It removes
other task-named folders under `All-New-Feedbacks/` only; it does not remove
task source folders. Keep additional fresh feedback folders with:

```bash
bash scripts/start_revision.sh \
  --task <task-name> \
  --submission <submission-id> \
  --keep-task <task-to-preserve>
```

Use `--keep-task` multiple times, `--keep-tasks a,b,c`, or
`--no-clean-feedback-folders` when you intentionally need the old behavior.

This leaves `Auto-Eval-Logs/` untouched as report history. It refreshes only
`All-New-Feedbacks/<task-name>/`, then runs `scripts/pull_auto_eval_logs.sh` and
post-processes the folder into a latest-only view. The fresh folder keeps the
current feedback, selected latest task review, selected latest quality report,
selected latest test-quality report, latest difficulty summary, portal rubric,
human reviewer feedback when present, manifest, command logs, and report zip.
Bulk aggregate files such as `all_test_quality_reports.txt` are removed from
the fresh folder.

Use `scripts/pull_auto_eval_logs.sh` directly only when you intentionally want
to write into the historical `Auto-Eval-Logs/` tree or another custom location.

## 2. Read The Last Feedback First

Generate the compact brief:

```bash
python scripts/summarize_fresh_feedback.py --task <task-name>
```

The generated `REVISION_BRIEF.md` is intentionally copy-friendly: it includes
the full curated fresh report files in one markdown document and does not
truncate sections or omit extra file mentions.

Start with the newest or most specific report sections:

- `REVISION_BRIEF.md`
- `notes.txt`
- `agent_review.txt`
- `task_review_report.txt`
- `quality_report.txt`
- `test_quality_judge_report.txt`
- `difficulty_check_latest.txt`
- `code_quality_check_results.txt`
- `human_reviewer_feedback.txt`

When reports disagree, prefer the most recent portal revision notes and the
last vulnerable or failed section at the end of the report.

## 3. Patch The Task

Fix every high-severity issue and any actionable warnings or coverage gaps.
Keep edits scoped to the task folder, preserve the milestone structure, and
update rubrics or instructions when the report says the scoring contract or
spec is incomplete.

## 4. Validate

Run local preflight and the oracle before packaging:

```bash
python scripts/preflight_task.py <task-name>
USE_DIRECT_HARBOR=1 bash scripts/terminus2_cli.sh oracle ./<task-name>
```

If the Harbor static-check script exists in the checkout or validation image,
run it too. Clean local cache artifacts before packaging.

## 5. Rebuild The Upload Zip

Always use the standard zip script:

```bash
bash scripts/zip.sh --task <task-name> --out new-task-upload
```

Confirm the zip does not contain caches, logs, reports, or generated test
artifacts before uploading.

Then run:

```bash
python scripts/check_revision_completion.py --task <task-name>
```
