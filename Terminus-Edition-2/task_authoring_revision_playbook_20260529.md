# Task Authoring and Revision Playbook

Use this playbook for every new task and every revision task before packaging or resubmitting. Follow the steps in order. Do not skip the generic audits just because the reported issue names one task; most failures repeat across sibling tasks.

## 1. Start With The Reported Failure

1. Identify the exact task folder from the portal zip name.
   - Example: `go-fuel-card-authorization-settler_20260529_161919.zip` maps to `Terminus-Edition-2/go-fuel-card-authorization-settler`.

2. Read the portal failure carefully and classify it as one of these:
   - `instruction/spec mismatch`: tests expect behavior not stated in instructions.
   - `output path mismatch`: tests read one output filename, instructions name another.
   - `oracle/runtime issue`: oracle failed, solve scripts are not self-contained, wrong language entrypoint, Docker build failed.
   - `timeout/build issue`: task has missing/incorrect timeout metadata, Dockerfile issue, hardcoded platform, package install problem.
   - `test quality issue`: missing docstrings, ellipsis stubs, indistinguishable tie-breaker, untested requirement.
   - `difficulty issue`: too trivial or too hard because tests/spec do not align with expected agent pass rates.

3. Fix the named task first. Then run the matching generic scan from this playbook to catch siblings with the same pattern.

4. For every revision, inspect and update `rubric.txt` before packaging. A task is not done until rubric criteria still match the changed instructions/tests, each milestone section has valid scored `Agent... , +N/-N` lines, and no criterion references verifier-only internals.

5. For LLMaJ-driven work, treat the report as a triage input, not as a blind patch list. Fix concrete instruction/test/oracle/naming findings. Keep known local-format noise documented:
   - `anti_cheating_measures` may fail strict LLMaJ because local `steps/*/solution/` folders exist; this is expected when solutions are excluded from the runtime image.
   - `test_deps_in_image` may fail strict LLMaJ because pinned pytest packages are baked into the offline task image; current Edition 2 practice keeps pinned verifier dependencies in `environment/Dockerfile`.

## 2. Required Files To Inspect

For the target task, always inspect these files:

- `task.toml`
- `rubric.txt`
- `environment/Dockerfile`
- `environment/config/*`
- `environment/app/*`, `environment/cmd/*`, `environment/src/*`, or equivalent implementation path
- `steps/milestone_*/instruction.md`
- `steps/milestone_*/tests/test_*.py`
- `steps/milestone_*/tests/test.sh`
- `steps/milestone_*/solution/solve.sh`
- `steps/milestone_*/solution/solve*.sh`

Use the task-specific implementation path in the rubric and instruction. Do not move implementations to a language or file the verifier does not run.

## 3. Standard Verifier `test.sh` Pattern

Use this format for milestone verifier shell scripts unless a task has a documented special runner requirement.

```bash
#!/bin/bash
set -uo pipefail
mkdir -p /logs/verifier
echo 0 > /logs/verifier/reward.txt

if [ "$PWD" = "/" ]; then
    echo "Error: No working directory set."
    exit 1
fi

python3 -m pytest --ctrf /logs/verifier/ctrf.json /tests/test_m1.py -rA

if [ $? -eq 0 ]; then
    echo 1 > /logs/verifier/reward.txt
else
    echo 0 > /logs/verifier/reward.txt
fi
```

Rules:

- Keep `set -uo pipefail`; this is the current standard.
- Do not use `set -e` in verifier scripts that inspect `$?` after `pytest`, because `-e` can exit before the reward rewrite runs.
- Prewrite `/logs/verifier/reward.txt` to `0` before invoking pytest.
- Include the `$PWD = "/"` guard for clearer failures when WORKDIR is misconfigured.
- Change only the milestone test filename (`test_m1.py`, `test_m2.py`, etc.) per step.
- If a review objects to `set -euo pipefail`, remove `-e` but keep `-uo pipefail` and the reward prewrite.
- Do not install packages in `test.sh`. For offline tasks, install pinned verifier packages in `environment/Dockerfile`.

## 4. Metadata And Timeout Rules

Every task must have portal-safe top-level metadata and per-step timeouts.

Required `task.toml` values:

```toml
[agent]
timeout_sec = 1800

[verifier]
timeout_sec = 900

[environment]
allow_internet = false
build_timeout_sec = 900
cpus = 2
memory_mb = 4096
storage_mb = 10240
```

Rules:

- Keep top-level `[agent]` and `[verifier]`; do not rely only on `[steps.agent]` and `[steps.verifier]`.
- Keep per-step timeouts too.
- Use only one `build_timeout_sec`.
- Do not duplicate `[agent]`, `[verifier]`, or `[environment]` sections.
- If admin guidance changes, update this playbook and the audit doc.

