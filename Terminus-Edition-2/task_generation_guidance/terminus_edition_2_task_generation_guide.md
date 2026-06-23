# Terminus Edition 2 Task Generation Guide

Use this document as a task-generation and review checklist before creating or submitting Harbor / Terminus Edition 2 tasks. It is tuned for the repeated revision issues we saw across Go, Bash, Ruby, and COBOL milestone tasks.

## Goal

Generate tasks that are:

- Structurally valid for milestone tasks.
- Offline and reproducible.
- Hard enough to avoid trivial agent success.
- Clear enough that failures are implementation mistakes, not prompt ambiguity.
- Covered by behavioral tests for every stated requirement.
- Packaged correctly with oracle and nop validation passing locally.

## Required Milestone Task Structure

A milestone task zip must have these items at the zip root:

```text
task.toml
environment/
steps/
```

Do not nest the task under an extra folder inside the zip.

For each milestone:

```text
steps/milestone_1/instruction.md
steps/milestone_1/tests/test.sh
steps/milestone_1/tests/test_m1.py
steps/milestone_1/solution/solve.sh
steps/milestone_1/solution/solve1.sh
```

Repeat for `milestone_2`, `milestone_3`, etc.

Do not include root-level `instruction.md`, `tests/`, or `solution/` in milestone tasks.

## task.toml Standards

Use Edition 2 metadata and per-step timeouts.

```toml
version = "2.0"

[metadata]
author_name = "anonymous"
author_email = "anonymous@example.com"
difficulty = "hard"
category = "debugging"
subcategories = []
number_of_milestones = 3
codebase_size = "small"
languages = ["go", "bash"]
tags = ["go", "csv", "reconciliation", "cli", "debugging"]
expert_time_estimate_min = 90
junior_time_estimate_min = 180

[environment]
allow_internet = false
build_timeout_sec = 900.0
cpus = 2
memory_mb = 4096
storage_mb = 10240
workdir = "/app"

[[steps]]
name = "milestone_1"
[steps.agent]
timeout_sec = 1800.0
[steps.verifier]
timeout_sec = 900.0

[[steps]]
name = "milestone_2"
[steps.agent]
timeout_sec = 1800.0
[steps.verifier]
timeout_sec = 900.0

[[steps]]
name = "milestone_3"
[steps.agent]
timeout_sec = 1800.0
[steps.verifier]
timeout_sec = 900.0
```

Do not add root-level `[agent]` or `[verifier]` blocks in milestone tasks.

Do not add `gpus = 0` unless the official task schema requires it for that task type.

Use a valid email format, such as `anonymous@example.com`.

## Dockerfile Standards

The Dockerfile must be inside `environment/Dockerfile`.

Install required runtime tools:

- `tmux`
- `asciinema`
- `ca-certificates`
- language/toolchain dependencies

For Python-based verifiers using `--ctrf`, install pinned verifier packages at image build time:

```dockerfile
RUN pip3 install --break-system-packages pytest==8.4.1 pytest-json-ctrf==0.3.5
```

Do not rely only on Debian `python3-pytest` if `test.sh` uses `--ctrf`; Debian pytest will not understand `--ctrf` without `pytest-json-ctrf`.

For Debian apt packages, do not pin apt package versions unless specifically required. Pin pip/gem/npm/cargo-style application dependencies.

A typical Debian Dockerfile:

```dockerfile
FROM debian:bookworm-slim

WORKDIR /app

RUN apt-get update && apt-get install -y --no-install-recommends \
    bash \
    asciinema \
    ca-certificates \
    curl \
    python3 \
    python3-pip \
    tmux \
    && rm -rf /var/lib/apt/lists/*

RUN pip3 install --break-system-packages pytest==8.4.1 pytest-json-ctrf==0.3.5

COPY scripts/ /app/scripts/
COPY data/ /app/data/
COPY config/ /app/config/
COPY docs/ /app/docs/
COPY lib/ /app/lib/

RUN mkdir -p /app/out && chmod +x /app/scripts/*.sh
```

Do not copy `steps/`, `tests/`, or `solution/` into the image.

## test.sh Standard

Each milestone test runner must always write `/logs/verifier/reward.txt` and exit with the actual pytest status.

Recommended pattern:

