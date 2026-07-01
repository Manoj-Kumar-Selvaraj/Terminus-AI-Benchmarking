# Transactional replay, journal repair, and final verification

Preserve Milestones 1 through 4. Complete the recovery workflow so it is restart-safe, fail-closed, and idempotent.

Requirements:

- `apply` and `resume` must use `/app/state/recovery_journal.jsonl`.
- `--fail-after route_commit` and `--fail-after endpoint_commit` simulate lost responses after durable commits. They must exit with a non-zero status and leave enough state and journal data for the same owner to resume safely.
- A torn final JSONL journal record may be truncated and repaired on `resume`; only the final malformed record may be discarded.
- Corruption before the final record must fail closed with error substring `journal corruption`.
- A different owner must not resume an active operation and must fail with error substring `stale owner`.
- A changed config digest must not resume the same operation and must fail with error substring `config digest changed`.
- Repeated `apply` after successful recovery must be idempotent. It must not duplicate moved actions, endpoint associations, routes, or journal records that affect recovered state.
- `verify --json` must read the recovered state without mutating files. It must report `valid: true` and `phase: "READY"` only after the controller-generated recovered state exists.
- Keep the exact final recovered-state schema value `vpc-recovery.aws.1`.
- The final recovered state must preserve the cumulative `route_tables`, `gateway_endpoints`, `subnets`, `moved`, `flow_log`, `resolver_security_group`, `drift_report`, `outputs`, and `plan_actions` fields.
- Final `outputs.private_app_route_table_ids` must match the recovered app route table IDs, and every gateway endpoint must associate exactly to those route tables.