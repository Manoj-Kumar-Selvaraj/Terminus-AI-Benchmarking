# Go matcher milestone task — structural template

Fork this folder when creating a new Terminus Edition 2 multi-milestone Go reconciliation task,
or when fixing portal oracle path failures.

## Fork checklist

1. Copy entire `template-go-matcher-milestone` folder to `go-your-domain-action-matcher`.
2. Search-replace `REPLACE_ME` across all files (domain names, paths, columns).
3. Expand `environment/cmd/reconcile/main.go` bugs to match your scenario.
4. Update `solve1.sh` / `solve2.sh` / `solve3.sh` patches to match your starter source.
5. When adding milestone N > 1: **copy prior `solveK.sh` files** into `steps/milestone_N/solution/`.
6. Keep every `solve.sh` using only `bash "$SCRIPT_DIR/solveK.sh"` (never `/steps/milestone_*`).
7. Write real instructions, tests, and rubric; sync `rubric.txt` to `revision-custom-rubrics/`.
8. Validate:

```bash
cd Terminus-Edition-2
grep -R --include='solve*.sh' -E '/steps/milestone|TASK_ROOT' ./go-your-task/steps/   # must be empty
bash scripts/terminus2_cli.sh preflight ./go-your-task
bash scripts/terminus2_cli.sh oracle ./go-your-task
```

## Layout

```text
template-go-matcher-milestone/
  README.md                 ← this file
  task.toml
  rubric.txt                ← local only; exclude from zip
  environment/              ← Docker image context only
  steps/milestone_{1,2,3}/
    instruction.md
    tests/test.sh
    tests/test_mN.py
    solution/solve.sh       ← portal-safe wrapper
    solution/solveN.sh        ← oracle logic
```

## Portal-safe solution rule

Harbor mounts **only** `/solution/` for the current milestone. Milestone 2 must contain
` solve1.sh` (copy from M1) plus `solve2.sh`. Milestone 3 must contain copies of
`solve1.sh`, `solve2.sh`, plus `solve3.sh`.

See also:

- `Revision-ChatGpt/PORTAL_ORACLE_FAILURE_RESOLUTION.txt`
- `Revision-ChatGpt/PORTAL_SAFE_SOLUTION_SCRIPTS_TEMPLATE.txt`
- `documentation/GO_TASK_TEMPLATE.md`

## Reference tasks (working examples)

- `go-catering-order-adjustment-matcher` — chained local solve copies
- `go-gym-membership-waiver-matcher` — `$SCRIPT_DIR` wrappers
- `go-live-auction-bid-reversal-ledger` — self-contained heredoc per milestone
