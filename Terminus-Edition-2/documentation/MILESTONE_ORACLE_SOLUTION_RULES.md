# Milestone Task Oracle Solution Rules

For milestone tasks, every milestone oracle solution must be self-contained and portal-safe.

Portal validation may mount only the current milestone’s `/solution` directory. A solution can pass local cumulative oracle but fail in portal if it depends on `/steps/milestone_1`, `/steps/milestone_2`, or any previous milestone folder.

## Required Pattern

Each milestone solution folder must contain only the current milestone entrypoint and current milestone oracle script:

```text
steps/milestone_1/solution/solve.sh
steps/milestone_1/solution/solve1.sh

steps/milestone_2/solution/solve.sh
steps/milestone_2/solution/solve2.sh

steps/milestone_3/solution/solve.sh
steps/milestone_3/solution/solve3.sh
```

`solve.sh` must dispatch only to the local milestone script using `SCRIPT_DIR`:

```bash
#!/usr/bin/env bash
set -Eeuo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
exec bash "${SCRIPT_DIR}/solveN.sh"
```

Replace `solveN.sh` with the correct milestone script, for example `solve3.sh` in milestone 3.

## Standalone Cumulative Fixes

Each `solveN.sh` must apply the full cumulative oracle fix needed for milestone N starting from the original broken codebase.

Example:

- `solve1.sh` fixes only milestone 1 behavior.
- `solve2.sh` fixes milestone 1 and milestone 2 behavior directly.
- `solve3.sh` fixes milestone 1, milestone 2, and milestone 3 behavior directly.
- `solve4.sh` fixes milestone 1 through milestone 4 behavior directly.

Do not make `solve3.sh` call `solve2.sh`. Do not make `solve4.sh` call `solve3.sh`.

## Use SCRIPT_DIR For Local Helpers

Always resolve solution-local files using `SCRIPT_DIR`.

Good:

```bash
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
bash "${SCRIPT_DIR}/solve3.sh"
python3 "${SCRIPT_DIR}/helper.py"
```

Bad:

```bash
bash /steps/milestone_2/solution/solve2.sh
bash ../milestone_2/solution/solve2.sh
python3 /solution/helper.py
```

`SCRIPT_DIR` is stable because it follows the actual location of the running script. Absolute paths can differ between local runners and portal runners.

## Forbidden Patterns

Do not use cross-milestone solution paths:

```bash
bash /steps/milestone_1/solution/solve1.sh
bash /steps/milestone_2/solution/solve2.sh
bash ../milestone_1/solution/solve1.sh
bash ../milestone_2/solution/solve2.sh
```

Do not use copied prior-solve chains:

```text
milestone_5/solution/solve5.sh -> solve4.sh -> solve3.sh -> solve2.sh -> solve1.sh
```

Prefer one standalone cumulative `solve5.sh`.

## Validation Requirement

Run both validations before submission.

Normal oracle must pass.

Also run isolated milestone validation:

1. Mount only `steps/milestone_N/solution` as `/solution`.
2. Mount only `steps/milestone_N/tests` as `/tests`.
3. Run:

```bash
bash /solution/solve.sh
python3 -m pytest /tests/test_mN.py
```

Repeat for every milestone.

If isolated milestone validation fails but cumulative oracle passes, the task is at risk of portal oracle failure.

## Short Rule

Each milestone’s `solve.sh` may call only its own local `solveN.sh` using `SCRIPT_DIR`.

Each `solveN.sh` must be a standalone cumulative fix for that milestone and must not call previous milestone solutions.
