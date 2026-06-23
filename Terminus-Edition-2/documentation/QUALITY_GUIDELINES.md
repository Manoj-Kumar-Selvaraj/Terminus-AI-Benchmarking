# Quality Guidelines

These guidelines define the quality bar for Terminus Edition 2 tasks.

## High-Level Requirements

### Instruction Prompt Styling

Prompts should be realistic, concise, human-written, and avoid hints. They should generally describe the problem in one to three paragraphs.

### Multi-Step

Tasks should require chaining multiple commands, handling intermediate states, and reasoning. Avoid tasks solvable with a single command or a single obvious action.

### Testable

Tasks must be fully specified, self-contained, and deterministically verifiable.

### Novel

Avoid variations of existing TerminalBench or Terminus Edition 1 tasks. Use new setup, data, and task definitions.

### No Privileged Operations

Tasks must not require unsafe Docker settings such as `--privileged`.

### Standalone

Tasks must run without human input after start. All parameters should be provided via files, flags, or environment variables.

## Scenarios to Avoid

### 1. Latency-Based Tests

Do not test hardware-dependent performance or latency.

Instead, test correctness and functional behavior.

### 2. Different Oracle and Agent Testing

Verifier logic must be identical for oracle and agent. No conditional logic based on execution mode.

### 3. Missing Compose Metadata

If `docker-compose.yaml` exists:

```toml
custom_docker_compose = true
```

If multiple containers are used:

```toml
is_multi_container = true
```

### 4. Web Data Fetching

Do not fetch runtime task data from web URLs. Store required data in `environment/`.

Package installs through package managers are acceptable.

### 5. Reserved Directories

Do not create or modify:

- `/tests`
- `/solution`
- `/oracle`

These are reserved by Harbor.

### 6. Missing Reward on Failure

Failed runs must write `0` to reward.

Good:

```bash
uvx -w pytest==8.4.1 pytest /tests/test_outputs.py -rA && rc=0 || rc=$?

if [ "$rc" -eq 0 ]; then
  echo 1 > /logs/verifier/reward.txt
else
  echo 0 > /logs/verifier/reward.txt
fi
```

### 7. Missing Environment Variable Defaults

If using variables such as `TEST_DIR`, provide defaults:

```bash
TEST_DIR="${TEST_DIR:-/tests}"
pytest "$TEST_DIR/test_outputs.py" -rA
```

Hardcoded `/tests/test_outputs.py` is also acceptable.

### 8. Oracle-Proximity Performance Thresholds

Do not set thresholds so close to oracle performance that the task becomes "replicate the oracle".

Thresholds should allow multiple valid solution strategies.

Ask: would a fundamentally different correct approach pass?

## Quick Reference

| Rule | Summary |
|---|---|
| No latency tests | avoid hardware-dependent metrics |
| Identical testing | same verifier for oracle and agent |
| Tag compose | `custom_docker_compose = true` |
| Tag multi-container | `is_multi_container = true` |
| No web fetching | store data locally |
| Reserved dirs | do not create `/tests`, `/solution`, `/oracle` |
| Always write reward | write `0` on failure |
| Default env vars | use `${VAR:-default}` |
