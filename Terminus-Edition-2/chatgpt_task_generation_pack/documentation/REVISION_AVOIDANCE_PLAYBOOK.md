# Revision Avoidance Playbook

Use this context when creating or revising Terminus Edition 2 tasks with Cursor, Codex, or multiple parallel agents. The goal is not just to make the oracle pass. The task should survive static checks, quality review, test-quality review, difficulty review, agent simulation, and manual reviewer inspection.

## Prime Directive

Instructions, tests, and oracle solutions must stay in sync.

Every behavior in tests must be stated in the milestone instruction. Every behavior in the instruction must have at least one focused test. Every tested behavior must be implemented by the milestone solution script. If any one of those three moves, update the other two before zipping.

## Standard Work Loop

For each task, work in this order:

1. Read `task.toml`, all milestone `instruction.md` files, tests, solution scripts, and the main source file.
2. Identify revision risks: setup compliance, missing behavior coverage, ambiguous wording, weak difficulty, oracle/test drift, and brittle verifier scripts.
3. Patch instructions, tests, and solution together.
4. Run preflight.
5. Build the Docker image.
6. Run a cumulative oracle-style solve: milestone 1 solution, milestone 1 tests, then milestone 2 solution, milestone 2 tests, etc.
7. Run a NOP baseline check against milestone 1. It must return reward `0`.
8. Zip only after both oracle and NOP behave correctly.

Useful commands from the repository root:

```powershell
.\scripts\terminus2_cli.ps1 preflight .\TASK_NAME
docker build -t local/TASK_NAME:check .\TASK_NAME\environment
```

Oracle-style cumulative run:

```powershell
$task=(Resolve-Path .\TASK_NAME).Path
$cmd='set -e; for m in 1 2 3; do echo === milestone_$m ===; bash /steps/milestone_${m}/solution/solve.sh; rm -rf /tests; mkdir -p /tests; cp -r /steps/milestone_${m}/tests/. /tests/; bash /tests/test.sh; reward=$(cat /logs/verifier/reward.txt 2>/dev/null || true); echo reward=$reward; if [ "$reward" != "1" ]; then exit 1; fi; done'
docker run --rm -v "${task}\steps:/steps:ro" local/TASK_NAME:check bash -lc $cmd
```

NOP baseline:

```powershell
$task=(Resolve-Path .\TASK_NAME).Path
$cmd='set -e; rm -rf /tests; mkdir -p /tests; cp -r /steps/milestone_1/tests/. /tests/; bash /tests/test.sh; reward=$(cat /logs/verifier/reward.txt 2>/dev/null || true); echo reward=$reward; if [ "$reward" = "1" ]; then exit 1; fi'
docker run --rm -v "${task}\steps:/steps:ro" local/TASK_NAME:check bash -lc $cmd
```

Zip:

```powershell
.\scripts\terminus2_cli.ps1 zip .\TASK_NAME
```

## Setup Compliance

`task.toml` must include:

```toml
[environment]
allow_internet = false
workdir = "/app"
```

Base images must be pinned by digest, for example:

```dockerfile
FROM golang:1.22.12-bookworm@sha256:...
```

Agent runtime images should include basic interactive tooling. In practice, missing `tmux` can cause all agent trials to fail before the verifier runs:

```text
RuntimeError: Failed to start tmux session. Error: None
verifier_did_not_run
```

For Go tasks based on the official Go image, install at least:

```dockerfile
RUN apt-get update \
    && apt-get install -y --no-install-recommends python3 tmux \
    && rm -rf /var/lib/apt/lists/*
```

For COBOL tasks, keep `gnucobol`, `make`, `python3`, and `tmux` in the image.

Do not bake test-only dependencies into the image:

```text
Do not install pytest or pytest-json-ctrf in Dockerfile.
Do not run curl, uv, uvx, apt, or pip install in test.sh.
```

Prefer an offline `mini_pytest.py` runner in each `steps/milestone_N/tests/` directory. Keep `pytest -rA` text in a comment if the static checker expects it:

```bash
python3 /tests/mini_pytest.py /tests/test_m1.py -rA  # pytest -rA compatibility
```

## Instruction Quality Rules

A reviewer should not need to infer hidden behavior from tests.

Each milestone instruction should explicitly state:

- exact input files and output files
- exact CSV or fixed-width input schema when relevant
- exact output schema and status values
- all matching criteria
- all allowed reason/channel/method values
- alias mappings and whether aliases occur in source records or transaction records
- canonical value emitted in matched report rows
- blank field behavior for unmatched rows
- deduplication or consumed-record behavior
- tie-breaking rules
- positive or signed amount semantics
- date/calendar behavior
- backward compatibility behavior for old rows or missing columns

When adding milestone 2, do not repeat the whole milestone 1 prompt unless needed. Say that milestone 1 behavior remains intact, then focus on the new work. But do restate any output or status contract if agents were previously misinterpreting it.

Avoid ambiguous phrases like:

```text
older rows without those columns should still be readable
```

Use explicit wording:

```text
Older rows without those columns must still be readable without crashing. They are readable only for reporting: rows missing the new date fields are not eligible to match and must produce UNMATCHED rows rather than falling back to earlier milestone matching.
```

For claim-side aliases, say exactly where aliases appear:

```text
The alias values appear in claims.dat claim records. Adjustment records do not contain a reason field.
```

If a valid canonical value from milestone 1 remains valid in milestone 2, list it again:

```text
Canonical reasons remain MED, NEC, COB, and AUT. Aliases map BIL -> COB, AUN -> AUT, and CLN -> NEC.
```

## Test Quality Rules

Tests should be deterministic, scenario-specific, and resistant to shortcuts.

Required patterns:

- Each test overwrites `/app/data/...` with fresh custom inputs.
- Tests delete stale outputs before running.
- Tests compile/run the real program.
- Tests assert exact output rows and summary totals.
- Tests check report header/order and input row order.
- Tests check unmatched rows leave reason/channel/method blank.
- Tests check amounts are positive integers in summaries.
- Tests check full identifiers, not prefixes.
- Tests check at-most-once consumption of matched records.
- Tests check whitespace trimming and case normalization.
- Tests check aliases emit canonical values.

For date-based milestone 3 tasks, include tests for:

- open date succeeds
- closed date fails
- absent calendar date fails
- blank date value fails
- old-format row without the date column is readable but unmatched
- equality boundary is allowed when spec says "not later than"
- latest eligible date selection is genuinely tested with two otherwise identical candidates
- same-date tie uses input row order
- consumed-record behavior still works with date logic

Bad M3 test pattern:

```text
Two candidates differ in reason/channel, so only one is actually eligible.
```

That does not test latest-date selection. Use two candidates that differ only in the date field and are both otherwise eligible.

## Oracle Solution Rules

Oracle scripts should patch source code or otherwise perform realistic repairs. They should not echo precomputed outputs.

After changing tests, update the corresponding `solve*.sh` immediately. The cumulative oracle run must pass:

```text
M1 solution -> M1 tests
M2 solution -> M2 tests
M3 solution -> M3 tests
```

Milestone solutions should be incremental. Milestone 2 should assume milestone 1 has been fixed. Milestone 3 should assume milestones 1 and 2 have been fixed.

## Difficulty Rules

Avoid tasks that are solved by one or two obvious substitutions.

Medium/hard debugging tasks usually need several interacting fixes:

- full identifier matching instead of prefix matching
- allowed value omission
- sign bug in summary total
- trimming and case normalization
- duplicate consumed-record tracking
- alias normalization with canonical output
- date/calendar gating
- latest eligible date selection
- tie-breaking by input order
- missing/old-format row handling

Difficulty should come from coherent domain logic, not hidden requirements or brittle environment setup.

### Best-practice hardening loop for trivial/instruction-sufficiency revisions

When a reviewer reports `trivial` or instruction sufficiency issues, use this explicit loop before re-zipping:

1. **Simulate a real agent pass** against the current instruction only (no tests open). Note which behaviors are under-specified or easy to shortcut.
2. **Add one milestone with orthogonal logic**, not just extra assertions. Preferred pattern: runtime config gate (`config/methods.csv`, `config/channels.csv`, etc.) that must compose with prior matching + date rules.
3. **State backward compatibility explicitly** in the new instruction:
   - prior milestone behavior remains unchanged
   - dated and undated mode behavior is explicit
   - missing/malformed config semantics are explicit
4. **Add focused tests for the new milestone**:
   - enabled/disabled config paths
   - missing config rows
   - malformed/non-boolean config rows
   - interaction with prior gates (date/status/identity) so config alone cannot pass
5. **Update oracle solution for the milestone** to implement realistic code changes (no hardcoded output shortcuts).
6. **Re-run preflight + oracle** and only then rebuild zip.

