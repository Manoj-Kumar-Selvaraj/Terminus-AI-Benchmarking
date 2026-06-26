# Revision Agent Bible

Use these instructions for every Terminus Edition 2 revision task. The goal is
factory-style consistency: read the same inputs, follow the same order, validate
the same way, and never miss an actionable issue.

## Prime Directive

Fix every actionable issue in `REVISION_BRIEF.md`. Do not hunt through old logs
unless explicitly told to. Do not final-answer until the task is validated and
the upload zip is rebuilt. Before final-answering, review the revised task as a
submission package: instructions, tests, oracle solutions, `task.toml`,
Dockerfile, and rubric must still agree with each other.

If `REVISION_BRIEF.md` contains a `User Overrides` section, those instructions
supersede conflicting report feedback.

## Required Inputs

The user or operator should run:

```bash
bash scripts/pull_auto_eval_logs_fresh.sh --task <task-name> --submission <submission-id>
python scripts/summarize_fresh_feedback.py --task <task-name>
```

Then the agent must use:

```text
All-New-Feedbacks/<task-name>/REVISION_BRIEF.md
```

The task source is:

```text
<task-name>/
```

**Important:** the fresh pull is curated for token discipline. It does **not**
retain `raw_feedback/` oracle job logs. When portal oracle failed, also run
`pull_auto_eval_logs.sh` (full pull) or read
`Auto-Eval-Logs/<task-name>/raw_feedback/` — see Portal Oracle Failure
Debugging.

## Reading Order

1. Read `REVISION_BRIEF.md` completely.
2. Read only the task files needed to fix the issues in the brief.
3. Read full report files from `All-New-Feedbacks/<task-name>/` only if the
   brief is ambiguous.
4. If the brief, portal notes, local validation, or latest oracle log says
   oracle failed, **stop and run the Portal Oracle Failure Debugging
   workflow below before editing further.** Summaries alone are not enough.
5. Always review the task-instruction / instruction-sufficiency summary inside
   the fresh brief and fresh reports, even when difficulty is already hard and
   oracle passes. Treat gaps there as actionable unless clearly superseded by
   newer human feedback.
6. Do not read `Auto-Eval-Logs/`, archived logs, raw feedback trees, or old
   zips unless the user explicitly asks **or** you are debugging a portal
   oracle failure (see below — that is a required exception).

## Work Rules

- Treat human reviewer feedback as highest priority.
- Then fix portal revision notes, agent review critical issues, test quality
  gaps, task review failures, quality/static failures, and difficulty/oracle
  failures.
- If feedback conflicts, follow the newest human/portal feedback. State the
  conflict briefly in the final answer.
- If user overrides conflict with report feedback, follow the user overrides.
- Keep edits scoped to the task unless the request is automation/workflow
  improvement.
- Do not revert unrelated user changes.
- Use `apply_patch` for manual edits.
- Remove generated caches before zipping.
- Always use `scripts/zip.sh` to create upload zips.
- Update the final rubric after task changes. The rubric must match the final
  milestone behavior, use valid score values and headers, and avoid stale
  criteria from earlier versions of the task.

## Issue Checklist

For every issue in `REVISION_BRIEF.md`, mark it mentally or in a local note as:

```text
FIXED / N/A / BLOCKED
```

Use `N/A` only when the issue is explicitly superseded by newer feedback or is
not present in the current task. Use `BLOCKED` only when required data or tools
are unavailable.

Common issue types to check:

- Docker build failures
- Docker base image static failures:
  - Prefer a digest-pinned base image already accepted by static checks.
  - Do not switch to a tagged `ghcr.io/laude-institute/t-bench/...` base merely
    because a review suggests it; portal static may reject tagged or
    non-canonical bases.
  - If a raw digest-pinned base is used, install required runtime/session tools
    explicitly, especially `tmux` and `asciinema`.
- blocked or wrong task category:
  - Portal static checks (`run_static_checks.py --version edition_2`) reject
    `debugging` and `software-engineering` for this project even though they are
    valid Edition 2 categories in the repo validator.
  - Before upload, confirm `task.toml` `category` is **not** one of those two
    blocked values. Keep `debugging` in `tags` when it describes the work.
  - Typical remaps: COBOL/batch billing and ledger tasks → `data-processing`;
    infra/K8s/AWS/Docker recovery tasks → `system-administration`; build/CI
    pipeline tasks → `build-and-dependency-management`.
  - Runtime Dockerfile warnings about `make`, `gnucobol`, or other build
    toolchains in a single-stage image are expected false positives when the
    agent must compile COBOL (or similar) at runtime; keep the single-stage
    Dockerfile and add a brief comment citing the carve-out.