Validation:

```powershell
python Terminus-Edition-2\scripts\preflight_task.py Terminus-Edition-2\<task-name>
```

## 5. Docker Rules

Check `environment/Dockerfile`.

Required:

- Include `tmux`.
- Pin base images by digest when existing task family does so.
- Do not pin Debian apt package versions.
- Do not copy `steps/`, `tests/`, or `solution/` into the image.
- Do not hardcode `FROM --platform=linux/amd64 ...` unless the platform team explicitly requires it.
- For COBOL Dockerfiles, apt continuation lines must use one backslash only:

```dockerfile
RUN apt-get update && apt-get install -y --no-install-recommends \
    bash \
    ca-certificates \
    gnucobol \
    python3 \
    python3-pip \
    tmux \
    && rm -rf /var/lib/apt/lists/*
```

Never leave malformed lines like:

```dockerfile
bash \ \
ca-certificates \ \
```

Generic checks:

```powershell
rg -n -- "--platform=linux/amd64|FROM --platform" Terminus-Edition-2
rg -n "COPY\s+(tests|solution|steps)/" Terminus-Edition-2 -g Dockerfile
```

Also refer to:

- `Terminus-Edition-2/all_tasks_common_issue_audit_20260529.txt`

## 6. Oracle Solution Rules

Portal may mount only the current milestone's `/solution` directory. Therefore every milestone solution directory must be self-contained.

Required:

- `steps/milestone_2/solution` must contain what it needs from milestone 1.
- `steps/milestone_3/solution` must contain what it needs from milestones 1 and 2.
- `steps/milestone_4/solution` must contain what it needs from milestones 1, 2, and 3.
- Do not call sibling paths such as `../milestone_1/solution/solve1.sh`, `/steps/milestone_1/...`, or `/app/steps/...`.

Generic scan:

```powershell
rg -n "\.\./milestone_|/app/steps/milestone_|/steps/milestone_|\$STEPS_DIR/milestone_|\$steps_dir/milestone_" Terminus-Edition-2 -g "solve*.sh"
```

Expected result: no matches.

Shell hygiene:

```powershell
bash -lc "find Terminus-Edition-2 -name '*.sh' -print0 | xargs -0 -n1 bash -n"
```

All shell scripts must be LF and UTF-8 without BOM.

If an oracle uses many exact string replacements and a starter cleanup changes those strings, either update every replacement to match the new source or replace the milestone oracle with a complete source rewrite that still computes outputs from runtime inputs. Dead/no-op replacements are a review warning and can hide a broken oracle.

## 7. Output Path Rules

Instructions, tests, implementation, solutions, `job.properties`, and rubric must agree on output filenames.

Common failure:

- Instruction says `/app/out/report.csv` and `/app/out/summary.txt`.
- Tests expect task-specific files such as `/app/out/concession_refund_report.csv`.

Generic checks:

```powershell
rg -n "/app/out/(report\.csv|summary\.txt)" Terminus-Edition-2 -g "instruction.md"
```

Also compare test output constants against every milestone instruction. If tests use:

```python
REPORT = APP / "out" / "some_report.csv"
SUMMARY = APP / "out" / "some_summary.txt"
```

then that exact path must appear in the same milestone's `instruction.md`, not only in milestone 1 or milestone 3.

If a later milestone says â€œkeep prior behavior,â€ still add one explicit sentence:

```text
Continue to write `/app/out/<report>` and `/app/out/<summary>` with the same schemas, status labels, blank unmatched fields, and summary keys from the earlier milestone.
```

## 8. Output Schema And Status Rules

Every milestone instruction must explicitly state:

- Report output filename.
- Report column order.
- Summary output filename.
- Summary keys.
- Status literals.
- Action/correction input order is preserved.
- Matched rows emit canonical source category/kind/type.
- Unmatched rows leave the category/kind/type field blank.
- Amount totals are positive integers.

Do not rely on the existing buggy code or `job.properties` to imply schema.

Bad:

```text
Write the documented report schema.
```

Good:

```text
Write `/app/out/fuel_reversal_report.csv` with columns `action_id,auth_id,fleet_id,batch_id,kind,amount,reason,status`, preserving correction input order. Use only `MATCHED` and `UNMATCHED`. Matched rows report the canonical source `kind`; unmatched rows leave `kind` blank.
```

## 9. Matching Gate Rules

When tests enforce a gate, the same gate must be stated in the milestone instruction.

Common gates:

