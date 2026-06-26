# Milestone 5 — Reconcile restart, drift, and mixed event versions

Generation pinning and single-writer cutover work in steady state. A controller restart during an uncertain alias response leaves a damaged journal tail, a pending execution, and drift between the saved deployment and trusted runtime. The rollout also contains both Jenkins bridge events and the new Lambda event schema.

Review:

- `/app/evidence/restart_reconciliation.log`
- `/app/docs/recovery-contract.md`
- `/app/docs/event-contract.md`
- `/app/docs/security-contract.md`

Complete restart-safe reconciliation. Preserve valid journal records in `/app/state/operations.journal.jsonl` when the final JSONL record is incomplete, repair confirmed active-generation drift from the saved deployment, and resume pending executions from their durable checkpoints. Repeated reconciliation must be idempotent.

`pipelinectl reconcile` must print JSON with exactly these fields:

- `journal_repaired` (bool): `true` when a corrupt journal tail was repaired
- `drift_repaired` (bool): `true` when active-generation drift was cleared
- `resumed` (string array): execution IDs resumed during this pass

Support both documented event versions. Version 1 must remain functional and derive its owner exactly as `legacy-jenkins/<batch_id>`. Version 2 must require and preserve its explicit owner. Checkpoints returned by `run` and `resume` must preserve `protocol_version` and `owner` from the accepted request. Reject unsupported requests and reject reuse of an execution ID with a different batch ID, owner, or artifact digest before side effects. One owner or stale worker must not take over another execution.

Do not erase state, rotate execution IDs, fabricate runtime output, persist credentials, add static Jenkins or AWS secrets, or rewrite completed histories.
