# Task Components

Every Harbor task is made of required components: prompt, metadata, environment, oracle solution, and verifier tests.

Harbor is the evolution of Terminal-Bench. Terminus Edition 2 uses the Harbor task format.

## Non-Milestone File Structure

```text
my-task-folder/
|-- instruction.md
|-- task.toml
|-- environment/
|   |-- Dockerfile
|   |-- docker-compose.yaml
|   `-- build files
|-- solution/
|   `-- solve.sh
`-- tests/
    |-- test.sh
    `-- test_outputs.py
```

Milestone tasks use a different `steps/` layout. See [MILESTONES_GUIDE.md](MILESTONES_GUIDE.md).

## instruction.md

This is the prompt shown to the agent. It should be human-written and realistic.

Instructions must be:

- concise
- well specified
- interesting
- free of answers and hints
- unique
- written with absolute paths

See [PROMPT_STYLING_GUIDE.md](PROMPT_STYLING_GUIDE.md).

## task.toml

`task.toml` contains metadata and runtime configuration.

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

For milestone tasks, use `[[steps]]` blocks and per-step `[steps.agent]` and `[steps.verifier]`.

## environment/

The environment definition belongs in `environment/`.

Rules:

- Pin application dependency versions.
- Use a specific base image tag; avoid `latest`.
- Never copy `solution/` or `tests/` in the Dockerfile.
- Do not use privileged mode.
- Keep build context inside `environment/`.

Special runtime paths:

- `/logs/verifier/`: reward file and verifier logs
- `/logs/agent/`: agent logs
- `/oracle/`: solution folder copied here at runtime
- `/tests/`: tests folder copied here at runtime

## solution/solve.sh

The oracle solution should:

- demonstrate the command sequence
- be deterministic
- avoid hardcoded final answers
- be self-contained
- be idempotent when practical

Template:

```bash
#!/bin/bash
set -euo pipefail

cd /app
# solution commands here
```

## tests/

`tests/test.sh` is the verifier entrypoint. It must produce a reward file.

```bash
#!/bin/bash
echo 0 > /logs/verifier/reward.txt

uvx \
  -p 3.13 \
  -w pytest==8.4.1 \
  -w pytest-json-ctrf==0.3.5 \
  pytest --ctrf /logs/verifier/ctrf.json /tests/test_outputs.py -rA

if [ $? -eq 0 ]; then
  echo 1 > /logs/verifier/reward.txt
else
  echo 0 > /logs/verifier/reward.txt
fi
```

Test principles:

- Always write reward, including on failure.
- Use absolute paths.
- Test behavior, not implementation.
- Add docstrings to every test.
- Cover all explicit and implicit prompt requirements.
