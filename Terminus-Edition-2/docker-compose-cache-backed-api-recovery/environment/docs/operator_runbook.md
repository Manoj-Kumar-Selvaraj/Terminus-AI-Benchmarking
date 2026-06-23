# Operator runbook

Use only offline simulator commands under `/app/tools/compose_api_recovery.py`.

- Read `/app/docs/simulator_contract.md` for CLI subcommands, state JSON schema, cache key format, and `result.json` status values.
- Every subcommand requires `--state <path>` and `--out <dir>`; operator evidence is always written to `<dir>/result.json`.
- Preserve public flags, JSON state schemas, and service names (`db`, `cache`, `api`).
- Do not edit verifier fixtures or replace the simulator with static output generation.