- Full source identifier equality, not prefix/substring.
- All identity fields match.
- Integer amount match.
- Source status literal.
- Eligible correction reason.
- Canonical kind/category/type gate.
- Timestamp values are numeric.
- Correction/action timestamp is on or after source timestamp.
- Window is `OPEN`.
- Action timestamp is not after window close.
- Same property/location/market/region/window key.
- Each source row can be consumed once.
- Candidate selection uses latest source timestamp/date.
- Equal timestamp/date tie-breaker uses earliest source input row.

Never introduce a gate only in M3 if M1 or M2 tests already enforce it.

## 10. Alias Target Canonicality Rules

This is a high-risk repeated failure class.

If M1 allows only two canonical values and M2 adds an alias whose target is a third value, M2 must explicitly say the third value becomes canonical and match-eligible.

Bad:

```text
M2 keeps every M1 rule and adds aliases. CHARGE means EV.
```

Why bad: if M1 says only `DIESEL` or `GAS` are valid, an agent may correctly reject `EV`.

Good:

```text
Milestone 2 keeps every milestone 1 rule and adds the documented legacy kind aliases: `DSL` means `DIESEL`, `PETROL` means `GAS`, and `CHARGE` means `EV`. From milestone 2 onward, the canonical match-eligible kind values are exactly `DIESEL`, `GAS`, and `EV`; `EV` becomes valid because it is the canonical target for `CHARGE`.
```

M3 must preserve the canonical gate:

```text
Unknown normalized values such as `BAD` are never match-eligible even if source and correction both contain the same unknown kind.
```

Generic scan for `kind_aliases.csv` tasks:

```powershell
@'
from pathlib import Path
root=Path("Terminus-Edition-2")
for task in sorted(root.glob("*")):
    if not task.is_dir() or not (task/"task.toml").exists():
        continue
    m2=task/"steps/milestone_2/instruction.md"
    aliases=task/"environment/config/kind_aliases.csv"
    if not m2.exists() or not aliases.exists():
        continue
    txt=m2.read_text(encoding="utf-8", errors="ignore")
    targets=[r.split(",")[1].strip() for r in aliases.read_text(encoding="utf-8", errors="ignore").splitlines()[1:] if "," in r]
    missing=[t for t in targets if t and f"`{t}`" not in txt]
    if missing:
        print(task.name, sorted(set(missing)))
'@ | python -
```

Expected result: no missing alias targets.

For non-`kind_aliases.csv` files, adapt this same scan to the actual config name, such as:

- `method_aliases.csv`
- `category_aliases.csv`
- `rate_aliases.csv`
- `service_aliases.csv`
- `*_aliases.csv`

Prefer config filenames that match the field name under test. For example, use `access_tier_aliases.csv` for `access_tier`, not a stale template name like `kind_aliases.csv`. If a generic filename is intentionally kept, name it explicitly in the milestone instruction and docs so it is not read as a typo.

## 11. Window Rules

If a milestone introduces realtime/calendar/window config, instruction and tests must cover:

- Config filename.
- Key used to select the window.
- Only `OPEN` windows are eligible.
- Closed, missing, malformed, and unlisted windows are ineligible.
- Window timestamps must be numeric.
- Source timestamp is inside the window when required.
- Correction/action timestamp is on or after source timestamp.
- Correction/action timestamp is not after window close.
- Existing identity, reason, status, canonical kind, and consumption gates still apply.
- Candidate selection and tie-breaker still apply.

If instruction says â€œnot after window close,â€ add a test where every other gate passes but action timestamp is after close.

If instruction says the source timestamp must be inside a window, add a test where every other gate passes but source timestamp is before `open_ts` or after `close_ts`.

If a milestone adds date/window columns but earlier schemas remain supported, state the legacy rule explicitly: when both files omit the new columns entirely, preserve the prior milestone behavior; when the columns exist but a row value is blank/missing, that row is ineligible.

## 12. Candidate Selection Tests

When instruction says:

```text
Choose latest source timestamp; if tied, choose earliest source input row.
```

Tests must make the selected source observable.

Bad:

- Two duplicate candidates have identical emitted values.
- Test only checks `MATCHED`, so either candidate passes.

Good:

- Latest candidate has a different canonical kind/category/type or otherwise observable output.
- Equal timestamp candidates have distinguishable output, so earliest row tie-breaker is testable.

## 13. COBOL-Specific Rules

COBOL tasks need extra clarity.

Instructions must say:

- The verifier compiles with free-format COBOL if tests use `cobc -x -free`.
- Rewritten comments/code must be valid in free-format COBOL.
- Fixed-width fields must be trimmed when writing CSV output.
- Blank unmatched CSV fields must be truly empty, not spaces.

For unmatched report rows, say:

