# Human Task Authoring Playbook

This is the practical workflow I should follow when I want to create or revise a Terminus Edition 2 task mostly on my own. The goal is not to memorize every rule. The goal is to build a task like an engineer: clear problem, realistic broken code, strong tests, deterministic oracle, clean packaging, and no hidden unfairness.

## 1. What A Good Task Feels Like

A good task is something a careful human engineer can solve confidently, but a frontier coding agent may miss because it requires investigation, state tracking, or domain judgment.

Good difficulty usually comes from:

- A real debugging story, not a puzzle for its own sake.
- Multiple interacting bugs.
- A codebase with enough files to require inspection.
- One or two subtle rules that are clearly stated in the prompt.
- Tests that check behavior, not source-code patterns.

Avoid making difficulty come from:

- Ambiguous requirements.
- Hidden output formatting.
- Brittle exact text checks not described in the prompt.
- Randomness, timing, or internet dependencies.
- Too many tiny instructions that only test obedience.

## 2. Start With The Task Idea

Before touching files, write this down in plain English:

```text
Program: What already exists?
Symptom: What is wrong?
Expected behavior: What should be true after the fix?
Why it is hard: What will an agent likely miss?
How to verify: What output or behavior proves it?
```

For the final three tasks, the hard parts were:

- COBOL ACH: full trace match, allowed SEC/reason, positive totals, one settlement consumed once.
- COBOL claims: full claim id match, COB reason, positive totals, one claim consumed once.
- Go invoices: full invoice id match, CARD allowed, positive totals, invoice consumed once, trim/case normalization.

That pattern is strong: basic bug fixes plus one stateful rule.

## 3. Build The Folder Correctly

For a normal non-milestone task:

```text
task-name/
+-- instruction.md
+-- task.toml
+-- environment/
|   +-- Dockerfile
|   +-- app files
+-- solution/
|   +-- solve.sh
+-- tests/
    +-- test.sh
    +-- test_outputs.py
```

Do not put `tests`, `solution`, or `oracle` into the Docker image. Harbor mounts them at runtime.

Use `codebase_size = "small"` for new submissions. That means at least 20 real files under `environment/`.

## 4. Write The Instruction Like A Human

The prompt should be short, direct, and complete. Usually 2-3 paragraphs is enough.

Good structure:

```text
Paragraph 1: What is broken and where the main source file is.
Paragraph 2: What input files are read, what output files are written, and the matching/business rules.
Paragraph 3: Exact output schema and formatting requirements.
```

Checklist:

- Every mentioned path is absolute, like `/app/src/main.go`.
- Every output file tested is named in the instruction.
- Every output schema tested is described.
- Every special formatting rule is explicit.
- No solution hints like "add a used array" or "change this line".
- No task name in the prompt.

Important lesson from our revisions:

If tests expect `0000000300`, the instruction must say "10-character zero-padded cents value". Do not assume agents will preserve formatting unless told.

## 5. Seed Bugs Fairly

Seed bugs in the environment source code, not in the tests or solution.

Good seeded bugs:

- Partial identifier comparison instead of full identifier.
- Missing allowed code in a filter.
- Wrong sign in a total.
- Missing one-time consumption of matched records.
- Missing normalization for input whitespace/case.

Bad seeded bugs:

- Syntax errors that prevent basic exploration.
- Broken Docker environment.
- Missing dependencies.
- Output files impossible to produce.
- Requirements not described in the instruction.

## 6. Write Behavioral Tests

Tests should run the actual program and check final behavior.

Good tests check:

- The main bug is fixed.
- Full-id matching avoids collisions.
- All required gates must match.
- Duplicate/consumed records behave correctly.
- Output schema and input order are stable.
- Summary totals and counts are correct.

Do not test implementation by grepping source code.

Every test function needs a docstring:

```python
def test_duplicate_payments_do_not_reuse_consumed_invoice():
    """Only the earliest eligible payment may consume a matching invoice."""
```

Each requirement in `instruction.md` should have a matching test. Each test should map back to something the instruction says.

## 7. Keep `tests/test.sh` Boring

The verifier script should always write a reward.

Use the canonical ending:

```bash
if [ $? -eq 0 ]; then
    echo 1 > /logs/verifier/reward.txt
else
    echo 0 > /logs/verifier/reward.txt
fi
```

Do not exit before that block unless there is a truly external infrastructure failure.

Install test-only dependencies here, not in the Dockerfile. Use pinned versions such as:

```bash
uvx \
  -p 3.13 \
  --with pytest==8.4.1 \
  --with pytest-json-ctrf==0.3.5 \
  pytest --ctrf /logs/verifier/ctrf.json /tests/test_outputs.py -rA
```

## 8. Write A Real Oracle

`solution/solve.sh` must solve the task, not dump expected outputs.

Good oracle behavior:

- Edits the source code.
- Runs the normal build or batch script.
- Checks output files exist.
- Uses deterministic commands.
- Uses `set -euo pipefail`.

Bad oracle behavior:

