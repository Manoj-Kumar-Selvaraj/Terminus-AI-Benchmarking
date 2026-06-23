# Task Requirements

This page summarizes requirements every Terminus Edition 2 task must meet to pass review.

## Structural Requirements

### Required for All Tasks

| Component | Required | Notes |
|---|---|---|
| `task.toml` | Yes | Manifest with metadata and runtime limits |
| `environment/Dockerfile` or `environment/docker-compose.yaml` | Yes | Environment setup |
| `README.md` | Optional | Contributor notes |

### Non-Milestone Tasks

| Component | Required | Notes |
|---|---|---|
| `instruction.md` | Yes | Human-style task instructions |
| `solution/solve.sh` | Yes | Reference oracle solution |
| `tests/test.sh` | Yes | Main verifier runner, writes reward |
| `tests/test_outputs.py` | Yes | Deterministic pytest validation |

### Milestone Tasks

Milestone tasks use `steps/milestone_N/` directories instead of root-level prompt, solution, and tests.

Each milestone must include:

- `steps/milestone_N/instruction.md`
- `steps/milestone_N/tests/test.sh`
- `steps/milestone_N/tests/test_mN.py`
- `steps/milestone_N/solution/solve.sh`
- `steps/milestone_N/solution/solveN.sh`

Milestone tasks must not include root-level `instruction.md`, `tests/`, `solution/`, or `milestone_x.md`.

## task.toml Requirements

Required metadata:

- `author_name`
- `author_email`
- `difficulty`
- `category`
- `subcategories`
- `number_of_milestones`
- `codebase_size`
- `languages`
- `tags`
- `expert_time_estimate_min`
- `junior_time_estimate_min`

Required runtime limits:

- agent timeout
- verifier timeout
- environment build timeout

Example:

```toml
version = "2.0"

[metadata]
author_name = "anonymous"
author_email = "anonymous"
difficulty = "unknown"
category = "software-engineering"
subcategories = []
number_of_milestones = 0
codebase_size = "small"
languages = ["bash"]
tags = ["file-operations"]
expert_time_estimate_min = 60
junior_time_estimate_min = 120

[verifier]
timeout_sec = 450.0

[agent]
timeout_sec = 900.0

[environment]
build_timeout_sec = 600.0
cpus = 2
memory_mb = 4096
storage_mb = 10240
```

For milestone tasks, `[agent]` and `[verifier]` are replaced by per-step `[steps.agent]` and `[steps.verifier]` sections.

## instruction.md Requirements

Instructions must be:

- concise
- well specified
- interesting
- free of answers and hints
- unique
- written with absolute paths

No canary strings are allowed.

## Solution Requirements

`solve.sh` should usually start with:

```bash
#!/bin/bash
set -euo pipefail
```

Standards:

- human-written
- deterministic
- self-contained
- idempotent when practical
- no external dependencies that are not in the environment
- no hardcoded final answers

## Test Requirements

Tests must fully cover:

- explicit prompt requirements
- implicit expected behavior
- critical edge cases

Every prompt requirement should map to a test.

Test quality checklist:

- [ ] docstrings on every test
- [ ] test behavior, not implementation
- [ ] one test per requirement where practical
- [ ] no leaked answers
- [ ] anti-cheating coverage
- [ ] deterministic execution

## Dependency Pinning

Application packages must use exact version pins.

Base images must use specific version tags and must not use `latest`.

Digest pins are not required, but are allowed.

Good:

```dockerfile
FROM python:3.11-slim
RUN pip install pandas==2.0.0 numpy==1.24.0
```

Bad:

```dockerfile
FROM python:latest
RUN pip install pandas numpy
```

## Security Requirements

- [ ] No privileged containers.
- [ ] Solution files are not baked into the image.
- [ ] Tests are not baked into the image.
- [ ] Test dependencies are not pre-installed as application dependencies.
- [ ] Minimal attack surface.
- [ ] `environment/` structure prevents accidental copying.

## Difficulty Requirements

New submissions must be medium or hard by model pass rate.

| Difficulty | Accuracy Target |
|---|---|
| Hard | Accuracy <= 20% on best model, or <= 20% on worst model |
| Medium | 20% < accuracy <= 60% on worst model |
| Easy | 60% < accuracy <= 80% on worst model |

Tasks where the worst model scores above 80% will not be accepted. Current diversity requirements also block easy tasks.

## Anti-Cheating Requirements

Required:

- dynamic or computed values, not hardcoded answers
- multiple validation layers
- non-trivial verification
- no solution clues in tests or environment

Red flags:

- solution can be copied from test assertions
- output format reveals the answer
- hardcoded values pass tests
- agent can guess the answer

## Rubric Requirements

Every submission must include a rubric aligned to the task.

- Authored and edited in the Snorkel submission UI.
- At least three negative-reward criteria.
- Allowed negative values: `-1`, `-2`, `-3`, `-5`.
- Never use score `4` or `-4`.

## Automated Check Requirements

CI checks that must pass include:

- `pinned_dependencies`
- `typos`
- `tests_or_solution_in_image`
- `check_dockerfile_references`
- `check_test_sh`
- `check_task_absolute_path`
- `ruff`
- `validate_task_fields`

LLMaJ checks that must pass include:

- `behavior_in_task_description`
- `behavior_in_tests`
- `informative_test_docstrings`
- `anti_cheating_measures`
- `hardcoded_solution`
- `file_reference_mentioned`
- `structured_data_schema`
