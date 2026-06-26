# Preserve stateful EBS ownership through replacement and replay

The rollout retry moved a retained payments volume twice and inventory later showed a volume attached to an instance from another logical slot.

Preserve milestones 1–3. Use `/app/docs/storage_contract.md` and `/app/evidence/storage_inventory.json`.

## Required behavior

- Each logical slot owns one stable encrypted volume for every configured logical volume definition.
- Volume identity is based on application, slot, and logical name, not transient instance ID.
- Successful replacement increments attachment generation exactly once and produces the deterministic fenced attachment token described in `/app/docs/storage_contract.md`.
- Lost-response replay reuses already committed attachment state instead of incrementing it again.
- Failed pilot rollback leaves all prior volume attachments, generations, and tokens unchanged.
- Reject unencrypted definitions, missing aliases, wrong-account KMS ARNs, destructive deletion settings, duplicate logical names, and prior attachment ownership conflicts.
- Multiple logical volume definitions remain independent and unique per slot. Emit the exact `ebs_volumes` fields and volume tag schema documented in `/app/docs/storage_contract.md`.
- Preserve all prior rollout, network, and release guarantees.

Do not orphan retained volumes, derive volume IDs from instance IDs, silently repair cross-slot ownership, or delete data to make replay pass.
