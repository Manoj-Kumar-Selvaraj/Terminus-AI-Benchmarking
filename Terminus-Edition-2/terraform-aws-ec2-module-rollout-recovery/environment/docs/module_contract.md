# EC2 module compatibility contract

This is an offline simulator. Do not call AWS and do not require Terraform.

Preserve:

- `/app/infra/modules/ec2`
- every Terraform resource label in `main.tf`
- every output key in `outputs.tf`
- `tools/ec2sim` commands `plan`, `apply`, and `validate`
- flags `--config`, `--prior-state`, `--out`, `--state`, and `--journal`

Top-level output schema is `ec2sim.aws.2`. Required sections are `release_identity`, `launch_template`, `security_group`, `autoscaling_group`, `instances`, `ebs_volumes`, `iam_role`, `drift_report`, `import_report`, `plan_actions`, `journal_repair`, and `outputs`.

Nested schemas are part of the contract. `launch_template` includes `id`, `version`, `ami_id`, `architecture`, `instance_type`, `user_data_sha256`, `metadata_options`, `provenance`, and `tags`. `security_group` includes `id`, exact `ingress`, and exact `egress` rule arrays. Each instance includes `id`, `slot`, `az`, `subnet_id`, `public_ip_associated`, `security_group_id`, `launch_template_version`, `ami_id`, `state`, `health`, and `tags`. Every output `slot`, including instance, volume, event, and drift slots, is a zero-based JSON integer. Only the AWS-style `tags.Slot` value is a decimal string. `autoscaling_group.instance_refresh.status` is `stable` when no replacement is executing, `in_progress` after durable partial progress, `completed` after a successful replacement, or `rolled_back` after a failed health check. `outputs` includes `launch_template_id`, `launch_template_version`, `autoscaling_group_name`, `instance_ids`, `volume_ids`, `rollout_operation_id`, and `drift_report`.

`plan_actions` describes the simulated plan rather than an untyped log. Every `create`, `no_op`, and `scale_in` entry has `action`, integer `slot`, and `instance_id`. Every `rolling_replace` entry has those fields plus `operation_id`. A `report_only` entry has `action`, `instance_id`, and `field`; it must not cause a replacement. Entries may be empty only when no simulated action is required.

Every `instance_refresh` contains `strategy: "pilot-then-wave"`, `operation_id`, `owner_token`, `source_manifest_sha256`, `target_manifest_sha256`, `status`, integer `cursor`, ascending integer `completed_slots`, `min_healthy_percentage`, `max_unavailable`, and `events`. Each event object stores its event name in the field `event`; do not use a `name` field for event identity. The event and progress rules are defined in `/app/docs/rollout_contract.md`.

The simulator CLI is part of the harness contract. Repair the module implementation rather than replacing the CLI, fabricating output files, or hardcoding the provided production sample.

For `apply`, atomically replace `--state` and append one JSONL record to `--journal`, or to `${state}.journal.jsonl` when `--journal` is omitted. Every journal record contains `operation_id`, `release_manifest_sha256`, `refresh_status`, and `state_digest`. `release_manifest_sha256` is the rendered approved release identity's manifest digest, and `state_digest` is the digest of the state written by that apply.
