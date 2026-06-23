# EC2 module contract

Offline simulator only. Preserve `/app/infra/modules/ec2`, resource labels in `main.tf`, output keys in `outputs.tf`, and `tools/ec2sim.py plan|apply|validate` CLI flags (`--config`, `--prior-state`, `--out`, `--state`).

## Release artifact pinning (Milestone 1)

- `launch_template.ami_id`, `user_data_sha256`, `provenance.commit_sha`, and `provenance.build_id` must come from `release_artifact`, not `ami_catalog.latest`.
- `validate` must fail closed when any of `ami_id`, `commit_sha`, `build_id`, or `user_data_sha256` is missing; errors must name the field as `release_artifact.<field>`.
- Instance tags must include `CommitSha` and `BuildId` from the artifact.
- `apply` must accept `--prior-state` and `--state` alongside `--config` and `--out`.

## Private placement and ingress (Milestone 2)

- Every instance has `public_ip_associated: false` and lands only in configured `private_app` subnets.
- `security_group.ingress` must be exactly one ALB rule: TCP `from_port`/`to_port` 8080 with `source_security_group_id` from config.
- `validate` must reject subnets whose `tier` is not `private_app`; errors must mention `private_app`.

## Instance refresh (Milestone 3)

- Passing refresh uses `strategy: canary-then-batch`, `min_healthy_percentage >= 90`, and `min_healthy_instances >= 5`.
- Failed `candidate_health` rolls back with `status: rolled_back`, event `kept_previous_capacity`, and prior instance IDs preserved.
- Re-running `plan` with `--prior-state` must not duplicate instance IDs.

## Encrypted EBS (Milestone 4)

- Each instance gets a non-orphaned encrypted volume with `kms_key_alias`, `ManagedBy: terraform-aws-ec2-module`, and `delete_on_termination: false`.
- `validate` rejects unencrypted or unscoped volumes; errors must contain `unencrypted`.

## IMDSv2, IAM, and drift (Milestone 5)

- `launch_template.metadata_options` requires `http_tokens: required` and `http_put_response_hop_limit: 1`.
- IAM policy must not contain wildcard admin `"Action": ["*"]`; it must include `ssm:UpdateInstanceInformation`, `s3:GetObject`, `kms:Decrypt`, and `cloudwatch:PutMetricData`.
- Drift on `launch_template_version` is `action: report_only` without replacing instances.

## ec2sim output schema

Top-level `schema_version` is `ec2sim.aws.1`. Key fields: `launch_template`, `security_group`, `autoscaling_group.instance_refresh`, `instances`, `ebs_volumes`, `iam_role`, `drift_report`, `outputs`.