```bash
#!/bin/bash
set -uo pipefail
mkdir -p /logs/verifier
echo 0 > /logs/verifier/reward.txt
pytest_status=1
trap 'exit $pytest_status' EXIT

if [ "$PWD" = "/" ]; then
    echo "Error: No working directory set. Please set a WORKDIR in your Dockerfile before running this script."
    exit 1
fi

python3 -m pytest --ctrf /logs/verifier/ctrf.json /tests/test_m1.py -rA
pytest_status=$?

if [ $pytest_status -eq 0 ]; then
    echo 1 > /logs/verifier/reward.txt
else
    echo 0 > /logs/verifier/reward.txt
fi
```

Common mistake: writing reward.txt but then exiting with the final `echo` status. That masks failed tests as process exit 0.

## Oracle Solution Standards

Each milestone has:

- `solution/solve.sh`: wrapper
- `solution/solveN.sh`: real solution for milestone N

Wrapper:

```bash
#!/usr/bin/env bash
set -euo pipefail
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
bash "$SCRIPT_DIR/solve1.sh"
```

Use `bash "$SCRIPT_DIR/solveN.sh"` instead of `"$SCRIPT_DIR/solveN.sh"` to avoid permission failures when executable bits are lost.

Oracle scripts must be deterministic and compute outputs by fixing/running the program. Do not echo hardcoded final CSV/JSON answers.

For milestone tasks, keep oracle scripts milestone-scoped:

- M1 solution should solve only M1 behavior.
- M2 solution should build on M1 and add only M2 behavior.
- M3 solution should add only M3 behavior.

Avoid making every `solveN.sh` a full final-state implementation.

## Prompt / Instruction Rules

Instructions should be concise but explicit.

Always include absolute paths for:

- Main source file to fix.
- Input files.
- Output files.
- Config/calendar files.

Spell out literal status values. Avoid vague phrases such as “posted status” unless you also name the CSV value.

Examples:

- “posted visit status `CLOSED`”
- “posted class status `BOOKED`”
- “eligible order status `SHIPPED`”
- “settled sale status `S`”
- “sample status `FINAL`”

Explicitly state:

- Full identifier matching, not prefix matching.
- Allowed values and aliases.
- Case-insensitive comparison and trimming rules.
- Output schemas and exact status labels.
- Blank field behavior for unmatched/exception rows.
- Positive-cent summary totals.
- Row-position consumption semantics.
- Selection rules when multiple rows match.

Do not mention verifier/test internals in instructions.

## Test Quality Rules

Tests must be behavioral, not static-only. They should run the program and verify outputs.

Every requirement in instructions must have a test. Every test expectation must be described in instructions.

Each test should have a docstring explaining the behavior it verifies.

Use synthetic input data written inside tests. Do not rely on preloaded environment data.

For each milestone, include regression checks for prior behavior when there is risk of regression.

Common M3 regression checks:

- Aliases from M2 still work.
- Row consumption still works.
- Full ID matching still works.
- Blank unmatched field still works.
- Prior status labels and schema still work.

## Make Tie-Breaking Observable

Do not test a tie-break rule with two identical candidate rows if the output cannot reveal which row was consumed.

Bad pattern:

- Two identical source rows.
- Three identical actions.
- Expected statuses: `MATCHED, MATCHED, UNMATCHED`.

Any consumption order can pass that.

Better pattern:

- First action can match two candidate rows.
- Correct tie/latest rule consumes one specific row.
- Second action is designed to match only the row that should have been left over.
- Assert the second action’s status changes if the wrong row was consumed.

If a rule cannot be made observable through outputs, remove or reframe the requirement.

## Calendar / Date Logic Coverage

If instructions say dates must be open in a calendar, tests must isolate each condition:

- Open date matches.
- Closed date rejects.
- Missing/unlisted date rejects.
- Blank date rejects.
- Date order rule rejects when violated.
- Exactly-on-boundary rule passes if specified.
- One-over-boundary rule rejects.
- Both sides of date rules are tested if both source and action dates matter.

For “latest date wins”, make it observable with a later action/credit/refund that depends on the correct row being left unconsumed.

## Alias Coverage

If instructions mention aliases, test every alias directly.

Example: If instructions say `PU -> PICKUP`, `DEL -> DELIVERY`, and `OS -> ONSITE`, tests must include a row using `PU`, not only canonical `pickup`.

Matched report rows should usually emit canonical values. If that is expected, state it clearly in instructions and assert it in tests.

Unknown aliases should produce unmatched/exception rows without schema changes.

## COBOL-Specific Anti-Bypass Checks

If the task says to fix COBOL, tests should make bypassing COBOL harder.

Recommended checks:

