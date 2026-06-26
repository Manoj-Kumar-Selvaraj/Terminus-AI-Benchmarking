The broker now resists assertion and exchange replay attacks, yet the emergency security-generation rehearsal can still switch signers on stale acknowledgements, lose its phase after restart, or reactivate compromised material during rollback. Use `/app/evidence/rotation-rehearsal.log`, `/app/docs/rotation-contract.md`, and the existing state/journals to make rotation recoverable.

Keep exactly one active signer, bind quorum to the exact generation and bundle, preserve the bounded verification overlap, and resume every injected failure or lost response.

## Success criteria

1. Rotation completes only when **both** required verifier nodes acknowledge the **exact target generation** and **exact bundle hash** (for example generation `42` with `bundle-42-a8d9`).
2. Stale-generation or wrong-bundle acknowledgements do not count toward quorum; rotation remains blocked and the active signer stays `broker-v1`.
3. After a successful switch, exactly one signer is `active` (`broker-v2`); the former signer is `verify_only` during overlap and `retired` afterward.
4. Injected failures after prepare, quorum validation, signer switch, or journal commit resume the same `operation_id` without split signers or lost phase. Call `maybe_fail` at the exact points in `/app/docs/rotation-contract.md`: `AFTER_ROTATION_PREPARE`, `AFTER_QUORUM`, `AFTER_SIGNER_SWITCH`, and `AFTER_ROTATION_JOURNAL`. Each phase must be written to `/app/state/rotation.json` before its matching failure point.
5. A lost response after commit returns the same committed result on retry.
6. Rollback before signer switch returns safely to idle; rollback after switch returns status `forward_recovery_required` and must not resurrect a revoked key.
7. `broker recover` reconstructs durable rotation phase and generation after restart.

Preserve all earlier verification, policy, replay, CLI, and state contracts. Do not modify `/opt/task-tools`.
