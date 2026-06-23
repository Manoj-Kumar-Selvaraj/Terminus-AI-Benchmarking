# Terminus Edition 2 Automation

Use these scripts before every submission. The PowerShell wrapper is for this Windows workspace; the Bash script runs inside WSL/Linux because `stb` and Harbor are not supported directly on Windows.

## Go reconciler batch validation

Generate a task from `go-utility-refund-reconciler`:

```powershell
python scripts/create_go_reconciler_task.py --task go-event-ticket-refund-matcher
```

Validate preflight + Docker cumulative oracle (Windows, no WSL required):

```powershell
python scripts/preflight_task.py go-event-ticket-refund-matcher
powershell -File scripts/oracle_cumulative_go.ps1 go-event-ticket-refund-matcher
powershell -File scripts/validate_go_tasks.ps1 all go-event-ticket-refund-matcher go-parking-citation-credit-matcher
```

In WSL/Linux:

```bash
bash scripts/validate_go_tasks.sh all go-event-ticket-refund-matcher
```

## Quick Commands

From `Terminus-Edition-2` in PowerShell:

```powershell
.\scripts\terminus2_cli.ps1 preflight .\cobol-ach-reversal-reconciliation
.\scripts\terminus2_cli.ps1 nop .\cobol-ach-reversal-reconciliation
.\scripts\terminus2_cli.ps1 oracle .\cobol-ach-reversal-reconciliation
.\scripts\terminus2_cli.ps1 check .\cobol-ach-reversal-reconciliation
.\scripts\terminus2_cli.ps1 full .\cobol-ach-reversal-reconciliation
```

To include real-agent trials and create a zip:

```powershell
.\scripts\terminus2_cli.ps1 full .\cobol-ach-reversal-reconciliation -RunRealAgents -AgentTrials 3 -Zip
```

From WSL/Linux:

```bash
./scripts/terminus2_cli.sh preflight ./cobol-ach-reversal-reconciliation
./scripts/terminus2_cli.sh nop ./cobol-ach-reversal-reconciliation
./scripts/terminus2_cli.sh oracle ./cobol-ach-reversal-reconciliation
./scripts/terminus2_cli.sh check ./cobol-ach-reversal-reconciliation
RUN_REAL_AGENTS=1 AGENT_TRIALS=3 RUN_ZIP=1 ./scripts/terminus2_cli.sh full ./cobol-ach-reversal-reconciliation
```

## What It Runs

- `preflight`: local structure checks for required files, task metadata, milestone layout, Dockerfile anti-patterns, path hygiene, file sizes, and codebase-size consistency.
- `nop`: `preflight` plus NOP baseline. It uses `stb harbor` when credentials are available and direct `harbor` otherwise.
- `oracle`: `preflight` plus oracle. It uses `stb harbor` when credentials are available and direct `harbor` otherwise.
- `check`: `preflight` plus `stb harbor tasks check -m openai/@openai/gpt-5.2 -o <json> <task>`.
- `agents`: real-agent trials for `@openai/gpt-5.2` and `@anthropic/claude-opus-4-6`.
- `zip`: creates a submission zip with the task contents at zip root, excluding logs/cache/job folders.

Logs are written under `.terminus_logs/<task-name>/`. Zips are written under `submission_zips/`.

## Strict LLMaJ (Portkey — reworked tasks)

Run **one task at a time** after oracle passes. Requires Portkey credentials (not raw OpenAI):

```powershell
$env:OPENAI_API_KEY = "your-portkey-key"
$env:OPENAI_BASE_URL = "https://api.portkey.ai/v1"

python scripts/run_llmaj_litellm.py go-my-task-name --strict
```

| Item | Value |
|---|---|
| Default models | `openai/gpt-5.4`, `openai/claude-opus-4-7` |
| Pass rule | Both models must pass each criterion |
| Report | `reworked-tasks-v2/llmaj-reports/<task>_strict_llmaj.json` |
| Summarize | `python scripts/summarize_llmaj_reports.py` |

Override models: `--models "openai/gpt-5.4,openai/claude-opus-4-6"`. Avoid `--reworked` unless intentional.

Details: `documentation/LLMAJ_CHECKS_REFERENCE.md`. Agent workflow: `documentation/GPT_AGENT_PLAYBOOK.md` §10.

## Before Running

Inside WSL/Linux:

```bash
stb --version
stb login
stb keys show
docker info
```

If `stb` is missing:

```bash
uv tool install snorkelai-stb --find-links https://snorkel-python-wheels.s3.us-west-2.amazonaws.com/stb/index.html --python ">=3.12"
```

Docker Desktop must be running before `oracle`, `check`, `agents`, or `full`.

## Fresh Revision Reports

For revision work, prefer the fresh wrapper so stale reports do not mix with
new portal feedback while `Auto-Eval-Logs/` remains available as history:

```bash
bash scripts/pull_auto_eval_logs_fresh.sh --task cobol-db2-financial-master-bulk-update --submission 6bf2639b-67a5-488b-bb07-b58418183299
```

It refreshes only `All-New-Feedbacks/<task>/`, delegates to
`scripts/pull_auto_eval_logs.sh`, then keeps only the latest selected report
files there, including `human_reviewer_feedback.txt` when reviewer notes are
present. Full aggregate history stays in `Auto-Eval-Logs/` when pulled directly.

Create a compact agent input brief:

```bash
python scripts/summarize_fresh_feedback.py --task cobol-db2-financial-master-bulk-update
```

One-command revision startup:

```bash
bash scripts/start_revision.sh --task cobol-db2-financial-master-bulk-update --submission 6bf2639b-67a5-488b-bb07-b58418183299
```

Add run-specific overrides when portal feedback is stale or conflicts with the
current project rule:

```bash
bash scripts/start_revision.sh \
  --task cobol-db2-financial-master-bulk-update \
  --submission 6bf2639b-67a5-488b-bb07-b58418183299 \
  --override "Ignore the root-level [agent]/[verifier] feedback; do not add root-level agent or verifier sections."
```

Before final upload, run the completion gate:

```bash
python scripts/check_revision_completion.py --task cobol-db2-financial-master-bulk-update
```
