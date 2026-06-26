# Security-generation rotation contract

A rotation couples the broker signer and policy generation. Its durable phases are `IDLE -> PREPARED -> QUORUM_VALIDATED -> SIGNER_SWITCHED -> OVERLAP -> COMPLETED`. Required verifier nodes count only when they acknowledge the exact target generation and bundle hash. The target signer must be staged and the generation must advance exactly once.

Only one signer is active. The former signer becomes verify-only during the bounded overlap and then retired; a revoked key is never resurrected. Retrying a completed operation returns its committed result. A different operation cannot join an active rotation. Rollback is safe before signer switch. After signer switch the controller follows forward recovery rather than reactivating the old key, returning status string `forward_recovery_required`. Every phase must survive process restart and injected failure.

Each phase transition must flush durable state before the matching `maybe_fail` call: `/app/state/rotation.json` records the current `phase`, `operation_id`, and generation after `PREPARED`, `QUORUM_VALIDATED`, `SIGNER_SWITCHED`, `OVERLAP`, and `COMPLETED` journal appends. Crash injection at `AFTER_ROTATION_PREPARE` or `AFTER_QUORUM` must be recoverable from those on-disk records plus the checksum journal.

## Injected failure points

`/opt/task-tools/capability-lab inject-failure --point <NAME>` arms `/app/state/failure.json`. Broker rotation code must call `maybe_fail('<NAME>')` at the matching phase (injected failures exit **75**):

| Point | Phase |
|-------|--------|
| `AFTER_ROTATION_PREPARE` | immediately after the `PREPARED` rotation journal append |
| `AFTER_QUORUM` | immediately after quorum validation and `QUORUM_VALIDATED` journal append |
| `AFTER_SIGNER_SWITCH` | immediately after switching `broker-keys.json` active signer, before overlap completion |
| `AFTER_ROTATION_JOURNAL` | immediately after the final rotation journal append for the committed result |

String names are case-sensitive and must match exactly.
