# Stateful EBS continuity contract

Each logical instance slot owns one volume for each configured `logical_name`.

- Volume identity is derived from application, logical slot, and logical volume name, never from transient instance ID.
- Volumes are encrypted with the configured KMS key in the configured account and have `delete_on_termination: false`.
- `attachment_generation` increases exactly once when a volume moves to a replacement instance.
- `attachment_token` is the first 24 hex characters of SHA-256 over canonical JSON `{"generation":N,"instance_id":"...","volume_id":"..."}` using sorted keys and compact separators.
- Rollback leaves prior volume attachments unchanged.
- Replaying after a lost response must not create another volume or increment attachment generation twice.
- Duplicate logical names, unencrypted definitions, wrong-account KMS ARNs, missing aliases, or destructive deletion settings fail closed.
- Prior state showing a volume attached to an instance from another logical slot fails closed with a `slot ownership` error.

## Validation error fragments

`validate` must fail closed with `error` text containing these substrings:

| Violation | Required substring in `error` |
|-----------|-------------------------------|
| Duplicate `logical_name` | `duplicate ebs logical_name` |
| `encrypted` not true | `unencrypted` |
| Missing `kms_key_alias` | `kms_key_alias` |
| KMS ARN outside configured account/region | `outside configured account` |
| `delete_on_termination` not false | `delete_on_termination false` |
| Volume attached to wrong slot instance | `slot ownership` |

Each `ebs_volumes` output entry has `id`, `logical_name`, `slot`, `size_gb`, `encrypted`, `kms_key_alias`, `kms_key_arn`, `delete_on_termination`, `orphaned`, `attached_instance_id`, `attachment_generation`, `attachment_token`, and `tags`. Managed volumes must have `encrypted: true`, `delete_on_termination: false`, and `orphaned: false`.

Volume tags are exactly `Application`, `Environment`, `Slot`, `VolumeRole`, and `ManagedBy`. `Slot` is the logical slot string, `VolumeRole` is the configured `logical_name`, and `ManagedBy` is `terraform-aws-ec2-module`.
