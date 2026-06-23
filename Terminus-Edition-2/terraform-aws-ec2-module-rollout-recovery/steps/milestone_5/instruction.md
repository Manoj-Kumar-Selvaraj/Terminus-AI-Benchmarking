# Enforce IMDSv2, SSM support, least-privilege IAM, and drift reporting

You are recovering a Terraform AWS EC2 module rollout for the payments API fleet. This is offline: do not call AWS and do not require Terraform. Use `/app/tools/ec2sim.py`, `/app/docs/module_contract.md`, and `/app/evidence`.

Require IMDSv2, remove wildcard-admin policy, keep SSM/artifact/KMS/metrics permissions scoped, and report drift without replacement.

## Success criteria

- Preserve milestones 1–4 behavior.
- `launch_template.metadata_options` has `http_tokens: required` and `http_put_response_hop_limit: 1`.
- IAM policy must not include `"Action": ["*"]`; serialized policy must include `ssm:UpdateInstanceInformation`, `s3:GetObject`, `kms:Decrypt`, and `cloudwatch:PutMetricData`.
- Drift on `launch_template_version` is reported with `action: report_only` without reducing instance count.

Compatibility constraints: keep `/app/infra/modules/ec2`, all labels in `main.tf`, all outputs in `outputs.tf`, and CLI flags `plan`, `apply`, `validate`, `--config`, `--prior-state`, `--out`, `--state`. Do not hardcode sample JSON or edit verifier fixtures.