- `test.sh` reward section format (portal static error):
  - Each milestone `steps/milestone_N/tests/test.sh` must end with either
    `if [ $? -eq 0 ]` immediately after pytest, or `var=$?` then
    `if [ "$var" -eq 0 ]` (quoted variable).
  - `exit_code=$?` followed by `if [ $exit_code -eq 0 ]` (unquoted) fails
    `run_static_checks.py --version edition_2`.
- ruff static failures:
  - Portal runs `ruff check` across the whole task tree (environment scripts
    and milestone tests). Fix E401 (split imports), F401 (unused imports),
    E701/E703 (one-statement-per-line), then rerun `python -m ruff check <task>`.
- root-level agent/verifier rules
- missing required dependencies such as `tmux` or `asciinema`
- tests/solution copied into Docker image
- stale `.pytest_cache`, `.ruff_cache`, `__pycache__`, `.pyc`
- instruction insufficiency
- task-instruction summary concerns inside difficulty or quality reports
- test coverage gaps
- rubric headers, point ranges, invalid point values, or wrong task rubric
- oracle failures
- static check failures
- difficulty failures or "not run by any agent" caused by task environment

## Mandatory Difficulty Report Review

Do not treat the difficulty label as the whole difficulty report. For every
revision, inspect the complete fresh difficulty summary and any task-instruction
analysis included with it. Record each item as `PASS`, `FIXED`, `N/A`, or
`BLOCKED`:

1. Difficulty classification and whether it meets the project requirement.
2. Solvable status and oracle success rate.
3. Frontier-agent pass rates and abnormal failure categories.
4. Task-instruction summary, instruction-sufficiency findings, and any tested
   behavior described as absent, ambiguous, or under-specified.
5. Tests not passed by any agent, suspicious test variance, and runs skipped
   because of oracle, verifier, build, reward, or timeout failures.

A `hard` classification and passing oracle do not override an instruction
sufficiency concern. Fix the instructions or referenced contract documents,
align tests and oracle solutions, update the rubric, and rerun validation.

Before final-answering, explicitly report:

```text
difficulty report: reviewed
instruction sufficiency: reviewed / updated
```

## Oracle Failure Escalation

Treat oracle failures as a special stop-and-investigate condition, even when a
previous agent claims all fixes are implemented.

When oracle failed in the portal or fails locally:

1. Read the latest fresh difficulty/oracle evidence from
   `All-New-Feedbacks/<task-name>/`, not old `Auto-Eval-Logs/` (except raw
   oracle logs — see Portal Oracle Failure Debugging).
2. Identify whether the failure is Docker build, verifier did not run, reward
   file missing, a specific milestone test failure, timeout, static failure, or
   local/portal environment drift.
3. Compare the fresh portal failure with the latest local oracle log under
   `.terminus_logs/<task-name>/`.
4. Reproduce locally when possible, fix the root cause, and rerun oracle.
5. If local oracle passes but portal oracle failed, inspect Dockerfile,
   `test.sh`, line endings, root/per-step timeouts, workdir, copied files,
   package structure, and generated-cache issues before concluding N/A.
6. If fresh difficulty says the task was not tested because the oracle failed
   but local oracle passes, do not stop there. Re-read agent/test-quality/task
   review warnings and fix any actionable packaging, fixture-leakage, coverage,
   rubric, timeout, or static-risk issues that could make the portal reject the
   same upload again. Then rerun local oracle after those edits.
7. If the portal feedback does not include the failing oracle transcript, say
   that explicitly in the final answer and report the newest local oracle log
   used for validation.

Do not final-answer with "oracle passed" unless the oracle command was run
after the latest relevant task edits and the latest oracle log shows every
milestone reward passed.

## Portal Oracle Failure Debugging

**Mandatory when any of these are true:**

- `notes.txt` or `difficulty_check_latest.txt` says oracle failed, build
  failed, or agents were not run because oracle failed
- `AutoEval Execution Summary: ... Build status: FAILED`
- Local oracle passes but portal oracle failed on the same submission

