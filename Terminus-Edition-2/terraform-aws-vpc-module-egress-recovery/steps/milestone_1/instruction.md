# Route-ownership recovery controller

The incident is no longer a static VPC renderer repair. Implement `/app/cmd/vpcrecover/main.go` so `/app/bin/vpc-recover` supports:

```bash
vpc-recover inspect --root /app --json
vpc-recover plan --root /app --json
vpc-recover apply --root /app --owner OWNER [--fail-after route_commit]
vpc-recover resume --root /app --owner OWNER
vpc-recover verify --root /app --json
```

Use the desired config plus structured evidence under `/app/evidence`. The noisy production log is intentionally long and includes irrelevant INFO, WARN, and ERROR lines; do not hardcode a single log line.

Requirements:

- JSON output must use the exact schema values documented in `/app/docs/recovery_controller_contract.md`: `schema_version` is exactly `vpc-recovery.aws.1`; `inspect --json` includes integer `feature_level` and `evidence_files`; `plan --json` includes `environment`, `config_digest`, and recovered `route_tables`.
- App route tables must route `0.0.0.0/0` to a healthy NAT gateway in the same AZ.
- Data route tables must not keep module-owned default internet routes.
- Manual non-default routes and route-table metadata must be preserved.
- `plan` must not write recovered state or journal files.
- `apply` must write `/app/state/vpc_recovered_state.json` and `/app/state/recovery_journal.jsonl`.
- The journal must use snake_case JSONL records with event names `route_plan_written` and `apply_committed`, the owner, and the config digest.
- `--fail-after route_commit` simulates a lost response after durable route recovery. It must exit with a non-zero status, leave enough recovered state and journal data for the same owner to resume, and must not be treated as a successful command that only prints an interrupted JSON message.
- `resume` must continue after a lost response following `route_commit`.
- `verify --json` must read the recovered state without mutating files, return `valid: true` and `phase: "READY"` after successful recovery, and report a non-ready result when recovered state is absent.
- Recovery owner and config digest must fence stale or changed resumes with error substrings `stale owner` and `config digest changed`.
- Missing or unhealthy same-AZ NAT for an app AZ must fail before state mutation with error substring `missing nat gateway`.
- Do not leave manual test journals or recovered state in `/app/state`; the verifier copies the starting environment into every test root.