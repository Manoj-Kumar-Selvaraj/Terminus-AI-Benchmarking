The crash-recovery rollout exposed a key-rotation regression: an authorization prepared under the old key was retried under the newly active key. Review `/app/evidence/rotation_incident.log`, `/app/docs/key_rotation_contract.md`, and the persisted request and policy fields.

Preserve a request's original key and policy generation through retry and recovery while retaining milestones 1 and 2. Enforce the old-key grace deadline and revocation only before a new HSM side effect. A matching HSM audit row that already exists must still be finalized without a second call. New requests must use the current key, and invalid rotations must leave policy unchanged.

The verifier covers recovery during and after grace, revocation before and after the external side effect, new-request key selection, invalid rotation rollback, repeated recovery, and stale-fence administration.
