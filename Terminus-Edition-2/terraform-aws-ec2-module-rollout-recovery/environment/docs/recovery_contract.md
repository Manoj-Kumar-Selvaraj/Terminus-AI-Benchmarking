# Import, hardening, and reconciliation contract

The final module preserves all prior recovery behavior and adds:

- IMDSv2 required, endpoint enabled, response-hop limit one.
- Least-privilege IAM with exactly four policy statements. The simulator may expose the policy either as a flat statement list or as a conventional AWS policy document whose `Statement` field contains that list. Statements may include the conventional `Effect: "Allow"` field, but no other effect value is permitted. `SsmControlPlane` uses actions `ec2messages:GetMessages`, `ssm:UpdateInstanceInformation`, `ssmmessages:CreateControlChannel`, and `ssmmessages:OpenControlChannel`, resource `*`, and condition `{"StringEquals":{"aws:ResourceAccount": account_id}}`. `ReadReleaseArtifact` uses `["s3:GetObject"]` on `artifact_bucket_arn + "/*"`. `DecryptDataVolume` uses `["kms:Decrypt"]` on the sorted configured EBS KMS ARNs. `PublishPaymentsMetrics` uses `["cloudwatch:PutMetricData"]`, resource `*`, and condition `{"StringEquals":{"cloudwatch:namespace": metric_namespace}}`.
- Wildcard actions are forbidden. Wildcard resources are permitted only for `SsmControlPlane` and `PublishPaymentsMetrics`, and only with their documented restrictive conditions.
- Legacy state migration declarations for launch template, autoscaling group, security group, IAM role, EBS volume collection, and attachment collection. The required `state_migrations.tf` moved blocks are exactly: `aws_launch_template.payments` to `aws_launch_template.this`, `aws_autoscaling_group.payments` to `aws_autoscaling_group.this`, `aws_security_group.payments_instance` to `aws_security_group.instance`, `aws_iam_role.payments_instance` to `aws_iam_role.instance`, `aws_ebs_volume.payments_data` to `aws_ebs_volume.data`, and `aws_volume_attachment.payments_data` to `aws_volume_attachment.data`.
- Legacy instances without `slot` recover it from the `Slot` tag. The tag must be a decimal representation of a zero-based integer, and recovered output uses that integer rather than the tag string. Their IDs and stable placements are preserved when desired release and capacity are unchanged.
- Manual drift in launch-template version, public-IP association, subnet, or security-group identity is `report_only`; the plan does not silently replace or mutate instances. Every drift entry includes `instance_id`, `slot`, `field`, `expected`, `actual`, and `action: "report_only"`.
- An invalid final JSONL journal line is truncated while every valid record is preserved. Invalid interior records fail closed.
- Reconciliation of an in-progress operation is fenced by owner and target release, resumes from durable state, and is idempotent.

## Validation and reconciliation error fragments

| Violation | Required substring in `error` |
|-----------|-------------------------------|
| Legacy instance missing `Slot` tag | `missing Slot tag` |
| Interior journal record fails checksum/parse | `invalid interior journal record` |
| Different `rollout.owner_token` resumes in-progress state | `stale rollout owner` |