- Echoing final output files.
- Copying answers from solution files.
- Using network calls.
- Depending on random values.

For source edits, a small Python rewrite inside `solve.sh` is okay if it edits the app source deterministically.

## 9. Sync Check Before Running Anything

For each test, ask:

```text
Is this behavior described in instruction.md?
Is this behavior actually verified in tests?
Does the oracle implement it generally?
Is the seeded source initially broken for this behavior?
```

If any answer is no, fix the task before submission.

The common failure pattern is "test knows something the prompt never said." That gets flagged as instruction insufficiency.

## 10. Dockerfile Quality

Dockerfile rules:

- Use a specific base image tag, not `latest`.
- Install only app/runtime dependencies.
- Do not copy `tests/`, `solution/`, or `/oracle`.
- Do not create `/tests`, `/solution`, or `/oracle`.
- No privileged mode.
- Keep all build context inside `environment/`.

Example checks:

```powershell
Select-String -Path .\environment\Dockerfile -Pattern 'tests|solution|oracle|latest|privileged'
```

This should return nothing suspicious.

## 11. Metadata Checklist

`task.toml` should include:

```toml
version = "2.0"

[metadata]
author_name = "anonymous"
author_email = "anonymous"
difficulty = "hard"
category = "debugging"
subcategories = ["tool_specific"]
number_of_milestones = 0
codebase_size = "small"
languages = ["cobol", "bash"]
tags = ["cobol", "gnucobol", "fixed-width", "reconciliation"]
expert_time_estimate_min = 75
junior_time_estimate_min = 180

[verifier]
timeout_sec = 450.0

[agent]
timeout_sec = 900.0

[environment]
build_timeout_sec = 600.0
cpus = 2
memory_mb = 4096
storage_mb = 10240
workdir = "/app"
```

Use the right category and subcategory. COBOL/GnuCOBOL tasks fit `tool_specific`. Go CLI tasks may have no subcategory.

## 12. Required Local Verification

Run these checks before uploading.

Python syntax:

```powershell
python -m py_compile .\tests\test_outputs.py
```

Environment file count:

```powershell
(Get-ChildItem .\environment -Recurse -File | Measure-Object).Count
```

Docker build:

```powershell
docker build -t my-task:qa .\environment
```

Baseline should fail:

```powershell
$root = (Resolve-Path .).Path
$tests = Join-Path $root 'tests'
docker run --rm -v "${tests}:/tests:ro" my-task:qa bash -lc 'mkdir -p /logs/verifier; bash /tests/test.sh; cat /logs/verifier/reward.txt'
```

Expected: `0`

Oracle should pass:

```powershell
$root = (Resolve-Path .).Path
$tests = Join-Path $root 'tests'
$solution = Join-Path $root 'solution'
docker run --rm -v "${tests}:/tests:ro" -v "${solution}:/oracle:ro" my-task:qa bash -lc 'set -e; mkdir -p /logs/verifier; bash /oracle/solve.sh; bash /tests/test.sh; cat /logs/verifier/reward.txt'
```

Expected: `1`

This baseline/oracle pair is the most important sanity check. Baseline `0` proves tests catch the seeded bugs. Oracle `1` proves the task is solvable.

## 13. Rubric Rules

Rubrics are pasted in the platform UI, not packaged in the zip.

Every rubric line must:

- Start with `Agent`.
- End with `, +N` or `, -N`.
- Use only `1`, `2`, `3`, or `5`.
- Include at least 3 negative criteria.
- Avoid mentioning pytest, `/tests`, `instruction.md`, `task.toml`, oracle, or NOP.

Good rubric themes:

- Reads relevant source.
- Understands data format.
- Fixes each core bug.
- Handles the hard stateful rule.
- Builds/runs/inspects outputs.
- Penalizes broken compile, hardcoding, test tampering, or dropped matching criteria.

## 14. Packaging

Zip only:

```text
instruction.md
task.toml
environment/
solution/
tests/
```

Exclude:

```text
__pycache__/
*.pyc
logs/
jobs/
old zips
```

After zipping, inspect entries:

- Required files are present.
- Paths use `/`, not `\`.
- No top-level parent folder unless the platform expects it.

## 15. Final Self-Review

Before submitting, answer yes to all:

- Is the prompt concise but complete?
- Are all paths absolute?
- Does every tested behavior appear in the prompt?
- Does every prompt requirement have a test?
- Does the oracle pass in Docker?
- Does the baseline fail in Docker?
- Does `test.sh` always write reward?
- Is `codebase_size` small or large?
- Are dependencies/base images pinned?
- Are rubrics updated for the final task version?
- Are there at least 3 negative rubric criteria?

If all are yes, the task is in good shape.

## 16. How To Use Me Minimally

Use me for review, not authorship.

Best prompts to ask me:

```text
Review this task for instruction/test mismatch.
Check whether this rubric follows Edition 2 format.
Run Docker oracle and baseline verification.
Find cheating opportunities in this task.
Package this task after I made the final changes.
```

Avoid asking me to invent everything first. You make the first version, then I help tighten it.