- `compile.sh` contains `cobc`.
- `compile.sh` references `.cbl` source.
- At least one `.cbl` file exists under `/app/src`.
- Produced batch binary starts with ELF bytes.

Example helper:

```python
def assert_cobol_binary():
    """Verify the batch still comes from the COBOL compile path."""
    compile_script = (APP / "scripts" / "compile.sh").read_text().lower()
    assert "cobc" in compile_script
    assert ".cbl" in compile_script
    assert any((APP / "src").glob("*.cbl"))
    assert (APP / "build" / "batch").read_bytes().startswith(b"\x7fELF")
```

## Rubric Format

Every rubric criterion line must start with `Agent` and end with a valid signed score.

Allowed scores:

- Positive: `+1`, `+2`, `+3`, `+5`
- Negative: `-1`, `-2`, `-3`, `-5`

Do not use `+4`, `+6`, `+7`, etc.

Avoid blank lines if the portal parser is strict.

Good:

```text
Agent compares full invoice IDs and avoids prefix matching, +3
Agent preserves output schema and status labels, +2
Agent hardcodes output files instead of fixing the program, -5
```

Bad:

```text
The program compares IDs correctly, +3
Agent. compares IDs correctly, +3
Agent compares IDs correctly, 3
Agent compares IDs correctly, +4
```

For milestone tasks, ensure each milestone has 10-40 positive points.

Include at least three negative criteria overall, preferably one or more per milestone.

## Common Revision Causes

1. Stale zip uploaded instead of the latest fixed zip.
2. Zip contains an extra top-level folder.
3. Missing executable bits on shell scripts.
4. `solve.sh` directly executes non-executable `solveN.sh`.
5. `test.sh` masks pytest failure exit codes.
6. `pytest-json-ctrf` missing while `--ctrf` is used.
7. Missing `tmux` or `asciinema` in Dockerfile.
8. Root `[agent]` or `[verifier]` blocks in milestone task.
9. Invalid `author_email`.
10. Unnecessary or invalid `gpus = 0`.
11. Prompt says one behavior, tests expect another.
12. Instructions mention alias not covered by tests.
13. Tests assert behavior not stated in instructions.
14. M3 tests do not re-check prior milestone behavior.
15. Tie-breaking requirement is unobservable.
16. Docs/config contradict the instructions.
17. COBOL task can be solved by replacing compile script with Python/Bash.
18. Top-level README or extra scaffolding triggers reviewer cleanup requests.
19. Debian apt package pinning confusion.
20. Build completion timeout is portal infrastructure noise unless task also has real static/oracle/verifier errors.

## Pre-Upload Checklist

Before uploading, always validate the exact zip you will submit.

1. Repack from inside the task directory so zip root is correct.
2. Extract the zip to a temporary folder.
3. Verify root contains only expected task files, especially `task.toml`, `environment/`, `steps/`.
4. Check shell executable bits inside zip.
5. Run actual oracle:

```bash
stb harbor run -a oracle --path ./extracted-task -q --yes
```

6. Run nop:

```bash
stb harbor run -a nop --path ./extracted-task -q --yes
```

Expected:

- Oracle mean: `1.000`
- Nop mean: `0.000`

7. Check rubrics with a simple pattern:

```text
^Agent .+, [+-](1|2|3|5)$
```

8. Upload only that exact validated zip.

## Task Generation Prompt Template

Use this prompt when asking ChatGPT to generate a new task:

```text
Create a Terminus Edition 2 milestone debugging task using the attached guide.

Requirements:
- Use milestone structure with 3 milestones.
- Put task files at zip root: task.toml, environment/, steps/.
- Do not include root instruction.md, tests/, or solution/.
- Use allow_internet=false and per-step timeouts of 1800 agent / 900 verifier.
- Include tmux and asciinema in Dockerfile.
- Use pytest==8.4.1 and pytest-json-ctrf==0.3.5 if Python verifier uses --ctrf.
- Each test.sh must write /logs/verifier/reward.txt and exit with pytest status.
- Each milestone must have instruction.md, tests/test.sh, tests/test_mN.py, solution/solve.sh, solution/solveN.sh.
- Oracle scripts must be milestone-scoped and deterministic.
- Tests must cover every instruction requirement and avoid unobservable tie-breaks.
- Include strict rubrics where every line starts with Agent and ends with , +1/+2/+3/+5 or , -1/-2/-3/-5.
- Generate a hard debugging task, not a trivial one.

After generating, self-review against the attached guide and list any possible reviewer concerns.
```
