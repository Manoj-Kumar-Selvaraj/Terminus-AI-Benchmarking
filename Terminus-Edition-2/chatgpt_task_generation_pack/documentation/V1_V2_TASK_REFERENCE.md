# Terminus Edition 2 Task Reference: V1 and V2 Patterns

This document summarizes the local research across:

- `TerminalBench_v1/`: 79 Harbor/Terminus-style task folders.
- `Terminalbench_V2/submission4/`: one full Edition 2 submission package with task, eval results, rubrics, and model logs.
- `Sentinal/`: review playbooks and copied Harbor/TerminalBench reference docs.

The important finding: v1 and v2 use the same core task anatomy. Edition 2 adds stricter metadata and review expectations, but the working shape of a task remains `instruction.md`, `task.toml`, `environment/`, `solution/`, and `tests/`.

For Edition 2 onboarding and setup commands, use [EDITION2_QUICK_START.md](EDITION2_QUICK_START.md).

## Repository Map

```text
TerminalBench/
|-- TerminalBench_v1/
|   |-- Task-Guide.md
|   |-- instructions-guide.md
|   |-- <task-name>/
|   |   |-- instruction.md
|   |   |-- task.toml
|   |   |-- environment/
|   |   |-- solution/
|   |   `-- tests/
|   `-- January/, feb/, cobol-*, infra-*, ...
|
|-- Terminalbench_V2/
|   |-- CLAUDE.md
|   |-- review-output.txt
|   `-- submission4/
|       |-- task/
|       |-- eval_results/
|       `-- model_logs/
|
|-- Sentinal/
|   |-- README.md
|   |-- AGENT_START_PROMPT.md
|   |-- submission_template.md
|   `-- reference/
|
`-- Terminus-Edition-2/
    `-- V1_V2_TASK_REFERENCE.md
```

## Canonical Task Structure

Every accepted task should be self-contained:

```text
<task-name>/
|-- instruction.md
|-- task.toml
|-- environment/
|   |-- Dockerfile
|   `-- task input files, source code, data, compose file if needed
|-- solution/
|   `-- solve.sh
`-- tests/
    |-- test.sh
    `-- test_outputs.py
```

Optional files:

- `rubrics.txt` or platform-generated `test_rubrics.md`
- `milestones.md`, `solution/solve1.sh`, `tests/test_m1.py`, etc. for milestone tasks
- `environment/docker-compose.yaml` for multi-container tasks

Do not put `solution/` or `tests/` inside the Docker image. Harbor mounts these at runtime.

## V1 vs V2

The v1 task folders already use a Harbor/Terminus style and many `task.toml` files are `version = "2.0"`. Treat "v1" here as earlier local task production, not as the old Terminal-Bench YAML format.

Core fields that appear in v1 examples:

```toml
id = "cobol-pharmacy-claim-validator"
version = "2.0"
title = "COBOL: Pharmacy Claim Batch Validator (Copays & Fees)"
description = "..."

[metadata]
author_name = "TerminalBench Contributors"
author_email = "tbench@example.com"
difficulty = "hard"
category = "debugging"
tags = ["cobol", "healthcare", "fixed-width", "legacy", "debugging"]
expert_time_estimate_min = 40.0
junior_time_estimate_min = 90.0
```

Edition 2 submission metadata is stricter and should be the default going forward:

```toml
version = "2.0"

[metadata]
author_name = "anonymous"
author_email = "anonymous"
difficulty = "hard"
category = "security"
subcategories = ["tool_specific"]
languages = ["bash", "c"]
codebase_size = "small"
tags = ["security", "capabilities", "least-privilege", "linux"]
expert_time_estimate_min = 60.0
junior_time_estimate_min = 180.0
number_of_milestones = 0

[verifier]
timeout_sec = 300

[agent]
timeout_sec = 900

[environment]
build_timeout_sec = 300
cpus = 1
memory_mb = 2048
storage_mb = 10240
```

For Edition 2, include all required metadata fields. `subcategories = []` is acceptable if none apply. `author_name` and `author_email` must exist; use `anonymous` if needed.

## Instruction Pattern

Good `instruction.md` files read like a realistic user request to a coding agent:

- Clear objective in one to three short paragraphs.
- Absolute paths only, such as `/app/service_binary`, `/app/launcher.sh`, `/app/data/input.txt`.
- Measurable success criteria.
- Inputs and outputs named explicitly.
- No task name in the first line unless it is naturally part of the prompt.
- No canary strings.
- No step-by-step solution hints.
- No unverifiable tool commands such as "use vim".

Earlier v1 tasks sometimes use long specs, especially COBOL fixed-width validators with tables and priority error codes. Those are acceptable when the domain requires precision, but Edition 2 reviewers prefer concise prompts. Make the task hard because of the engineering problem, not because of a large instruction-following checklist.

Recommended structure:

```markdown
There is a broken component at `/app/...`. It currently does X, but it needs to do Y.

