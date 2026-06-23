# Preserve encrypted EBS data volumes across replacement

You are recovering a Terraform AWS EC2 module rollout for the payments API fleet. This is offline: do not call AWS and do not require Terraform. Use `/app/tools/ec2sim.py`, `/app/docs/module_contract.md`, and `/app/evidence`.

Attach non-orphaned encrypted KMS data volumes and reject unencrypted volume definitions.

## Success criteria

- Preserve milestones 1–3 behavior.
- Each instance has one encrypted, non-orphaned volume with `kms_key_alias: alias/payments-ebs`, `ManagedBy: terraform-aws-ec2-module`, and `delete_on_termination: false`.
- `validate` rejects volumes with `encrypted: false`; errors must contain `unencrypted`.

Compatibility constraints: keep `/app/infra/modules/ec2`, all labels in `main.tf`, all outputs in `outputs.tf`, and CLI flags `plan`, `apply`, `validate`, `--config`, `--prior-state`, `--out`, `--state`. Do not hardcode sample JSON or edit verifier fixtures.
