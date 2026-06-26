# Writing the Oracle Solution

The oracle solution is an expert-authored script that reliably completes the task.

For non-milestone tasks, it lives at:

```text
solution/solve.sh
```

For milestone tasks, each milestone has its own solution under:

```text
steps/milestone_N/solution/
```

## Basic Structure

```bash
#!/bin/bash
set -euo pipefail

cd /app

# Perform the task

# Verify the result
```

## Key Principles

### Demonstrate the Command Sequence

Good:

```bash
#!/bin/bash
set -euo pipefail

grep -r "TypeError" /app/logs/ | head -1
sed -i '42s/data.process()/data.process() if data else None/' /app/main.py
python -m pytest /app/tests/ -v
```

Bad:

```bash
#!/bin/bash
echo "42" > /output/answer.txt
```

The oracle should derive the answer or perform the repair, not simply write expected output.

### Be Deterministic

Avoid:

- random values without seeds
- time-dependent operations
- network calls to external services
- filesystem-order assumptions such as unsorted `ls`

### Be Human-Written

The solution should be authored by you. Minimal assistance for syntax is okay, but the command sequence and reasoning should be yours.

### Fail Fast

Use `set -euo pipefail` where practical. Avoid hiding failures with `|| true` unless the failure is expected and intentionally handled.

## Advanced Patterns

Python block:

```bash
#!/bin/bash
set -euo pipefail
cd /app

python <<'PY'
import pandas as pd

df = pd.read_csv('/data/input.csv')
df['total'] = df['price'] * df['quantity']
df.to_csv('/data/output.csv', index=False)
PY
```

Service restart:

```bash
pkill -f server.py || true
python server.py &
sleep 2
curl -s http://localhost:8080/health | grep -q "ok"
```

## Common Mistakes

- hardcoding answers
- using randomness without seed
- relying on external network
- silently ignoring errors
- solving only what visible tests check
- making a solution that cannot run multiple times
- calling `/steps/milestone_N/...` or `../../milestone_N/solution/` from `solveN.sh` (Harbor mounts only the current milestone at `/solution/`)
- chaining prior milestone solves inside `solveN.sh` (for example `solve3.sh` calling `solve2.sh`)
- `text.replace(...)` lines that no longer match starter source (dead replacements)

### Milestone oracle layout

See **[MILESTONE_ORACLE_SOLUTION_RULES.md](MILESTONE_ORACLE_SOLUTION_RULES.md)** for the full portal-safe pattern.

```bash
# steps/milestone_N/solution/solve.sh
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
exec bash "${SCRIPT_DIR}/solveN.sh"
```

Each `solveN.sh` must be a **standalone cumulative** fix for milestones 1 through N starting from the broken starter codebase. Do not call prior milestone `solve*.sh` scripts from inside `solveN.sh`.

See [COMMON_ERRORS.md](COMMON_ERRORS.md#platform-qc-and-harbor-pitfalls-2026-0506) for the full recent QC checklist.

## Test the Oracle

Interactively:

```bash
harbor tasks start-env -p <task-folder> -i
```

Run oracle:

```bash
harbor run -a oracle -p <task-folder>
```

The oracle must pass consistently.