This loop consistently reduces “trivial” passes by forcing multi-dimensional reasoning (identity + normalization + temporal gating + runtime configuration).

## Common Revision Causes And Fixes

`test_deps_in_image` fails:

- Remove pytest and pytest-json-ctrf from Dockerfile.
- Use offline test runner or verifier-provided tools.

`pytest is missing -rA flag` fails:

- Include `-rA` in the test command or in the compatibility command/comment used by the static checker.

`verifier_did_not_run` with tmux startup failure:

- Ensure Dockerfile installs `tmux`.
- This is often infra, but missing tmux in the task image makes it worse.
- Add a smoke check before difficulty runs:
  - `tmux -V`
  - `tmux new-session -d -s smoke && tmux kill-session -t smoke`
- If this fails, treat the run as infrastructure-invalid and re-run after image fix; do not tune task difficulty from that report.

`task.toml codebase_size mismatch` static error:

- Static checks count files under `environment/` while excluding Dockerfile and docker-compose files.
- `codebase_size = "small"` requires at least 20 counted files. An environment with 19 counted files fails even though `small` is otherwise a valid value.
- New submissions should use `small` or `large`, not `minimal`; if a task has only 19 counted files, add a realistic support file under `environment/docs/`, `environment/samples/`, or `environment/scripts/` instead of switching back to `minimal`.
- Re-run the count before packaging:
  `Get-ChildItem environment -Recurse -File -Force | Where-Object { $_.Name -notin @("Dockerfile","docker-compose.yml","docker-compose.yaml") } | Measure-Object`

Challenge 1 timeout-block revisions (mandatory on every task):

- Every `task.toml` must include top-level `[agent]`, `[verifier]`, and `[environment]` blocks with the values below, plus per-milestone `[steps.agent]` / `[steps.verifier]` when `[[steps]]` exist.
- Bulk fix: `python3 scripts/audit_fix_task_toml_timeouts.py`
- Full-repo scan: `python3 scripts/audit_all_tasks_common_issues.py` (`--fix` for CRLF/placeholder/toml auto-fixes; `--preflight` for structural checks). Report: `all_tasks_common_issue_audit_20260529.txt`
- Current admin guidance says timeout issues should be handled with top-level timeout blocks in `task.toml`:
  ```toml
  [agent]
  timeout_sec = 1800

  [verifier]
  timeout_sec = 900
  ```
- Keep the per-milestone blocks as well unless the portal/template explicitly rejects them:
  ```toml
  [steps.agent]
  timeout_sec = 1800.0

  [steps.verifier]
  timeout_sec = 900.0
  ```
- If a reviewer asks to remove top-level `[agent]`/`[verifier]` only because per-step metadata exists, treat that as a Challenge 1/platform-guidance conflict. Do not remove the top-level blocks by default; they help avoid 7200s completion-marker timeout failures.
- Other non-timeout revision items are still actionable: add missing test docstrings, strengthen weak verifier cases, align instruction/test/oracle behavior, and clean Docker/test harness issues.

Ruby tasks (`ruby-*`):

- Follow [RUBY_TASK_TEMPLATE.md](RUBY_TASK_TEMPLATE.md): unified Dockerfile, `.dockerignore`, canonical `test.sh`, `run_batch.sh`, and self-contained milestone `solution/` scripts (no `../../milestone_N/solution/` paths).
- Normalize before packaging: `python3 scripts/normalize_ruby_tasks.py`.
- Use either `environment/lib/reconcile.rb` or `environment/app/reconcile.rb`, never both.

Pinned-image and build-context static errors:

- Digest-pin Docker base images: `FROM <image>@sha256:<digest>`.
- Always include `environment/.dockerignore` with standard cache/source exclusions.
- Re-zip with task files at zip root (`task.toml`, `environment/`, `steps/`), never nested under an extra top folder.

Behavior described but not tested:

- Add a focused test or remove the instruction.

Behavior tested but not described:

- Add explicit instruction wording.

Agent misread backward compatibility:

- Say old rows are readable but not eligible to match.

Agent invented a transaction-side reason field:

- Say the transaction/adjustment record has no reason field, and aliases are on the claim/source record only.

Agent dropped an existing valid canonical value:

- Restate the full canonical set in later milestones.

COBOL blank/zero formatting failures:

- Test zero totals explicitly.
- State that zero values must be emitted as numeric `0`, not blanks or spaces.
- Ensure trimming routines convert all-zero numeric display fields to `0`.

## Copy-Paste Context For Parallel Agents

Use this prompt for Cursor or another agent:

```text
You are revising a Terminus Edition 2 task to avoid CI/reviewer revisions. Keep instructions, tests, and oracle solutions synchronized. Inspect task.toml, environment/Dockerfile, all milestone instructions, tests, solution scripts, and the source code before editing.

Fix setup compliance: allow_internet=false, digest-pinned base image, tmux available in the agent image, no pytest/test-only deps baked into Dockerfile, no live curl/apt/pip/uv install in test.sh. Prefer offline mini_pytest.py with a pytest -rA compatibility comment.

Improve quality and difficulty only through explicit, tested domain logic. Any behavior tested must be described in instruction.md. Any behavior described must be tested. Any changed behavior must be implemented by the matching solution script.

Always update rubrics when the task changes: keep `<task>/rubric.txt`, `ALL_RUBRICS_20260526/parser_safe/`, `ALL_RUBRICS_20260526/milestone_blocks/`, `ALL_RUBRICS_STRICT_20260526/copy_paste/`, and `ALL_RUBRICS_STRICT_20260526/milestone_blocks/` in sync (see SUBMISSION_CHECKLIST.md Rubric section). Use task-specific paths and domain terms (not generic "record" wording). Milestone blocks must include negative criteria per milestone.

For date milestones, old rows without new date columns must be readable but not eligible to match. Test blank dates, absent calendar dates, closed dates, equality boundaries, latest eligible date selection, same-date tie-breaking, and consumed-record behavior.

After edits, run preflight, docker build, cumulative oracle M1->M2->M3, NOP baseline, then zip. Do not zip unless oracle reward is 1 for every milestone and NOP reward is 0.

Replace noncanonical trap-based test.sh files with the standard reward-writing pytest script from documentation/GPT_AGENT_PLAYBOOK.md section 5. Normalize every .sh file in the task to LF line endings (Windows CRLF causes `/usr/bin/env: 'bash\r': No such file or directory` in portal oracle runs).
```

## Portal Verifier Traps Beyond Dockerfile

A task zip can pass the usual portal blockers (digest-pinned image, `.dockerignore`, `tmux`, correct zip root) and still fail oracle or quality checks because of verifier script issues.

### Noncanonical `test.sh` with `trap`

Avoid this pattern:

```bash
pytest_status=1
trap 'exit $pytest_status' EXIT
python3 -m pytest ...
pytest_status=$?
```

It can confuse portal quality/verifier behavior and mask real failures. Use the canonical template instead:

```bash
#!/bin/bash
set -uo pipefail
mkdir -p /logs/verifier
echo 0 > /logs/verifier/reward.txt

python3 -m pytest --ctrf /logs/verifier/ctrf.json /tests/test_mN.py -rA

if [ $? -eq 0 ]; then
    echo 1 > /logs/verifier/reward.txt
else
    echo 0 > /logs/verifier/reward.txt
fi
```

See `documentation/GPT_AGENT_PLAYBOOK.md` section 5 for the full notes (`set -uo` without `-e` so reward is always written).

### Windows CRLF in shell scripts

If any `.sh` file has CRLF endings, Linux containers may fail with:

```text
/usr/bin/env: 'bash\r': No such file or directory
```

Before zipping:

- Replace every milestone `steps/milestone_*/tests/test.sh` with the canonical shape above.
- Normalize **all** task `.sh` files (verifier `test.sh`, `solution/solve*.sh`, `environment/scripts/*.sh`) to LF.

Short Cursor fix prompt:

```text
Replace noncanonical trap-based test.sh files with the standard reward-writing pytest script, normalize all .sh files to LF endings, rerun oracle, then rebuild the zip.
```

## Final Submission Checklist

Before upload, confirm:

- preflight passed
- Docker build passed
- every milestone `test.sh` uses the canonical reward-writing pytest template (no `trap 'exit $pytest_status' EXIT`)
- all task `.sh` files use LF line endings (no CRLF)
- oracle-style cumulative run passed every milestone with reward `1`
- NOP baseline returned reward `0`
- task zip has files at root, not nested under an extra folder
- rubrics cover every milestone and include negative criteria; all five local rubric paths are synced with the task
- comments to reviewer mention any intentional design choices
- generated rubric checkbox is selected if significant changes were made