Fix it so the following observable behavior holds. Mention any files the agent must create or preserve.
```

Avoid:

- "You are an expert programmer..."
- long motivational framing
- solution strategy hints
- hidden requirements tested only in `tests/`
- relative paths

## Environment Pattern

The environment directory owns every file needed for the initial task state.

Common v1 examples:

- COBOL validators: `debian:bookworm-slim`, `gnucobol`, source in `/app`.
- Infrastructure/debugging tasks: Docker Compose, nginx, k8s-like manifests, systemd simulations.
- Data or legacy-processing tasks: static input files stored under `environment/`.

Edition 2 example:

- Uses pinned base image digests.
- Installs runtime tools (`gcc`, `libcap2-bin`, `strace`) in the image because agents are expected to inspect a binary.
- Copies only source/data from `environment/`.
- Compiles `/app/service_binary`, removes source if source should not be available, and sets initial permissions.

Rules:

- Keep all task files inside `environment/`; do not use build context outside it.
- Do not copy tests or solution into the image.
- Do not fetch arbitrary content from the internet during build.
- Pin Python/npm/gem/etc. package dependencies.
- Base image digests are preferred for Edition 2.
- Avoid privileged containers, docker socket mounts, or dangerous Linux capabilities unless the task is explicitly about those and the verifier can safely contain it.
- If `docker-compose.yaml` exists, set `custom_docker_compose = true`; if it has more than one service, also set `is_multi_container = true`.

## Oracle Solution Pattern

`solution/solve.sh` is the oracle. It should:

- Be executable and deterministic.
- Use `set -euo pipefail` where practical.
- Actually solve the stated task, not echo hardcoded expected outputs.
- Avoid internet access and package installation.
- Leave the same final state a successful agent should produce.
- Include self-checks when useful.

Good oracle behavior from the v2 sample:

- Derives a candidate capability set.
- Empirically prunes it.
- Writes `/app/launcher.sh` and `/app/capabilities.txt`.
- Runs the launcher and verifies output before exiting.

Avoid:

- random behavior without fixed seeds
- latency-based sleeps as correctness
- `ls` output without sorting when order matters
- incomplete scripts that only satisfy visible tests

## Verifier Pattern

`tests/test.sh` should always write `/logs/verifier/reward.txt`.

Preferred Edition 2 pattern:

```bash
#!/bin/bash
echo 0 > /logs/verifier/reward.txt

if [ "$PWD" = "/" ]; then
    echo "Error: No working directory set."
    exit 1
fi

uvx \
  --with pytest==8.4.1 \
  --with pytest-json-ctrf==0.3.5 \
  pytest --ctrf /logs/verifier/ctrf.json /tests/test_outputs.py -rA

if [ $? -eq 0 ]; then
  echo 1 > /logs/verifier/reward.txt
else
  echo 0 > /logs/verifier/reward.txt
fi
```

Notes from v1:

- Some older `test.sh` files install `uv` using `curl`. This is present in local v1 docs, but Edition 2 packaging is cleaner when `uvx` is available in the image or copied from a pinned `ghcr.io/astral-sh/uv` image.
- Tests commonly use `pytest==8.4.1` and `pytest-json-ctrf==0.3.5`.

`tests/test_outputs.py` should:

- Use behavior tests, not implementation grep, unless command usage is part of the task and must be trace-verified.
- Include docstrings for every test.
- Be deterministic and order-independent.
- Reset mutable state per test.
- Verify correctness, not only file existence or format.
- Avoid exact string matching unless exact output is explicitly part of the task.
- Avoid hidden requirements that the instruction never implies.
- Avoid partial rewards; reward is binary 0 or 1.

Edition 2 reviewers tolerate anti-cheat checks if they validate the stated behavior and do not impose extra hidden work. Example: verifying a binary was actually executed via marker file and `strace`.

## Rubric Pattern

Rubrics are optional. If present, they must follow strict formatting:

```text
Agent uses strace or capsh to inspect runtime capability behavior, +2
Agent empirically tests candidate capabilities by running the service through capsh, +3
Agent modifies /app/service_binary or any file under /app/data/, -5
```

Rules:

- Every line starts with `Agent`.
- Every line ends with `, <score>`.
- Scores must be one of `+1`, `+2`, `+3`, `+5`, `-1`, `-2`, `-3`, `-5`.
- Include at least three negative penalties if rubrics are provided.
- Do not mention oracle, NOP, tests, `task.toml`, or `instruction.md`.
- Criteria should be trace-evidenced agent behavior.

## Eval Package Structure

Edition 2 submissions include more than the task:

```text
submission/
|-- task/
|   |-- instruction.md
|   |-- task.toml
|   |-- environment/
|   |-- solution/
|   `-- tests/
|-- eval_results/
|   |-- text_summary.md
|   |-- quality_check_summary.md
|   |-- test_rubrics.md
|   `-- code_quality_check_results.txt
`-- model_logs/
    |-- agent_performance.json
    |-- debug-output-tbench-task.json
    |-- summary-of-runs-comment.md
    `-- jobs/
