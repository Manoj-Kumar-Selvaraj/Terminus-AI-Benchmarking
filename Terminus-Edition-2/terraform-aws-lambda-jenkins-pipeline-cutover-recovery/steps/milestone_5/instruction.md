# Milestone 5 - Reconcile restart, drift, and mixed event versions

An uncertain alias response left a torn journal tail, a pending execution, and active-generation drift. The rollout must also accept Jenkins bridge events beside the Lambda event schema. Use `/app/evidence/restart_reconciliation.log`, `/app/docs/recovery-contract.md`, `/app/docs/event-contract.md`, and `/app/docs/security-contract.md`.

Implement restart-safe `pipelinectl reconcile`: discard only an incomplete final journal line, reapply the saved deployment only for confirmed active-generation drift, and resume pending checkpoints without duplicate effects. Repeated reconciliation is idempotent and prints exactly `journal_repaired` (bool), `drift_repaired` (bool), and `resumed` (string array).

Keep version 1 events working with owner `legacy-jenkins/<batch_id>` and require version 2's explicit owner. Returned checkpoints preserve accepted protocol and owner. Reject unsupported protocols and execution-ID reuse with changed batch, owner, or artifact before side effects; reject these requests nonzero and include `conflicting` for execution-identity reuse. Do not erase state, rotate IDs, fabricate runtime output, persist credentials, add static secrets, or rewrite completed history.