```text
Unmatched rows emit an empty string for the `<field>` column (two consecutive commas in the CSV, not whitespace-padded).
```

Avoid `DELIMITED BY SIZE` for output fields unless it is intentionally padded and tests expect padding. Most tests expect trimmed strings.

## 14. Test Quality Rules

Every test function should have:

- A descriptive function name.
- A docstring describing the behavior checked.
- Fixture comments for dense multi-gate rows.

Avoid:

- `def test_x(...): ...`
- Ellipsis/pass stubs in later milestones.
- Class-level docstring only, with method docstrings missing.
- Identical duplicate candidate rows when testing tie-breakers.
- A test name that says one category but the body uses another category.
- A docstring that describes a broad rule but only asserts an indirect final status. Rename or split the test so the name matches the exact assertion.

Generic scan:

```powershell
rg -n "^\s*\.\.\.\s*$|def test_.*:\s*\.\.\." Terminus-Edition-2 -g "test_*.py"
```

Expected result: no matches.

## 15. Anti-Cheating And Runtime Freshness

Tests should overwrite runtime inputs before each scenario.

Required:

- Tests write fresh `/app/data/*` and `/app/config/*` fixtures.
- Dockerfile does not copy tests or solutions into image.
- Sample data is not enough to pass.
- Starting implementation is buggy enough to require a real fix.
- Solutions compute output from input files and do not echo precomputed final answers.

## 16. Difficulty Control

If task is too trivial:

- Add one more milestone or test dimension.
- Add a config gate, such as methods, calendar, or priority.
- Add a source-side alias or runtime config reload.
- Add a malformed config row case.
- Add a tie-breaker with observable output.
- Add regression tests preserving all earlier gates.

If task is too hard or no agent passes:

- First check for spec/test contradiction.
- Check filenames.
- Check language entrypoint.
- Check oracle self-containedness.
- Check canonical alias target wording.
- Check if tests enforce behavior not described until a later milestone.
- Do not simply remove tests unless the behavior is not part of the intended task.

## 17. Required Verification Before Finalizing

For a single revised task:

```powershell
python Terminus-Edition-2\scripts\preflight_task.py Terminus-Edition-2\<task-name>
```

Run Docker oracle for every changed milestone:

```powershell
docker build -q -t tb-check-<task-name> Terminus-Edition-2/<task-name>/environment
docker run --rm -v "<abs-solution>:/solution" -v "<abs-tests>:/tests" tb-check-<task-name> bash -lc "bash /solution/solve.sh && bash /tests/test.sh && cat /logs/verifier/reward.txt"
```

Expected reward output: `1`.

For generic/batch edits:

1. Run structural scans from this playbook.
2. Run `preflight_task.py` on every touched task.
3. Run Docker oracle on:
   - The originally reported task.
   - At least one Go task if Go files were touched.
   - At least one Ruby task if Ruby files were touched.
   - At least one COBOL task if COBOL/Docker files were touched.
   - Any task whose tests, solution, or Dockerfile changed.

For new-task batches hardened from LLMaJ reports:

1. Put strict reports under `new-tasks-v*/llmaj-reports/`.
2. Patch one task at a time from its report.
3. Run preflight and cumulative oracle for that task.
4. Package into the requested batch folder, for example:

```powershell
New-Item -ItemType Directory -Force Terminus-Edition-2\new-tasks-v5\batch-1
bash scripts/zip_task.sh --task <task> --out new-tasks-v5/batch-1 --zip-name <task>.zip --include-rubric
```

5. Verify each zip contains `task.toml` and `rubric.txt` at the archive root.

## 18. What To Tell The User

Final response should include:

- Root cause.
- Files changed.
- Whether the fix was task-specific, generic, or both.
- Verification run and pass counts.
- Any residual risk.
- Whether the existing uploaded zip is stale and must be rebuilt.

Example:

```text
Fixed `go-fuel-card-authorization-settler`.

Root cause: M2 introduced `CHARGE -> EV` but did not explicitly make `EV` canonical, so agents preserved the M1 DIESEL/GAS-only gate.

Changed M2/M3 instructions and rubric. Also scanned sibling alias tasks and patched the same canonical-target wording where needed.

Verification: Docker oracle passed M1 1/1, M2 2/2, M3 3/3. Preflight passed.

The old uploaded zip is stale; rebuild from the updated folder.
```

## 19. Keep The Audit Doc Updated

After any generic fix, update:

- `Terminus-Edition-2/all_tasks_common_issue_audit_20260529.txt`

Add:

- What pattern was found.
- Which tasks were patched.
- Which command verified the pattern is now clean.
- Which Docker oracle checks passed.

