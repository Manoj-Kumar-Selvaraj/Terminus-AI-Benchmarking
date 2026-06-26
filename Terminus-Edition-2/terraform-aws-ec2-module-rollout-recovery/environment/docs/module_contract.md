# EC2 module compatibility contract

This is an offline simulator. Do not call AWS and do not require Terraform.

Preserve:

- `/app/infra/modules/ec2`
- every Terraform resource label in `main.tf`
- every output key in `outputs.tf`
- `tools/ec2sim` commands `plan`, `apply`, and `validate`
- flags `--config`, `--prior-state`, `--out`, `--state`, and `--journal`

Top-level output schema is `ec2sim.aws.2`. Required sections are `release_identity`, `launch_template`, `security_group`, `autoscaling_group`, `instances`, `ebs_volumes`, `iam_role`, `drift_report`, `import_report`, `plan_actions`, `journal_repair`, and `outputs`.

Nested schemas are part of the contract. `launch_template` includes `id`, `version`, `ami_id`, `architecture`, `instance_type`, `user_data_sha256`, `metadata_options`, `provenance`, and `tags`. `security_group` includes `id`, exact `ingress`, and exact `egress` rule arrays. Each instance includes `id`, `slot`, `az`, `subnet_id`, `public_ip_associated`, `security_group_id`, `launch_template_version`, `ami_id`, `state`, `health`, and `tags`. `autoscaling_group.instance_refresh.status` is one of `completed`, `rolled_back`, or `in_progress` — never informal values such as `stable`. `outputs` includes `launch_template_id`, `launch_template_version`, `autoscaling_group_name`, `instance_ids`, `volume_ids`, `rollout_operation_id`, and `drift_report`.

The simulator CLI is part of the harness contract. Repair the module implementation rather than replacing the CLI, fabricating output files, or hardcoding the provided production sample.

For `apply`, atomically replace `--state` and append one JSONL record to `--journal`, or to `${state}.journal.jsonl` when `--journal` is omitted. Every journal record contains `operation_id`, `release_manifest_sha256`, `refresh_status`, and `state_digest`. `release_manifest_sha256` is the rendered approved release identity's manifest digest, and `state_digest` is the digest of the state written by that apply.