**Why summaries are not enough:** `pull_auto_eval_logs_fresh.sh` keeps only
curated reports under `All-New-Feedbacks/<task-name>/`. It removes
`raw_feedback/` and `difficulty_check_runs.json`. Those deletions are
intentional for token discipline, but they hide the actual oracle stderr,
per-milestone `reward.txt`, and pytest output. A one-line
`difficulty_check_latest.txt` such as "Oracle solution failed" is **not**
sufficient to diagnose or fix the task.

### Step 1 — Read fresh summaries first

From `All-New-Feedbacks/<task-name>/`:

- `REVISION_BRIEF.md`
- `notes.txt`
- `difficulty_check_latest.txt`
- `code_quality_check_results.txt` (distinguish Docker **build** failure from
  oracle **verifier** failure)

### Step 2 — Pull or locate raw oracle job logs (required)

Do **one** of the following before claiming the root cause:

```bash
# Preferred when stb is available: full pull keeps raw_feedback/
bash scripts/pull_auto_eval_logs.sh \
  --task <task-name> \
  --submission <submission-id>
```

Then read:

```text
Auto-Eval-Logs/<task-name>/raw_feedback/agent_logs/jobs/github-action-oracle_*/
```

If a full pull is unavailable, read the same paths from the most recent
`/tmp/feedback_<submission-id>_*/agent_logs/jobs/` tree left by
`stb submissions feedback <submission-id>`.

**Do not skip this step** when oracle failed in portal. Do not infer the fix
from Dockerfile warnings, agent review suggestions, or a passing local oracle
alone.

### Step 3 — Read these files in order

For each milestone `N` that failed (start with the earliest failing step):

```text
.../steps/milestone_N/agent/oracle.txt      # solve.sh stderr — read first
.../steps/milestone_N/agent/exit-code.txt
.../steps/milestone_N/verifier/test-stdout.txt
.../steps/milestone_N/verifier/reward.txt     # expect 1
.../job.log                                   # build / step order
```

Search raw logs quickly:

```bash
rg -i "fail|error|No such file|solve|reward|assert" \
  Auto-Eval-Logs/<task-name>/raw_feedback/agent_logs/jobs/
```

### Step 4 — Classify the failure

| Symptom in raw logs | Likely cause | Typical fix |
|---|---|---|
| `bash: //milestone_1/solution/solve1.sh: No such file or directory` or other cross-milestone path errors | M2+ `solve.sh` calls `$TASK_ROOT/milestone_*/solution/...` which resolves wrong in portal mounts | Copy prior `solveN.sh` into each later milestone's `solution/`; chain only via `$SCRIPT_DIR` |
| M1 passes, M2/M3 fail on `workflow_ready is False` or prior-milestone assertions | Later milestone oracle never applied earlier fixes (same root cause as above) | Self-contained per-milestone solution scripts |
| Docker build error in `code_quality_check_results.txt` or build phase | Apt pin drift, missing deps, bad base image | Fix Dockerfile; unpinned apt where appropriate; keep digest-pinned base |
| `reward.txt` is `0`, pytest assertion in `test-stdout.txt` | Real test/solution mismatch | Fix oracle solution or align tests/docs |
| Local cumulative oracle passes, portal fails with path errors | Local harness runs each milestone in a **fresh container**; portal Harbor runs **sequentially in one container** | Fix portal path/layout; do not treat "step-only solve.sh" as validated unless portal logs confirm it |
| Oracle job never ran; only "Build status: FAILED" | Environment build failed before verifier | Fix Docker/build first, then rerun |

### Step 5 — Apply the fix and re-validate

After fixing from raw logs (not guesses):

```bash
python scripts/preflight_task.py <task-name>
USE_DIRECT_HARBOR=1 bash scripts/terminus2_cli.sh oracle ./<task-name>
bash scripts/zip.sh --task <task-name> --out new-task-upload
python scripts/check_revision_completion.py --task <task-name> --allow-unchecked
```

In the final answer, cite:

- which raw log file showed the root cause (path only, not full paste)
- which milestone failed first
- why local oracle alone was or was not sufficient evidence

### Multi-step oracle layout rule (portal-safe)

For milestone tasks, later `solve.sh` files must not depend on cross-milestone
paths such as `$TASK_ROOT/milestone_1/solution/solve1.sh`. Portal mounts
only the current milestone's `/solution` directory.

**Required pattern** (full detail: [MILESTONE_ORACLE_SOLUTION_RULES.md](MILESTONE_ORACLE_SOLUTION_RULES.md)):

