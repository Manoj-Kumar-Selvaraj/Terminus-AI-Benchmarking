# Understanding Milestones

Milestones let Terminus Edition 2 move beyond all-or-nothing task completion.

Terminology: Harbor calls these multi-step tasks. Terminus docs call them milestones. The terms are interchangeable.

## What Are Milestones?

Milestones divide a complex engineering task into standalone, sequential subtasks.

The agent works through milestones in order. Each milestone is verified independently before the next one runs, allowing incremental rewards and better process evaluation.

## The Milestone Rule

Each stage must be a prerequisite for the next.

A milestone task should not be a list of unrelated tasks. Milestone 2 should depend on correct completion of milestone 1.

## File Structure

```text
your-task/
|-- task.toml
|-- environment/
|   |-- Dockerfile
|   `-- environment files
`-- steps/
    |-- milestone_1/
    |   |-- instruction.md
    |   |-- tests/
    |   |   |-- test.sh
    |   |   `-- test_m1.py
    |   `-- solution/
    |       |-- solve.sh
    |       `-- solve1.sh
    |-- milestone_2/
    |   `-- ...
    `-- milestone_3/
        `-- ...
```

Do not include root-level `instruction.md`, `tests/`, `solution/`, or `milestone_x.md`.

Files persist across milestones. The same container filesystem is shared, so files created in milestone 1 are visible to milestone 2.

## Per-Milestone Instructions

Each milestone has:

```text
steps/milestone_N/instruction.md
```

Milestone 1 should include the overall context. Later milestones can be shorter and describe only new requirements.

## Per-Milestone Verifiers

Each milestone has:

```text
steps/milestone_N/tests/test.sh
steps/milestone_N/tests/test_mN.py
```

Each `test_mN.py` should use a single `TestMilestoneN` class.

Tests must:

- score only that milestone
- avoid checking future milestone requirements
- be deterministic
- tolerate state left by previous milestones

## Per-Milestone Oracle Solutions

Each milestone has:

```text
steps/milestone_N/solution/solve.sh
steps/milestone_N/solution/solveN.sh
```

`solve.sh` is a thin wrapper:

```bash
#!/bin/bash
set -euo pipefail
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
bash "$SCRIPT_DIR/solve1.sh"
```

`solveN.sh` contains only commands required for milestone N.

## task.toml

Milestone tasks use `[[steps]]` array-of-tables. The order determines execution order.

```toml
version = "2.0"

[metadata]
author_name = "anonymous"
author_email = "anonymous"
difficulty = "hard"
category = "software-engineering"
subcategories = []
number_of_milestones = 2
codebase_size = "small"
languages = ["python", "bash"]
tags = ["debugging", "tests", "workflow"]
expert_time_estimate_min = 60
junior_time_estimate_min = 120

[environment]
build_timeout_sec = 600.0
cpus = 2
memory_mb = 4096
storage_mb = 10240
workdir = "/app"

[[steps]]
name = "milestone_1"

[steps.agent]
timeout_sec = 1200.0

[steps.verifier]
timeout_sec = 450.0

[[steps]]
name = "milestone_2"

[steps.agent]
timeout_sec = 1200.0

[steps.verifier]
timeout_sec = 450.0
```

Rules:

- `number_of_milestones` must equal the number of `[[steps]]` blocks.
- `[[steps]].name` must be `milestone_1`, `milestone_2`, etc.
- Step names must match directories under `steps/`.
- Do not use top-level `[agent]` or `[verifier]` blocks.
- `[environment]` applies globally.

## Rubric

The rubric should cover all milestones.

Each milestone should be represented with 10-40 positive points.

| Milestones | Positive Point Range |
|---|---|
| 1 | 10-40 |
| 2 | 20-80 |
| 3 | 30-120 |

For more milestones, continue the same pattern.

## Best Practices

- Make milestone N depend on milestone N-1.
- Keep milestone boundaries clear.
- Use 2-5 milestones for most tasks.
- Avoid over-segmenting.
- Remember that the filesystem is shared.
- If a later milestone needs a clean path, reset it explicitly.