```

Use `eval_results/text_summary.md` to understand:

- difficulty label
- solvability
- agent pass rates
- oracle and NOP pass rates
- per-test pass counts
- failure analysis

Use `quality_check_summary.md` to cross-check:

- instruction/test alignment
- pinned dependencies
- anti-cheating measures
- tests/solution not baked into image
- hardcoded solution risk
- file references mentioned

## Difficulty Target

Accepted tasks should not be trivial:

- NOP should fail.
- Oracle should pass consistently.
- Agent pass rate should generally stay below 80%.
- Hard tasks often show 0-40% pass rate on frontier agents.

The local v2 example is marked hard:

- Oracle: 100% pass.
- NOP: 0% pass.
- Claude: 0/5 full passes.
- GPT-5: 1/5 full passes.
- All tests passed by at least one agent run, so it is solvable.

Remember the distinction:

- Passing a run: one run passes every test.
- Solvable: across all runs, every individual test passes at least once.

## Common Accepted Task Families

Observed in local v1:

- COBOL fixed-width business validators.
- PL/I and legacy file processors.
- Infrastructure repair tasks: Terraform, k8s, nginx, docker-compose, systemd.
- Data-processing and reconciliation tasks.
- Security and least-privilege tasks.
- API or service debugging tasks.

For Edition 2, prefer tasks that are:

- realistic engineering work
- novel relative to existing local tasks
- inspectable from local files
- multi-step, but not artificially long
- difficult through domain reasoning or debugging, not vague requirements

## Creation Checklist

Before packaging a new Edition 2 task:

- `instruction.md` is concise, realistic, and uses absolute paths.
- Every tested behavior is stated or clearly implied in the instruction.
- `task.toml` has all Edition 2 metadata fields.
- `environment/` contains all initial files and no solution/test files.
- Dependencies are pinned where practical.
- `solution/solve.sh` is deterministic and passes.
- `tests/test.sh` writes reward `0` before running tests and writes final `0/1`.
- `tests/test_outputs.py` has docstrings and behavior-focused assertions.
- NOP fails.
- Oracle passes repeatedly.
- Task is not too similar to local v1/v2 examples.
- If rubrics exist, they follow the exact score and line format.
- No leftover job logs, caches, parent `README.md`, or submission artifacts are packaged with the task.

## Review Checklist

When reviewing a task submission:

- Read `task/task.toml`.
- Read `task/instruction.md`.
- Read `task/environment/Dockerfile` and compose files if any.
- Read `task/solution/solve.sh`.
- Read `task/tests/test.sh` and `task/tests/test_outputs.py`.
- Read `eval_results/text_summary.md`.
- Read `eval_results/quality_check_summary.md`.
- Read rubrics only if present.
- Inspect model logs only when pass/failure reasons are unclear.

High-severity rejection reasons:

- Missing required files.
- Oracle fails or is flaky.
- NOP passes.
- Tests do not match instructions.
- Verifier can exit without reward.
- Tests bake in hidden requirements.
- Environment exposes solution or test answers.
- Dependencies or network usage make the task non-reproducible.
- Metadata required by Edition 2 is missing.
- Task is too easy, duplicate, or fundamentally unfair.

## Recommended Edition 2 Template

```text
<task-name>/
|-- instruction.md
|-- task.toml
|-- environment/
|   |-- Dockerfile
|   `-- app files and static data
|-- solution/
|   `-- solve.sh
`-- tests/
    |-- test.sh
    `-- test_outputs.py
```

Use `Terminalbench_V2/submission4/task` as the closest local Edition 2 package example.
Use `TerminalBench_v1/Task-Guide.md` and `Sentinal/reference/Task-Guide.md` as the broader task-production and review references.
