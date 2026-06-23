# Milestone 5 — Preserve upgrade guardrails and restrictions

The final release must satisfy security and rollback restrictions. Update `/app/terraform/restrictions.json`, `/app/terraform/outputs.tf`, and `/app/fixtures/terraform_plan.json`.

## restrictions.json fields

- `plugin_source`: `"internal-mirror"`
- `script_console_enabled`: `false`
- `controller_to_controller_job_trigger`: `false`
- `approved_plugin_ids`: all eight IDs listed in `/app/docs/jenkins_fleet_contract.md`

## Legacy outputs (must remain)

Preserve these Terraform outputs in `outputs.tf` and keep them in the plan fixture with non-delete actions:

- joc_hostname
- joc_url
- controller_names
- jenkins_namespace
- irsa_role_arns

## Protected plan resources

The plan fixture must include these resources with non-destructive actions only (no delete or replace):

- `module.eks.aws_eks_cluster.this[0]`
- `helm_release.joc`
- `helm_release.payments_controller`
- `helm_release.risk_controller`
- `helm_release.platform_controller`
