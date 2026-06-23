# Restore private placement and security-group boundaries

You are recovering a Terraform AWS EC2 module rollout for the payments API fleet. This is offline: do not call AWS and do not require Terraform. Use `/app/tools/ec2sim.py`, `/app/docs/module_contract.md`, and `/app/evidence`.

Ensure all instances stay in private app subnets with no public IP and ALB-only service ingress.

## Success criteria

- Preserve milestone 1 release-artifact pinning behavior.
- Every instance has `public_ip_associated: false` and uses only configured subnet IDs.
- `security_group.ingress` is exactly one TCP rule on port 8080 from `alb_security_group_id` (no `0.0.0.0/0` admin ingress).
- `validate` rejects subnets whose `tier` is not `private_app`; errors must mention `private_app`.

Compatibility constraints: keep `/app/infra/modules/ec2`, all labels in `main.tf`, all outputs in `outputs.tf`, and CLI flags `plan`, `apply`, `validate`, `--config`, `--prior-state`, `--out`, `--state`. Do not hardcode sample JSON or edit verifier fixtures.
