# Restore audit-grade flow logs and resolver security boundaries

You are on the network platform rotation for a failed Terraform AWS VPC module rollout. This is offline: do not call AWS and do not require Terraform. Use `/app/tools/vpcsim.py`, `/app/docs/module_contract.md`, and `/app/evidence` to diagnose the incident.

## Requirements

- Emit VPC flow logs covering all subnets with `traffic_type: ALL` and the configured destination.
- Flow log IAM policy `Resource` must not be `*`; `log_format` must include `${interface-id}`.
- Resolver security group ingress must be exactly two rules: TCP 53 and UDP 53 from configured corporate CIDRs only (no `0.0.0.0/0`).
- Preserve `main.tf` resource labels and `outputs.tf` output keys.

Compatibility constraints: keep `/app/infra/modules/vpc`, all labels in `main.tf`, all outputs in `outputs.tf`, and CLI flags `plan`, `apply`, `validate`, `--config`, `--prior-state`, `--out`, `--state`. Do not hardcode sample JSON or edit verifier fixtures.
