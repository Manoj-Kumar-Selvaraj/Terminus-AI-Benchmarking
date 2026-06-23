# Oracle Agent

The Oracle Agent runs your `solution/solve.sh` in the task environment and verifies that all tests pass.

The Oracle Agent is run three times during evaluation.

## What It Does

The Oracle Agent:

1. Starts the Docker environment.
2. Executes the oracle solution.
3. Runs verifier tests.
4. Reports pass or fail.

If the Oracle Agent cannot solve the task, the task is broken.

## Run Oracle

```bash
harbor run -a oracle -p <task-folder>
```

Verbose:

```bash
harbor run -a oracle -p <task-folder> -v
```

## Debugging Failures

When oracle fails:

1. Read the error carefully.
2. Identify which step failed.
3. Reproduce interactively.
4. Fix `solution/solve.sh`, tests, or environment.
5. Re-run oracle.

Interactive reproduction:

```bash
harbor tasks start-env -p <task-folder> -i
```

Inside the container, run solution commands one by one.

## Common Failure Types

| Symptom | Likely Cause | Fix |
|---|---|---|
| `command not found` | Missing dependency | Add to `environment/Dockerfile` |
| `file not found` | Wrong path or missing COPY | Use absolute paths and check Dockerfile |
| `permission denied` | Bad permissions | Fix ownership or `chmod` in environment |
| tests fail | Solution/test mismatch | Inspect test output and align behavior |
| timeout | Slow solution | Optimize or adjust timeout |

## Oracle vs Real Agents

| Oracle | Real Agents |
|---|---|
| Runs your `solve.sh` | Generate their own solution |
| Should be deterministic | May vary between runs |
| Tests task validity | Tests task difficulty |
| Must always pass | May fail, which is expected |

Run oracle early and often.