- Each milestone's `solution/` contains only `solve.sh` and `solveN.sh` for that milestone
- `solve.sh` dispatches only to `"$SCRIPT_DIR/solveN.sh"`
- Each `solveN.sh` is a **standalone cumulative** fix for milestones 1 through N from the broken starter codebase
- Do **not** chain `solve3.sh` → `solve2.sh` → `solve1.sh` inside later milestones

Validate both cumulative oracle and isolated per-milestone mounts before submission.

## Validation Order

Run these from `Terminus-Edition-2` unless the user says they already ran them:

```bash
python scripts/preflight_task.py <task-name>
USE_DIRECT_HARBOR=1 bash scripts/terminus2_cli.sh oracle ./<task-name>
bash scripts/zip.sh --task <task-name> --out new-task-upload
python scripts/check_revision_completion.py --task <task-name> --allow-unchecked
```

If the Harbor static-check script is available locally, run it too:

```bash
python3 scripts/run_static_checks.py --task-dir ./<task-name> --version edition_2
```

Confirm `task.toml` category is not `debugging` or `software-engineering`
(portal blockers). If the script is not available locally, say so in the final
answer and still verify category manually.

Do not confirm completion unless the oracle command has actually run after the
latest edits and the latest oracle log shows a pass. If oracle fails, follow
Oracle Failure Escalation, fix the task, and rerun oracle; if oracle cannot be
run, mark the task blocked and explain why.

The final upload zip must be created after the latest passing oracle run. If
multiple zips exist, use the newest timestamped zip printed by `scripts/zip.sh`
and by `check_revision_completion.py`; never reuse an older clean zip just
because the checker found one.

Before zipping, do one explicit instruction-sufficiency pass: for every new or
changed test assertion, confirm the behavior is stated in the milestone
instruction or a referenced `/app/docs/...` contract. Also scan the fresh
difficulty/task-instruction summary for concerns that are not represented as a
hard failure line. Do not rely only on the difficulty label, solvable status, or
agent pass rate.

## Token Discipline

- Prefer `REVISION_BRIEF.md` over full reports.
- Prefer targeted file reads over broad recursive scans.
- Use `rg` for search.
- Do not paste long Docker or oracle logs into the final answer.
- Summarize command outcomes, not full output.
- If a command succeeds, record the command and result only.
- If a command fails, inspect only the failing section.
- **Exception:** when portal oracle failed, reading targeted files under
  `raw_feedback/agent_logs/jobs/` is required even though those logs are large.
  Read `oracle.txt`, `test-stdout.txt`, and `reward.txt` per failing milestone
  only — not entire job trees.

## Final Answer Format

Keep the final answer short and concrete:

```text
Fixed <task-name>.

Changes:
- ...

Validation:
- preflight: passed
- oracle: passed
- static: not available locally / passed
- oracle log: .terminus_logs/<task-name>/oracle_<timestamp>.log
- portal oracle debug: <raw log path consulted, or "N/A — portal oracle passed / not reported">
- difficulty report: reviewed
- instruction sufficiency: reviewed / updated
- rubric: <task-name>/rubric.txt
- zip: <path>
```

Mention any `N/A`, conflict, or skipped validation honestly.

## Pasteable Agent Prompt

```text
Follow documentation/REVISION_AGENT_BIBLE.md exactly.

Task: <task-name>
Submission: <submission-id>

Use only:
- All-New-Feedbacks/<task-name>/REVISION_BRIEF.md
- <task-name>/

Fix every actionable issue in the brief. Do not read old Auto-Eval-Logs unless
I explicitly ask or portal oracle failed. Keep edits scoped. Run preflight,
oracle, rebuild the upload zip with scripts/zip.sh, and run
check_revision_completion.py. Do not final answer until validation is complete
or a blocker is explicit.

If portal oracle failed (or difficulty says agents were not run because oracle
failed), follow Portal Oracle Failure Debugging in the bible: read raw
`raw_feedback/.../oracle.txt` and verifier logs — do not rely on
difficulty_check_latest.txt alone.

Always check the task-instruction / instruction-sufficiency summary in the
fresh reports; do not rely only on difficulty, solvable status, or oracle pass.
Also review agent pass rates, abnormal failures, unpassed/flaky tests, and
skipped runs. Report "difficulty report: reviewed" and
"instruction sufficiency: reviewed / updated" in the final answer.
```
